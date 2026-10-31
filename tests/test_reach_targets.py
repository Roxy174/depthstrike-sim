"""Measure comfortable reach before presenting targets on the measured path."""
from dataclasses import replace

import numpy as np
import pytest

from depthstrike.config import AppConfig, load_config
from depthstrike.types import Joint3D
from test_calibration import Driver


def measured_config(**values):
    return AppConfig(target_layout='measured_path', target_reach_ratio=.8,
                     target_height_m=0, fist_offset_m=0, smoothing_tau_s=0, **values)


def test_reach_measurement_never_requires_or_displays_an_unmeasured_ball(skeleton):
    d = Driver(skeleton, AppConfig(preview_targets=True, fist_offset_m=0, smoothing_tau_s=0))
    for duration, pose, stage in ((.7, {}, 'REACH_LEFT'),
            (.5, {'left_z': 1.4}, 'RETURN_LEFT'), (.3, {}, 'REACH_RIGHT'),
            (.5, {'right_z': 1.4}, 'RETURN_RIGHT')):
        state = d.hold(duration, **pose)
        assert state.guidance.stage == stage
        assert not state.targets
        assert state.score == 0
    state = d.hold(.3)
    assert state.guidance.stage == 'PRACTICE_LEFT'
    assert len(state.targets) == 2 and state.targets[0].active


def test_measured_targets_follow_each_hands_observed_path(skeleton):
    def natural_reach(t, **pose):
        frame = skeleton(t, **pose)
        for hand, inward in (('left', .18), ('right', -.18)):
            name = f'{hand}_wrist'
            joint = frame.joints[name]
            if joint.position is not None and joint.position[2] < 1.7:
                frame.joints[name] = Joint3D(joint.position+(inward, -.12, 0), joint.confidence)
        return frame
    d = Driver(natural_reach, measured_config())
    state = d.calibrate(left_z=1.6, right_z=1.6)
    assert state.guidance.stage == 'PRACTICE_LEFT'
    for target, hand, inward in zip(state.targets, ('left', 'right'), (.18, -.18)):
        neutral = skeleton(0).joints[f'{hand}_wrist'].position
        comfortable = natural_reach(0, **{f'{hand}_z': 1.6}).joints[f'{hand}_wrist'].position
        assert target.center == pytest.approx(neutral+.8*(comfortable-neutral))
        assert np.linalg.norm(target.center-neutral) > d.config.hand_radius_m+d.config.target_radius_m+.02


def test_short_reach_can_complete_practice_without_extending_past_calibration(skeleton):
    d = Driver(skeleton, measured_config())
    state = d.calibrate(left_z=1.68, right_z=1.68)
    assert state.guidance.stage == 'PRACTICE_LEFT'
    for target in state.targets:
        assert 1.68 <= target.center[2] < 1.69
    d.hold(.1)
    assert d.hold(0, left_z=1.68).guidance.stage == 'PRACTICE_RIGHT'
    d.hold(.15)
    assert d.hold(0, right_z=1.68).guidance.stage == 'COUNTDOWN'
    assert d.hold(2.3).guidance.stage == 'RUNNING'
    assert d.hold(0, left_z=1.68).score == 10


def test_insufficient_range_still_cannot_place_a_ball_inside_neutral_fist(skeleton):
    state = Driver(skeleton, measured_config()).calibrate(left_z=1.71, right_z=1.71)
    assert state.guidance.stage == 'REACH_LEFT'
    assert state.guidance.message_code == 'reach_too_small'
    assert not state.targets


def test_short_reach_practice_also_works_with_the_actual_adaptive_filter(skeleton):
    config = replace(load_config('configs/adaptive.json'), interaction_mode='guided', fist_offset_m=0)
    d = Driver(skeleton, config)
    d.hold(1.)
    d.hold(1., left_z=1.68)
    d.hold(1.)
    d.hold(1., right_z=1.68)
    assert d.hold(1.).guidance.stage == 'PRACTICE_LEFT'
    assert d.hold(.2, left_z=1.68).guidance.stage == 'PRACTICE_RIGHT'
    d.hold(.5)
    assert d.hold(.2, right_z=1.68).guidance.stage == 'COUNTDOWN'
    assert d.hold(2.5).guidance.stage == 'RUNNING'


def test_optional_vertical_offset_must_still_intersect_observed_reach(skeleton):
    config = replace(measured_config(), target_height_m=1.)
    state = Driver(skeleton, config).calibrate()
    assert state.guidance.message_code == 'target_unreachable'
    assert not state.targets


def test_adaptive_uses_measured_path_while_old_configs_keep_their_layout():
    config = load_config('configs/adaptive.json')
    assert config.target_layout == 'measured_path'
    assert config.target_height_m == 0
    assert config.target_reach_ratio == .8
    assert AppConfig().target_layout == 'shoulder'
    with pytest.raises(ValueError):
        AppConfig(target_layout='unknown')


def test_reach_screen_explicitly_guides_measurement_instead_of_ball_contact(skeleton, monkeypatch):
    pytest.importorskip('cv2')
    from depthstrike import visualization
    d = Driver(skeleton)
    state = d.hold(.7)
    messages = []
    monkeypatch.setattr(visualization, 'draw_text', lambda image, value, *args, **kwargs: messages.append(str(value)))
    visualization.render_hud(state, None, d.config)
    assert '无需触碰目标' in messages
    assert any('左手' in message and '保持' in message for message in messages)
