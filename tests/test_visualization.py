from dataclasses import replace
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig
from depthstrike.types import HitEvent, Intrinsics, Joint3D, SceneState


class Visualizer:
    def __init__(self):
        self.added = []
        self.updated = []
        self.closed = False
        self.alive = True
        self.options = SimpleNamespace()
        self.control = SimpleNamespace(**{n: lambda *a: None for n in
                                         ("set_lookat", "set_front", "set_up", "set_zoom")})
    def create_window(self, *args, **kwargs): return True
    def add_geometry(self, geometry, **kwargs): self.added.append(geometry); return True
    def update_geometry(self, geometry): self.updated.append(id(geometry)); return True
    def remove_geometry(self, *args, **kwargs): raise AssertionError("Per-frame removal is forbidden")
    def get_render_option(self): return self.options
    def get_view_control(self): return self.control
    def register_key_callback(self, *args): pass
    def poll_events(self): return self.alive
    def update_renderer(self): pass
    def destroy_window(self): self.closed = True


def test_arena_reuses_geometries_and_restores_invalid_points(skeleton):
    from depthstrike.arena import ArenaRenderer
    o3d = pytest.importorskip("open3d")
    vis = Visualizer()
    config = AppConfig(interaction_mode="legacy", calibration_duration_s=0, smoothing_tau_s=0)
    sim = BoxingSimulation(config)
    with ArenaRenderer(config, visualizer=vis, o3d=o3d) as arena:
        arena.render(sim.step(skeleton(0)))
        identities = [id(g) for g in vis.added]
        for n in range(1, 101):
            arena.render(sim.step(skeleton(n/30, shift=.1)))
        assert [id(g) for g in vis.added] == identities
        mesh = arena.geometries["fist_left"]
        assert np.asarray(mesh.vertices).mean(axis=0) == pytest.approx((-.1, -.04, -1.85))
        arena.render(sim.step(skeleton(101/30, invalid="left_wrist")))
        assert len(mesh.vertices) == 0
        arena.render(sim.step(skeleton(102/30)))
        assert len(mesh.vertices) > 0 and id(mesh) == identities[vis.added.index(mesh)]
        assert np.asarray(mesh.vertices).mean(axis=0) == pytest.approx((-.2, -.04, -1.85))
    assert vis.closed


def test_overlay_does_not_import_open3d():
    code = """import cv2, sys
cv2.namedWindow=lambda *a: None
cv2.moveWindow=lambda *a: None
cv2.destroyWindow=lambda *a: None
from depthstrike.visualization import SceneView
from depthstrike.config import AppConfig
with SceneView(AppConfig(), layout='overlay'):
    assert 'open3d' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("surface", ["overlay", "arena"])
def test_closing_either_surface_ends_session_and_closes_all(monkeypatch, skeleton, surface):
    import cv2
    from depthstrike import visualization
    from depthstrike.app import run_session
    from test_app import Input, sim
    monkeypatch.setattr(cv2, "namedWindow", lambda *a: None)
    monkeypatch.setattr(cv2, "moveWindow", lambda *a: None)
    monkeypatch.setattr(cv2, "destroyWindow", lambda *a: None)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda *a: 0 if surface == "overlay" else 1)
    monkeypatch.setattr(cv2, "waitKey", lambda *a: -1)
    class Arena:
        vis = None
        closed = False
        def __init__(self, *a): pass
        def poll_actions(self): return ["quit"] if surface == "arena" else []
        def close(self): self.closed = True
    monkeypatch.setattr(visualization, "ArenaRenderer", Arena)
    view = visualization.SceneView(AppConfig(), layout="dual")
    source = Input([skeleton(0)])
    summary = run_session(source, sim(), view)
    assert summary.frames == 0 and source.closed and view.arena.closed and view._closed


def test_projection_ignores_nonfinite_and_behind_camera_points():
    from depthstrike.visualization import _pixel
    i = Intrinsics(640, 480, 600, 600, 320, 240)
    assert _pixel((np.nan, 0, 1), i) is None
    assert _pixel((0, 0, -1), i) is None


def test_hud_has_guidance_and_current_fist_feedback(skeleton):
    from depthstrike.visualization import render_hud
    config = AppConfig(fist_offset_m=0)
    state = BoxingSimulation(config).step(skeleton(0))
    image = render_hud(state, None, config)
    assert image.shape == (800, 960, 3) and image.dtype == np.uint8
    lost = replace(state, skeleton=None, fists={}, feedback={}, status="WAITING FOR CAMERA")
    assert not np.array_equal(image, render_hud(lost, None, config))


def test_audio_failure_is_nonfatal_and_reported_once(capsys):
    from depthstrike.audio import AudioFeedback
    class Broken:
        SND_ALIAS, SND_ASYNC, SND_NODEFAULT = 1, 2, 4
        def PlaySound(self, sound, flags): raise RuntimeError("no audio driver")
    audio = AudioFeedback(True, backend=Broken())
    event = HitEvent(1., "left", 0, 1, 10)
    audio.notify((event,))
    audio.notify((event,))
    audio.close()
    assert capsys.readouterr().err.count("no audio driver") == 1


def test_sound_is_opt_in_and_headless_rejects_it(capsys):
    from depthstrike.cli import main
    assert main(["--headless", "--sound", "--frames", "1"]) != 0
    assert "--sound requires a display" in capsys.readouterr().err
