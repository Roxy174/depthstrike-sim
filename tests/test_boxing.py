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
