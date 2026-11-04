"""Observed three-dimensional overlap is sufficient for ordinary live hits."""
from dataclasses import replace

import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig, load_config
from depthstrike.types import Joint3D


def config(**values):
    return replace(load_config(), smoothing_tau_s=0., **values)


def at_targets(skeleton, t, centers, **kwargs):
    frame = skeleton(t, **kwargs)
    for hand, center in centers.items():
        frame.joints[f'{hand}_wrist'] = Joint3D(center, .95)
    return frame


def test_slow_touch_scores_without_guard_attack_speed_or_travel(skeleton):
    sim = BoxingSimulation(config(punch_speed_m_s=100., punch_min_travel_m=1.))
    for n in range(15):
        state = sim.step(skeleton(n * .1, left_z=1.95 - n * .01))
    assert state.score == 10 and state.hits == 1
    assert sim.punches['left'].attack_id == 0
    assert state.targets[0].center == pytest.approx((-.2, .04, 1.7))
    assert state.targets[1].active


def test_punch_extension_thresholds_do_not_move_overlap_targets(skeleton):
    sim = BoxingSimulation(config(guard_extension_m=.8, attack_extension_m=.9))
    state = sim.step(skeleton(0., left_z=1.7))
    assert state.targets[0].center[2] == pytest.approx(1.7)
    assert state.hits == 1


def test_first_frame_already_overlapping_scores_once_without_moving(skeleton):
    sim = BoxingSimulation(config())
    state = sim.step(skeleton(0., left_z=1.7))
    assert state.score == 10 and state.targets[0].flash
    assert state.events[0].target_id == 0 and state.events[0].points == 10
    assert not sim.step(skeleton(.1, left_z=1.7)).events


@pytest.mark.parametrize('distance,hit', [(.14, False), (.13, False), (.121, False),
                                          (.12, True), (.11, True), (0., True)])
def test_two_centimeter_penetration_threshold(distance, hit, skeleton):
    sim = BoxingSimulation(config())
    state = sim.step(skeleton(0., left_z=1.7 + distance))
    assert state.hits == int(hit)


@pytest.mark.parametrize('axis', [0, 1, 2])
def test_overlap_uses_all_three_dimensions(axis, skeleton):
    sim = BoxingSimulation(config())
    center = sim.step(skeleton(0.)).targets[0].center
    far = center.copy()
    far[axis] += .2
    assert not sim.step(at_targets(skeleton, .1, {'left': far})).events
    assert sim.step(at_targets(skeleton, .2, {'left': center})).hits == 1


def test_trajectory_crossing_without_an_observed_overlap_does_not_hit(skeleton):
    sim = BoxingSimulation(config())
    sim.step(skeleton(0., left_z=1.88))
    assert not sim.step(skeleton(.1, left_z=1.5)).events


def test_only_the_designated_hand_and_active_ball_score(skeleton):
    sim = BoxingSimulation(config())
    state = sim.step(skeleton(0.))
    left_center = state.targets[0].center
    assert not sim.step(at_targets(skeleton, .1, {'right': left_center})).events
    state = sim.step(at_targets(skeleton, .2, {'left': state.targets[2].center}))
    assert not state.events
    assert sim.step(at_targets(skeleton, .3, {'left': left_center})).hits == 1


def held_pair(skeleton):
    sim = BoxingSimulation(config(direct_targets_per_hand=1))
    state = sim.step(skeleton(0.))
    centers = {target.hand: target.center for target in state.targets}
    sim.step(at_targets(skeleton, .1, centers))
    state = sim.step(at_targets(skeleton, .2, centers))
    assert state.hits == 2 and state.targets[0].active
    return sim, centers


def test_two_hands_held_in_two_balls_do_not_repeat_scores(skeleton):
    sim, centers = held_pair(skeleton)
    for n in range(3, 30):
        state = sim.step(at_targets(skeleton, n * .1, centers))
        assert state.hits == 2 and not state.events
        assert state.phases['left'] == 'TOUCH_RELEASE'
        assert state.feedback['left'].reason == 'leave_target'


def test_exit_hysteresis_prevents_jitter_and_rearms_after_full_separation(skeleton):
    sim, centers = held_pair(skeleton)
    for n, distance in enumerate((.11, .13, .145, .119, .125, .1), 3):
        moved = dict(centers, left=centers['left'] + (0, 0, distance))
        assert not sim.step(at_targets(skeleton, n * .1, moved)).events
    sim.step(at_targets(skeleton, .9, dict(centers, left=centers['left'] + (0, 0, .16))))
    state = sim.step(at_targets(skeleton, 1., centers))
    assert state.hits == 3 and state.events[0].hand == 'left'
    assert not sim.step(at_targets(skeleton, 1.1, centers)).events  # Right is still latched.


