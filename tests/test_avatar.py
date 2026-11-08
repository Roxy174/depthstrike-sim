"""The cartoon follows display poses without modifying measured interaction."""
from dataclasses import replace
import subprocess
import sys

import numpy as np
import pytest

from depthstrike.avatar import build_avatar, draw_avatar, surface_samples
from depthstrike.boxing import BoxingSimulation
from depthstrike.config import AppConfig, load_config
from depthstrike.types import Intrinsics, Joint3D


def config(**values):
    return replace(load_config(), smoothing_tau_s=0., **values)


def parts(state, cfg):
    return {part.name: part for part in build_avatar(state, cfg)}


def test_character_has_head_face_torso_arms_and_exact_interaction_gloves(skeleton):
    cfg = config()
    state = BoxingSimulation(cfg).step(skeleton(0.))
    character = parts(state, cfg)
    assert {'head', 'hair', 'torso', 'eye_left', 'eye_right', 'upper_arm_left',
            'forearm_right', 'glove_left', 'glove_right'} <= character.keys()
    for hand in ('left', 'right'):
        glove = character[f'glove_{hand}']
        np.testing.assert_array_equal(glove.center, state.fists[hand].position)
        np.testing.assert_array_equal(glove.radii, np.full(3, cfg.hand_radius_m))
    for part in character.values():
        assert np.isfinite(part.transform).all() and np.all(part.radii > 0)
        np.testing.assert_allclose(part.basis.T @ part.basis, np.eye(3), atol=1e-10)


@pytest.mark.parametrize('elbow,wrist', [
    ((-.35, -.1, 1.9), (-.45, -.45, 1.8)),
    ((-.3, .2, 1.8), (-.2, .04, 1.45)),
    ((-.4, .1, 2.), (-.6, .1, 2.)),
])
def test_arm_axes_follow_raised_extended_and_sideways_motion(elbow, wrist, skeleton):
    cfg = config()
    frame = skeleton(0.)
    frame.joints['left_elbow'] = Joint3D(elbow, .95)
    frame.joints['left_wrist'] = Joint3D(wrist, .95)
    state = BoxingSimulation(cfg).step(frame)
    forearm = parts(state, cfg)['forearm_left']
    direction = np.asarray(wrist) - elbow
    np.testing.assert_allclose(forearm.basis[:, 1], direction / np.linalg.norm(direction))
    np.testing.assert_allclose(forearm.center, (np.asarray(wrist) + elbow) / 2)


def test_missing_elbow_hides_that_arm_without_displacing_valid_gloves(skeleton):
    cfg = config()
    state = BoxingSimulation(cfg).step(skeleton(0., invalid='left_elbow'))
    character = parts(state, cfg)
    assert 'upper_arm_left' not in character and 'forearm_left' not in character
    assert 'forearm_right' in character and 'glove_left' in character
    np.testing.assert_array_equal(character['glove_left'].center, state.fists['left'].position)


def test_display_prediction_is_gray_bounded_and_never_added_to_scoring_state(skeleton):
    cfg = config(prediction_horizon_s=.2)
    state = BoxingSimulation(cfg).step(skeleton(0., invalid='left_wrist'))
    estimated = Joint3D((-.2, .04, 1.6), .4, provenance='predicted', age_s=.1)
    state = replace(state, display_joints={'left_wrist': estimated})
    glove = parts(state, cfg)['glove_left']
    assert glove.estimated and glove.display_color == (.62, .65, .67)
    assert state.fists['left'].position is None and state.score == 0
    expired = replace(state, display_joints={'left_wrist': replace(estimated, age_s=.21)})
    assert 'glove_left' not in parts(expired, cfg)
    assert not build_avatar(replace(state, skeleton=None), cfg)


def test_degenerate_bones_are_hidden_without_nonfinite_mesh_transforms(skeleton):
    cfg = config()
    frame = skeleton(0.)
    frame.joints['left_elbow'] = frame.joints['left_wrist']
    character = parts(BoxingSimulation(cfg).step(frame), cfg)
    assert 'forearm_left' not in character
    assert all(np.isfinite(part.transform).all() for part in character.values())


def test_torso_and_head_can_be_displayed_without_hip_measurements(skeleton):
    cfg = config()
    frame = skeleton(0., invalid='left_hip')
    frame.joints['right_hip'] = Joint3D(None)
    character = parts(BoxingSimulation(cfg).step(frame), cfg)
    assert 'torso' in character and 'head' in character


def test_avatar_rendering_does_not_mutate_joints_or_change_hit_events(skeleton):
    pytest.importorskip('cv2')
    cartoon = BoxingSimulation(config())
    skeleton_sim = BoxingSimulation(config(avatar_style='skeleton'))
    for t, left_z, right_z in ((0., 1.85, 1.85), (.1, 1.7, 1.85), (.2, 1.85, 1.7)):
        frame = skeleton(t, left_z=left_z, right_z=right_z)
        before = {name: joint.position.copy() for name, joint in frame.joints.items()}
        state = cartoon.step(frame)
        reference = skeleton_sim.step(frame)
        draw_avatar(np.zeros((360, 640, 3), np.uint8), build_avatar(state, cartoon.config),
                    Intrinsics(640, 360, 600, 600, 320, 150))
        assert (state.score, state.hits, state.events) == (reference.score, reference.hits, reference.events)
        for name in before: np.testing.assert_array_equal(frame.joints[name].position, before[name])


