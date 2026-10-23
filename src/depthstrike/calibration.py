"""Deterministic reach calibration. Input time, not wall time, drives stages."""
from dataclasses import dataclass

import numpy as np

from .config import AppConfig
from .geometry import segment_sphere_intersection
from .types import Joint3D, SkeletonFrame

HANDS = ("left", "right")
REQUIRED_JOINTS = tuple(f"{h}_{p}" for h in HANDS for p in ("shoulder", "elbow", "wrist"))


@dataclass(frozen=True)
class CalibrationProfile:
    reference_shoulders: dict[str, np.ndarray]
    neutral_extensions: dict[str, float]
    comfortable_extensions: dict[str, float]
    guard_thresholds: dict[str, float]
    attack_thresholds: dict[str, float]
    travel_thresholds: dict[str, float]
    target_centers: dict[str, np.ndarray]


@dataclass(frozen=True)
class GuidanceState:
    stage: str
    progress: float
    message_code: str
    profile: CalibrationProfile | None = None


def valid_body(frame: SkeletonFrame, fists: dict[str, Joint3D], config: AppConfig) -> bool:
    joints = [frame.joints.get(name) for name in REQUIRED_JOINTS] + [fists.get(h) for h in HANDS]
    return all(j is not None and j.is_observed and j.confidence >= config.confidence_threshold
               for j in joints)


def valid_hand(frame, fists, hand, config):
    joints = (frame.joints.get(f"{hand}_shoulder"), fists.get(hand))
    return all(j is not None and j.is_observed and j.confidence >= config.confidence_threshold for j in joints)


