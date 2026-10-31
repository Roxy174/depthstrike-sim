"""Real reach can include shoulder protraction without body translation."""
from dataclasses import replace

import numpy as np
import pytest

from depthstrike.config import AppConfig, load_config
from depthstrike.interaction import estimate_hand
from depthstrike.types import Joint3D
from test_calibration import Driver


def config():
    return replace(load_config('configs/adaptive.json'), interaction_mode='guided', filter_mode='exponential',
                   smoothing_tau_s=0, fist_offset_m=0)


def natural_pose(skeleton):
    def make(t, **pose):
        frame = skeleton(t, **pose)
        for hand, inward in (('left', .18), ('right', -.18)):
            wrist = frame.joints[hand+'_wrist']
            if wrist.is_observed and wrist.position[2] < 1.8:
                frame.joints[hand+'_wrist'] = replace(wrist, position=wrist.position+(inward, 0, 0))
                shoulder = frame.joints[hand+'_shoulder']
                frame.joints[hand+'_shoulder'] = replace(shoulder, position=shoulder.position+(0, 0, -.05))
        return frame
    return make


def test_shoulder_protraction_does_not_cancel_measured_forward_reach(skeleton):
    d = Driver(natural_pose(skeleton), config())
    d.hold(.7)
    state = d.hold(.5, left_z=1.72)
    assert state.guidance.stage == 'RETURN_LEFT'


def test_measured_target_and_practice_use_the_same_protracted_pose(skeleton):
    d = Driver(natural_pose(skeleton), config())
    state = d.calibrate(left_z=1.72, right_z=1.72)
    assert state.guidance.stage == 'PRACTICE_LEFT'
    assert state.targets[0].center == pytest.approx((-.056, .04, 1.746))
    assert state.guidance.profile.comfortable_extensions['left'] == pytest.approx(.23)
    d.hold(.1)
    assert d.hold(0, left_z=1.72).guidance.stage == 'PRACTICE_RIGHT'
    d.hold(.15)
    assert d.hold(0, right_z=1.72).guidance.stage == 'COUNTDOWN'


def test_whole_body_translation_is_not_measured_as_arm_reach(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    def translated(t, **pose):
        frame = skeleton(t, **pose)
        return replace(frame, joints={k: replace(j, position=j.position+(0, 0, -.04)) for k, j in frame.joints.items()})
    d.make = translated
    state = d.hold(.5)
    assert state.guidance.stage == 'REACH_LEFT'
    assert state.guidance.progress == 0
    assert state.guidance.measurements['forward_m'] == pytest.approx(0, abs=1e-8)


def test_extending_the_other_hand_has_an_explicit_instruction(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    state = d.hold(.5, right_z=1.4)
    assert state.guidance.stage == 'REACH_LEFT'
    assert state.guidance.message_code == 'wrong_hand'
    assert state.guidance.progress == 0


def test_forward_and_hold_conditions_are_exposed_as_snapshot_values(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    state = d.hold(.1, left_z=1.65)
    measurements = dict(state.guidance.measurements)
    assert measurements['forward_m'] == pytest.approx(.2)
    assert measurements['required_forward_m'] == .1
    assert measurements['hold_s'] == pytest.approx(.1)
    assert measurements['required_hold_s'] == .35
    d.hold(.1, left_z=1.65)
    assert state.guidance.measurements == measurements


def test_a_lost_wrist_is_identified_without_faking_reach(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    state = d.hold(0, invalid='left_wrist')
    assert state.guidance.measurements['blocked_joint'] == 'left_wrist'
    assert state.guidance.measurements['forward_m'] is None
    assert state.guidance.progress == 0


def test_wrist_mode_does_not_require_a_visible_forearm_during_reach(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    assert d.hold(.5, left_z=1.4, invalid='left_elbow').guidance.stage == 'RETURN_LEFT'


@pytest.mark.parametrize('joint', [Joint3D(None), Joint3D((0, 0, 2), .2),
                                 Joint3D((0, 0, 2), .99, provenance='predicted')])
def test_wrist_mode_still_rejects_missing_uncertain_or_predicted_input(joint):
    result = estimate_hand({'left_wrist':joint}, 'left', AppConfig(fist_mode='wrist'))
    assert not result.is_observed


def test_forward_screen_shows_measured_centimeters_and_hold_time(skeleton, monkeypatch):
    pytest.importorskip('cv2')
    from depthstrike import visualization
    d = Driver(skeleton, config())
    d.hold(.7)
    state = d.hold(.1, left_z=1.65)
    messages = []
    monkeypatch.setattr(visualization, 'draw_text', lambda image, value, *a, **kw: messages.append(str(value)))
    visualization.render_hud(state, None, d.config)
    assert any('前伸' in message and '20.0' in message and '10.0' in message for message in messages)
    assert any('保持' in message and '0.10' in message and '0.35' in message for message in messages)