def test_synthetic_camera_frames_the_entire_upper_body(skeleton):
    from depthstrike.spatial import project
    cfg = config()
    state = BoxingSimulation(cfg).step(skeleton(0.))
    intrinsics = Intrinsics(640, 360, 600, 600, 320, 150)
    vertices = np.concatenate([surface_samples(part.shape) @ part.transform.T + part.center
                               for part in build_avatar(state, cfg)])
    pixels = project(vertices, intrinsics)
    assert pixels[:, 0].min() > 0 and pixels[:, 0].max() < 640
    assert pixels[:, 1].min() > 0 and pixels[:, 1].max() < 360


def test_arena_reuses_meshes_and_hides_unavailable_parts_and_style_switches(skeleton):
    o3d = pytest.importorskip('open3d')
    from depthstrike.arena import ArenaRenderer, display_position
    from test_visualization import Visualizer
    cfg = config()
    vis = Visualizer()
    simulation = BoxingSimulation(cfg)
    with ArenaRenderer(cfg, visualizer=vis, o3d=o3d) as arena:
        state = simulation.step(skeleton(0.))
        arena.render(state)
        identities = {name: id(mesh) for name, mesh in arena.geometries.items()}
        for n in range(1, 20):
            latest = simulation.step(skeleton(n / 30, left_z=1.6))
            arena.render(latest)
        assert identities == {name: id(mesh) for name, mesh in arena.geometries.items()}
        glove = arena.geometries['avatar_glove_left']
        assert glove.has_vertex_normals() and glove.has_triangle_normals()
        assert np.isfinite(np.asarray(glove.vertex_normals)).all()
        np.testing.assert_allclose(np.asarray(glove.vertices).mean(axis=0),
                                   display_position(latest.fists['left'].position), atol=1e-9)
        arena.avatar_style = 'skeleton'
        arena.render(state)
        assert len(glove.vertices) == 0 and len(arena.geometries['fist_left'].vertices) > 0
        arena.avatar_style = 'cartoon'
        arena.render(replace(state, skeleton=None, fists={}, display_joints={}))
        assert all(len(mesh.vertices) == 0 for name, mesh in arena.geometries.items() if name.startswith('avatar_'))
    assert vis.closed


@pytest.mark.parametrize('key', [ord('v'), ord('V')])
def test_visual_toggle_is_not_returned_as_a_recorded_game_action(monkeypatch, key):
    import cv2
    from depthstrike.visualization import SceneView
    monkeypatch.setattr(cv2, 'namedWindow', lambda *a: None)
    monkeypatch.setattr(cv2, 'moveWindow', lambda *a: None)
    monkeypatch.setattr(cv2, 'destroyWindow', lambda *a: None)
    monkeypatch.setattr(cv2, 'getWindowProperty', lambda *a: 1)
    monkeypatch.setattr(cv2, 'waitKey', lambda *a: key)
    with SceneView(config()) as view:
        assert view.avatar_style == 'cartoon'
        assert view.poll_actions() == [] and view.avatar_style == 'skeleton'
        assert view.poll_actions() == [] and view.avatar_style == 'cartoon'


@pytest.mark.parametrize('style', ['skeleton', 'cartoon'])
def test_avatar_flag_is_applied_after_loading_a_pose_recording(monkeypatch, tmp_path, capsys, skeleton, style):
    from depthstrike import cli
    from depthstrike.recording import PoseRecorder
    from depthstrike.visualization import NullView
    recorded = tmp_path / 'source.jsonl'
    with PoseRecorder(recorded, config(avatar_style='skeleton')) as recorder:
        recorder.write(skeleton(0.), ())
    chosen = []
    class View(NullView):
        def __init__(self, cfg, *a, **kw): chosen.append(cfg.avatar_style)
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    monkeypatch.setattr(cli, 'SceneView', View)
    assert cli.main(['--source', 'replay', '--input', str(recorded), '--avatar', style]) == 0
    capsys.readouterr()
    assert chosen == [style]


def test_headless_cartoon_does_not_import_vision_or_graphics_packages():
    code = "from depthstrike.cli import main; import sys; result=main(['--headless','--frames','3','--avatar','cartoon']); assert not {'cv2','open3d','mediapipe','PIL'} & set(sys.modules); raise SystemExit(result)"
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_historical_configs_keep_skeleton_and_invalid_avatar_styles_are_rejected():
    assert AppConfig().avatar_style == 'skeleton'
    assert load_config().avatar_style == 'cartoon'
    with pytest.raises(ValueError, match='avatar_style'): config(avatar_style='unknown')
