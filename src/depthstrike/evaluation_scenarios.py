"""Small analytic action cases. Labels are hand-derived, not detector outputs."""
from .config import AppConfig
from .recording import COORDINATES
from .types import Joint3D, SkeletonFrame


def _frame(t, *, left=(-.45, .04, 1.85), right=(.45, .04, 1.85), invalid=None):
    positions = {"left_shoulder": (-.2, 0, 2.), "right_shoulder": (.2, 0, 2.),
                 "left_elbow": (-.25, .2, 1.95), "right_elbow": (.25, .2, 1.95),
                 "left_wrist": left, "right_wrist": right}
    joints = {n: Joint3D(p, .99) for n, p in positions.items()}
    if invalid: joints[invalid] = Joint3D(None, invalid_reason="invalid_depth")
    return SkeletonFrame(round(t*10000), t, joints)


def _labels(windows=(), *, two_targets=False, schedule=None):
    targets = [{"target_id": 0, "hand": "left", "center": [-.2, .04, 1.5], "radius": .08}]
    if two_targets: targets.append({"target_id": 1, "hand": "right", "center": [.2, .04, 1.5], "radius": .08})
    return {"schema_version": 1, "evidence": "synthetic", "unit": "m", "timestamp_unit": "s",
            "coordinates": COORDINATES,
            "label_basis": "Analytic positions in evaluation_scenarios.py; proxy radii sum to 0.14 m. Independent effective forward attacks only.",
            "intrinsics": {"width": 640, "height": 480, "fx": 600., "fy": 600., "cx": 320., "cy": 240.},
            "targets": targets, "active_schedule": schedule or [{"start_s": 0., "end_s": 2., "hand": "left", "target_id": 0}],
            "expected_windows": list(windows), "ignore_windows": []}


def _window(start, end, hand="left", target_id=0):
    return {"start_s": start, "end_s": end, "hand": hand, "target_id": target_id}


def build_scenarios():
    config = AppConfig(fist_offset_m=0, smoothing_tau_s=0)
    # At z=1.85 the left hand remains 0.35 m behind the target: no 3D contact,
    # although lateral motion enters its projected image disk.
    depth = [_frame(0), _frame(.1, left=(-.2, .04, 1.85))]
    # z=1.85 -> 1.15 crosses z=1.5. Entry at z=1.64 occurs 0.03 s after t=0;
    # both endpoints remain outside the combined 0.14 m radius.
    fast = [_frame(0, left=(-.2, .04, 1.85)), _frame(.1, left=(-.2, .04, 1.15))]
    # 0.05 m per 0.1 s is 0.5 m/s, below the configured 0.65 m/s attack speed.
    slow = [_frame(n*.1, left=(-.2, .04, 1.85-.05*n)) for n in range(11)]
    # After the first attack, withdrawal to z=1.68 stays extended (0.32 m),
    # so a second contact is not a new attack without returning to guard.
    reentry = [_frame(0), _frame(.1, left=(-.2, .04, 1.5)),
               _frame(.15, left=(-.2, .04, 1.5)), _frame(.2, left=(-.2, .04, 1.68)),
               _frame(.25, left=(-.2, .04, 1.5))]
    stationary = [_frame(0)] + [_frame(t, left=(-.2, .04, 1.5)) for t in (.1, .15, .2, .25)]
    tracking = [_frame(0), _frame(.1, invalid="left_elbow"), _frame(.15, left=(-.2, .04, 1.5)),
                _frame(.25), _frame(.35, left=(-.2, .04, 1.5))]
    normal = [_frame(0), _frame(.1, left=(-.2, .04, 1.5)), _frame(.2), _frame(.3, right=(.2, .04, 1.5))]
    schedule = [{"start_s": 0., "end_s": .2, "hand": "left", "target_id": 0},
                {"start_s": .2, "end_s": 1., "hand": "right", "target_id": 1}]
    return [
        ("depth_mismatch", depth, _labels(), config),
        ("fast_crossing", fast, _labels([_window(.025, .045)]), config),
        ("slow_extension", slow, _labels(), config),
        ("contact_reentry", reentry, _labels([_window(.04, .28)]), config),
        ("stationary_contact", stationary, _labels([_window(.04, .28)]), config),
        ("tracking_recovery", tracking, _labels([_window(.30, .38)]), config),
        ("normal_left_right", normal, _labels([_window(.04, .12), _window(.24, .32, "right", 1)],
                                               two_targets=True, schedule=schedule), config),
    ]
