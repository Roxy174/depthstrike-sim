"""A camera depth plane stays independent of the player's initial distance."""
from dataclasses import replace

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig, load_config


def config(**values):
    return replace(load_config(), direct_target_reference='camera',
                   smoothing_tau_s=0., **values)


def translate(frame, offset):
    return replace(frame, joints={name: replace(joint, position=joint.position + offset)
                                 if joint.position is not None else joint
                                 for name, joint in frame.joints.items()})


@pytest.mark.parametrize('person_depth', [1.2, 1.8, 2., 3.])
@pytest.mark.parametrize('count', [1, 3, 4])
def test_all_balls_share_camera_depth_for_different_initial_person_distances(person_depth, count, skeleton):
    sim = BoxingSimulation(config(direct_targets_per_hand=count))
    frame = translate(skeleton(0.), (0, 0, person_depth - 2.))
    state = sim.step(frame)
    assert len(state.targets) == 2 * count and state.status == 'RUNNING'
    assert [target.center[2] for target in state.targets] == [1.5] * (2 * count)
    assert state.targets[0].center[:2] == pytest.approx((-.2, .04))
    assert state.targets[1].center[:2] == pytest.approx((.2, .04))
    for hand, target in zip(('left', 'right'), state.targets):
        np.testing.assert_array_equal(sim.calibration.profile.target_centers[hand], target.center)
        assert sim.calibration.profile.comfortable_extensions[hand] > 0


def test_different_left_right_shoulder_depths_do_not_tilt_the_ball_plane(skeleton):
    frame = skeleton(0.)
    for hand, offset in (('left', -.2), ('right', .3)):
        joint = frame.joints[f'{hand}_shoulder']
        frame.joints[f'{hand}_shoulder'] = replace(joint, position=joint.position + (0, 0, offset))
    assert all(target.center[2] == 1.5 for target in BoxingSimulation(config()).step(frame).targets)


def test_reset_updates_lateral_placement_but_keeps_camera_depth(skeleton):
    sim = BoxingSimulation(config())
    initial = sim.step(skeleton(0.))
    moved = translate(skeleton(.1, shift=.4), (0, .1, .8))
    state = sim.step(moved)
    for old, current in zip(initial.targets, state.targets):
        np.testing.assert_array_equal(current.center, old.center)
    sim.reset()
    state = sim.step(replace(moved, timestamp_s=.2, frame_id=200))
    for old, current in zip(initial.targets, state.targets):
        assert current.center[:2] == pytest.approx(old.center[:2] + (.4, .1))
        assert current.center[2] == 1.5


def test_camera_depth_ignores_shoulder_forward_distance_and_punch_thresholds(skeleton):
    sim = BoxingSimulation(config(camera_target_depth_m=1.3, direct_target_forward_m=.9,
                                  guard_extension_m=.8, attack_extension_m=.9))
    assert all(target.center[2] == 1.3 for target in sim.step(skeleton(0.)).targets)


def test_fixed_camera_ball_can_be_hit_by_observed_overlap(skeleton):
    sim = BoxingSimulation(config())
    sim.step(skeleton(0.))
    state = sim.step(skeleton(.1, left_z=1.5))
    assert state.hits == 1 and state.events[0].target_id == 0
    assert state.targets[1].active and state.targets[0].flash


def test_camera_mode_still_waits_for_shoulders_to_place_lateral_positions(skeleton):
    sim = BoxingSimulation(config())
    assert not sim.step(skeleton(0., invalid='left_shoulder')).targets
    state = sim.step(skeleton(.1))
    assert len(state.targets) == 6 and state.targets[0].center[2] == 1.5


@pytest.mark.parametrize('values', [{'direct_target_reference': 'unknown'},
    {'camera_target_depth_m': 0}, {'camera_target_depth_m': -.1},
    {'camera_target_depth_m': float('nan')}, {'camera_target_depth_m': True},
    {'camera_target_depth_m': .3}, {'camera_target_depth_m': 5.}])
def test_invalid_camera_target_configuration_is_rejected(values):
    cfg = dict(direct_target_reference='camera') | values
    with pytest.raises(ValueError): replace(load_config(), **cfg)


def test_shoulder_default_remains_compatible_and_camera_config_is_explicit(skeleton):
    assert AppConfig().direct_target_reference == 'shoulder'
    assert load_config().direct_target_reference == 'shoulder'
    adaptive = load_config('configs/adaptive.json')
    assert adaptive.direct_target_reference == 'camera' and adaptive.camera_target_depth_m == 1.5
    state = BoxingSimulation(adaptive).step(skeleton(0.))
    assert all(target.center[2] == 1.5 for target in state.targets)
    shoulder = replace(config(), direct_target_reference='shoulder', direct_target_forward_m=.3)
    assert BoxingSimulation(shoulder).step(skeleton(0.)).targets[0].center[2] == pytest.approx(1.7)


def test_camera_target_recording_roundtrips_and_demo_can_reach_all_slots(tmp_path):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    from depthstrike.sources import DemoPoseSource
    cfg = config()
    sim = BoxingSimulation(cfg)
    path = tmp_path / 'camera-depth.jsonl'
    original = []
    with DemoPoseSource(config=cfg, total_frames=300) as source, PoseRecorder(path, cfg) as recorder:
        while (frame := source.read()) is not None:
            state = sim.step(frame)
            original.extend(state.events)
            recorder.write(frame, state.events)
    assert {event.target_id for event in original} == set(range(6))
    replayed = []
    with PoseReplaySource(path) as source:
        assert source.config.camera_target_depth_m == 1.5
        replay = BoxingSimulation(source.config)
        while (frame := source.read()) is not None:
            state = replay.step(frame)
            replayed.extend(state.events)
            assert all(target.center[2] == 1.5 for target in state.targets)
    assert replayed == original
