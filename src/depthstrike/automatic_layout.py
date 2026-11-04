"""Place fixed targets from observed shoulders without a calibration sequence."""
import numpy as np

from .calibration import CalibrationProfile, GuidanceState, HANDS


def direct_target_offsets(config):
    """Shoulder-relative positions, interleaved left/right for each spatial slot."""
    # Touch play uses the requested distance directly. Historical punch rounds
    # retain their placement clearance relative to attack and guard thresholds.
    forward = (config.direct_target_forward_m if config.hit_mode == "overlap" else
               max(config.direct_target_forward_m, config.attack_extension_m,
                   config.guard_extension_m + .02))
    spacing = max(.18, 2 * config.target_radius_m + .02)
    slots = ((0., 0., 0.), (.55 * spacing, -spacing, .02),
             (.22 * spacing, spacing, 0.), (1.15 * spacing, 0., .04))
    return tuple(np.array((sign * x, config.target_height_m + y, -forward - extra))
                 for x, y, extra in slots[:config.direct_targets_per_hand]
                 for sign in (-1, 1))


def direct_target_positions(profile, config):
    offsets = direct_target_offsets(config)
    return [profile.reference_shoulders[HANDS[n % 2]] + offset
            for n, offset in enumerate(offsets)]


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
        offsets = direct_target_offsets(c)
        positions = [shoulders[HANDS[n % 2]].position + offset
                     for n, offset in enumerate(offsets)]
        forward = -offsets[0][2]
        centers = dict(zip(HANDS, positions[:2]))
        if any(not c.min_depth_m+c.target_radius_m <= p[2] <= c.max_depth_m-c.target_radius_m
               for p in positions):
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
