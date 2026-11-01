"""Discover supported cameras without opening streams or selecting a webcam."""
import importlib
import os
import sys

from .types import DepthStrikeError


def load_orbbec_sdk():
    # The SDK extension prints directly to native stdout during import.
    # Python redirect_stdout alone cannot keep CLI JSON output clean.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.flush()
    try:
        saved = os.dup(1)
    except OSError:
        # pythonw may have no console file descriptors.
        return importlib.import_module('pyorbbecsdk')
    try:
        try:
            os.dup2(2, 1)
        except OSError:
            pass
        return importlib.import_module('pyorbbecsdk')
    finally:
        os.dup2(saved, 1)
        os.close(saved)


def is_gemini2(name):
    return ''.join(c for c in name.casefold() if c.isalnum()) in ('gemini2', 'orbbecgemini2')


def gemini_indices(devices):
    return [i for i in range(devices.get_count()) if is_gemini2(devices.get_device_name_by_index(i))]


def discover_cameras(*, sdk=None, cv2_module=None, enumerate_devices=None):
    cameras, diagnostics = [], []
    try:
        sdk = sdk if sdk is not None else load_orbbec_sdk()
        context = sdk.Context()
        devices = context.query_devices()
        for i in gemini_indices(devices):
            cameras.append({'source': 'gemini-camera', 'name': devices.get_device_name_by_index(i)})
    except Exception as exc:
        diagnostics.append(f'Gemini 2 SDK discovery unavailable: {exc}; install .[camera] if missing')
    try:
        if os.name != 'nt' and cv2_module is None:
            raise DepthStrikeError('The legacy Astra adapter requires Windows x64')
        cv = cv2_module if cv2_module is not None else importlib.import_module('cv2')
        if enumerate_devices is None:
            enumerate_devices = importlib.import_module('cv2_enumerate_cameras').enumerate_cameras
        for camera in enumerate_devices(cv.CAP_DSHOW):
            if camera.vid == 0x2bc5 and camera.pid == 0x050f:
                cameras.append({'source': 'astra-camera', 'name': 'Astra 2bc5:060f / 2bc5:050f'})
    except Exception as exc:
        diagnostics.append(f'Astra discovery unavailable: {exc}; install .[astra] if missing')
    return {'cameras': cameras, 'diagnostics': diagnostics}


class AutoCameraSource:
    def __init__(self, config, directory=None, *, discover=None, gemini_factory=None, astra_factory=None):
        report = (discover or discover_cameras)()
        cameras = report['cameras']
        if not cameras:
            details = '; '.join(report['diagnostics'])
            raise DepthStrikeError('No supported Gemini 2 or Astra camera found. Check power, USB data cable '
                                  'and device ownership; run --list-cameras. ' + details)
        if len(cameras) != 1:
            raise DepthStrikeError('Multiple supported cameras found. Select --source gemini-camera or '
                                  '--source astra-camera; connect only one camera of each model.')
        self.selected_source = cameras[0]['source']
        self._closed = False
        if self.selected_source == 'gemini-camera':
            from .capture import GeminiSource
            self.capture = (gemini_factory or GeminiSource)(config)
        elif self.selected_source == 'astra-camera':
            from .astra_capture import AstraSource
            self.capture = (astra_factory or AstraSource)(config, directory)
        else:
            raise DepthStrikeError('Unsupported camera selection')

    def read(self): return self.capture.read()
    def describe(self):
        return {**self.capture.describe(), 'requested_camera_source': 'auto-camera',
                'selected_camera_source': self.selected_source}
    def close(self):
        if not self._closed:
            self._closed = True
            self.capture.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
