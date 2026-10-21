"""Explicit punch state and deterministic target-boxing rules."""
from dataclasses import dataclass

import numpy as np

from .config import AppConfig
from .calibration import GuidedCalibration, valid_body
from .geometry import segment_sphere_intersection
from .interaction import estimate_fist
from .feedback import build_feedback
from .tracking import SkeletonTracker
from .types import HitEvent, Joint3D, SceneState, SkeletonFrame, Target


@dataclass(frozen=True)
class PunchState:
    phase: str
    attack_id: int
    previous_position: np.ndarray | None
    position: np.ndarray | None
    can_hit: bool
    reason: str = "return_guard"


class PunchTracker:
    def __init__(self, config: AppConfig):
        self.config = config
        self.attack_id = 0
        self.reset()

    def reset(self):
        self.phase = "RECOVERING"
        self._previous = None
        self._guard_extension = None
        self._attack_start = None

    def update(self, timestamp_s: float, wrist: Joint3D | None, shoulder: Joint3D | None, *,
               guard_extension_m=None, attack_extension_m=None, min_travel_m=None) -> PunchState:
        config = self.config
        guard_threshold = config.guard_extension_m if guard_extension_m is None else guard_extension_m
        attack_threshold = config.attack_extension_m if attack_extension_m is None else attack_extension_m
        travel_threshold = config.punch_min_travel_m if min_travel_m is None else min_travel_m
        if any(j is None or j.position is None or j.confidence < config.confidence_threshold for j in (wrist, shoulder)):
            self.reset()
            return PunchState(self.phase, self.attack_id, None, None, False, "invalid_tracking")
        position = wrist.position
        extension = float(shoulder.position[2]-position[2])
        previous = self._previous
        dt = timestamp_s-previous[0] if previous else None
        broken = dt is not None and (dt <= 0 or dt > config.max_track_gap_s)
        if broken:
            self.reset()
            previous = None
        can_hit = False
        reason = "return_guard"
        if extension <= guard_threshold:
            self.phase = "READY"
            self._guard_extension = extension
            reason = "ready"
        elif previous is not None:
            speed = (extension-previous[2])/dt
            if self.phase == "READY" and self._guard_extension is not None:
                reason = "low_speed" if speed < config.punch_speed_m_s else "insufficient_travel"
                if (speed >= config.punch_speed_m_s and extension >= attack_threshold
                        and extension-self._guard_extension >= travel_threshold):
                    self.attack_id += 1
                    self.phase = "ATTACKING"
                    self._attack_start = timestamp_s
                    can_hit = True
                    reason = "attacking"
            elif self.phase == "ATTACKING":
                if speed > 0 and timestamp_s-self._attack_start <= config.max_attack_duration_s:
                    can_hit = True
                    reason = "attacking"
                else:
                    self.phase = "RECOVERING"
        self._previous = (timestamp_s, position.copy(), extension)
        return PunchState(self.phase, self.attack_id,
                          previous[1] if previous is not None and not broken else None,
                          position.copy(), can_hit and not broken, reason)


