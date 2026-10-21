"""Validated engineering parameters, not measured accuracy claims."""
from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    hand_radius_m: float = .06
    target_radius_m: float = .08
    confidence_threshold: float = .6
    max_track_gap_s: float = .2
    round_duration_s: float = 60.0
    min_depth_m: float = .25
    max_depth_m: float = 5.0
    depth_window_px: int = 5
    depth_min_valid_ratio: float = .6
    depth_max_spread_m: float = .12
    smoothing_tau_s: float = .035
    punch_speed_m_s: float = .65
    punch_min_travel_m: float = .08
    guard_extension_m: float = .22
    attack_extension_m: float = .28
    max_attack_duration_s: float = .8
    calibration_duration_s: float = .6
    calibration_motion_m: float = .06
    target_forward_m: float = .5
    target_height_m: float = .04
    hit_flash_s: float = .25
    frame_sync_tolerance_s: float = .035
    camera_timeout_ms: int = 150
    stream_timeout_s: float = 5.0
    model_path: str = "models/pose_landmarker_lite.task"
    legacy_sdk_distortion_model: str = "unknown"

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "legacy_sdk_distortion_model":
                if value not in ("unknown", "brown_conrady", "none"):
                    raise ValueError("Unsupported legacy_sdk_distortion_model")
                continue
            if item.name == "model_path":
                if not isinstance(value, str) or not value:
                    raise ValueError("model_path must be a non-empty string")
                continue
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f"{item.name} must be finite and numeric")
            if value < 0 or (value == 0 and item.name not in {"smoothing_tau_s", "calibration_duration_s", "target_height_m"}):
                raise ValueError(f"{item.name} must be positive")
        for name in ("confidence_threshold", "depth_min_valid_ratio"):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.min_depth_m >= self.max_depth_m:
            raise ValueError("min_depth_m must be smaller than max_depth_m")
        if self.guard_extension_m >= self.attack_extension_m:
            raise ValueError("Guard must be closer to shoulder than attack threshold")
        if not isinstance(self.depth_window_px, int) or self.depth_window_px % 2 != 1:
            raise ValueError("depth_window_px must be an odd integer")
        if not isinstance(self.camera_timeout_ms, int):
            raise ValueError("camera_timeout_ms must be an integer")

    def to_dict(self):
        return asdict(self)


def load_config(path: Path | None = None) -> AppConfig:
    if path is None:
        return AppConfig()
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        raise ValueError("Configuration must be a JSON object")
    unknown = set(values) - {f.name for f in fields(AppConfig)}
    if unknown:
        raise ValueError(f"Unknown configuration fields: {', '.join(sorted(unknown))}")
    return AppConfig(**values)
