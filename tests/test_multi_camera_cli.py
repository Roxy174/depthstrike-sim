import json
from types import SimpleNamespace

import numpy as np
import pytest

from depthstrike import cli
from depthstrike.types import Intrinsics, RGBDFrame
from depthstrike.visualization import NullView


def test_list_cameras_is_read_only_and_never_loads_pose_or_opens_streams(monkeypatch, capsys):
    report = {'cameras': [{'source': 'gemini-camera', 'name': 'Orbbec Gemini 2'}], 'diagnostics': []}
    monkeypatch.setattr(cli, 'discover_cameras', lambda: report)
    monkeypatch.setattr(cli, 'CameraPoseSource', lambda *a, **kw: pytest.fail('No streaming during discovery'))
    assert cli.main(['--list-cameras']) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert cli.main(['--list-cameras', '--record', 'unused.jsonl']) != 0
    assert cli.main(['--list-cameras', '--frames', '0']) != 0


@pytest.mark.parametrize('source_name', ['auto-camera', 'gemini-camera', 'camera'])
def test_gemini_aliases_preserve_rgbd_pose_metadata_and_live_timing(monkeypatch, tmp_path, capsys, source_name):
    captures, modes, session_options = [], [], []
    class Capture:
        def __init__(self, config, directory=None):
            self.frames, self.closed = 0, False
            captures.append(self)
        def read(self):
            if self.frames: return None
            self.frames += 1
            return RGBDFrame(0, 1., np.zeros((3, 4, 3), np.uint8), np.ones((3, 4), np.float32),
                             Intrinsics(4, 3, 6, 6, 2, 1.5))
        def describe(self):
            return {'capture_backend': 'orbbec_sdk_gemini2', 'source': 'Gemini 2', 'evidence': 'unverified',
                    'timestamp_source': 'device_timestamp', 'selected_camera_source': 'gemini-camera'}
        def close(self): self.closed = True
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    class View(NullView):
        def __init__(self, config, mode, **kwargs): modes.append(mode)
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    run_session = cli.run_session
    def run(*args, **kwargs):
        session_options.append(kwargs)
        return run_session(*args, **kwargs)
    monkeypatch.setattr(cli, 'run_session', run)
    monkeypatch.setattr(cli, 'AutoCameraSource', Capture)
    monkeypatch.setattr('depthstrike.sources.GeminiSource', Capture)
    monkeypatch.setattr('depthstrike.sources.PoseEstimator', lambda c: SimpleNamespace(detect=lambda f: {}, close=lambda: None))
    monkeypatch.setattr(cli, 'SceneView', View)
    recording, rgbd = tmp_path/'pose.jsonl', tmp_path/'rgbd'
    assert cli.main(['--source', source_name, '--frames', '1', '--record', str(recording), '--record-rgbd', str(rgbd)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)['frames'] == 1 and 'Gemini 2' in output.err
    assert captures[0].closed and modes == ['gemini-camera']
    assert not session_options[0]['realtime']
    for path in (recording, rgbd/'frames.jsonl'):
        header = json.loads(path.read_text(encoding='utf-8').splitlines()[0])
        assert header['metadata']['capture_backend'] == 'orbbec_sdk_gemini2'
        assert header['metadata']['timestamp_source'] == 'device_timestamp'
        assert header['config']['interaction_mode'] == 'direct'


def test_gemini_identity_survives_pose_replay_and_rerecording(monkeypatch, tmp_path, capsys):
    from depthstrike.config import load_config
    from depthstrike.recording import PoseRecorder
    from depthstrike.types import SkeletonFrame
    original, copied = tmp_path/'original.jsonl', tmp_path/'copied.jsonl'
    metadata = {'capture_backend': 'orbbec_sdk_gemini2', 'timestamp_source': 'device_timestamp',
                'evidence': 'unverified'}
    with PoseRecorder(original, load_config(), metadata) as recorder:
        recorder.write(SkeletonFrame(0, 1., {}), ())
    modes = []
    class View(NullView):
        def __init__(self, config, mode, **kwargs): modes.append(mode)
        def __enter__(self): return self
        def __exit__(self, *a): self.close()
    monkeypatch.setattr(cli, 'SceneView', View)
    assert cli.main(['--source', 'replay', '--input', str(original), '--record', str(copied)]) == 0
    assert cli.main(['--source', 'replay', '--input', str(copied)]) == 0
    capsys.readouterr()
    assert modes == ['gemini-camera']*2
