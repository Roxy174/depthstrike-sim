from dataclasses import replace
import os

import numpy as np

import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig
from depthstrike.types import DepthStrikeError, FrameTimeout


class Input:
    def __init__(self, items):
        self.items = iter(items)
        self.closed = False
    def read(self):
        value = next(self.items, None)
        if isinstance(value, Exception): raise value
        return value
    def close(self): self.closed = True


class View:
    def __init__(self, actions=()):
        self.actions = iter(actions)
        self.closed = False
        self.states = []
    def poll_actions(self): return next(self.actions, [])
    def render(self, state, rgbd): self.states.append(state)
    def close(self): self.closed = True


def sim(): return BoxingSimulation(replace(AppConfig(), interaction_mode="legacy", smoothing_tau_s=0, calibration_duration_s=0))


def test_eof_and_source_failure_close_all_resources(skeleton):
    from depthstrike.app import run_session
    source, view = Input([skeleton(0), skeleton(.1, left_z=1.4)]), View()
    summary = run_session(source, sim(), view, None, max_frames=10)
    assert summary.frames == 2 and summary.score == 10
    assert source.closed and view.closed
    source, view = Input([RuntimeError("disconnected")]), View()
    with pytest.raises(RuntimeError, match="disconnected"):
        run_session(source, sim(), view, None)
    assert source.closed and view.closed


def test_pause_reset_quit_are_applied_before_frame(skeleton):
    from depthstrike.app import run_session
    source = Input([skeleton(0), skeleton(.1, left_z=1.4), skeleton(.2), skeleton(.3), skeleton(.4)])
    view = View([[], ["pause"], ["pause"], ["reset"], ["quit"]])
    summary = run_session(source, sim(), view, None)
    assert summary.frames == 4 and summary.score == 0
    assert view.states[1].status == "PAUSED"
    assert source.closed and view.closed


def test_temporary_timeout_cancels_attack_but_keeps_rendering(skeleton):
    from depthstrike.app import run_session
    source = Input([skeleton(0), FrameTimeout("late"), skeleton(.1, left_z=1.4)])
    view = View()
    summary = run_session(source, sim(), view, None)
    assert summary.score == 0 and summary.timeouts == 1
    assert len(view.states) >= 3
    assert any(s.status == "WAITING FOR CAMERA" for s in view.states)
    waiting = next(s for s in view.states if s.status == "WAITING FOR CAMERA")
    assert not waiting.fists and not waiting.feedback


def test_continuous_timeout_exits_with_clear_error(skeleton):
    from depthstrike.app import run_session
    source, view = Input([FrameTimeout("late")]*4), View()
    times = iter([0., 1., 6., 7., 8.])
    with pytest.raises(DepthStrikeError, match="5|frames"):
        run_session(source, sim(), view, None, clock=lambda: next(times))
    assert source.closed and view.closed


def test_hud_and_scene_use_valid_finite_coordinates(skeleton):
    pytest.importorskip("cv2")
    from depthstrike.visualization import render_hud, display_position
    state = sim().step(skeleton(0))
    image = render_hud(state, None, AppConfig(), "demo")
    assert image.shape == (800, 960, 3) and image.dtype.name == "uint8"
    assert tuple(display_position((1, 2, 3))) == (1, -2, -3)


@pytest.mark.skipif(not os.environ.get("DEPTHSTRIKE_GUI_TESTS"), reason="Opt-in real display test")
def test_initial_camera_frames_target_region(skeleton):
    from depthstrike.visualization import SceneView, display_position
    simulation = sim()
    state = simulation.step(skeleton(0))
    with SceneView(AppConfig(), layout="dual") as view:
        view.render(state, None)
        camera = view.vis.get_view_control().convert_to_pinhole_camera_parameters()
        for target in state.targets:
            xyz = camera.extrinsic @ np.r_[display_position(target.center), 1.]
            pixel = camera.intrinsic.intrinsic_matrix @ xyz[:3]
            u, v = pixel[:2]/pixel[2]
            assert 50 < u < 910 and 50 < v < 670, (u, v)


class FakeClock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now
    def sleep(self, duration): self.now += duration


def test_low_fps_replay_preserves_elapsed_time(monkeypatch):
    from depthstrike import app
    from depthstrike.sources import DemoPoseSource
    clock = FakeClock()
    monkeypatch.setattr(app.time, "sleep", clock.sleep)
    summary = app.run_session(DemoPoseSource(config=sim().config, fps=5, total_frames=6), sim(), View(),
                              realtime=True, clock=clock)
    assert summary.frames == 6
    assert clock.now == pytest.approx(1.)


def test_long_replay_wait_remains_responsive_to_quit(monkeypatch):
    from depthstrike import app
    from depthstrike.sources import DemoPoseSource
    clock = FakeClock()
    monkeypatch.setattr(app.time, "sleep", clock.sleep)
    class QuitWhileWaiting(View):
        def poll_actions(self): return ["quit"] if clock.now >= .15 else []
    source = DemoPoseSource(config=sim().config, fps=1, total_frames=3)
    summary = app.run_session(source, sim(), QuitWhileWaiting(), realtime=True, clock=clock)
    assert clock.now <= .21 and summary.frames == 1 and source.closed


def test_timed_replay_presents_each_skeleton_sample_once(monkeypatch):
    from depthstrike import app
    from depthstrike.sources import DemoPoseSource
    clock, view = FakeClock(), View()
    monkeypatch.setattr(app.time, "sleep", clock.sleep)
    app.run_session(DemoPoseSource(config=sim().config, fps=5, total_frames=3), sim(), view,
                    realtime=True, clock=clock)
    # Event pumping while waiting must not inject duplicate track samples.
    assert [s.skeleton.frame_id for s in view.states] == [0, 1, 2]
