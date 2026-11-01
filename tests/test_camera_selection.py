from types import SimpleNamespace
import os

import pytest

from depthstrike import camera_selection
from depthstrike.camera_selection import AutoCameraSource, discover_cameras
from depthstrike.config import load_config
from depthstrike.types import DepthStrikeError


def sdk_with(*names):
    devices = SimpleNamespace(get_count=lambda: len(names), get_device_name_by_index=lambda i: names[i])
    return SimpleNamespace(Context=lambda: SimpleNamespace(query_devices=lambda: devices))


def inventory(names=(), usb=()):
    return discover_cameras(sdk=sdk_with(*names), cv2_module=SimpleNamespace(CAP_DSHOW=700),
        enumerate_devices=lambda backend: [SimpleNamespace(vid=v, pid=p) for v, p in usb])


def test_discovery_distinguishes_gemini_astra_and_unrelated_webcams():
    report = inventory(('Orbbec Gemini 2', 'Astra 2', 'Gemini 215'),
                       ((0x1234, 1), (0x2bc5, 0x050f)))
    assert [c['source'] for c in report['cameras']] == ['gemini-camera', 'astra-camera']
    assert not report['diagnostics']
    assert not inventory((), ((0x1234, 1),))['cameras']


def test_missing_sdk_does_not_disable_astra(monkeypatch):
    def missing(name): raise ImportError('SDK not installed')
    monkeypatch.setattr(camera_selection.importlib, 'import_module', missing)
    report = discover_cameras(cv2_module=SimpleNamespace(CAP_DSHOW=700),
        enumerate_devices=lambda b: [SimpleNamespace(vid=0x2bc5, pid=0x050f)])
    assert [c['source'] for c in report['cameras']] == ['astra-camera']
    assert 'SDK not installed' in report['diagnostics'][0]


def test_missing_astra_enumerator_does_not_disable_gemini(monkeypatch):
    def missing(name): raise ImportError('No camera enumerator')
    monkeypatch.setattr(camera_selection.importlib, 'import_module', missing)
    report = discover_cameras(sdk=sdk_with('Gemini 2'), cv2_module=SimpleNamespace(CAP_DSHOW=700))
    assert [c['source'] for c in report['cameras']] == ['gemini-camera']
    assert 'No camera enumerator' in report['diagnostics'][0]


@pytest.mark.parametrize('failure', [False, True])
def test_sdk_native_import_log_goes_to_stderr_and_stdout_is_restored(monkeypatch, capfd, failure):
    def load(name):
        os.write(1, b'native SDK log\n')
        if failure: raise ImportError('unavailable SDK')
        return 'SDK module'
    monkeypatch.setattr(camera_selection.importlib, 'import_module', load)
    if failure:
        with pytest.raises(ImportError): camera_selection.load_orbbec_sdk()
    else:
        assert camera_selection.load_orbbec_sdk() == 'SDK module'
    print('output after SDK import')
    out, err = capfd.readouterr()
    assert out == 'output after SDK import\n'
    assert err == 'native SDK log\n'


@pytest.mark.parametrize('name', ['Gemini 2', 'Orbbec Gemini 2', 'GEMINI2'])
def test_supported_model_names_are_normalized(name):
    assert camera_selection.is_gemini2(name)


class Capture:
    closed = 0
    def read(self): return 'measured-frame'
    def describe(self): return {'capture_backend': 'test-backend', 'evidence': 'unverified'}
    def close(self): self.closed += 1


@pytest.mark.parametrize('source', ['gemini-camera', 'astra-camera'])
def test_automatic_selection_uses_only_matching_backend_and_preserves_metadata(source):
    calls, capture, config = [], Capture(), load_config()
    def gemini(c): calls.append(('gemini-camera', c)); return capture
    def astra(c, directory): calls.append(('astra-camera', c, directory)); return capture
    with AutoCameraSource(config, 'local-openni',
        discover=lambda: {'cameras': [{'source': source, 'name': 'test'}], 'diagnostics': []},
        gemini_factory=gemini, astra_factory=astra) as selected:
        assert selected.read() == 'measured-frame'
        assert calls == ([(source, config)] if source == 'gemini-camera' else [(source, config, 'local-openni')])
        metadata = selected.describe()
        assert metadata['capture_backend'] == 'test-backend'
        assert metadata['requested_camera_source'] == 'auto-camera'
        assert metadata['selected_camera_source'] == source
    selected.close()
    assert capture.closed == 1


@pytest.mark.parametrize('cameras, message', [([], 'No supported'),
    ([{'source': 'gemini-camera'}, {'source': 'astra-camera'}], 'Multiple supported'),
    ([{'source': 'gemini-camera'}]*2, 'Multiple supported')])
def test_absent_or_ambiguous_devices_never_open_a_stream(cameras, message):
    def forbidden(*args): pytest.fail('Must not open a camera when selection is ambiguous')
    with pytest.raises(DepthStrikeError, match=message):
        AutoCameraSource(load_config(), discover=lambda: {'cameras': cameras, 'diagnostics': []},
                         gemini_factory=forbidden, astra_factory=forbidden)
