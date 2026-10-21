"""Observable interaction conditions, not claims about the cause of a miss."""
from dataclasses import dataclass

import numpy as np

from .config import AppConfig
from .types import Joint3D, Target


@dataclass(frozen=True)
class HandFeedback:
    reason: str
    surface_gap_m: float | None
    depth_delta_m: float | None
    lateral_m: float | None


def build_feedback(fists: dict[str, Joint3D], targets: tuple[Target, ...], phases: dict[str, str],
                   status: str, config: AppConfig, diagnostics: dict[str, str]) -> dict[str, HandFeedback]:
    result = {}
    for hand in ("left", "right"):
        fist = fists.get(hand)
        target = next((t for t in targets if t.hand == hand), None)
        global_reason = {"PAUSED": "paused", "FINISHED": "finished", "TRACKING LOST": "invalid_tracking",
                         "WAITING FOR CAMERA": "invalid_tracking"}.get(status)
        if global_reason or fist is None or fist.position is None:
            reason = global_reason or (fist.invalid_reason if fist else None) or "missing_joint"
            result[hand] = HandFeedback(reason, None, None, None)
            continue
        if target is None:
            result[hand] = HandFeedback("calibrating", None, None, None)
            continue
        delta = fist.position - np.asarray(target.center)
        radius = config.hand_radius_m + target.radius
        gap, depth, lateral = float(np.linalg.norm(delta) - radius), float(delta[2]), float(np.linalg.norm(delta[:2]))
        if status == "CALIBRATING": reason = "calibrating"
        elif not target.active: reason = "inactive_hand"
        elif phases.get(hand) == "RECOVERING": reason = "return_guard"
        elif diagnostics.get(hand) in ("low_speed", "insufficient_travel"): reason = diagnostics[hand]
        elif abs(depth) > radius: reason = "depth_gap"
        elif lateral > radius: reason = "off_axis"
        else: reason = "ready"
        result[hand] = HandFeedback(reason, gap, depth, lateral)
    return result
