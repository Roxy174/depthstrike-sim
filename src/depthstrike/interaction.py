"""Measured surface-based interaction proxies, not anatomical joint estimates."""
import numpy as np

from .config import AppConfig
from .types import Joint3D


def estimate_fist(elbow: Joint3D | None, wrist: Joint3D | None, config: AppConfig) -> Joint3D:
    for joint in (wrist, elbow):
        if joint is None or not joint.is_observed:
            return Joint3D(None, invalid_reason=(joint.invalid_reason if joint else None) or "missing_joint")
        if joint.confidence < config.confidence_threshold:
            return Joint3D(None, invalid_reason="low_confidence")
    forearm = wrist.position - elbow.position
    length = float(np.linalg.norm(forearm))
    if length < config.forearm_min_length_m:
        return Joint3D(None, invalid_reason="degenerate_forearm")
    return Joint3D(wrist.position + config.fist_offset_m * forearm / length,
                   min(elbow.confidence, wrist.confidence), depth_quality=min(elbow.depth_quality, wrist.depth_quality))


def estimate_hand(joints, hand, config):
    if config.fist_mode == "hand":
        wrist, index, pinky = (joints.get(f"{hand}_{p}") for p in ("wrist", "index", "pinky"))
        if all(j is not None and j.is_observed and j.confidence >= config.confidence_threshold
               for j in (wrist, index, pinky)):
            if max(np.linalg.norm(j.position-wrist.position) for j in (index, pinky)) <= .20:
                return Joint3D((index.position+pinky.position)/2, min(j.confidence for j in (wrist, index, pinky)),
                               provenance="hand_surface", depth_quality=min(j.depth_quality for j in (wrist, index, pinky)))
    return estimate_fist(joints.get(f"{hand}_elbow"), joints.get(f"{hand}_wrist"), config)
