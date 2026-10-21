"""Open3D auxiliary view with persistent geometry and main-thread updates."""
from collections import deque

import numpy as np

from .types import DepthStrikeError

COLORS = {"left": (.15, .39, .76), "right": (.81, .41, .18)}
BONES = (("left_shoulder", "right_shoulder"), ("left_shoulder", "left_elbow"),
         ("left_elbow", "left_wrist"), ("right_shoulder", "right_elbow"),
         ("right_elbow", "right_wrist"), ("left_shoulder", "left_hip"),
         ("right_shoulder", "right_hip"), ("left_hip", "right_hip"),
         ("left_shoulder", "nose"), ("right_shoulder", "nose"))


def display_position(position):
    return np.asarray(position) * np.array((1, -1, -1))


class ArenaRenderer:
    def __init__(self, config, *, visualizer=None, o3d=None):
        self.config = config
        self.vis = None
        self._closed = False
        self._actions = []
        self._last_t = None
        self._trails = {h: deque(maxlen=16) for h in COLORS}
        self.geometries = {}
        self._templates = {}
        try:
            if o3d is None:
                import open3d as o3d
            self.o3d = o3d
            self.vis = visualizer if visualizer is not None else o3d.visualization.VisualizerWithKeyCallback()
            if not self.vis.create_window("DepthStrike | 3D target arena", 960, 720, 1000, 60):
                raise DepthStrikeError("Open3D window failed. Use --view overlay or --headless.")
            self.vis.get_render_option().background_color = np.array((.93, .95, .97))
            self.vis.get_render_option().line_width = 3.
            grid = []
            for x in np.arange(-1.2, 1.3, .2): grid.append(((x, .75, .5), (x, .75, 3.)))
            for z in np.arange(.5, 3.01, .2): grid.append(((-1.2, .75, z), (1.2, .75, z)))
            ground = o3d.geometry.LineSet()
            self._set_lines(ground, grid, (.75, .79, .83))
            self.vis.add_geometry(ground)
            self.vis.add_geometry(o3d.geometry.TriangleMesh.create_coordinate_frame(size=.2), reset_bounding_box=False)
            for name in ("bones", "trail_left", "trail_right"):
                self.geometries[name] = o3d.geometry.LineSet()
                self.vis.add_geometry(self.geometries[name], reset_bounding_box=False)
            for name in ("nose", "fist_left", "fist_right", "target_0", "target_1"):
                self._new_sphere(name)
            for key, action in ((32, "pause"), (ord("R"), "reset"), (ord("Q"), "quit"), (256, "quit")):
                self.vis.register_key_callback(key, lambda vis, a=action: self._enqueue(a))
            control = self.vis.get_view_control()
            control.set_lookat([0, -.1, -1.7])
            control.set_front([.7, .25, 1.])
            control.set_up([0, 1, 0])
            control.set_zoom(.6)
        except BaseException as exc:
            self.close()
            if isinstance(exc, DepthStrikeError): raise
            raise DepthStrikeError(f"Open3D initialization failed: {exc}. Install .[display] or use --view overlay.") from exc

    def _enqueue(self, action):
        self._actions.append(action)
        return False

    def _new_sphere(self, name):
        mesh = self.o3d.geometry.TriangleMesh.create_sphere(1., resolution=12)
        mesh.compute_vertex_normals()
        self._templates[name] = (np.asarray(mesh.vertices).copy(), np.asarray(mesh.triangles).copy(),
                                 np.asarray(mesh.vertex_normals).copy())
        mesh.clear()
        self.geometries[name] = mesh
        self.vis.add_geometry(mesh, reset_bounding_box=False)

    def _set_lines(self, lines, segments, color):
        points = np.asarray([display_position(p) for segment in segments for p in segment]).reshape(-1, 3)
        lines.points = self.o3d.utility.Vector3dVector(points)
        lines.lines = self.o3d.utility.Vector2iVector(np.arange(len(points)).reshape(-1, 2))
        lines.paint_uniform_color(color)

    def _update_sphere(self, name, center, radius, color):
        if name not in self.geometries:
            self._new_sphere(name)
        mesh = self.geometries[name]
        if center is None:
            mesh.clear()
        else:
            vertices, triangles, normals = self._templates[name]
            mesh.vertices = self.o3d.utility.Vector3dVector(vertices * radius + display_position(center))
            mesh.triangles = self.o3d.utility.Vector3iVector(triangles)
            mesh.vertex_normals = self.o3d.utility.Vector3dVector(normals)
            mesh.paint_uniform_color(color)
        self.vis.update_geometry(mesh)

    def render(self, state):
        if self._closed: return
        frame = state.skeleton
        points = {n: j.position for n, j in frame.joints.items() if j.position is not None} if frame else {}
        segments = [(points[a], points[b]) for a, b in BONES if a in points and b in points]
        proxies = {}
        for hand in COLORS:
            joint = state.fists.get(hand)
            proxies[hand] = (joint.position if joint is not None else points.get(f"{hand}_wrist")) if frame else None
            wrist = points.get(f"{hand}_wrist")
            if proxies[hand] is not None and wrist is not None:
                segments.append((wrist, proxies[hand]))
        self._set_lines(self.geometries["bones"], segments, (.27, .34, .42))
        self.vis.update_geometry(self.geometries["bones"])
        self._update_sphere("nose", points.get("nose"), .075, (.64, .69, .74))
        broken = frame is None or self._last_t is not None and not 0 < frame.timestamp_s - self._last_t <= self.config.max_track_gap_s + 1e-9
        self._last_t = frame.timestamp_s if frame else None
        for hand, point in proxies.items():
            trail = self._trails[hand]
            if broken or point is None or state.status in ("PAUSED", "CALIBRATING", "TRACKING LOST"):
                trail.clear()
            if point is not None:
                trail.append(point.copy())
            self._update_sphere(f"fist_{hand}", point, self.config.hand_radius_m, COLORS[hand])
            self._set_lines(self.geometries[f"trail_{hand}"], list(zip(list(trail)[:-1], list(trail)[1:])), COLORS[hand])
            self.vis.update_geometry(self.geometries[f"trail_{hand}"])
        present = set()
        for target in state.targets:
            name = f"target_{target.target_id}"
            present.add(name)
            color = (.17, .54, .36) if target.flash else (COLORS[target.hand] if target.active else (.75, .79, .83))
            self._update_sphere(name, target.center, target.radius, color)
        for name in self._templates:
            if name.startswith("target_") and name not in present:
                self._update_sphere(name, None, 1, (0, 0, 0))
        self.vis.update_renderer()

    def poll_actions(self):
        if self._closed or not self.vis.poll_events(): return ["quit"]
        actions, self._actions = self._actions, []
        return actions

    def close(self):
        if not self._closed and self.vis is not None:
            self.vis.destroy_window()
        self._closed = True

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
