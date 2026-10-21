import json
import os
import subprocess
import sys

import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig
from depthstrike.sources import DemoPoseSource
from depthstrike.visualization import NullView


def test_guided_demo_pause_reset_and_tracking_loss_roundtrip(tmp_path):
    from depthstrike.app import run_session
    from depthstrike.recording import PoseRecorder, PoseReplaySource
    config = AppConfig()
    class Controls(NullView):
        def __init__(self): self.calls = 0
        def poll_actions(self):
            n = self.calls
            self.calls += 1
            return {70: ["pause"], 130: ["pause"], 450: ["reset"], 520: ["tracking_lost"]}.get(n, [])
    path = tmp_path/"interactive.jsonl"
    first = run_session(DemoPoseSource(config=config, total_frames=1200), BoxingSimulation(config),
                        Controls(), PoseRecorder(path, config, {"evidence": "synthetic"}))
    assert first.hits >= 3
    with PoseReplaySource(path) as source:
        replay = run_session(source, BoxingSimulation(source.config), NullView())
    assert (first.frames, first.score, first.hits, first.remaining_s) == (
        replay.frames, replay.score, replay.hits, replay.remaining_s)


@pytest.mark.parametrize("changes", [
    {"fist_offset_m": .03}, {"target_reach_ratio": .8},
    {"calibration_duration_s": 1., "reach_hold_s": .5},
])
def test_reasonable_demo_overrides_complete_guidance(changes):
    from depthstrike.app import run_session
    config = AppConfig(**changes)
    result = run_session(DemoPoseSource(config=config, total_frames=900), BoxingSimulation(config), NullView())
    assert result.hits >= 3 and result.remaining_s < config.round_duration_s


@pytest.mark.parametrize("changes", [
    {"target_reach_ratio": .1}, {"punch_speed_m_s": 20.}, {"smoothing_tau_s": 10.},
])
def test_unsupported_demo_config_is_rejected_not_left_in_endless_practice(changes):
    with pytest.raises(ValueError, match="demo|Demo|Synthetic"):
        DemoPoseSource(config=AppConfig(**changes))


def test_headless_comparison_does_not_require_vision_or_display_packages():
    code = """import sys
from depthstrike.evaluation import evaluate_synthetic_suite
r=evaluate_synthetic_suite()
assert len(r['scenarios']) == 7
assert not {'pyorbbecsdk','mediapipe','open3d','cv2'} & set(sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not os.environ.get("DEPTHSTRIKE_GUI_TESTS"), reason="Opt-in actual window lifecycle")
@pytest.mark.parametrize("surface", ["overlay", "arena"])
def test_actual_closing_either_window_releases_source(surface):
    from depthstrike.app import run_session
    from depthstrike.visualization import SceneView
    class CloseAfterRender(SceneView):
        def render(self, state, rgbd):
            super().render(state, rgbd)
            if surface == "overlay": self.cv2.destroyWindow(self.hud_name)
            else: self.vis.destroy_window()
    config = AppConfig()
    source = DemoPoseSource(config=config, total_frames=5)
    view = CloseAfterRender(config, layout="dual")
    result = run_session(source, BoxingSimulation(config), view)
    assert result.frames == 1 and result.termination == "quit"
    assert source.closed and view._closed
