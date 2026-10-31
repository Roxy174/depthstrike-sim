"""Direct play has no posture holds, practice hits or calibration countdown."""
from dataclasses import replace
import json

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import load_config
from depthstrike.types import Joint3D, SkeletonFrame


def config(**values):
    return replace(load_config(), smoothing_tau_s=0, **values)


def test_runtime_defaults_and_shipped_configs_skip_calibration(tmp_path):
    path = tmp_path/'custom.json'
    path.write_text(json.dumps({'round_duration_s': 10}))
    for cfg in (load_config(), load_config(path), load_config('configs/default.json'),
                load_config('configs/adaptive.json')):
        assert cfg.interaction_mode == 'direct'
        assert cfg.fist_mode == 'wrist' and cfg.partial_tracking


def test_first_observed_shoulders_place_targets_without_any_hold_or_elbows(skeleton):
    sim = BoxingSimulation(config(calibration_duration_s=100, reach_hold_s=100, countdown_s=100))
    frame = skeleton(0, invalid='left_elbow')
    state = sim.step(frame)
    assert state.status == 'RUNNING' and state.guidance is None
    assert state.remaining_s == 60 and state.score == 0
    assert len(state.targets) == 2
    assert state.targets[0].center == pytest.approx((-.2, .04, 1.62))


@pytest.mark.parametrize('kind', ['missing', 'low_confidence', 'predicted'])
def test_unobserved_shoulders_never_place_targets_or_start_timer(skeleton, kind):
    sim = BoxingSimulation(config())
    for t in (0, .1, .2):
        frame = skeleton(t)
        shoulder = frame.joints['right_shoulder']
        frame.joints['right_shoulder'] = (Joint3D(None) if kind == 'missing' else
            replace(shoulder, confidence=.1) if kind == 'low_confidence' else
            replace(shoulder, provenance='predicted'))
        state = sim.step(frame)
        assert state.status == 'WAITING FOR PLAYER'
        assert not state.targets and state.guidance is None
        assert state.remaining_s == 60 and not state.events
    assert sim.step(skeleton(.3)).status == 'RUNNING'


def test_starting_with_extended_hands_does_not_require_calibration_or_award_a_hit(skeleton):
    sim = BoxingSimulation(config())
    for t in (0, .1, .2):
        state = sim.step(skeleton(t, left_z=1.62, right_z=1.62))
        assert state.status == 'RUNNING' and state.guidance is None
        assert state.score == 0 and not state.events
    sim.step(skeleton(.3))
    assert sim.step(skeleton(.4, left_z=1.62)).score == 10


def test_alternating_punches_score_immediately_and_targets_stay_fixed(skeleton):
    sim = BoxingSimulation(config())
    initial = sim.step(skeleton(0))
    left = sim.step(skeleton(.1, left_z=1.62))
    assert left.score == 10 and left.events[0].hand == 'left'
    assert left.targets[1].active
    sim.step(skeleton(.2))
    right = sim.step(skeleton(.3, right_z=1.62))
    assert right.score == 20 and right.events[0].hand == 'right'
    assert right.targets[0].active
    moved = sim.step(skeleton(.4, shift=.1))
    for a, b in zip(initial.targets, moved.targets):
        np.testing.assert_array_equal(a.center, b.center)


def test_inactive_arm_loss_does_not_block_the_active_hand(skeleton):
    sim = BoxingSimulation(config())
    sim.step(skeleton(0))
    state = sim.step(skeleton(.1, left_z=1.62, invalid='right_wrist'))
    assert state.score == 10 and state.events[0].hand == 'left'
    assert sim.step(skeleton(.2, invalid='right_wrist')).status == 'TRACKING LOST'


