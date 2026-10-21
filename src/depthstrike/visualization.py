"""Sensor-first OpenCV overlay, optionally paired with an Open3D debug arena."""
from collections import deque
import os

import numpy as np

from .arena import ArenaRenderer, BONES, COLORS, display_position
from .audio import AudioFeedback
from .types import DepthStrikeError, Intrinsics

GUIDANCE = {
    "hold_guard": "Hold both hands near your shoulders",
    "reach_left": "Extend your left hand comfortably",
    "reach_right": "Extend your right hand comfortably",
    "return_left": "Return both hands to guard",
    "return_right": "Return both hands to guard",
    "extend_comfortably": "Extend comfortably; do not lean forward",
    "hold_reach": "Hold this comfortable reach briefly",
    "return_guard": "Bring both hands back to guard",
    "restore_position": "Return your shoulders to the starting position",
    "adjust_distance": "Adjust your distance, then press R",
    "reach_too_small": "Reach is too short; retry comfortably or press R",
    "target_unreachable": "Check target height / reach direction; press R to retry",
    "missing_body": "Keep both shoulders, elbows and wrists visible",
    "timestamp_invalid": "Waiting for continuous input",
    "practice_left": "Practice: strike the blue ball with your left fist",
    "practice_right": "Practice: strike the orange ball with your right fist",
    "countdown": "Stay in guard; the round starts shortly",
    "running": "Alternate straight punches towards the camera",
}
REASONS = {"depth_gap": "Depth not reached", "off_axis": "Aim towards the ball",
           "low_speed": "Forward speed too low", "insufficient_travel": "Extend further",
           "return_guard": "Return to guard", "ready": "Ready to punch", "inactive_hand": "Other hand next",
           "invalid_tracking": "Tracking unavailable", "invalid_depth": "Hand depth unavailable",
           "low_confidence": "Keypoint confidence low", "missing_joint": "Joint not visible",
           "degenerate_forearm": "Forearm direction unavailable", "depth_discontinuity": "Depth edge rejected",
           "insufficient_depth": "Not enough valid depth", "out_of_frame": "Move back into view",
           "calibrating": "Follow the setup guide", "paused": "Paused", "finished": "Round complete"}


def _pixel(position, intrinsics):
    p = np.asarray(position, dtype=float)
    if p.shape != (3,) or not np.isfinite(p).all() or p[2] <= 0:
        return None
    x, y, z = p
    i = intrinsics
    if i.distortion_model == "brown_conrady":
        import cv2
        matrix = np.array([[i.fx, 0, i.cx], [0, i.fy, i.cy], [0, 0, 1.]])
        projected, _ = cv2.projectPoints(p.reshape(1, 3), np.zeros(3), np.zeros(3), matrix, np.asarray(i.distortion))
        u, v = projected.reshape(2)
    elif i.distortion_model == "none":
        u, v = i.fx*x/z+i.cx, i.fy*y/z+i.cy
    else:
        return None
    if not np.isfinite((u, v)).all() or abs(u) > 100000 or abs(v) > 100000:
        return None
    return int(u), int(v)


def _bgr(hand):
    return tuple(round(c * 255) for c in COLORS[hand][::-1])


