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
    measurements: dict | None = None


def valid_body(frame: SkeletonFrame, fists: dict[str, Joint3D], config: AppConfig) -> bool:
    joints = [frame.joints.get(name) for name in REQUIRED_JOINTS] + [fists.get(h) for h in HANDS]
    return all(j is not None and j.is_observed and j.confidence >= config.confidence_threshold
               for j in joints)


def valid_hand(frame, fists, hand, config):
    joints = (frame.joints.get(f"{hand}_shoulder"), fists.get(hand))
    return all(j is not None and j.is_observed and j.confidence >= config.confidence_threshold for j in joints)


def calibrated_target_center(shoulder, neutral_fist, comfortable_fist, config):
    """Place a target from measured positions; preserve old record geometry."""
    if config.target_layout == "shoulder":
        reach = shoulder[2]-comfortable_fist[2]
        return shoulder+np.array((0, config.target_height_m, -config.target_reach_ratio*reach))
    direction = comfortable_fist-neutral_fist
    length = float(np.linalg.norm(direction))
    separation = config.hand_radius_m+config.target_radius_m+.02
    if length <= separation:
        return None
    # A short measured stroke may need a larger fraction to keep the target
    # clear of the neutral fist. Never extend beyond the measured endpoint.
    distance = max(config.target_reach_ratio*length, min(length, separation+.0001))
    center = neutral_fist+direction*(distance/length)
    return center+np.array((0, config.target_height_m, 0))


