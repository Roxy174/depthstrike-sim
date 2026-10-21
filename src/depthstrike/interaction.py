"""Measured surface-based interaction proxies, not anatomical joint estimates."""
import numpy as np

from .config import AppConfig
from .types import Joint3D


def estimate_fist(elbow: Joint3D | None, wrist: Joint3D | None, config: AppConfig) -> Joint3D:
    for joint in (wrist, elbow):
        if joint is None or joint.position is None:
            return Joint3D(None, invalid_reason=(joint.invalid_reason if joint else None) or "missing_joint")
        if joint.confidence < config.confidence_threshold:
            return Joint3D(None, invalid_reason="low_confidence")
    forearm = wrist.position - elbow.position
    length = float(np.linalg.norm(forearm))
    if length < config.forearm_min_length_m:
        return Joint3D(None, invalid_reason="degenerate_forearm")
    return Joint3D(wrist.position + config.fist_offset_m * forearm / length,
                   min(elbow.confidence, wrist.confidence))
