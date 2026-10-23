"""Shared data contracts. Coordinates: camera X right, Y down, Z forward (m)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .calibration import GuidanceState
    from .feedback import HandFeedback

import numpy as np


def vector3(value) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError("Position must contain three finite values")
    return result.copy()


@dataclass(frozen=True)
class Intrinsics:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    distortion_model: str = "none"
    distortion: tuple[float, ...] = ()

    def __post_init__(self):
        values = (self.fx, self.fy, self.cx, self.cy, *self.distortion)
        if (self.width <= 0 or self.height <= 0 or self.fx <= 0 or self.fy <= 0
                or not np.isfinite(values).all()):
            raise ValueError("Invalid camera intrinsics")


@dataclass(frozen=True)
class RGBDFrame:
    frame_id: int
    timestamp_s: float
    color_rgb: np.ndarray
    depth_m: np.ndarray
    intrinsics: Intrinsics
    # Live calibrated deprojection; recordings retain full calibration instead.
    deproject: Callable[[float, float, float], np.ndarray] | None = field(
        default=None, compare=False, repr=False)

    def __post_init__(self):
        shape = (self.intrinsics.height, self.intrinsics.width)
        if (self.color_rgb.shape != (*shape, 3) or self.color_rgb.dtype != np.uint8
                or self.depth_m.shape != shape or self.depth_m.dtype.kind != "f"):
            raise ValueError("Aligned RGB/depth dimensions or dtypes do not match intrinsics")
        if self.frame_id < 0 or not np.isfinite(self.timestamp_s) or self.timestamp_s < 0:
            raise ValueError("Invalid frame identity or timestamp")


@dataclass(frozen=True)
class Landmark:
    u: float
    v: float
    confidence: float


@dataclass(frozen=True)
class Joint3D:
    position: np.ndarray | None
    confidence: float = 0.0
    invalid_reason: str | None = None
    provenance: str = "observed"
    depth_quality: float = 1.0
    age_s: float = 0.0

    def __post_init__(self):
        if self.provenance not in ("observed", "depth_patch", "hand_surface", "predicted"):
            raise ValueError("Unknown joint provenance")
        if (not np.isfinite((self.depth_quality, self.age_s)).all()
                or not 0 <= self.depth_quality <= 1 or self.age_s < 0):
            raise ValueError("Invalid joint quality or age")
        if not np.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("Joint confidence must be in [0, 1]")
        if self.invalid_reason is not None and (
                not isinstance(self.invalid_reason, str) or not 0 < len(self.invalid_reason) <= 128
                or self.position is not None):
            raise ValueError("Invalid reason is only allowed on an invalid joint")
        if self.position is not None:
            object.__setattr__(self, "position", vector3(self.position))

    @property
    def is_observed(self):
        return self.position is not None and self.provenance != "predicted"


@dataclass(frozen=True)
class SkeletonFrame:
    frame_id: int
    timestamp_s: float
    joints: dict[str, Joint3D]

    def __post_init__(self):
        if self.frame_id < 0 or not np.isfinite(self.timestamp_s) or self.timestamp_s < 0:
            raise ValueError("Invalid skeleton identity or timestamp")


@dataclass(frozen=True)
class HitEvent:
    timestamp_s: float
    hand: str
    target_id: int
    attack_id: int
    points: int


@dataclass(frozen=True)
class Target:
    target_id: int
    hand: str
    center: np.ndarray
    radius: float
    active: bool
    flash: bool = False
    preview: bool = False


@dataclass(frozen=True)
class SceneState:
    skeleton: SkeletonFrame | None
    targets: tuple[Target, ...]
    score: int
    hits: int
    remaining_s: float
    events: tuple[HitEvent, ...]
    status: str
    phases: dict[str, str] = field(default_factory=dict)
    guidance: GuidanceState | None = None
    fists: dict[str, Joint3D] = field(default_factory=dict)
    feedback: dict[str, HandFeedback] = field(default_factory=dict)
    diagnostics: dict[str, str] = field(default_factory=dict)
    challenge: dict | None = None
    display_joints: dict[str, Joint3D] = field(default_factory=dict)


class FrameTimeout(TimeoutError):
    """Temporary live input loss, not EOF."""


class DepthStrikeError(RuntimeError):
    """Actionable runtime failure at an external boundary."""
