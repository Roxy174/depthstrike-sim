"""Intermittent segmentation/depth must not erase a valid calibration hold."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from depthstrike.config import AppConfig, load_config
from depthstrike.fusion import estimate_joint
from depthstrike.pose import landmarks_from_result
from depthstrike.types import Landmark
from test_adaptive import frame
from test_calibration import Driver


@pytest.mark.parametrize('mask_value', [0., .25, float('nan')])
def test_pose_visibility_remains_independent_of_a_bad_mask_pixel(mask_value):
    mask = np.ones((21, 21), np.float32)
    mask[10, 10] = mask_value
    points = [SimpleNamespace(x=10/21, y=10/21, visibility=.95, presence=.8) for _ in range(33)]
    result = SimpleNamespace(pose_landmarks=[points],
                             segmentation_masks=[SimpleNamespace(numpy_view=lambda: mask)])
    point = landmarks_from_result(result, 21, 21)['left_shoulder']
    assert point.confidence == .8
    joint = estimate_joint(point, frame(), AppConfig(fusion_mode='masked'), mask=mask)
    assert joint.is_observed
    assert joint.position == pytest.approx((0, 0, 2))


def test_local_mask_support_cannot_accept_a_background_depth_at_the_joint():
    rgbd = frame()
    rgbd.depth_m[10, 10] = 3.
    mask = np.ones((21, 21), np.float32)
    mask[10, 10] = .1
    joint = estimate_joint(Landmark(10/21, 10/21, .9), rgbd,
                           AppConfig(fusion_mode='masked'), mask=mask)
    assert not joint.is_observed
    assert joint.invalid_reason == 'depth_discontinuity'


def test_sparse_person_mask_cannot_turn_background_into_body():
    mask = np.zeros((21, 21), np.float32)
    mask[10, 10] = 1.
    joint = estimate_joint(Landmark(10/21, 10/21, .9), frame(),
                           AppConfig(fusion_mode='masked'), mask=mask)
    assert not joint.is_observed
    assert joint.invalid_reason == 'outside_person'


@pytest.mark.parametrize('partial', [False, True])
def test_short_dropout_freezes_progress_and_resumes_only_valid_hold_time(skeleton, partial):
    config = AppConfig(partial_tracking=partial, calibration_grace_s=.2,
                       fist_offset_m=0, smoothing_tau_s=0)
    d = Driver(skeleton, config)
    progress = d.hold(.4).guidance.progress
    lost = d.hold(0, invalid='left_wrist')
    assert lost.guidance.progress == progress
    assert lost.guidance.message_code == 'reacquiring'
    assert lost.guidance.stage == 'HOLD_GUARD'
    assert d.hold(0).guidance.progress == progress
    assert d.hold(.1).guidance.stage == 'HOLD_GUARD'
    assert d.hold(0).guidance.stage == 'REACH_LEFT'


def test_repeated_dropouts_do_not_accumulate_missing_time(skeleton):
    d = Driver(skeleton, AppConfig(partial_tracking=True, calibration_grace_s=.2,
                                   fist_offset_m=0, smoothing_tau_s=0))
    progress = d.hold(.1).guidance.progress
    for _ in range(20):
        d.hold(0, invalid='left_wrist')
        state = d.hold(0)
        assert state.guidance.stage == 'HOLD_GUARD'
        assert state.guidance.progress == progress
    assert d.t > d.config.calibration_duration_s


def test_periodic_missing_frames_can_finish_a_hold_with_recovery_enabled(skeleton):
    stages = []
    for grace in (0., .2):
        d = Driver(skeleton, AppConfig(partial_tracking=True, calibration_grace_s=grace,
                                       fist_offset_m=0, smoothing_tau_s=0))
        for n in range(40):
            state = d.hold(0, invalid='left_wrist' if n % 5 == 4 else None)
            if state.guidance.stage != 'HOLD_GUARD':
                break
        stages.append(state.guidance.stage)
    assert stages == ['HOLD_GUARD', 'REACH_LEFT']


def test_reacquisition_after_grace_expiry_discards_the_old_hold(skeleton):
    d = Driver(skeleton, AppConfig(partial_tracking=True, calibration_grace_s=.12,
                                   fist_offset_m=0, smoothing_tau_s=0))
    d.hold(.4)
    assert d.hold(0, invalid='left_wrist').guidance.progress > 0
    # No expiry frame is necessary: check again when observation returns.
    d.t += .1
    assert d.hold(0).guidance.progress == 0
    assert d.hold(.2).guidance.stage == 'HOLD_GUARD'


def test_reacquisition_at_a_different_position_restarts_the_hold(skeleton):
    d = Driver(skeleton, AppConfig(partial_tracking=True, calibration_grace_s=.2,
                                   fist_offset_m=0, smoothing_tau_s=0))
    d.hold(.4)
    d.hold(0, invalid='left_wrist')
    assert d.hold(0, shift=.15).guidance.progress == 0


def test_reach_stage_resumes_after_an_active_hand_dropout(skeleton):
    d = Driver(skeleton, AppConfig(partial_tracking=True, calibration_grace_s=.2,
                                   fist_offset_m=0, smoothing_tau_s=0))
    d.hold(.7)
    before = d.hold(.2, left_z=1.4).guidance.progress
    assert 0 < before < 1
    assert d.hold(0, left_z=1.4, invalid='left_wrist').guidance.progress == before
    assert d.hold(0, left_z=1.4).guidance.progress == before
    assert d.hold(.2, left_z=1.4).guidance.stage == 'RETURN_LEFT'


def test_dropout_still_restarts_countdown_and_cannot_bridge_a_punch(skeleton):
    d = Driver(skeleton, AppConfig(partial_tracking=True, calibration_grace_s=.2,
                                   fist_offset_m=0, smoothing_tau_s=0))
    d.calibrate()
    d.practice()
    d.hold(1.)
    d.hold(0, invalid='left_wrist')
    assert d.hold(1.2).guidance.stage == 'COUNTDOWN'
    assert d.hold(1.).guidance.stage == 'RUNNING'
    d.hold(0, invalid='left_wrist')
    assert d.hold(0, left_z=1.4).score == 0
    d.hold(.1)
    assert d.hold(0, left_z=1.4).score == 10


def test_other_valid_joints_keep_their_filter_after_one_arm_is_lost(skeleton):
    d = Driver(skeleton, AppConfig(fist_offset_m=0, smoothing_tau_s=.1))
    d.hold(.2)
    state = d.hold(0, right_z=1.7, invalid='left_wrist')
    z = state.skeleton.joints['right_wrist'].position[2]
    # Resetting the entire tracker would make the next point jump to raw 1.7.
    next_z = d.hold(0, right_z=1.7, invalid='left_wrist').skeleton.joints['right_wrist'].position[2]
    assert 1.7 < next_z < z < 1.85


def test_adaptive_config_enables_bounded_recovery_without_lowering_confidence():
    config = load_config('configs/adaptive.json')
    assert config.calibration_grace_s == .2
    assert config.confidence_threshold == AppConfig().confidence_threshold
    assert config.prediction_horizon_s == .2
    assert AppConfig().calibration_grace_s == 0
    for invalid in (-.01, float('inf'), True):
        with pytest.raises(ValueError):
            replace(config, calibration_grace_s=invalid)


def test_recovery_page_explains_preserved_progress_in_chinese(skeleton, monkeypatch):
    pytest.importorskip('cv2')
    from depthstrike import visualization
    d = Driver(skeleton, AppConfig(partial_tracking=True, calibration_grace_s=.2,
                                   fist_offset_m=0, smoothing_tau_s=0))
    d.hold(.3)
    state = d.hold(0, invalid='left_wrist')
    messages = []
    monkeypatch.setattr(visualization, 'draw_text',
                        lambda image, value, *args, **kwargs: messages.append(str(value)))
    visualization.render_hud(state, None, d.config)
    assert '追踪恢复中' in messages
    assert any('校准进度已保留' in message for message in messages)
