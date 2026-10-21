"""Independent Open3D scene and OpenCV feedback. No collision rules here."""
from collections import deque
import os

import numpy as np

from .types import DepthStrikeError

COLORS = {"left": (.13, .42, .83), "right": (.91, .40, .17)}
BONES = (("left_shoulder", "right_shoulder"), ("left_shoulder", "left_elbow"),
         ("left_elbow", "left_wrist"), ("right_shoulder", "right_elbow"),
         ("right_elbow", "right_wrist"), ("left_shoulder", "left_hip"),
         ("right_shoulder", "right_hip"), ("left_hip", "right_hip"),
         ("left_shoulder", "nose"), ("right_shoulder", "nose"))


def display_position(position):
    return np.asarray(position)*np.array((1, -1, -1))


def _pixel(position, intrinsics):
    import cv2
    x, y, z = position
    if z <= 0: return None
    i = intrinsics
    if i.distortion_model == "brown_conrady":
        matrix = np.array([[i.fx, 0, i.cx], [0, i.fy, i.cy], [0, 0, 1.]])
        projected, _ = cv2.projectPoints(np.array([[x, y, z]], dtype=float), np.zeros(3), np.zeros(3), matrix, np.asarray(i.distortion))
        u, v = projected.reshape(2)
    else:
        u, v = i.fx*x/z+i.cx, i.fy*y/z+i.cy
    if not np.isfinite((u, v)).all() or abs(u) > 100000 or abs(v) > 100000: return None
    return int(u), int(v)


def render_hud(state, rgbd_frame, config, mode="demo"):
    import cv2
    from .types import Intrinsics
    canvas = np.full((720, 640, 3), (245, 243, 240), np.uint8)
    ink, muted = (50, 41, 31), (120, 108, 96)
    cv2.rectangle(canvas, (0, 0), (639, 78), (71, 48, 26), -1)
    def text(value, at, size=.6, color=ink, weight=1):
        cv2.putText(canvas, value, at, cv2.FONT_HERSHEY_SIMPLEX, size, color, weight, cv2.LINE_AA)
    text("DepthStrike", (26, 35), .95, (255, 255, 255), 2)
    text(f"Target boxing / {mode}", (28, 61), .48, (225, 218, 205))
    if rgbd_frame is None:
        image = np.full((360, 640, 3), (235, 232, 226), np.uint8)
        intrinsics = Intrinsics(640, 360, 750, 750, 320, 130)
    else:
        image = cv2.cvtColor(rgbd_frame.color_rgb.copy(), cv2.COLOR_RGB2BGR)
        intrinsics = rgbd_frame.intrinsics
    points = {}
    if state.skeleton is not None:
        for name, joint in state.skeleton.joints.items():
            if joint.position is not None:
                points[name] = _pixel(joint.position, intrinsics)
        for a, b in BONES:
            if points.get(a) is not None and points.get(b) is not None:
                cv2.line(image, points[a], points[b], (112, 105, 90), 2, cv2.LINE_AA)
        for name, point in points.items():
            if point is not None:
                color = COLORS["left" if name.startswith("left") else "right"]
                bgr = tuple(int(c*255) for c in color[::-1])
                cv2.circle(image, point, 7 if "wrist" in name else 4, bgr, -1, cv2.LINE_AA)
    for target in state.targets:
        point = _pixel(target.center, intrinsics)
        if point is None: continue
        radius = max(2, min(200, round(intrinsics.fx*target.radius/target.center[2])))
        color = (68, 166, 58) if target.flash else tuple(int(c*255) for c in COLORS[target.hand][::-1])
        if not target.active and not target.flash: color = (170, 167, 158)
        cv2.circle(image, point, radius, color, 3, cv2.LINE_AA)
    scale = min(640/image.shape[1], 360/image.shape[0])
    w, h = round(image.shape[1]*scale), round(image.shape[0]*scale)
    image = cv2.resize(image, (w, h))
    x, y = (640-w)//2, 80+(360-h)//2
    canvas[y:y+h, x:x+w] = image
    text(str(state.score), (27, 517), 1.65, ink, 3)
    text("points", (29, 547), .5, muted)
    text(f"{state.hits} hits", (245, 499), .8)
    text(f"{state.remaining_s:04.1f} s", (451, 499), .8)
    text(state.status, (26, 587), .64, ink, 2)
    active = next((t.hand for t in state.targets if t.active), None)
    hint = "Stand still with hands near shoulders to calibrate" if not state.targets else f"Next: {active} fist. Punch towards the camera."
    text(hint, (26, 615), .46, muted)
    phases = "   ".join(f"{h}: {state.phases.get(h, 'invalid')}" for h in ("left", "right"))
    text(phases, (26, 642), .46, muted)
    cv2.line(canvas, (26, 663), (614, 663), (211, 207, 200), 1)
    text("Space: pause    R: recalibrate    Q / Esc: exit", (26, 691), .48)
    return canvas


class NullView:
    def render(self, state, rgbd_frame): pass
    def poll_actions(self): return []
    def close(self): pass


