"""Reject isolated sensor jumps without suppressing fast observed punches."""
from dataclasses import replace

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig
from depthstrike.tracking import SkeletonTracker
from depthstrike.types import SkeletonFrame
from test_calibration import Driver


def config(**values):
    return AppConfig(reject_tracking_outliers=True, partial_tracking=True,
                     fist_offset_m=0, smoothing_tau_s=0, **values)


def test_isolated_shoulder_jump_is_invalid_and_cannot_poison_recovery(skeleton):
    tracker = SkeletonTracker(config())
    first = tracker.update(skeleton(0))
    bad = tracker.update(skeleton(.03, shift=.8))
    assert not bad.joints['left_shoulder'].is_observed
    assert bad.joints['left_shoulder'].invalid_reason == 'motion_outlier'
    recovered = tracker.update(skeleton(.06))
    assert recovered.joints['left_shoulder'].position == pytest.approx(first.joints['left_shoulder'].position)


def test_fast_observed_hand_movement_uses_raw_anchors_not_filter_lag(skeleton):
    tracker = SkeletonTracker(config(filter_mode='one_euro', one_euro_beta=.001))
    tracker.update(skeleton(0))
    assert tracker.update(skeleton(.05, left_z=1.35)).joints['left_wrist'].is_observed
    assert tracker.update(skeleton(.10, left_z=.85)).joints['left_wrist'].is_observed


def test_an_invalid_frame_does_not_remove_the_recent_outlier_anchor(skeleton):
    tracker = SkeletonTracker(config())
    tracker.update(skeleton(0))
    tracker.update(skeleton(.05, invalid='left_shoulder'))
    joint = tracker.update(skeleton(.10, shift=.8)).joints['left_shoulder']
    assert not joint.is_observed and joint.invalid_reason == 'motion_outlier'


def test_expired_anchor_does_not_permanently_lock_out_a_new_position(skeleton):
    tracker = SkeletonTracker(config())
    tracker.update(skeleton(0))
    for t in (.05, .1, .15, .2):
        tracker.update(SkeletonFrame(round(t*1000), t, {}))
    joint = tracker.update(skeleton(.25, shift=.8)).joints['left_shoulder']
    assert joint.is_observed
    assert joint.position == pytest.approx((.6, 0, 2))


def test_outlier_cannot_move_the_calibration_preview_or_create_a_hit(skeleton):
    sim = BoxingSimulation(config(preview_targets=True))
    first = sim.step(skeleton(0))
    bad = sim.step(skeleton(.03, shift=.8))
    assert len(bad.targets) == 2
    for before, after in zip(first.targets, bad.targets):
        assert after.preview and not after.active
        assert after.center == pytest.approx(before.center)
    assert bad.score == 0 and not bad.events
    expired = sim.step(SkeletonFrame(300, .3, {}))
    assert not expired.targets


def test_a_normal_fast_punch_can_still_score_with_outlier_rejection(skeleton):
    d = Driver(skeleton, config())
    d.running()
    assert d.hold(0, left_z=1.4).score == 10


def test_rejected_wrist_cannot_bridge_to_a_hit(skeleton):
    d = Driver(skeleton, config())
    d.running()
    assert d.hold(0, left_z=.35).score == 0
    assert d.state.skeleton.joints['left_wrist'].invalid_reason == 'motion_outlier'
    assert d.hold(0, left_z=1.4).score == 0
    d.hold(.1)
    assert d.hold(0, left_z=1.4).score == 10


def test_body_prediction_speed_is_bounded(skeleton):
    tracker = SkeletonTracker(config())
    tracker.update(skeleton(0))
    last = tracker.update(skeleton(.05, shift=.15))
    tracker.update(SkeletonFrame(100, .10, {}))
    shift = tracker.display_joints['left_shoulder'].position-last.joints['left_shoulder'].position
    assert np.linalg.norm(shift) <= .05*tracker.config.tracking_body_speed_m_s+1e-9


def test_outlier_rejection_can_be_disabled_for_legacy_inputs(skeleton):
    tracker = SkeletonTracker(replace(config(), reject_tracking_outliers=False))
    tracker.update(skeleton(0))
    assert tracker.update(skeleton(.03, shift=.8)).joints['left_shoulder'].is_observed


@pytest.mark.parametrize('override', [dict(reject_tracking_outliers=1),
    dict(tracking_outlier_slack_m=0), dict(tracking_body_speed_m_s=-1),
    dict(tracking_hand_speed_m_s=float('nan'))])
def test_invalid_outlier_configuration_is_rejected(override):
    with pytest.raises(ValueError):
        replace(config(), **override)
