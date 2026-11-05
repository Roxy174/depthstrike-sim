"""Readable cumulative hits and brief, non-repeating score notifications."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from depthstrike.config import load_config
from depthstrike.feedback import HitNotice, ScoreFeedback
from depthstrike.types import HitEvent


class Clock:
    now = 0.
    def __call__(self): return self.now


def totals(hits=0, *, events=()):
    return SimpleNamespace(hits=hits, score=hits * 10, events=events)


def hit(t=0., attack=1):
    return HitEvent(t, 'left', 0, attack, 10)


def test_single_frame_hit_remains_visible_briefly_and_redraw_cannot_retrigger_it():
    clock = Clock()
    feedback = ScoreFeedback(clock)
    assert feedback.update(totals()) is None
    event_state = totals(1, events=(hit(),))
    assert feedback.update(event_state) == HitNotice(1, 10)
    clock.now = .5
    assert feedback.update(totals(1)) == HitNotice(1, 10)
    clock.now = 1.
    assert feedback.update(event_state) is None
    assert feedback.update(totals(1)) is None


def test_reset_clears_the_previous_round_notice():
    feedback = ScoreFeedback(Clock())
    feedback.update(totals(1, events=(hit(),)))
    assert feedback.update(totals()) is None
    assert feedback.update(totals(1, events=(hit(.1, 2),))) == HitNotice(1, 10)


def test_new_round_immediate_hit_with_the_same_totals_still_gets_a_new_notice():
    clock = Clock()
    feedback = ScoreFeedback(clock)
    feedback.update(totals(1, events=(hit(),)))
    clock.now = .8
    feedback.update(totals(1, events=(hit(.8, 2),)))
    clock.now = 1.3
    assert feedback.update(totals(1)) == HitNotice(1, 10)


def test_loading_existing_totals_does_not_invent_a_hit_but_later_gains_are_shown():
    feedback = ScoreFeedback(Clock())
    assert feedback.update(totals(12)) is None
    assert feedback.update(totals(14)) == HitNotice(2, 20)


@pytest.mark.parametrize('status', ['RUNNING', 'PAUSED', 'TRACKING LOST', 'WAITING FOR CAMERA', 'FINISHED'])
def test_counter_shows_authoritative_totals_in_all_play_states(monkeypatch, skeleton, status):
    pytest.importorskip('cv2')
    from depthstrike.boxing import BoxingSimulation
    from depthstrike import visualization
    cfg = load_config()
    state = replace(BoxingSimulation(cfg).step(skeleton(0.)), hits=37, score=370, status=status)
    drawn = []
    def text(canvas, value, at, size, *args, **kwargs):
        drawn.append((str(value), at, size))
    monkeypatch.setattr(visualization, 'draw_text', text)
    visualization.render_hud(state, None, cfg, hit_notice=HitNotice(1, 10))
    assert any(value == '累计击中小球' for value, _, _ in drawn)
    assert any(value == '37' and size >= 1.5 for value, _, size in drawn)
    assert any(value == '370 分' for value, _, _ in drawn)
    assert any('命中！+1 次' in value and '+10 分' in value for value, _, _ in drawn)
    if status == 'FINISHED':
        assert any(value == '击中小球 37 次' for value, _, _ in drawn)
        assert any(value == '本轮积分 370 分' for value, _, _ in drawn)


def test_finished_window_keeps_totals_visible_without_reading_more_camera_frames(monkeypatch, skeleton):
    from depthstrike import app
    from depthstrike.boxing import BoxingSimulation
    from test_app import Input, View
    monkeypatch.setattr(app.time, 'sleep', lambda duration: None)
    source = Input([skeleton(0.), skeleton(.05, left_z=1.7), skeleton(.1), skeleton(.2),
                    RuntimeError('Finished display must not keep capturing')])
    view = View([[], [], [], [], [], ['quit']])
    view.keep_open_on_finish = True
    cfg = replace(load_config(), smoothing_tau_s=0., round_duration_s=.2)
    summary = app.run_session(source, BoxingSimulation(cfg), view)
    assert summary.frames == 4 and summary.hits == 1 and summary.score == 10
    assert [state.status for state in view.states[-2:]] == ['FINISHED', 'FINISHED']
    assert all(state.hits == 1 and state.score == 10 for state in view.states[-2:])
    assert summary.termination == 'quit' and view.closed and source.closed


def test_reset_from_final_results_starts_a_new_scored_round(monkeypatch, skeleton):
    from depthstrike import app
    from depthstrike.boxing import BoxingSimulation
    from test_app import Input, View
    monkeypatch.setattr(app.time, 'sleep', lambda duration: None)
    source = Input([skeleton(0.), skeleton(.1), skeleton(.2, left_z=1.7)])
    view = View([[], [], ['reset'], ['quit']])
    view.keep_open_on_finish = True
    cfg = replace(load_config(), smoothing_tau_s=0., round_duration_s=.1)
    result = app.run_session(source, BoxingSimulation(cfg), view)
    assert view.states[1].status == 'FINISHED'
    assert view.states[2].status == 'RUNNING'
    assert result.hits == 1 and result.score == 10


def test_headless_sessions_still_end_at_the_round_limit(skeleton):
    from depthstrike.app import run_session
    from depthstrike.boxing import BoxingSimulation
    from depthstrike.visualization import NullView
    from test_app import Input
    cfg = replace(load_config(), round_duration_s=.1)
    source = Input([skeleton(0.), skeleton(.1), RuntimeError('Headless must finish')])
    summary = run_session(source, BoxingSimulation(cfg), NullView())
    assert summary.termination == 'round_finished' and summary.frames == 2
