"""Explicit punch state and deterministic target-boxing rules."""
from dataclasses import dataclass

import numpy as np

from .config import AppConfig
from .geometry import segment_sphere_intersection
from .tracking import SkeletonTracker
from .types import HitEvent, Joint3D, SceneState, SkeletonFrame, Target


@dataclass(frozen=True)
class PunchState:
    phase: str
    attack_id: int
    previous_position: np.ndarray | None
    position: np.ndarray | None
    can_hit: bool


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

    def update(self, timestamp_s: float, wrist: Joint3D | None, shoulder: Joint3D | None) -> PunchState:
        config = self.config
        if any(j is None or j.position is None or j.confidence < config.confidence_threshold for j in (wrist, shoulder)):
            self.reset()
            return PunchState(self.phase, self.attack_id, None, None, False)
        position = wrist.position
        extension = float(shoulder.position[2]-position[2])
        previous = self._previous
        dt = timestamp_s-previous[0] if previous else None
        broken = dt is not None and (dt <= 0 or dt > config.max_track_gap_s)
        if broken:
            self.reset()
            previous = None
        can_hit = False
        if extension <= config.guard_extension_m:
            self.phase = "READY"
            self._guard_extension = extension
        elif previous is not None:
            speed = (extension-previous[2])/dt
            if self.phase == "READY" and self._guard_extension is not None:
                if (speed >= config.punch_speed_m_s and extension >= config.attack_extension_m
                        and extension-self._guard_extension >= config.punch_min_travel_m):
                    self.attack_id += 1
                    self.phase = "ATTACKING"
                    self._attack_start = timestamp_s
                    can_hit = True
            elif self.phase == "ATTACKING":
                if speed > 0 and timestamp_s-self._attack_start <= config.max_attack_duration_s:
                    can_hit = True
                else:
                    self.phase = "RECOVERING"
        self._previous = (timestamp_s, position.copy(), extension)
        return PunchState(self.phase, self.attack_id,
                          previous[1] if previous is not None and not broken else None,
                          position.copy(), can_hit and not broken)


class BoxingSimulation:
    def __init__(self, config: AppConfig):
        self.config = config
        self.tracker = SkeletonTracker(config)
        self.punches = {hand: PunchTracker(config) for hand in ("left", "right")}
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
        self.invalidate_tracking()

    def invalidate_tracking(self):
        self.tracker.reset()
        for tracker in self.punches.values():
            tracker.reset()
        self._calibration = []

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

    def _state(self, frame, events, status, phases):
        targets = tuple(Target(n, hand, center.copy(), self.config.target_radius_m,
                               n == self._active, self._flashes.get(n, -1) > self._elapsed)
                        for n, (hand, center) in enumerate(zip(("left", "right"), self._centers)))
        return SceneState(frame, targets, self.score, self.hits,
                          max(0., self.config.round_duration_s-self._elapsed), events, status, phases)
