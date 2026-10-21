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


def sim(): return BoxingSimulation(replace(AppConfig(), smoothing_tau_s=0, calibration_duration_s=0))


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
    assert image.shape == (720, 640, 3) and image.dtype.name == "uint8"
    assert tuple(display_position((1, 2, 3))) == (1, -2, -3)


@pytest.mark.skipif(not os.environ.get("DEPTHSTRIKE_GUI_TESTS"), reason="Opt-in real display test")
def test_initial_camera_frames_target_region(skeleton):
    from depthstrike.visualization import SceneView, display_position
    simulation = sim()
    state = simulation.step(skeleton(0))
    with SceneView(AppConfig()) as view:
        view.render(state, None)
        camera = view.vis.get_view_control().convert_to_pinhole_camera_parameters()
        for target in state.targets:
            xyz = camera.extrinsic @ np.r_[display_position(target.center), 1.]
            pixel = camera.intrinsic.intrinsic_matrix @ xyz[:3]
            u, v = pixel[:2]/pixel[2]
            assert 50 < u < 910 and 50 < v < 670, (u, v)