def test_tracking_loss_and_pause_freeze_time_without_repositioning_or_bridging_hits(skeleton):
    sim = BoxingSimulation(config())
    initial = sim.step(skeleton(0))
    running = sim.step(skeleton(.1))
    lost = sim.step(skeleton(.2, invalid='left_wrist'))
    assert lost.remaining_s == running.remaining_s
    recovered = sim.step(skeleton(.3, left_z=1.62))
    assert recovered.remaining_s == running.remaining_s and recovered.score == 0
    sim.set_paused(True)
    paused = sim.step(skeleton(.4))
    assert paused.status == 'PAUSED' and paused.remaining_s == recovered.remaining_s
    sim.set_paused(False)
    resumed = sim.step(skeleton(.5, left_z=1.62))
    assert resumed.remaining_s == recovered.remaining_s and resumed.score == 0
    for a, b in zip(initial.targets, resumed.targets):
        np.testing.assert_array_equal(a.center, b.center)


def test_reset_restarts_and_repositions_in_the_next_frame(skeleton):
    sim = BoxingSimulation(config())
    sim.step(skeleton(0))
    assert sim.step(skeleton(.1, left_z=1.62)).score == 10
    sim.reset()
    state = sim.step(skeleton(.2, shift=.3))
    assert state.status == 'RUNNING' and state.remaining_s == 60 and state.score == 0
    assert state.targets[0].center[0] == pytest.approx(.1)


def test_depth_bounds_report_distance_instead_of_entering_calibration(skeleton):
    sim = BoxingSimulation(config(min_depth_m=1.5))
    frame = skeleton(0)
    frame = replace(frame, joints={name: replace(j, position=j.position+(0, 0, -.2))
                                  for name, j in frame.joints.items()})
    state = sim.step(frame)
    assert state.status == 'ADJUST DISTANCE' and state.guidance is None
    assert not state.targets and state.remaining_s == 60
    assert sim.step(skeleton(.1)).status == 'RUNNING'


def test_round_finishes_without_a_countdown_or_practice(skeleton):
    sim = BoxingSimulation(config(round_duration_s=.2))
    sim.step(skeleton(0))
    sim.step(skeleton(.1))
    state = sim.step(skeleton(.2))
    assert state.status == 'FINISHED' and state.remaining_s == 0 and state.guidance is None


@pytest.mark.parametrize('status', ['RUNNING', 'WAITING FOR PLAYER', 'ADJUST DISTANCE', 'PAUSED', 'FINISHED'])
def test_direct_hud_has_no_calibration_or_confirmation_prompts(skeleton, monkeypatch, status):
    pytest.importorskip('cv2')
    from depthstrike import visualization
    cfg = config()
    state = replace(BoxingSimulation(cfg).step(skeleton(0)), status=status)
    if status in ('WAITING FOR PLAYER', 'ADJUST DISTANCE'):
        state = replace(state, targets=())
    messages = []
    monkeypatch.setattr(visualization, 'draw_text', lambda image, value, *a, **kw: messages.append(str(value)))
    visualization.render_hud(state, None, cfg)
    assert 'R：重新开始' in messages
    assert not any('校准' in m or '试击' in m or '倒计时' in m or 'C：' in m or '肘' in m for m in messages)


def test_direct_recording_roundtrips_and_can_author_and_play_a_challenge(tmp_path):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    from depthstrike.sources import DemoPoseSource
    from depthstrike.motion_authoring import author_recording
    cfg = config()
    path = tmp_path/'direct.jsonl'
    original = BoxingSimulation(cfg)
    events = []
    with DemoPoseSource(config=cfg, total_frames=150) as source, PoseRecorder(path, cfg, source.describe()) as recorder:
        while (frame := source.read()) is not None:
            state = original.step(frame)
            events.extend(state.events)
            recorder.write(frame, state.events)
    assert events and events[0].timestamp_s < 2
    replayed = []
    with PoseReplaySource(path) as source:
        sim = BoxingSimulation(source.config)
        while (frame := source.read()) is not None:
            replayed.extend(sim.step(frame).events)
    assert replayed == events
    recipe = author_recording(path)
    assert recipe.to_dict()['extraction']['method'] == 'completed_direct_straight_punch_peak_v1'
    with PoseReplaySource(path) as source:
        challenge = BoxingSimulation(source.config, challenge=recipe)
        while (frame := source.read()) is not None:
            state = challenge.step(frame)
            assert state.guidance is None
    assert challenge.challenge.complete and challenge.hits > 0
    assert challenge.challenge.report()['player_calibration']['reference_kind'] == 'automatic_preset'
