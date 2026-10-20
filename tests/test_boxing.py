from dataclasses import replace

import pytest

from depthstrike.config import AppConfig
from depthstrike.types import Joint3D


def point(z):
    return Joint3D((0, 0, z), .95)


def test_forward_punch_then_retraction_rearms():
    from depthstrike.boxing import PunchTracker
    tracker = PunchTracker(AppConfig())
    shoulder = point(2.)
    assert not tracker.update(0., point(1.85), shoulder).can_hit
    punch = tracker.update(.1, point(1.5), shoulder)
    assert punch.phase == "ATTACKING" and punch.can_hit
    assert punch.previous_position[2] == 1.85
    assert not tracker.update(.15, point(1.5), shoulder).can_hit
    tracker.update(.2, point(1.85), shoulder)
    assert tracker.update(.3, point(1.5), shoulder).attack_id == 2


def test_slow_extension_or_torso_translation_not_a_punch():
    from depthstrike.boxing import PunchTracker
    tracker = PunchTracker(AppConfig())
    for n in range(15):
        assert not tracker.update(n*.1, point(1.85-n*.03), point(2)).can_hit
    tracker.reset()
    tracker.update(0, point(1.85), point(2))
    assert not tracker.update(.1, point(1.5), point(1.65)).can_hit


@pytest.mark.parametrize("break_time,invalid", [(.4, False), (0., False), (.1, True)])
def test_break_cancels_attack_and_requires_guard(break_time, invalid):
    from depthstrike.boxing import PunchTracker
    tracker = PunchTracker(AppConfig())
    tracker.update(0, point(1.85), point(2))
    broken = tracker.update(break_time, Joint3D(None) if invalid else point(1.5), point(2))
    assert not broken.can_hit and broken.previous_position is None
    recovered = tracker.update(break_time+.05, point(1.4), point(2))
    assert not recovered.can_hit
    tracker.update(break_time+.1, point(1.85), point(2))
    assert tracker.update(break_time+.2, point(1.5), point(2)).can_hit


@pytest.mark.parametrize("dt,expected", [(.1, True), (.19, True)])
def test_speed_uses_frame_interval(dt, expected):
    from depthstrike.boxing import PunchTracker
    tracker = PunchTracker(AppConfig())
    tracker.update(0, point(1.85), point(2))
    assert tracker.update(dt, point(1.5), point(2)).can_hit is expected


def simulation(**changes):
    from depthstrike.boxing import BoxingSimulation
    return BoxingSimulation(replace(AppConfig(), smoothing_tau_s=0, calibration_duration_s=0, **changes))


def test_calibration_requires_stable_neutral_pose(skeleton):
    from depthstrike.boxing import BoxingSimulation
    sim = BoxingSimulation(replace(AppConfig(), calibration_duration_s=.3, smoothing_tau_s=0))
    assert not sim.step(skeleton(0)).targets
    assert not sim.step(skeleton(.15, shift=.3)).targets
    assert not sim.step(skeleton(.3, shift=.3)).targets
    assert sim.step(skeleton(.46, shift=.3)).targets


def test_targets_remain_in_camera_space_after_body_moves(skeleton):
    sim = simulation()
    first = sim.step(skeleton(0))
    centers = [t.center.copy() for t in first.targets]
    shifted = sim.step(skeleton(.1, shift=.2))
    for target, center in zip(shifted.targets, centers):
        assert target.center == pytest.approx(center)
    assert centers[0] == pytest.approx((-.2, .04, 1.5))


def test_alternating_punches_score_once_per_attack(skeleton):
    sim = simulation()
    sim.step(skeleton(0))
    hit = sim.step(skeleton(.1, left_z=1.4))
    assert (hit.score, hit.hits, len(hit.events)) == (10, 1, 1)
    assert any(t.flash for t in hit.targets)
    assert sim.step(skeleton(.15, left_z=1.4)).score == 10
    assert sim.step(skeleton(.2, left_z=1.85, right_z=1.4)).score == 20
    assert sim.step(skeleton(.25, right_z=1.4)).score == 20


def test_wrong_depth_does_not_score(skeleton):
    sim = simulation()
    sim.step(skeleton(0))
    assert sim.step(skeleton(.1, left_z=1.7)).score == 0


def test_pause_reset_and_round_end(skeleton):
    sim = simulation(round_duration_s=.2)
    sim.step(skeleton(0))
    sim.set_paused(True)
    assert sim.step(skeleton(1, left_z=1.4)).remaining_s == .2
    sim.set_paused(False)
    sim.step(skeleton(1.1))
    assert sim.step(skeleton(1.2, left_z=1.4)).score == 10
    done = sim.step(skeleton(1.31, right_z=1.4))
    assert done.status == "FINISHED" and done.score == 10
    sim.reset()
    assert sim.step(skeleton(2)).score == 0


def test_timeout_cancels_sweep(skeleton):
    sim = simulation()
    sim.step(skeleton(0))
    sim.invalidate_tracking()
    assert sim.step(skeleton(.1, left_z=1.4)).score == 0


def test_repeated_trajectory_is_deterministic(skeleton):
    results = []
    for _ in range(2):
        sim = simulation()
        results.append([(s.score, s.events) for s in [
            sim.step(skeleton(0)), sim.step(skeleton(.1, left_z=1.4)),
            sim.step(skeleton(.2, right_z=1.4)),
        ]])
    assert results[0] == results[1]