@pytest.mark.parametrize('kind', ['missing', 'predicted', 'low_confidence'])
def test_invalid_observations_cannot_hit_or_rearm_a_previous_hit(kind, skeleton):
    def invalid(frame, hand, position):
        frame.joints[f'{hand}_wrist'] = (Joint3D(None) if kind == 'missing' else
            Joint3D(position, .95, provenance='predicted') if kind == 'predicted' else
            Joint3D(position, .1))
        return frame
    sim = BoxingSimulation(config())
    center = sim.step(skeleton(0.)).targets[0].center
    assert not sim.step(invalid(skeleton(.1), 'left', center)).events
    assert sim.step(at_targets(skeleton, .2, {'left': center})).hits == 1
    sim, centers = held_pair(skeleton)
    outside = centers['left'] + (0, 0, .3)
    assert not sim.step(invalid(at_targets(skeleton, .3, centers), 'left', outside)).events
    assert not sim.step(at_targets(skeleton, .4, centers)).events
    assert sim.hits == 2


def test_tracking_loss_and_pause_keep_touch_latches_but_allow_fresh_unhit_contacts(skeleton):
    sim, centers = held_pair(skeleton)
    sim.invalidate_tracking()
    assert not sim.step(at_targets(skeleton, .3, centers)).events
    sim.set_paused(True)
    assert not sim.step(at_targets(skeleton, .4, centers)).events
    sim.set_paused(False)
    assert not sim.step(at_targets(skeleton, .5, centers)).events
    fresh = BoxingSimulation(config())
    center = fresh.step(skeleton(0.)).targets[0].center
    fresh.step(skeleton(.1, invalid='left_wrist'))
    state = fresh.step(at_targets(skeleton, .2, {'left': center}, invalid='left_shoulder'))
    assert state.hits == 1 and state.status == 'RUNNING'


def test_bad_timestamps_never_add_overlap_hits(skeleton):
    sim = BoxingSimulation(config())
    state = sim.step(skeleton(0.))
    centers = {target.hand: target.center for target in state.targets[:2]}
    assert not sim.step(at_targets(skeleton, 0., centers)).events
    assert sim.step(at_targets(skeleton, .1, centers)).hits == 1
    assert not sim.step(at_targets(skeleton, .05, centers)).events
    assert sim.step(at_targets(skeleton, .2, centers)).hits == 2


def test_reset_clears_latches_and_finished_round_cannot_score(skeleton):
    sim, centers = held_pair(skeleton)
    sim.reset()
    assert sim.step(at_targets(skeleton, .3, centers)).hits == 1
    sim = BoxingSimulation(config(round_duration_s=.1))
    center = sim.step(skeleton(0.)).targets[0].center
    state = sim.step(at_targets(skeleton, .1, {'left': center}))
    assert state.status == 'FINISHED' and not state.events


def test_overlap_threshold_is_configurable(skeleton):
    for penetration, expected in ((.01, 1), (.04, 0)):
        sim = BoxingSimulation(config(overlap_depth_m=penetration))
        assert sim.step(skeleton(0., left_z=1.825)).hits == expected


@pytest.mark.parametrize('values', [{'hit_mode': 'unknown'}, {'overlap_depth_m': 0},
    {'overlap_depth_m': -.01}, {'overlap_depth_m': float('nan')}, {'overlap_depth_m': True},
    {'overlap_depth_m': .12}, {'interaction_mode': 'guided'}])
def test_invalid_overlap_configuration_rejected(values):
    with pytest.raises(ValueError): config(**values)


def test_recorded_slow_touches_reproduce_scores_and_events(tmp_path, skeleton):
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    cfg = config()
    sim = BoxingSimulation(cfg)
    path = tmp_path / 'touch.jsonl'
    expected = []
    with PoseRecorder(path, cfg) as recorder:
        for n in range(20):
            frame = skeleton(n * .1, left_z=1.95 - min(n, 14) * .01)
            state = sim.step(frame)
            expected.extend(state.events)
            recorder.write(frame, state.events)
    with PoseReplaySource(path) as source:
        replay = BoxingSimulation(source.config)
        actual = []
        while (frame := source.read()) is not None:
            actual.extend(replay.step(frame).events)
    assert actual == expected and replay.hits == 1
    assert source.config.hit_mode == 'overlap'
    assert AppConfig().hit_mode == 'punch'


def test_overlap_hud_only_requests_touching_and_separation(monkeypatch, skeleton):
    pytest.importorskip('cv2')
    from depthstrike import visualization
    cfg = config()
    state = BoxingSimulation(cfg).step(skeleton(0.))
    messages = []
    monkeypatch.setattr(visualization, 'draw_text', lambda canvas, value, *a, **kw: messages.append(str(value)))
    visualization.render_hud(state, None, cfg)
    assert any('重叠' in value for value in messages)
    assert any('可以触碰' in value for value in messages)
    assert not any('出拳' in value or '收拳' in value or '速度' in value for value in messages)
