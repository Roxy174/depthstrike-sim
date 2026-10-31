"""Place fixed targets from observed shoulders without a calibration sequence."""
import numpy as np

from .calibration import CalibrationProfile, GuidanceState, HANDS


class AutomaticLayout:
    """A preset reference for play, not a measurement of the player's reach."""

    stage = "RUNNING"
    workspace = None

    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.profile = None
        self.state = GuidanceState(self.stage, 0., "waiting_player")

    def invalidate(self):
        # A temporary tracking interruption must not move the targets.
        pass

    def update(self, frame, fists, *, capture=False):
        if self.profile is not None:
            return self.state
        c = self.config
        shoulders = {h: frame.joints.get(f"{h}_shoulder") for h in HANDS}
        if any(j is None or not j.is_observed or j.confidence < c.confidence_threshold
               for j in shoulders.values()):
            self.state = GuidanceState(self.stage, 0., "waiting_player")
            return self.state
        # Keep the targets clear of the configured guard position.
        forward = max(c.direct_target_forward_m,
                      c.guard_extension_m+c.hand_radius_m+c.target_radius_m+.02)
        centers = {h: j.position+np.array((0, c.target_height_m, -forward))
                   for h, j in shoulders.items()}
        if any(not c.min_depth_m+c.target_radius_m <= p[2] <= c.max_depth_m-c.target_radius_m
               for p in centers.values()):
            self.state = GuidanceState(self.stage, 0., "adjust_distance")
            return self.state
        self.profile = CalibrationProfile(
            reference_shoulders={h: j.position.copy() for h, j in shoulders.items()},
            neutral_extensions={h: max(0., c.guard_extension_m-.04) for h in HANDS},
            comfortable_extensions={h: forward+c.hand_radius_m+c.target_radius_m for h in HANDS},
            guard_thresholds={h: c.guard_extension_m for h in HANDS},
            attack_thresholds={h: c.attack_extension_m for h in HANDS},
            travel_thresholds={h: c.punch_min_travel_m for h in HANDS},
            target_centers=centers)
        self.state = GuidanceState(self.stage, 1., "running", self.profile)
        return self.state
