"""Common skeleton input boundary: live capture, deterministic demo or replay."""
from contextlib import nullcontext
import numpy as np

from .capture import GeminiSource
from .config import AppConfig
from .fusion import fuse_skeleton
from .interaction import estimate_fist
from .pose import PoseEstimator
from .types import Joint3D, SkeletonFrame


class CameraPoseSource:
    def __init__(self, config, *, capture=None, estimator=None, metrics=None):
        self.config = config
        self.metrics = metrics
        self.capture = self.estimator = None
        self.last_rgbd = None
        self.last_landmarks = {}
        self.actions = []
        try:
            self.capture = capture if capture is not None else GeminiSource(config)
            self.estimator = estimator if estimator is not None else PoseEstimator(config)
        except BaseException:
            self.close()
            raise

    def read(self):
        with self.metrics.measure("capture") if self.metrics else nullcontext():
            frame = self.capture.read()
        if frame is None:
            return None
        self.last_rgbd = frame
        self.actions = list(getattr(self.capture, "actions", ()))
        with self.metrics.measure("pose") if self.metrics else nullcontext():
            self.last_landmarks = self.estimator.detect(frame)
        with self.metrics.measure("fusion") if self.metrics else nullcontext():
            return fuse_skeleton(frame, self.last_landmarks, self.config)

    def describe(self):
        metadata = self.capture.describe() if hasattr(self.capture, "describe") else {"source": "rgbd-replay"}
        return {**metadata, "pose_model": getattr(self.estimator, "metadata", {})}

    def close(self):
        try:
            if self.estimator is not None:
                self.estimator.close()
        finally:
            if self.capture is not None:
                self.capture.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class DemoPoseSource:
    """Analytic upper-body motion, explicitly not a camera or model evaluation."""
    def __init__(self, config=None, fps=30., total_frames=None):
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError("Demo fps must be positive")
        self.fps, self.total_frames = fps, total_frames
        self.config = config or AppConfig()
        self.index = 0
        self._motion_index = 0.
        self._demo_paused = False
        self.closed = False
        self.actions = []
        self.last_rgbd = None
        if self.config.interaction_mode == "guided":
            if self.config.punch_speed_m_s > 2. or self.config.smoothing_tau_s > .1:
                raise ValueError("Synthetic demo supports punch_speed_m_s <= 2 and smoothing_tau_s <= 0.1; use a matching replay for other settings")
            if 1 / fps > self.config.max_track_gap_s + 1e-9:
                raise ValueError("Demo fps cannot provide continuous guided tracking for max_track_gap_s")
            c = self.config
            self._segments = [
                (c.calibration_duration_s + .25, 0., 0.),
                (.25, 1., 0.), (c.reach_hold_s + .25, 1., 0.),
                (.25, 0., 0.), (c.return_guard_s + .25, 0., 0.),
                (.25, 0., 1.), (c.reach_hold_s + .25, 0., 1.),
                (.25, 0., 0.), (c.return_guard_s + .25, 0., 0.)]
            self._setup_end = sum(s[0] for s in self._segments)
            self._official_start = self._setup_end + 2.4 + c.countdown_s + .5
            self._validate_guided_geometry()

    def _rewind_guided_phase(self):
        """Restart only the interrupted scripted hold, without rewinding frame time."""
        t = self._motion_index / self.fps
        elapsed = 0.
        for duration, _, _ in self._segments:
            if t < elapsed + duration:
                self._motion_index = elapsed * self.fps
                return
            elapsed += duration
        if t < self._setup_end + 2.4:
            cycle = int((t - self._setup_end) / 1.2)
            self._motion_index = (self._setup_end + cycle * 1.2) * self.fps
        elif t < self._official_start:
            self._motion_index = (self._setup_end + 2.4) * self.fps

    def handle_action(self, action, *, paused=False):
        if self.config.interaction_mode != "guided": return
        if action == "reset":
            self._motion_index = 0.
            self._demo_paused = False
        elif action == "pause":
            self._demo_paused = paused
            if not paused: self._rewind_guided_phase()
        elif action == "tracking_lost":
            self._rewind_guided_phase()

    def _validate_guided_geometry(self):
        from .geometry import segment_sphere_intersection
        c = self.config
        elbow = Joint3D((0, .16, 1.93), 1)
        neutral = estimate_fist(elbow, Joint3D((0, .04, 1.85), 1), c)
        extended = estimate_fist(elbow, Joint3D((0, .04, 1.35), 1), c)
        if neutral.position is None or extended.position is None:
            raise ValueError("Demo cannot construct valid fist proxies with this configuration")
        reach = 2. - extended.position[2]
        center = np.array((0, c.target_height_m, 2. - c.target_reach_ratio * reach))
        safe = (2. - neutral.position[2] <= c.guard_extension_m
                and reach - (2. - neutral.position[2]) >= c.reach_min_increment_m
                and all(c.min_depth_m + r <= p[2] <= c.max_depth_m - r for p, r in (
                    (neutral.position, c.hand_radius_m), (extended.position, c.hand_radius_m), (center, c.target_radius_m)))
                and np.linalg.norm(center - neutral.position) > c.hand_radius_m + c.target_radius_m + .02
                and segment_sphere_intersection(neutral.position, extended.position, center,
                    c.hand_radius_m + c.target_radius_m) is not None)
        if not safe:
            raise ValueError("Synthetic demo geometry cannot satisfy this guided configuration; use default reach/depth parameters or a matching replay")

    @staticmethod
    def _punch_reach(phase):
        if .25 <= phase < .45: return (phase - .25) / .2
        if .45 <= phase < .65: return 1.
        if .65 <= phase < .95: return 1 - (phase - .65) / .3
        return 0.

    def _guided_reaches(self, t):
        elapsed = 0.
        before = np.zeros(2)
        for duration, left, right in self._segments:
            goal = np.array((left, right))
            if t < elapsed + duration:
                return before + (goal - before) * ((t - elapsed) / duration)
            elapsed += duration
            before = goal
        if t < self._setup_end + 2.4:
            cycle = (t - self._setup_end) / 1.2
        elif t < self._official_start:
            return (0., 0.)
        else:
            cycle = (t - self._official_start) / 1.2
        reach = self._punch_reach((cycle % 1) * 1.2)
        return (reach, 0.) if int(cycle) % 2 == 0 else (0., reach)

    def read(self):
        if self.closed or self.total_frames is not None and self.index >= self.total_frames:
            return None
        t = self.index/self.fps
        if self.config.interaction_mode == "guided":
            left, right = self._guided_reaches(self._motion_index / self.fps)
            left_z, right_z = 1.85 - .5 * left, 1.85 - .5 * right
            elbows = {"left_elbow": (-.2, .16, 1.93), "right_elbow": (.2, .16, 1.93)}
        else:
            cycle = max(0., t-1.2)/1.2
            reach = self._punch_reach((cycle % 1)*1.2) if t >= 1.2 else 0.
            left_z = 1.85-.5*reach if int(cycle) % 2 == 0 else 1.85
            right_z = 1.85-.5*reach if int(cycle) % 2 else 1.85
            elbows = {"left_elbow": (-.24, .2, (2+left_z)/2), "right_elbow": (.24, .2, (2+right_z)/2)}
        values = {"nose": (0, -.25, 1.98),
                  "left_shoulder": (-.2, 0, 2.), "right_shoulder": (.2, 0, 2.),
                  **elbows,
                  "left_wrist": (-.2, .04, left_z), "right_wrist": (.2, .04, right_z),
                  "left_hip": (-.15, .5, 2.), "right_hip": (.15, .5, 2.)}
        result = SkeletonFrame(self.index, t, {name: Joint3D(value, .99) for name, value in values.items()})
        self.index += 1
        if not self._demo_paused: self._motion_index += 1
        return result

    def describe(self): return {"source": "synthetic demo", "evidence": "synthetic", "fps": self.fps,
                                "interaction_mode": self.config.interaction_mode}
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
