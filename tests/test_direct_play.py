"""Direct play has no posture holds, practice hits or calibration countdown."""
from dataclasses import replace
import json

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig, load_config
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
        assert cfg.direct_targets_per_hand == 3
        assert cfg.hit_mode == 'overlap' and cfg.overlap_depth_m == .02
    assert load_config().direct_target_forward_m == .30


def test_first_observed_shoulders_place_targets_without_any_hold_or_elbows(skeleton):
    sim = BoxingSimulation(config(calibration_duration_s=100, reach_hold_s=100, countdown_s=100))
    frame = skeleton(0, invalid='left_elbow')
    state = sim.step(frame)
    assert state.status == 'RUNNING' and state.guidance is None
    assert state.remaining_s == 60 and state.score == 0
    assert len(state.targets) == 6
    assert state.targets[0].center == pytest.approx((-.2, .04, 1.70))


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
    sim = BoxingSimulation(config(hit_mode='punch'))
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
    assert right.targets[2].active
    moved = sim.step(skeleton(.4, shift=.1))
    for a, b in zip(initial.targets, moved.targets):
        np.testing.assert_array_equal(a.center, b.center)


@pytest.mark.parametrize('count', [1, 2, 3, 4])
def test_all_spatial_targets_can_score_and_sequence_wraps_without_double_hits(skeleton, count):
    sim = BoxingSimulation(config(direct_targets_per_hand=count))
    initial = state = sim.step(skeleton(0))
    assert len(state.targets) == 2 * count
    centers = np.stack([t.center for t in state.targets])
    assert len(np.unique(centers, axis=0)) == 2 * count
    for n, target in enumerate(initial.targets):
        # Move away, then place a fresh observed hand inside this ball.
        sim.step(skeleton(.3 * n + .1))
        frame = skeleton(.3 * n + .2)
        frame.joints[f'{target.hand}_wrist'] = Joint3D(target.center, .95)
        state = sim.step(frame)
        assert len(state.events) == 1
        assert (state.events[0].target_id, state.events[0].hand) == (n, target.hand)
        assert state.score == 10 * (n + 1)
        assert sum(t.active for t in state.targets) == 1
        assert next(t.target_id for t in state.targets if t.active) == (n + 1) % (2 * count)
        held = replace(frame, timestamp_s=.3 * n + .25, frame_id=10000 + n)
        assert not sim.step(held).events
    for a, b in zip(initial.targets, state.targets):
        np.testing.assert_array_equal(a.center, b.center)


def test_extra_targets_still_require_guard_speed_and_travel(skeleton):
    sim = BoxingSimulation(config(hit_mode='punch'))
    for n in range(4):
        # Even with the closer ball intersecting the guard envelope, no motion
        # and an initially extended hand cannot start an attack.
        state = sim.step(skeleton(n * .1, left_z=1.7))
        assert state.score == 0 and not state.events
    sim.step(skeleton(.4))
    assert sim.step(skeleton(.5, left_z=1.84)).score == 0


def test_a_later_active_target_uses_its_own_hand_for_tracking_and_distance(skeleton):
    sim = BoxingSimulation(config(hit_mode='punch'))
    sim.step(skeleton(0))
    sim.step(skeleton(.1, left_z=1.7))
    sim.step(skeleton(.2))
    state = sim.step(skeleton(.3, right_z=1.7))
    target = state.targets[2]
    sim.invalidate_tracking()  # Inspect distance without starting another punch.
    frame = skeleton(.4, invalid='right_wrist')
    frame.joints['left_wrist'] = Joint3D(target.center, .95)
    state = sim.step(frame)
    assert state.status == 'RUNNING'  # The inactive arm cannot block target 3.
    assert state.feedback['left'].surface_gap_m == pytest.approx(-.14)
    assert state.feedback['left'].depth_delta_m == pytest.approx(0.)
    assert state.feedback['left'].lateral_m == pytest.approx(0.)


def test_every_spatial_ball_must_fit_within_depth_bounds(skeleton):
    # The primary ball fits at z=1.70, but upper balls at 1.68 would not.
    sim = BoxingSimulation(config(min_depth_m=1.61))
    state = sim.step(skeleton(0))
    assert state.status == 'ADJUST DISTANCE' and not state.targets


def test_old_direct_recording_without_count_keeps_two_original_targets(tmp_path, skeleton):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    cfg = AppConfig(interaction_mode='direct', fist_mode='wrist', smoothing_tau_s=0)
    path = tmp_path / 'old-direct.jsonl'
    with PoseRecorder(path, cfg) as recorder:
        recorder.write(skeleton(0), ())
    rows = path.read_text(encoding='utf-8').splitlines()
    header = json.loads(rows[0])
    del header['config']['direct_targets_per_hand']
    del header['config']['hit_mode']
    del header['config']['overlap_depth_m']
    del header['config']['direct_target_reference']
    del header['config']['camera_target_depth_m']
    rows[0] = json.dumps(header)
    path.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    with PoseReplaySource(path) as source:
        assert source.config.hit_mode == 'punch'
        state = BoxingSimulation(source.config).step(source.read())
    assert len(state.targets) == 2
    assert state.targets[0].center == pytest.approx((-.2, .04, 1.62))


@pytest.mark.parametrize('count', [0, -1, 5, 1.5, True, '3', None])
def test_invalid_spatial_target_counts_are_rejected(count):
    with pytest.raises(ValueError, match='direct_targets_per_hand'):
        config(direct_targets_per_hand=count)


def test_inactive_arm_loss_does_not_block_the_active_hand(skeleton):
    sim = BoxingSimulation(config())
    sim.step(skeleton(0))
    state = sim.step(skeleton(.1, left_z=1.62, invalid='right_wrist'))
    assert state.score == 10 and state.events[0].hand == 'left'
    assert sim.step(skeleton(.2, invalid='right_wrist')).status == 'TRACKING LOST'


def test_tracking_loss_and_pause_freeze_time_without_repositioning_or_bridging_hits(skeleton):
    sim = BoxingSimulation(config(hit_mode='punch'))
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
