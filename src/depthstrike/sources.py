"""Common skeleton input boundary: live capture, deterministic demo or replay."""
from contextlib import nullcontext
from collections import Counter
from copy import deepcopy
import numpy as np

from .capture import GeminiSource
from .automatic_layout import direct_target_offsets
from .config import AppConfig
from .fusion import fuse_skeleton
from .interaction import estimate_hand
from .pose import PoseEstimator
from .types import Joint3D, SkeletonFrame


class CameraPoseSource:
    def __init__(self, config, *, capture=None, estimator=None, metrics=None):
        self.config = config
        self.metrics = metrics
        self.capture = self.estimator = None
        self.last_rgbd = None
        self.last_landmarks = {}
        self._previous_skeleton = None
        self._depth_anchors = {}
        self._last_input_t = None
        self._quality_frames = 0
        self._hand_quality = {h: Counter() for h in ('left', 'right')}
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
        if self._last_input_t is not None and not 0 < frame.timestamp_s-self._last_input_t <= self.config.max_track_gap_s:
            self._depth_anchors.clear()
        self._last_input_t = frame.timestamp_s
        horizon = min(self.config.depth_recovery_s, self.config.max_track_gap_s)
        self._depth_anchors = {name: anchor for name, anchor in self._depth_anchors.items()
                               if 0 < frame.timestamp_s-anchor[0] <= horizon+1e-9}
        self.last_rgbd = frame
        self.actions = list(getattr(self.capture, "actions", ()))
        with self.metrics.measure("pose") if self.metrics else nullcontext():
            self.last_landmarks = self.estimator.detect(frame)
        with self.metrics.measure("fusion") if self.metrics else nullcontext():
            result = fuse_skeleton(frame, self.last_landmarks, self.config,
                                   mask=getattr(self.estimator, "last_mask", None), previous=self._previous_skeleton,
                                   depth_anchors=self._depth_anchors)
            if horizon > 0 and self.config.fusion_mode == 'masked':
                self._depth_anchors.update({name: (frame.timestamp_s, joint) for name, joint in result.joints.items()
                                           if joint.provenance == 'observed' and joint.is_observed})
            self._previous_skeleton = result
            self._quality_frames += 1
            for hand, counts in self._hand_quality.items():
                name = f'{hand}_wrist'
                point, joint = self.last_landmarks.get(name), result.joints.get(name)
                if point is None:
                    counts['pose_missing'] += 1
                elif not np.isfinite(point.confidence) or point.confidence < self.config.confidence_threshold:
                    counts['pose_low_confidence'] += 1
                elif not (0 <= point.u < 1 and 0 <= point.v < 1):
                    counts['pose_out_of_frame'] += 1
                else:
                    counts['pose_confident'] += 1
                    if joint is not None and joint.is_observed:
                        counts['measured_3d'] += 1
                        if joint.provenance == 'depth_patch': counts['depth_patch'] += 1
                    else:
                        counts['fusion_'+((joint.invalid_reason or 'invalid_depth') if joint is not None else 'missing_joint')] += 1
            return result

    def quality_summary(self):
        return {'frames': self._quality_frames, 'scope': 'pose_and_depth_before_motion_filter_availability_not_accuracy',
                'hands': deepcopy({h: dict(c) for h, c in self._hand_quality.items()})}

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
        from .calibration import calibrated_target_center
        from .geometry import segment_sphere_intersection
        c = self.config
        elbow = Joint3D((0, .16, 1.93), 1)
        neutral = estimate_hand({"left_elbow": elbow, "left_wrist": Joint3D((0, .04, 1.85), 1)}, "left", c)
        extended = estimate_hand({"left_elbow": elbow, "left_wrist": Joint3D((0, .04, 1.35), 1)}, "left", c)
        if neutral.position is None or extended.position is None:
            raise ValueError("Demo cannot construct valid fist proxies with this configuration")
        reach = 2. - extended.position[2]
        center = calibrated_target_center(np.array((0., 0., 2.)), neutral.position, extended.position, c)
        safe = (center is not None and 2. - neutral.position[2] <= c.guard_extension_m
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
        if self.config.interaction_mode == "direct":
            # Follow the same sequence of spatial slots as the live round.
            # This is scripted motion, not a tracker or a camera evaluation.
            slot = (int(cycle) // 2) % self.config.direct_targets_per_hand
            offsets = direct_target_offsets(self.config)
            for n, hand in enumerate(("left", "right")):
                amount = reach if int(cycle) % 2 == n else 0.
                neutral = np.array(values[f"{hand}_wrist"])
                neutral[2] = 1.85
                shoulder = np.array(values[f"{hand}_shoulder"])
                end = shoulder + offsets[2 * slot + n] + (0., 0., -.05)
                # Leave enough follow-through for a challenge authored from
                # this synthetic peak to have an eligible sphere-entry time.
                end[2] = min(end[2], shoulder[2] - self.config.attack_extension_m
                             - self.config.hand_radius_m - self.config.target_radius_m - .05)
                wrist = neutral + amount * (end - neutral)
                values[f"{hand}_wrist"] = wrist
                values[f"{hand}_elbow"] = (shoulder + wrist) / 2 + (0., .12, 0.)
        result = SkeletonFrame(self.index, t, {name: Joint3D(value, .99) for name, value in values.items()})
        self.index += 1
        if not self._demo_paused: self._motion_index += 1
        return result

    def describe(self): return {"source": "synthetic demo", "evidence": "synthetic", "fps": self.fps,
                                "interaction_mode": self.config.interaction_mode}
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