class BoxingSimulation:
    def __init__(self, config: AppConfig):
        self.config = config
        self.tracker = SkeletonTracker(config)
        self.punches = {hand: PunchTracker(config) for hand in ("left", "right")}
        self.calibration = GuidedCalibration(config) if config.interaction_mode == "guided" else None
        self.reset()

    def reset(self):
        self.score = self.hits = 0
        self.paused = False
        self._elapsed = 0.
        self._last_t = None
        self._skip_time = True
        self._calibration = []
        self._centers = []
        self._active = 0
        self._flashes = {}
        self._settled = set()
        self._guided_valid_previous = False
        self._practice_flashes = {}
        if self.calibration is not None:
            self.calibration.reset()
        self.invalidate_tracking()

    def invalidate_tracking(self):
        self.tracker.reset()
        for tracker in self.punches.values():
            tracker.reset()
        self._calibration = []
        self._guided_valid_previous = False
        if self.calibration is not None:
            self.calibration.invalidate()

    def set_paused(self, paused: bool):
        if paused != self.paused:
            self.paused = paused
            self._skip_time = True
            self.invalidate_tracking()

    def _calibrate(self, frame):
        names = [f"{hand}_{part}" for hand in ("left", "right") for part in ("shoulder", "elbow", "wrist")]
        joints = [frame.joints.get(name) for name in names]
        if any(j is None or j.position is None or j.confidence < self.config.confidence_threshold for j in joints):
            self._calibration = []
            return
        points = np.stack([j.position for j in joints])
        if any(points[n, 2]-points[n+2, 2] > self.config.guard_extension_m for n in (0, 3)):
            self._calibration = []
            return
        if self._calibration:
            reference = self._calibration[0][1]
            if np.linalg.norm(points-reference, axis=1).max() > self.config.calibration_motion_m:
                self._calibration = []
        self._calibration.append((frame.timestamp_s, points))
        if frame.timestamp_s-self._calibration[0][0] + 1e-9 >= self.config.calibration_duration_s:
            average = np.mean([p for _, p in self._calibration], axis=0)
            self._centers = [average[n] + np.array((0, self.config.target_height_m, -self.config.target_forward_m))
                             for n in (0, 3)]
            self._calibration = []
            self._skip_time = True

    def step(self, frame: SkeletonFrame) -> SceneState:
        if self.calibration is not None:
            return self._step_guided(frame)
        previous_t = self._last_t
        dt = frame.timestamp_s-previous_t if previous_t is not None else 0.
        self._last_t = frame.timestamp_s
        if previous_t is not None and (dt <= 0 or dt > self.config.max_track_gap_s):
            self.invalidate_tracking()
        was_calibrated = bool(self._centers)
        if self.paused:
            return self._state(frame, (), "PAUSED", {})
        if was_calibrated and dt > 0 and not self._skip_time:
            self._elapsed += dt
        self._skip_time = False
        if self._elapsed >= self.config.round_duration_s:
            self.invalidate_tracking()
            return self._state(frame, (), "FINISHED", {})
        if not was_calibrated:
            self._calibrate(frame)
        filtered = self.tracker.update(frame)
        states = {hand: tracker.update(frame.timestamp_s, filtered.joints.get(f"{hand}_wrist"),
                                      filtered.joints.get(f"{hand}_shoulder"))
                  for hand, tracker in self.punches.items()}
        events = []
        if self._centers:
            hand = ("left", "right")[self._active]
            punch = states[hand]
            key = (hand, punch.attack_id)
            if punch.can_hit and punch.previous_position is not None and key not in self._settled:
                contact = segment_sphere_intersection(punch.previous_position, punch.position,
                    self._centers[self._active], self.config.hand_radius_m+self.config.target_radius_m)
                if contact is not None:
                    self._settled.add(key)
                    event = HitEvent(frame.timestamp_s, hand, self._active, punch.attack_id, 10)
                    events.append(event)
                    self.score += event.points
                    self.hits += 1
                    self._flashes[self._active] = self._elapsed + self.config.hit_flash_s
                    self._active = 1-self._active
        valid = all(filtered.joints.get(f"{h}_wrist", Joint3D(None)).position is not None for h in ("left", "right"))
        status = "CALIBRATING" if not self._centers else ("RUNNING" if valid else "TRACKING LOST")
        return self._state(filtered, tuple(events), status, {h: s.phase for h, s in states.items()})

    def _step_guided(self, frame):
        previous_t = self._last_t
        dt = frame.timestamp_s - previous_t if previous_t is not None else 0.
        self._last_t = frame.timestamp_s
        if previous_t is not None and not 0 < dt <= self.config.max_track_gap_s + 1e-9:
            self.invalidate_tracking()
        filtered = self.tracker.update(frame)
        fists = {h: estimate_fist(filtered.joints.get(f"{h}_elbow"),
                                  filtered.joints.get(f"{h}_wrist"), self.config) for h in ("left", "right")}
        valid = valid_body(filtered, fists, self.config)
        guidance = self.calibration.state
        if self.paused:
            return self._guided_state(filtered, fists, (), "PAUSED", {}, guidance)
        if self._elapsed >= self.config.round_duration_s:
            self.invalidate_tracking()
            return self._guided_state(filtered, fists, (), "FINISHED", {}, guidance)
        was_running = guidance.stage == "RUNNING"
        if not valid:
            self.invalidate_tracking()
        guidance = self.calibration.update(filtered, fists)
        if guidance.profile is not None and not self._centers:
            self._centers = [guidance.profile.target_centers[h].copy() for h in ("left", "right")]
            for tracker in self.punches.values():
                tracker.reset()
        running = guidance.stage == "RUNNING"
        if running and was_running and valid and self._guided_valid_previous and dt > 0:
            self._elapsed += dt
        self._guided_valid_previous = valid and running
        if running and not was_running:
            for tracker in self.punches.values():
                tracker.reset()
        if self._elapsed + 1e-9 >= self.config.round_duration_s:
            self._elapsed = self.config.round_duration_s
            self.invalidate_tracking()
            return self._guided_state(filtered, fists, (), "FINISHED", {}, guidance)
        profile = guidance.profile
        states = {}
        for hand, tracker in self.punches.items():
            options = {} if profile is None else dict(
                guard_extension_m=profile.guard_thresholds[hand],
                attack_extension_m=profile.attack_thresholds[hand],
                min_travel_m=profile.travel_thresholds[hand])
            states[hand] = tracker.update(frame.timestamp_s, fists[hand] if valid else None,
                                         filtered.joints.get(f"{hand}_shoulder"), **options)
        practice = guidance.stage.startswith("PRACTICE")
        events = []
        if valid and self._centers and (running or practice):
            active = (0 if guidance.stage == "PRACTICE_LEFT" else 1) if practice else self._active
            hand = ("left", "right")[active]
            punch = states[hand]
            key = (hand, punch.attack_id)
            if punch.can_hit and punch.previous_position is not None and key not in self._settled:
                contact = segment_sphere_intersection(punch.previous_position, punch.position,
                    self._centers[active], self.config.hand_radius_m + self.config.target_radius_m)
                if contact is not None:
                    self._settled.add(key)
                    if practice:
                        self._practice_flashes[active] = frame.timestamp_s + self.config.hit_flash_s
                        self.calibration.register_practice_hit(hand)
                        guidance = self.calibration.state
                    else:
                        event = HitEvent(frame.timestamp_s, hand, active, punch.attack_id, 10)
                        events.append(event)
                        self.score += event.points
                        self.hits += 1
                        self._flashes[active] = self._elapsed + self.config.hit_flash_s
                        self._active = 1 - active
        status = "TRACKING LOST" if not valid else ("RUNNING" if running else "CALIBRATING")
        return self._guided_state(filtered, fists, tuple(events), status, states, guidance)

    def _guided_state(self, frame, fists, events, status, states, guidance):
        active = 0 if guidance.stage == "PRACTICE_LEFT" else (1 if guidance.stage == "PRACTICE_RIGHT" else self._active)
        targets = tuple(Target(n, hand, center.copy(), self.config.target_radius_m, n == active,
                               self._flashes.get(n, -1) > self._elapsed or
                               self._practice_flashes.get(n, -1) > frame.timestamp_s)
                        for n, (hand, center) in enumerate(zip(("left", "right"), self._centers)))
        phases = {h: s.phase for h, s in states.items()}
        diagnostics = {h: s.reason for h, s in states.items()}
        feedback_status = "RUNNING" if status == "CALIBRATING" and guidance.stage.startswith("PRACTICE") else status
        feedback = build_feedback(fists, targets, phases, feedback_status, self.config, diagnostics)
        return SceneState(frame, targets, self.score, self.hits,
                          max(0., self.config.round_duration_s - self._elapsed), events, status,
                          phases, guidance, fists, feedback, diagnostics)

    def _state(self, frame, events, status, phases):
        targets = tuple(Target(n, hand, center.copy(), self.config.target_radius_m,
                               n == self._active, self._flashes.get(n, -1) > self._elapsed)
                        for n, (hand, center) in enumerate(zip(("left", "right"), self._centers)))
        fists = {h: frame.joints.get(f"{h}_wrist", Joint3D(None)) for h in ("left", "right")} if frame else {}
        return SceneState(frame, targets, self.score, self.hits,
                          max(0., self.config.round_duration_s-self._elapsed), events, status, phases,
                          fists=fists, feedback=build_feedback(fists, targets, phases, status, self.config, {}))