def render_hud(state, rgbd_frame, config, mode="demo", trails=None):
    import cv2
    canvas = np.full((800, 960, 3), (247, 242, 237), np.uint8)
    ink, muted, teal = (72, 54, 38), (130, 112, 95), (122, 122, 31)
    def text(value, at, size=.55, color=ink, weight=1):
        cv2.putText(canvas, str(value), at, cv2.FONT_HERSHEY_SIMPLEX, size, color, weight, cv2.LINE_AA)
    cv2.rectangle(canvas, (0, 0), (959, 78), (72, 54, 38), -1)
    text("DepthStrike", (25, 36), .95, (255, 255, 255), 2)
    source_label = "Synthetic motion / no camera" if mode == "demo" else f"RGB-D target boxing / {mode}"
    text(source_label, (26, 61), .48, (227, 218, 207))
    text(state.status.replace("_", " ").title(), (660, 43), .62, (244, 234, 219), 2)
    if rgbd_frame is None:
        image = np.full((360, 640, 3), (239, 233, 226), np.uint8)
        intrinsics = Intrinsics(640, 360, 750, 750, 320, 130)
        # Spatial references belong to the synthetic field, never the live feed.
        for u in range(0, 640, 40): cv2.line(image, (u, 0), (u, 359), (225, 217, 207), 1)
        for v in range(0, 360, 40): cv2.line(image, (0, v), (639, v), (225, 217, 207), 1)
    else:
        image = cv2.cvtColor(rgbd_frame.color_rgb, cv2.COLOR_RGB2BGR).copy()
        intrinsics = rgbd_frame.intrinsics
    points = {}
    if state.skeleton is not None:
        points = {name: _pixel(j.position, intrinsics) for name, j in state.skeleton.joints.items() if j.position is not None}
        for a, b in BONES:
            if points.get(a) is not None and points.get(b) is not None:
                cv2.line(image, points[a], points[b], (110, 100, 87), 2, cv2.LINE_AA)
        for name, point in points.items():
            if point is not None:
                cv2.circle(image, point, 4, _bgr("left" if name.startswith("left") else "right"), -1, cv2.LINE_AA)
        for hand, joint in state.fists.items():
            if joint.position is None: continue
            p = _pixel(joint.position, intrinsics)
            if p is None: continue
            if trails:
                prior = [_pixel(v, intrinsics) for v in trails.get(hand, ())]
                for a, b in zip(prior[:-1], prior[1:]):
                    if a is not None and b is not None: cv2.line(image, a, b, _bgr(hand), 2, cv2.LINE_AA)
            wrist = points.get(f"{hand}_wrist")
            if wrist is not None: cv2.line(image, wrist, p, _bgr(hand), 2, cv2.LINE_AA)
            r = max(4, min(100, round(intrinsics.fx * config.hand_radius_m / joint.position[2])))
            cv2.circle(image, p, r, _bgr(hand), 2, cv2.LINE_AA)
            cv2.circle(image, p, 4, _bgr(hand), -1, cv2.LINE_AA)
    for target in state.targets:
        p = _pixel(target.center, intrinsics)
        if p is None: continue
        radius = max(3, min(200, round(intrinsics.fx * target.radius / target.center[2])))
        color = (93, 138, 43) if target.flash else (_bgr(target.hand) if target.active else (182, 169, 154))
        layer = image.copy()
        cv2.circle(layer, p, radius, color, -1, cv2.LINE_AA)
        cv2.addWeighted(layer, .18 if target.active else .08, image, .82 if target.active else .92, 0, image)
        cv2.circle(image, p, radius, color, 3 if target.active else 1, cv2.LINE_AA)
        cv2.ellipse(image, p, (radius, max(2, radius//3)), 0, 0, 360, color, 1, cv2.LINE_AA)
        cv2.circle(image, (p[0]-radius//3, p[1]-radius//3), max(2, radius//7), (255, 255, 255), -1, cv2.LINE_AA)
    scale = min(700 / image.shape[1], 500 / image.shape[0])
    w, h = round(image.shape[1] * scale), round(image.shape[0] * scale)
    x, y = 20 + (700-w)//2, 98 + (500-h)//2
    canvas[y:y+h, x:x+w] = cv2.resize(image, (w, h))
    active = next((t.hand for t in state.targets if t.active), None)
    text("Setup" if state.guidance and state.guidance.stage != "RUNNING" else "Round", (744, 116), .68, weight=2)
    stage = state.guidance.stage if state.guidance else state.status
    for n, word in enumerate(stage.replace("_", " ").title().split()):
        text(word, (744, 155+n*27), .64, teal, 2)
    if state.guidance:
        progress = state.guidance.progress
        cv2.rectangle(canvas, (744, 231), (932, 237), (216, 207, 195), -1)
        cv2.rectangle(canvas, (744, 231), (744+round(188*progress), 237), teal, -1)
    text("Next hand", (744, 280), .48, muted)
    text(active.title() if active else "Setup", (744, 311), .78, _bgr(active) if active else ink, 2)
    for n, hand in enumerate(("left", "right")):
        text(hand.title(), (744, 365+n*75), .55, _bgr(hand), 2)
        text(state.phases.get(hand, "unavailable").replace("_", " ").lower(), (744, 391+n*75), .43, muted)
    text("Space  pause", (744, 557), .44, muted)
    text("R  restart setup", (744, 579), .44, muted)
    text("Q / Esc  exit", (744, 601), .44, muted)
    guidance = state.guidance
    if state.status == "WAITING FOR CAMERA": hint = "Waiting for paired RGB-D frames; interaction is suspended"
    elif state.status == "PAUSED": hint = "Paused. Press Space to resume."
    elif state.status == "FINISHED": hint = "Round complete. Press R for another setup."
    else: hint = GUIDANCE.get(guidance.message_code, guidance.message_code) if guidance else "Alternate straight punches towards the camera"
    text(hint, (24, 637), .52, ink, 1)
    cv2.line(canvas, (24, 652), (934, 652), (212, 202, 188), 1)
    text(state.score, (24, 707), 1.35, ink, 2)
    text("points", (26, 737), .45, muted)
    text(f"{state.hits} hits", (160, 707), .8, ink, 2)
    text(f"{state.remaining_s:04.1f} s", (315, 707), .8, ink, 2)
    feedback = state.feedback.get(active) if active else None
    fields = None if feedback is None else (feedback.surface_gap_m, feedback.depth_delta_m, feedback.lateral_m)
    if fields is None or any(v is None for v in fields):
        text("Spatial feedback unavailable", (490, 688), .5, muted)
    else:
        text(f"Gap {fields[0]:+.2f} m   Depth {fields[1]:+.2f} m", (490, 686), .49, teal)
        text(f"Off-axis {fields[2]:.2f} m", (490, 713), .49, muted)
        amount = float(np.clip(1-max(0., fields[0])/.5, 0, 1))
        cv2.rectangle(canvas, (492, 733), (931, 739), (216, 207, 195), -1)
        cv2.rectangle(canvas, (492, 733), (492+round(439*amount), 739), teal, -1)
    reason = REASONS.get(feedback.reason, feedback.reason.replace("_", " ")) if feedback else "Keep shoulders, elbows and wrists in view"
    text(reason, (24, 778), .5, muted)
    text("3D proxy contact, not screen overlap", (540, 778), .43, muted)
    return canvas


class NullView:
    def render(self, state, rgbd_frame): pass
    def poll_actions(self): return []
    def close(self): pass


class SceneView:
    def __init__(self, config, mode="demo", layout="overlay", sound=False):
        self.config, self.mode = config, mode
        self._closed = False
        self.arena = None
        self.cv2 = None
        self.audio = AudioFeedback(sound)
        self._last_t = None
        self._trails = {h: deque(maxlen=16) for h in COLORS}
        self.hud_name = "DepthStrike | sensor and interaction"
        if layout not in ("overlay", "dual"):
            raise ValueError("view layout must be overlay or dual")
        if os.environ.get("DEPTHSTRIKE_NO_DISPLAY") or (os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")):
            raise DepthStrikeError("No display available. Use --headless --frames 600.")
        try:
            import cv2
            self.cv2 = cv2
            cv2.namedWindow(self.hud_name, cv2.WINDOW_AUTOSIZE)
            cv2.moveWindow(self.hud_name, 25, 40)
            if layout == "dual": self.arena = ArenaRenderer(config)
        except BaseException as exc:
            self.close()
            if isinstance(exc, DepthStrikeError): raise
            raise DepthStrikeError(f"Display initialization failed: {exc}. Install .[display] or use --headless.") from exc

    @property
    def vis(self):
        return self.arena.vis if self.arena else None

    def render(self, state, rgbd_frame):
        if self._closed: return
        frame = state.skeleton
        broken = frame is None or self._last_t is not None and not 0 < frame.timestamp_s-self._last_t <= self.config.max_track_gap_s + 1e-9
        self._last_t = frame.timestamp_s if frame else None
        for hand, trail in self._trails.items():
            joint = state.fists.get(hand)
            if broken or joint is None or joint.position is None or state.status in ("PAUSED", "CALIBRATING", "TRACKING LOST"):
                trail.clear()
            if frame is not None and joint is not None and joint.position is not None:
                trail.append(joint.position.copy())
        if self.arena: self.arena.render(state)
        self.cv2.imshow(self.hud_name, render_hud(state, rgbd_frame, self.config, self.mode, self._trails))
        self.audio.notify(state.events)

    def poll_actions(self):
        if self._closed: return ["quit"]
        actions = self.arena.poll_actions() if self.arena else []
        if "quit" in actions: return ["quit"]
        try:
            if self.cv2.getWindowProperty(self.hud_name, self.cv2.WND_PROP_VISIBLE) < 1: return ["quit"]
            key = self.cv2.waitKey(1) & 0xff
        except self.cv2.error:
            return ["quit"]
        action = {32: "pause", ord("r"): "reset", ord("q"): "quit", 27: "quit"}.get(key)
        if action and action not in actions: actions.append(action)
        return actions

    def close(self):
        if self._closed: return
        try:
            if self.arena: self.arena.close()
        finally:
            self.audio.close()
            if self.cv2 is not None:
                try: self.cv2.destroyWindow(self.hud_name)
                except self.cv2.error: pass
            self._closed = True

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