class GuidedCalibration:
    def __init__(self, config: AppConfig):
        self.config = config
        self.workspace = None
        self.reset()

    def reset(self):
        self.stage = "HOLD_GUARD"
        self.profile = None
        self._last_t = None
        self._last_valid_t = None
        self._measurements = {}
        self._clear_samples()
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
        self._last_valid_t = None
        self._measurements = {}
        self._clear_samples()
        self._countdown_start = None

    def _clear_samples(self):
        self._samples = []
        self._hold_elapsed = 0.
        self._hold_last_t = None
        self._hold_progress = 0.

    def _state(self, message, progress=0.):
        measurements = dict(self._measurements)
        if self.stage.startswith("REACH_"):
            measurements.update(hold_s=self._hold_elapsed, required_hold_s=self.config.reach_hold_s)
        self.state = GuidanceState(self.stage, float(np.clip(progress, 0, 1)), message, self.profile, measurements)
        return self.state

    def _transition(self, stage):
        self.stage = stage
        self._measurements = {}
        self._clear_samples()
        self._countdown_start = None
        return self._state(stage.lower())

    def _hold(self, timestamp, points, duration, *, stable_rows=None):
        if self._samples:
            displacement = np.linalg.norm(points-self._samples[0][1], axis=1)
            if stable_rows is not None:
                displacement = displacement[list(stable_rows)]
            if displacement.max() > self.config.calibration_motion_m:
                self._clear_samples()
                self._measurements["hold_reset_reason"] = "position_motion"
        if self._hold_last_t is not None:
            self._hold_elapsed += timestamp - self._hold_last_t
        self._hold_last_t = timestamp
        self._samples.append((timestamp, points.copy()))
        self._hold_progress = 1. if duration == 0 else min(1., self._hold_elapsed / duration)
        return duration == 0 or self._hold_elapsed + 1e-9 >= duration, self._hold_progress

    def _body_translation(self, frame, hand):
        other = "right" if hand == "left" else "left"
        # The opposite shoulder is not protracted by the measured arm. Use its
        # observed displacement to cancel body translation, not the arm's reach.
        for side in (other, hand):
            joint = frame.joints.get(f"{side}_shoulder")
            if joint is not None and joint.is_observed and joint.confidence >= self.config.confidence_threshold:
                return joint.position-self._reference[side]
        return None

    def _profile(self):
        c = self.config
        centers, guards, attacks, travel = {}, {}, {}, {}
        for hand in HANDS:
            reach = self._reaches[hand]
            if c.target_layout == "measured_path" and reach <= self._neutral[hand]+.04:
                return None, "reach_too_small"
            comfortable_fist = self._reference[hand] + self._reach_vectors[hand]
            center = calibrated_target_center(self._reference[hand], self._neutral_fists[hand], comfortable_fist, c)
            if center is None:
                return None, "reach_too_small"
            if (center[2] - c.target_radius_m < c.min_depth_m
                    or center[2] + c.target_radius_m > c.max_depth_m
                    or self._neutral_fists[hand][2] - c.hand_radius_m < c.min_depth_m
                    or self._neutral_fists[hand][2] + c.hand_radius_m > c.max_depth_m):
                return None, "adjust_distance"
            if np.linalg.norm(center - self._neutral_fists[hand]) <= c.hand_radius_m + c.target_radius_m + .02:
                return None, "reach_too_small"
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

    def update(self, frame: SkeletonFrame, fists: dict[str, Joint3D], *, capture=False) -> GuidanceState:
        c, t = self.config, frame.timestamp_s
        self._measurements = {}
        dt = t - self._last_t if self._last_t is not None else None
        broken = dt is not None and (dt <= 0 or dt > c.max_track_gap_s + 1e-9)
        if broken:
            self.invalidate()
        self._last_t = t
        if dt is not None and dt <= 0:
            return self._state("timestamp_invalid")
        hands = HANDS
        if c.partial_tracking and self.stage.startswith(("REACH", "RETURN", "PRACTICE")):
            hands = ("left" if self.stage.endswith("LEFT") else "right",)
        available = {h: valid_hand(frame, fists, h, c) for h in HANDS}
        if self.stage.startswith("REACH_"):
            hand = "left" if self.stage.endswith("LEFT") else "right"
            self._measurements = {"hand": hand, "forward_m": None, "required_forward_m": c.reach_min_increment_m}
            if available[hand]:
                translation = self._body_translation(frame, hand)
                forward = (self._neutral_fists[hand][2]-fists[hand].position[2]+translation[2]
                           if c.target_layout == "measured_path" else
                           frame.joints[f"{hand}_shoulder"].position[2]-fists[hand].position[2]-self._neutral[hand])
                self._measurements.update(forward_m=float(forward), body_motion_m=float(np.linalg.norm(translation)))
            for side in hands:
                if not available[side]:
                    shoulder = frame.joints.get(f"{side}_shoulder")
                    if shoulder is None or not shoulder.is_observed or shoulder.confidence < c.confidence_threshold:
                        self._measurements.update(blocked_joint=f"{side}_shoulder", blocked_reason=(shoulder.invalid_reason if shoulder else None) or "low_confidence")
                    else:
                        fist = fists.get(side)
                        part = "wrist" if c.fist_mode == "wrist" else "hand"
                        self._measurements.update(blocked_joint=f"{side}_{part}", blocked_reason=(fist.invalid_reason if fist else None) or "missing_joint")
                    break
        valid = (any(available.values()) if self.stage == "RUNNING" else all(available[h] for h in hands)) if c.partial_tracking else valid_body(frame, fists, c)
        if not valid:
            # Only valid, consecutive observations contribute hold time. Keep
            # existing samples through a bounded pose/depth dropout, but never
            # count that dropout toward completing the stage or countdown.
            self._hold_last_t = None
            self._countdown_start = None
            if (c.calibration_grace_s == 0 or self._last_valid_t is None
                    or t-self._last_valid_t > c.calibration_grace_s + 1e-9):
                self._clear_samples()
            return self._state("reacquiring" if self._samples else "missing_body", self._hold_progress)
        if (self._samples and self._hold_last_t is None and self._last_valid_t is not None
                and t-self._last_valid_t > c.calibration_grace_s + 1e-9):
            self._clear_samples()
        self._last_valid_t = t
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
                self._clear_samples()
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
        hand = "left" if self.stage.endswith("LEFT") else "right"
        translation = self._body_translation(frame, hand) if c.target_layout == "measured_path" else None
        moved = (np.linalg.norm(translation) > c.calibration_motion_m if translation is not None else
                 any(np.linalg.norm(shoulders[h]-self._reference[h]) > c.calibration_motion_m for h in shoulders))
        if moved:
            self._clear_samples()
            return self._state("restore_position")
        if self.stage.startswith("REACH"):
            forward = self._measurements["forward_m"]
            if forward + 1e-9 < c.reach_min_increment_m:
                self._clear_samples()
                other = "right" if hand == "left" else "left"
                if available[other] and extensions[other]-self._neutral[other] >= c.reach_min_increment_m:
                    return self._state("wrong_hand")
                return self._state(self._profile_error or "extend_comfortably")
            p = fists[hand].position
            if not c.min_depth_m + c.hand_radius_m <= p[2] <= c.max_depth_m - c.hand_radius_m:
                self._clear_samples()
                return self._state("adjust_distance")
            self._profile_error = None
            points = (np.stack((translation, shoulders[hand]-translation, p-translation-self._reference[hand]))
                      if c.target_layout == "measured_path" else
                      np.stack([shoulders[h] for h in hands] + [p-shoulders[hand]]))
            # Row 1 stores the active shoulder for attack thresholds. It is
            # metadata, not the stationary reference for this measured reach.
            stable_rows = (0, 2) if c.target_layout == "measured_path" else None
            done, progress = self._hold(t, points, c.reach_hold_s, stable_rows=stable_rows)
            if not done and not capture:
                return self._state("hold_reach", progress)
            vectors = np.asarray([p[-1] for _, p in self._samples])
            if c.target_layout == "measured_path":
                # Filter warm-up at the start of a hold underestimates short
                # reaches. Choose an observed point near the stable tail median.
                tail = vectors[len(vectors)//2:]
                middle = np.median(tail, axis=0)
                index = len(vectors)-1 if capture else len(vectors)//2+int(np.argmin(np.linalg.norm(tail-middle, axis=1)))
                self._reach_vectors[hand] = vectors[index].copy()
                # Attack thresholds retain the observed shoulder-to-hand
                # extension, while target placement retains the measured path.
                sample = self._samples[index][1]
                self._reaches[hand] = float(sample[1, 2]-(self._reference[hand][2]+vectors[index, 2]))
            else:
                self._reach_vectors[hand] = vectors[-1].copy() if capture else np.mean(vectors, axis=0)
                self._reaches[hand] = -float(self._reach_vectors[hand][2])
            return self._transition(f"RETURN_{hand.upper()}")
        if not guard:
            self._clear_samples()
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
