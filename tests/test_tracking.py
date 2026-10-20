from dataclasses import replace

import pytest

from depthstrike.config import AppConfig


def test_smoothing_uses_actual_elapsed_time(skeleton):
    from depthstrike.tracking import SkeletonTracker
    tracker = SkeletonTracker(replace(AppConfig(), smoothing_tau_s=.1))
    tracker.update(skeleton(0))
    frame = tracker.update(skeleton(.1, left_z=1.65))
    assert frame.joints["left_wrist"].position[2] == pytest.approx(1.85-.2*(1-__import__('math').exp(-1)))


def test_smoothing_can_be_disabled(skeleton):
    from depthstrike.tracking import SkeletonTracker
    tracker = SkeletonTracker(replace(AppConfig(), smoothing_tau_s=0))
    tracker.update(skeleton(0))
    assert tracker.update(skeleton(.1, left_z=1.5)).joints["left_wrist"].position[2] == 1.5


def test_invalid_joint_is_not_held_or_bridged(skeleton):
    from depthstrike.tracking import SkeletonTracker
    tracker = SkeletonTracker(AppConfig())
    tracker.update(skeleton(0))
    assert tracker.update(skeleton(.1, invalid="left_wrist")).joints["left_wrist"].position is None
    assert tracker.update(skeleton(.15, left_z=1.5)).joints["left_wrist"].position[2] == 1.5


def test_nonmonotonic_time_invalidates_frame(skeleton):
    from depthstrike.tracking import SkeletonTracker
    tracker = SkeletonTracker(AppConfig())
    tracker.update(skeleton(.1))
    assert tracker.update(skeleton(.1)).joints["left_wrist"].position is None
