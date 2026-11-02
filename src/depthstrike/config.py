"""Validated engineering parameters, not measured accuracy claims."""
from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    # Keep historical record defaults; load_config selects direct live play.
    interaction_mode: str = "guided"
    direct_target_forward_m: float = .38
    direct_targets_per_hand: int = 1  # Historical recordings keep their two targets.
    fist_offset_m: float = .06
    forearm_min_length_m: float = .02
    reach_hold_s: float = .35
    return_guard_s: float = .20
    reach_min_increment_m: float = .10
    target_reach_ratio: float = .85
    target_layout: str = "shoulder"
    countdown_s: float = 2.0
    hand_radius_m: float = .06
    target_radius_m: float = .08
    confidence_threshold: float = .6
    pose_confidence_threshold: float = 0.  # Zero inherits the historical joint threshold.
    segmentation_threshold: float = 0.  # Pixel membership is separate from landmark confidence.
    depth_surface_mode: str = "strict"
    depth_recovery_s: float = 0.
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
    calibration_grace_s: float = 0.0
    target_forward_m: float = .5
    target_height_m: float = .04
    hit_flash_s: float = .25
    frame_sync_tolerance_s: float = .035
    camera_timeout_ms: int = 150
    stream_timeout_s: float = 5.0
    model_path: str = "models/pose_landmarker_lite.task"
    legacy_sdk_distortion_model: str = "unknown"
    fusion_mode: str = "conservative"
    fist_mode: str = "forearm"
    filter_mode: str = "exponential"
    partial_tracking: bool = False
    reject_tracking_outliers: bool = False
    tracking_outlier_slack_m: float = .08
    tracking_body_speed_m_s: float = 2.0
    tracking_hand_speed_m_s: float = 10.0
    preview_targets: bool = False  # Accepted for old records; no targets before reach is measured.
    depth_occlusion: bool = False
    spatial_layout: bool = False
    prediction_horizon_s: float = .12
    one_euro_min_cutoff: float = 1.5
    one_euro_beta: float = 1.0

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "direct_targets_per_hand":
                if type(value) is not int or not 1 <= value <= 4:
                    raise ValueError("direct_targets_per_hand must be an integer from 1 to 4")
                continue
            choices = {"target_layout": ("shoulder", "measured_path"),
                       "depth_surface_mode": ("strict", "center_cluster"),
                       "fusion_mode": ("conservative", "masked"), "fist_mode": ("forearm", "hand", "wrist"),
                       "filter_mode": ("exponential", "one_euro", "kalman")}
            if item.name in choices:
                if value not in choices[item.name]: raise ValueError(f"Unsupported {item.name}")
                continue
            if item.name in ("partial_tracking", "preview_targets", "depth_occlusion", "spatial_layout", "reject_tracking_outliers"):
                if type(value) is not bool: raise ValueError(f"{item.name} must be boolean")
                continue
            if item.name == "interaction_mode":
                if value not in ("direct", "guided", "legacy"):
                    raise ValueError("interaction_mode must be direct, guided or legacy")
                continue
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
            if value < 0 or (value == 0 and item.name not in {"smoothing_tau_s", "calibration_duration_s", "target_height_m", "fist_offset_m", "calibration_grace_s", "pose_confidence_threshold", "segmentation_threshold", "depth_recovery_s"}):
                raise ValueError(f"{item.name} must be positive")
        if not 0 < self.target_reach_ratio < 1:
            raise ValueError("target_reach_ratio must be in (0, 1)")
        for name in ("confidence_threshold", "depth_min_valid_ratio", "pose_confidence_threshold", "segmentation_threshold"):
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
    values = {} if path is None else json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(values, dict):
        raise ValueError("Configuration must be a JSON object")
    unknown = set(values) - {f.name for f in fields(AppConfig)}
    if unknown:
        raise ValueError(f"Unknown configuration fields: {', '.join(sorted(unknown))}")
    defaults = ({"interaction_mode": "direct", "fist_mode": "wrist", "partial_tracking": True,
                 "direct_target_forward_m": .30, "direct_targets_per_hand": 3,
                 "model_path": "models/pose_landmarker_full.task", "pose_confidence_threshold": .5,
                 "segmentation_threshold": .35, "depth_surface_mode": "center_cluster", "depth_recovery_s": .2}
                if values.get("interaction_mode", "direct") == "direct" else {})
    return AppConfig(**(defaults | values))