class GuidedCalibration:
    def __init__(self, config: AppConfig):
        self.config = config
        self.workspace = None
        self.reset()

    def reset(self):
        self.stage = "HOLD_GUARD"
        self.profile = None
        self._last_t = None
        self._samples = []
        self._reference = {}
        self._neutral_fists = {}
        self._neutral = {}
        self._reaches = {}
        self._reach_vectors = {}
        self._countdown_start = None
        self._profile_error = None
        self.state = GuidanceState(self.stage, 0., "hold_guard")

    def invalidate(self):
        self._last_t = None
        self._samples = []
        self._countdown_start = None

    def _state(self, message, progress=0.):
        self.state = GuidanceState(self.stage, float(np.clip(progress, 0, 1)), message, self.profile)
        return self.state

    def _transition(self, stage):
        self.stage = stage
        self._samples = []
        self._countdown_start = None
        return self._state(stage.lower())

    def _hold(self, timestamp, points, duration):
        if self._samples and np.linalg.norm(points - self._samples[0][1], axis=1).max() > self.config.calibration_motion_m:
            self._samples = []
        self._samples.append((timestamp, points.copy()))
        elapsed = timestamp - self._samples[0][0]
        return (duration == 0 or elapsed + 1e-9 >= duration,
                1. if duration == 0 else min(1., elapsed / duration))

    def _profile(self):
        c = self.config
        centers, guards, attacks, travel = {}, {}, {}, {}
        for hand in HANDS:
            reach = self._reaches[hand]
            center = self._reference[hand] + np.array((0, c.target_height_m, -c.target_reach_ratio * reach))
            if (center[2] - c.target_radius_m < c.min_depth_m
                    or center[2] + c.target_radius_m > c.max_depth_m
                    or self._neutral_fists[hand][2] - c.hand_radius_m < c.min_depth_m
                    or self._neutral_fists[hand][2] + c.hand_radius_m > c.max_depth_m):
                return None, "adjust_distance"
            if np.linalg.norm(center - self._neutral_fists[hand]) <= c.hand_radius_m + c.target_radius_m + .02:
                return None, "reach_too_small"
            comfortable_fist = self._reference[hand] + self._reach_vectors[hand]
            if segment_sphere_intersection(self._neutral_fists[hand], comfortable_fist, center,
                                           c.hand_radius_m + c.target_radius_m) is None:
                return None, "target_unreachable"
            if c.spatial_layout and self.workspace is not None:
                direction = center-self._neutral_fists[hand]
                length = np.linalg.norm(direction)
                # Exclude the initial occupied fist volume before the sampled sweep.
                start = self._neutral_fists[hand]+direction*min(.5, (2*c.hand_radius_m+.02)/length)
                status = self.workspace.path_status(start, center, max(c.hand_radius_m, c.target_radius_m))
                if status != "clear": return None, f"workspace_{status}"
            guards[hand] = self._neutral[hand] + .04
            attacks[hand] = guards[hand] + .5 * (reach - guards[hand])
            travel[hand] = min(c.punch_min_travel_m, .25 * (reach - guards[hand]))
            centers[hand] = center
        return CalibrationProfile(
            {h: p.copy() for h, p in self._reference.items()}, dict(self._neutral), dict(self._reaches),
            guards, attacks, travel, centers), None

    def register_practice_hit(self, hand):
        if self.stage == "PRACTICE_LEFT" and hand == "left":
            self._transition("PRACTICE_RIGHT")
        elif self.stage == "PRACTICE_RIGHT" and hand == "right":
            self._transition("COUNTDOWN")

    def update(self, frame: SkeletonFrame, fists: dict[str, Joint3D]) -> GuidanceState:
        c, t = self.config, frame.timestamp_s
        dt = t - self._last_t if self._last_t is not None else None
        broken = dt is not None and (dt <= 0 or dt > c.max_track_gap_s + 1e-9)
        if broken:
            self.invalidate()
        self._last_t = t
        hands = HANDS
        if c.partial_tracking and self.stage.startswith(("REACH", "RETURN", "PRACTICE")):
            hands = ("left" if self.stage.endswith("LEFT") else "right",)
        available = {h: valid_hand(frame, fists, h, c) for h in HANDS}
        valid = (any(available.values()) if self.stage == "RUNNING" else all(available[h] for h in hands)) if c.partial_tracking else valid_body(frame, fists, c)
        if not valid:
            self.invalidate()
            return self._state("missing_body")
        if dt is not None and dt <= 0:
            return self._state("timestamp_invalid")
        shoulders = {h: frame.joints[f"{h}_shoulder"].position for h in HANDS if available[h]}
        extensions = {h: float(shoulders[h][2] - fists[h].position[2]) for h in shoulders}
        thresholds = self.profile.guard_thresholds if self.profile else {h: c.guard_extension_m for h in HANDS}
        guard = all(extensions.get(h, float("inf")) <= thresholds[h] for h in hands)
        if self.stage == "RUNNING":
            return self._state("running", 1.)
        if self.stage == "COUNTDOWN":
            if not guard:
                self._countdown_start = None
                return self._state("return_guard")
            if self._countdown_start is None:
                self._countdown_start = t
            elapsed = t - self._countdown_start
            if elapsed + 1e-9 >= c.countdown_s:
                return self._transition("RUNNING")
            return self._state("countdown", elapsed / c.countdown_s)
        if self.stage.startswith("PRACTICE"):
            return self._state(self.stage.lower())
        if self.stage == "HOLD_GUARD":
            if not guard:
                self._samples = []
                return self._state("return_guard")
            points = np.stack([shoulders[h] for h in HANDS] + [fists[h].position for h in HANDS])
            done, progress = self._hold(t, points, c.calibration_duration_s)
            if not done:
                return self._state("hold_guard", progress)
            mean = np.mean([p for _, p in self._samples], axis=0)
            self._reference = {h: mean[n].copy() for n, h in enumerate(HANDS)}
            self._neutral_fists = {h: mean[2+n].copy() for n, h in enumerate(HANDS)}
            self._neutral = {h: float(self._reference[h][2] - self._neutral_fists[h][2]) for h in HANDS}
            return self._transition("REACH_LEFT")
        if any(np.linalg.norm(shoulders[h] - self._reference[h]) > c.calibration_motion_m for h in shoulders):
            self._samples = []
            return self._state("restore_position")
        hand = "left" if self.stage.endswith("LEFT") else "right"
        if self.stage.startswith("REACH"):
            if extensions[hand] < self._neutral[hand] + c.reach_min_increment_m:
                self._samples = []
                return self._state(self._profile_error or "extend_comfortably")
            p = fists[hand].position
            if not c.min_depth_m + c.hand_radius_m <= p[2] <= c.max_depth_m - c.hand_radius_m:
                self._samples = []
                return self._state("adjust_distance")
            self._profile_error = None
            points = np.stack([shoulders[h] for h in hands] + [p - shoulders[hand]])
            done, progress = self._hold(t, points, c.reach_hold_s)
            if not done:
                return self._state("hold_reach", progress)
            self._reach_vectors[hand] = np.mean([p[-1] for _, p in self._samples], axis=0)
            self._reaches[hand] = -float(self._reach_vectors[hand][2])
            return self._transition(f"RETURN_{hand.upper()}")
        if not guard:
            self._samples = []
            return self._state("return_guard")
        points = np.stack([fists[h].position for h in hands])
        done, progress = self._hold(t, points, c.return_guard_s)
        if not done:
            return self._state("hold_guard", progress)
        if hand == "left":
            return self._transition("REACH_RIGHT")
        self.profile, error = self._profile()
        if error:
            self._transition("REACH_LEFT")
            self._profile_error = error
            return self._state(error)
        return self._transition("PRACTICE_LEFT")
