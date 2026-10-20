from dataclasses import replace

import numpy as np
import pytest

from depthstrike.config import AppConfig
from depthstrike.types import Intrinsics, Landmark, RGBDFrame


def rgbd(depth=2.):
    return RGBDFrame(0, 0., np.zeros((480, 640, 3), np.uint8),
                     np.full((480, 640), depth, np.float32),
                     Intrinsics(640, 480, 600, 600, 320, 240))


@pytest.mark.parametrize("u,v,z,want", [
    (.5, .5, 2., (0, 0, 2)),
    (380/640, .5, 2., (.2, 0, 2)),
    (380/640, .5, 1., (.1, 0, 1)),
])
def test_metric_deprojection(u, v, z, want):
    from depthstrike.fusion import estimate_joint
    joint = estimate_joint(Landmark(u, v, .9), rgbd(z), AppConfig())
    assert joint.position == pytest.approx(want)


@pytest.mark.parametrize("u,v,confidence,depth", [
    (.5, .5, .2, 2.), (-.1, .5, .9, 2.), (1, .5, .9, 2.),
    (.5, .5, .9, 0), (.5, .5, .9, np.inf), (.5, .5, .9, np.nan),
])
def test_invalid_joint_does_not_use_background_or_previous_depth(u, v, confidence, depth):
    from depthstrike.fusion import estimate_joint
    assert estimate_joint(Landmark(u, v, confidence), rgbd(depth), AppConfig()).position is None


def test_depth_discontinuity_invalidates_joint():
    from depthstrike.fusion import estimate_joint
    frame = rgbd()
    frame.depth_m[238:243, 318:321] = 1.
    assert estimate_joint(Landmark(.5, .5, .9), frame, AppConfig()).position is None


def test_edge_window_clipped_safely():
    from depthstrike.fusion import estimate_joint
    assert estimate_joint(Landmark(0, 0, 1), rgbd(), AppConfig()).position[2] == 2


def test_frame_dimension_mismatch_rejected():
    with pytest.raises(ValueError, match="dimensions"):
        replace(rgbd(), depth_m=np.zeros((10, 10), np.float32))


def test_unknown_distortion_is_not_assumed_pinhole():
    from depthstrike.fusion import estimate_joint
    frame = rgbd()
    frame = replace(frame, intrinsics=replace(frame.intrinsics, distortion_model="fisheye"))
    with pytest.raises(ValueError, match="distortion"):
        estimate_joint(Landmark(.5, .5, 1), frame, AppConfig())


def test_live_calibrated_transform_used():
    from depthstrike.fusion import fuse_skeleton
    frame = replace(rgbd(), deproject=lambda u, v, z: np.array([.1, .2, z]))
    skeleton = fuse_skeleton(frame, {"left_wrist": Landmark(.5, .5, .9)}, AppConfig())
    assert skeleton.joints["left_wrist"].position == pytest.approx((.1, .2, 2))
