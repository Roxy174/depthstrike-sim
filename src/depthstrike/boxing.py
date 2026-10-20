"""Explicit punch state and deterministic target-boxing rules."""
from dataclasses import dataclass

import numpy as np

from .config import AppConfig
from .types import Joint3D


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
