from dataclasses import replace

import pytest

from depthstrike.config import AppConfig
from depthstrike.types import Joint3D


def test_fist_extends_forearm_by_six_cm():
    from depthstrike.interaction import estimate_fist
    result = estimate_fist(Joint3D((0, 0, 2), .9), Joint3D((0, 0, 1.8), .8), AppConfig())
    assert result.position == pytest.approx((0, 0, 1.74))
    assert result.confidence == .8


@pytest.mark.parametrize("elbow,wrist", [
    (None, Joint3D((0, 0, 1.8), .9)),
    (Joint3D((0, 0, 2), .2), Joint3D((0, 0, 1.8), .9)),
    (Joint3D((0, 0, 2), .9), Joint3D((0, 0, 1.981), .9)),
    (Joint3D((0, 0, 2), .9), Joint3D(None)),
])
def test_missing_elbow_and_degenerate_forearm_are_invalid(elbow, wrist):
    from depthstrike.interaction import estimate_fist
    result = estimate_fist(elbow, wrist, AppConfig())
    assert result.position is None and result.invalid_reason


def test_zero_offset_keeps_wrist_but_still_requires_valid_forearm():
    from depthstrike.interaction import estimate_fist
    result = estimate_fist(Joint3D((0, 0, 2), 1), Joint3D((0, 0, 1.8), 1),
                           replace(AppConfig(), fist_offset_m=0))
    assert result.position == pytest.approx((0, 0, 1.8))


def test_invalid_reason_cannot_be_attached_to_a_valid_point():
    with pytest.raises(ValueError):
        Joint3D((0, 0, 2), 1, invalid_reason="invalid_depth")
