"""A stable wrist can be measured despite noisy shoulder depth; C is explicit."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from depthstrike.app import run_session
from depthstrike.boxing import BoxingSimulation
from depthstrike.recording import PoseRecorder, PoseReplaySource
from depthstrike.visualization import SceneView
from test_app import Input, View
from test_calibration import Driver
from test_reach_conditions import config


def test_noisy_active_shoulder_does_not_reset_a_stable_38cm_reach(skeleton):
    def noisy(t, **pose):
        frame = skeleton(t, **pose)
        if pose.get('left_z', 1.85) < 1.8:
            joint = frame.joints['left_shoulder']
            shift = .04 if round(t/.05) % 2 else -.04
            frame.joints['left_shoulder'] = replace(joint, position=joint.position+(0, 0, shift))
        return frame
    d = Driver(noisy, config())
    d.hold(.7)
    assert d.hold(.5, left_z=1.47).guidance.stage == 'RETURN_LEFT'


def test_capturing_current_reach_advances_without_waiting_or_scoring(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    d.sim.request_reach_capture()
    state = d.hold(0, left_z=1.47)
    assert state.guidance.stage == 'RETURN_LEFT'
    assert state.score == 0 and not state.events
    assert d.sim.calibration._reach_vectors['left'][2] == pytest.approx(-.53)


@pytest.mark.parametrize('pose', [{}, {'left_z':1.47, 'invalid':'left_wrist'},
                                 {'left_z':1.47, 'shift':.15}])
def test_capture_does_not_bypass_reach_tracking_or_body_validation(skeleton, pose):
    d = Driver(skeleton, config())
    d.hold(.7)
    d.sim.request_reach_capture()
    assert d.hold(0, **pose).guidance.stage == 'REACH_LEFT'
    # A rejected confirmation is consumed, never saved for a later pose.
    assert d.hold(0, left_z=1.47).guidance.stage == 'REACH_LEFT'


def test_explicit_capture_uses_a_fresh_frame_after_a_processing_gap(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    d.sim.request_reach_capture()
    d.t += .4
    state = d.hold(0, left_z=1.47)
    assert state.guidance.stage == 'RETURN_LEFT'
    assert state.score == 0


def test_paused_capture_does_not_survive_resume(skeleton):
    d = Driver(skeleton, config())
    d.hold(.7)
    d.sim.set_paused(True)
    d.sim.request_reach_capture()
    d.hold(.1, left_z=1.47)
    d.sim.set_paused(False)
    assert d.hold(.1, left_z=1.47).guidance.stage == 'REACH_LEFT'


@pytest.mark.parametrize('key', [ord('c'), ord('C')])
def test_hud_c_key_emits_the_recordable_capture_action(key):
    view = SceneView.__new__(SceneView)
    view._closed, view.arena, view.hud_name = False, None, 'test'
    view.cv2 = SimpleNamespace(getWindowProperty=lambda *a:1, WND_PROP_VISIBLE=1,
                               waitKey=lambda _:key, error=RuntimeError)
    assert view.poll_actions() == ['capture_reach']


def test_capture_action_is_applied_and_replayed_deterministically(skeleton, tmp_path):
    frames = [skeleton(n*.05) for n in range(16)]
    frames.extend([skeleton(.8, left_z=1.47), skeleton(.85, left_z=1.47)])
    actions = [[] for _ in frames]
    actions[16] = ['capture_reach']
    path = tmp_path/'capture.jsonl'
    original_view = View(actions)
    with PoseRecorder(path, config()) as recorder:
        run_session(Input(frames), BoxingSimulation(config()), original_view, recorder)
    assert original_view.states[16].guidance.stage == 'RETURN_LEFT'
    replay_view = View()
    run_session(PoseReplaySource(path), BoxingSimulation(config()), replay_view)
    assert [s.guidance.stage for s in replay_view.states] == [s.guidance.stage for s in original_view.states]


def test_wrist_motion_reset_is_explained_and_capture_is_shown(skeleton, monkeypatch):
    pytest.importorskip('cv2')
    from depthstrike import visualization
    d = Driver(skeleton, config())
    d.hold(.7)
    d.hold(.1,left_z=1.47)
    state = d.hold(0,left_z=1.47,shift=.04)
    # Change only the wrist so body displacement is not the reason for reset.
    frame = skeleton(d.t+.05,left_z=1.47)
    frame.joints['left_wrist'] = replace(frame.joints['left_wrist'], position=np.array((-.10,.04,1.47)))
    state = d.sim.step(frame)
    assert state.guidance.measurements['hold_reset_reason'] == 'position_motion'
    messages = []
    monkeypatch.setattr(visualization,'draw_text',lambda image,value,*a,**kw:messages.append(str(value)))
    visualization.render_hud(state,None,d.config)
    assert any('C' in message and '确认' in message for message in messages)
    assert any('重新计时' in message for message in messages)


def test_manual_calibration_recording_can_be_authored_into_a_challenge(skeleton, tmp_path):
    from depthstrike.motion_authoring import author_recording
    path = tmp_path/'manual-author.jsonl'
    # Each reach has only one observed frame: the C commands are necessary.
    segments = [(.7, {}, False), (0, {'left_z':1.47}, True), (.3, {}, False),
                (0, {'right_z':1.47}, True), (.3, {}, False), (.1, {}, False),
                (0, {'left_z':1.47}, False), (.15, {}, False),
                (0, {'right_z':1.47}, False), (2.3, {}, False), (.1, {}, False),
                (0, {'left_z':1.47}, False), (.3, {}, False)]
    t = -.05
    with PoseRecorder(path, config()) as recorder:
        for duration, pose, capture in segments:
            for index in range(round(duration/.05)+1):
                t += .05
                recorder.write(skeleton(t, **pose), (), actions=['capture_reach'] if capture and index == 0 else [])
    recipe = author_recording(path)
    assert len(recipe.cues) == 1 and recipe.cues[0].hand == 'left'


def test_capture_annotation_does_not_change_independent_evaluation(skeleton):
    from depthstrike.evaluation import EvaluationManifest, evaluate_frames
    from test_evaluation import manifest_dict
    frames = [skeleton(0), skeleton(.1,left_z=1.47)]
    manifest = EvaluationManifest.from_dict(manifest_dict())
    baseline = evaluate_frames(frames, manifest, config())
    captured = evaluate_frames([(frames[0],()), (frames[1],('capture_reach',))], manifest, config())
    for method in baseline['methods']:
        assert captured['methods'][method]['predictions'] == baseline['methods'][method]['predictions']
