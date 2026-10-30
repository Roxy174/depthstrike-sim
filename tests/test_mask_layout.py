"""Regression: native single-channel masks may retain a trailing channel axis."""
from types import SimpleNamespace
import warnings

import numpy as np
import pytest

from depthstrike.config import AppConfig
from depthstrike.fusion import estimate_joint
from depthstrike.pose import landmarks_from_result
from depthstrike.sources import CameraPoseSource
from depthstrike.types import Intrinsics, Landmark, RGBDFrame


def rgbd():
    return RGBDFrame(0, 0., np.zeros((6, 8, 3), np.uint8),
                     np.full((6, 8), 2., np.float32), Intrinsics(8, 6, 10, 10, 4, 3))


@pytest.mark.parametrize("shape", [(6, 8), (6, 8, 1)])
def test_native_mask_layout_preserves_valid_shoulder_in_camera_pipeline(shape):
    frame = rgbd()
    capture = SimpleNamespace(read=lambda: frame, close=lambda: None)
    estimator = SimpleNamespace(last_mask=np.ones(shape, np.float32),
        detect=lambda f: {"left_shoulder": Landmark(.5, .5, .9)}, close=lambda: None)
    with CameraPoseSource(AppConfig(fusion_mode="masked"), capture=capture, estimator=estimator) as source:
        joint = source.read().joints["left_shoulder"]
    assert joint.position == pytest.approx((0, 0, 2))


def test_single_channel_native_mask_confidence_is_scalar_without_deprecation():
    mask = np.ones((6, 8, 1), np.float32)
    mask[3, 4, 0] = .25
    result = SimpleNamespace(
        pose_landmarks=[[SimpleNamespace(x=.5, y=.5, visibility=.9, presence=.8) for _ in range(33)]],
        segmentation_masks=[SimpleNamespace(numpy_view=lambda: mask)])
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        landmarks = landmarks_from_result(result, 8, 6)
    assert landmarks["left_shoulder"].confidence == .25


@pytest.mark.parametrize("shape", [(6, 8, 3), (8, 6, 1), (1, 6, 8)])
def test_non_person_mask_layouts_still_rejected(shape):
    joint = estimate_joint(Landmark(.5, .5, .9), rgbd(), AppConfig(fusion_mode="masked"),
                           mask=np.ones(shape, np.float32))
    assert joint.position is None and joint.invalid_reason == "missing_mask"
