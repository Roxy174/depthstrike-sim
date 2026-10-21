import pytest

from depthstrike.config import AppConfig
from depthstrike.types import Joint3D, Target


def feedback(position, *, status="RUNNING", phase="ATTACKING", diagnostic="attacking"):
    from depthstrike.feedback import build_feedback
    point = Joint3D(position, .9) if position is not None else Joint3D(None, invalid_reason="invalid_depth")
    target = Target(0, "left", (-.2, .04, 1.5), .08, True)
    return build_feedback({"left": point}, (target,), {"left": phase}, status,
                          AppConfig(), {"left": diagnostic})["left"]


def test_depth_mismatch_is_explained_without_hit():
    result = feedback((-.2, .04, 1.8))
    assert result.reason == "depth_gap"
    assert result.surface_gap_m == pytest.approx(.16)
    assert result.depth_delta_m == pytest.approx(.3)
    assert result.lateral_m == pytest.approx(0)


def test_invalid_hand_clears_all_distance_fields():
    result = feedback(None)
    assert result.reason == "invalid_depth"
    assert (result.surface_gap_m, result.depth_delta_m, result.lateral_m) == (None, None, None)


def test_tracking_loss_precedes_speed_hint():
    result = feedback((-.2, .04, 1.8), status="TRACKING LOST", diagnostic="low_speed")
    assert result.reason == "invalid_tracking"
    assert result.surface_gap_m is None


@pytest.mark.parametrize("status,phase,diagnostic,want", [
    ("PAUSED", "READY", "low_speed", "paused"),
    ("FINISHED", "READY", "low_speed", "finished"),
    ("CALIBRATING", "READY", "low_speed", "calibrating"),
    ("RUNNING", "RECOVERING", "return_guard", "return_guard"),
    ("RUNNING", "READY", "low_speed", "low_speed"),
])
def test_feedback_obeys_condition_priority(status, phase, diagnostic, want):
    assert feedback((-.2, .04, 1.8), status=status, phase=phase, diagnostic=diagnostic).reason == want


def test_lateral_miss_is_not_reported_as_depth_gap():
    result = feedback((.2, .04, 1.5))
    assert result.reason == "off_axis" and result.lateral_m == pytest.approx(.4)