class SceneView:
    def __init__(self, config, mode="demo"):
        self.config, self.mode = config, mode
        self._actions = []
        self._closed = False
        self.vis = None
        self.cv2 = None
        self._dynamic = []
        self._trails = {h: deque(maxlen=16) for h in ("left", "right")}
        self._last_t = None
        self._alive = True
        self.hud_name = "DepthStrike | score and input"
        if os.environ.get("DEPTHSTRIKE_NO_DISPLAY") or (os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")):
            raise DepthStrikeError("No display available. Use --headless --frames 300.")
        try:
            import cv2
            import open3d as o3d
            self.cv2, self.o3d = cv2, o3d
            self.vis = o3d.visualization.VisualizerWithKeyCallback()
            if not self.vis.create_window("DepthStrike | 3D target arena", 960, 720, 25, 60):
                raise DepthStrikeError("Open3D window failed. Check graphics drivers or use --headless.")
            self.vis.get_render_option().background_color = np.array((.94, .95, .96))
            self.vis.get_render_option().line_width = 3.
            cv2.namedWindow(self.hud_name, cv2.WINDOW_AUTOSIZE)
            cv2.moveWindow(self.hud_name, 1000, 60)
            for key, action in ((32, "pause"), (ord("R"), "reset"), (ord("Q"), "quit"), (256, "quit")):
                self.vis.register_key_callback(key, lambda vis, a=action: self._enqueue(a))
            segments = []
            for x in np.arange(-1.2, 1.3, .2): segments.append(((x, .75, .5), (x, .75, 3.)))
            for z in np.arange(.5, 3.01, .2): segments.append(((-1.2, .75, z), (1.2, .75, z)))
            self.vis.add_geometry(self._lines(segments, (.75, .78, .81)))
            self.vis.add_geometry(o3d.geometry.TriangleMesh.create_coordinate_frame(size=.2), reset_bounding_box=False)
            control = self.vis.get_view_control()
            control.set_lookat([0, -.1, -1.7])
            control.set_front([.7, .25, 1.])
            control.set_up([0, 1, 0])
            control.set_zoom(.6)
        except BaseException as exc:
            self.close()
            if isinstance(exc, DepthStrikeError): raise
            raise DepthStrikeError(f"Display initialization failed: {exc}. Install .[display] or use --headless.") from exc

    def _enqueue(self, action):
        self._actions.append(action)
        return False

    def _lines(self, segments, color):
        lines = self.o3d.geometry.LineSet()
        points = np.array([display_position(p) for segment in segments for p in segment])
        lines.points = self.o3d.utility.Vector3dVector(points.reshape(-1, 3))
        lines.lines = self.o3d.utility.Vector2iVector(np.arange(len(points)).reshape(-1, 2))
        lines.paint_uniform_color(color)
        return lines

    def _sphere(self, center, radius, color):
        sphere = self.o3d.geometry.TriangleMesh.create_sphere(radius, resolution=12)
        sphere.compute_vertex_normals()
        sphere.paint_uniform_color(color)
        sphere.translate(display_position(center))
        return sphere

    def render(self, state, rgbd_frame):
        if self._closed: return
        for geometry in self._dynamic: self.vis.remove_geometry(geometry, reset_bounding_box=False)
        self._dynamic = []
        frame = state.skeleton
        points = {n: j.position for n, j in frame.joints.items() if j.position is not None} if frame else {}
        segments = [(points[a], points[b]) for a, b in BONES if a in points and b in points]
        if segments: self._dynamic.append(self._lines(segments, (.30, .35, .40)))
        if "nose" in points: self._dynamic.append(self._sphere(points["nose"], .075, (.65, .69, .72)))
        broken = frame is None or self._last_t is not None and not 0 < frame.timestamp_s-self._last_t <= self.config.max_track_gap_s
        self._last_t = frame.timestamp_s if frame else None
        for hand in ("left", "right"):
            trail = self._trails[hand]
            wrist = points.get(f"{hand}_wrist")
            if broken or wrist is None or state.status in ("PAUSED", "CALIBRATING"): trail.clear()
            if wrist is not None:
                self._dynamic.append(self._sphere(wrist, self.config.hand_radius_m, COLORS[hand]))
                trail.append(wrist.copy())
            if len(trail) > 1:
                self._dynamic.append(self._lines(list(zip(list(trail)[:-1], list(trail)[1:])), COLORS[hand]))
        for target in state.targets:
            color = (.25, .72, .30) if target.flash else (COLORS[target.hand] if target.active else (.77, .79, .81))
            self._dynamic.append(self._sphere(target.center, target.radius, color))
        for geometry in self._dynamic: self.vis.add_geometry(geometry, reset_bounding_box=False)
        self._alive = self.vis.poll_events()
        if self._alive: self.vis.update_renderer()
        self.cv2.imshow(self.hud_name, render_hud(state, rgbd_frame, self.config, self.mode))

    def poll_actions(self):
        if not self._alive: return ["quit"]
        if not self.vis.poll_events(): return ["quit"]
        try:
            if self.cv2.getWindowProperty(self.hud_name, self.cv2.WND_PROP_VISIBLE) < 1: return ["quit"]
            key = self.cv2.waitKey(1) & 0xff
        except self.cv2.error:
            return ["quit"]
        action = {32: "pause", ord("r"): "reset", ord("q"): "quit", 27: "quit"}.get(key)
        if action: self._actions.append(action)
        actions, self._actions = self._actions, []
        return actions

    def close(self):
        if self._closed: return
        self._closed = True
        try:
            if self.vis is not None: self.vis.destroy_window()
        finally:
            if self.cv2 is not None:
                try: self.cv2.destroyWindow(self.hud_name)
                except self.cv2.error: pass

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
