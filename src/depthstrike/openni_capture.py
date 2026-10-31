"""Legacy Astra 060f depth via the official OpenNI 2.3 Windows C API.

Native layouts and property IDs follow the SDK's OniCTypes.h/OniCProperties.h.
The runtime remains a separately downloaded local prerequisite.
"""
import ctypes as ct
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path

import numpy as np

from .types import DepthStrikeError, FrameTimeout, Intrinsics


class DeviceInfo(ct.Structure):
    _fields_ = [(name, ct.c_char * 256) for name in ("uri", "vendor", "name", "serial")] + [
        ("vid", ct.c_uint16), ("pid", ct.c_uint16)]


class VideoMode(ct.Structure):
    _fields_ = [(name, ct.c_int) for name in ("pixel_format", "width", "height", "fps")]


class SensorInfo(ct.Structure):
    _fields_ = [("sensor_type", ct.c_int), ("mode_count", ct.c_int),
                ("modes", ct.POINTER(VideoMode))]


class NativeFrame(ct.Structure):
    _fields_ = [("data_size", ct.c_int), ("data", ct.c_void_p), ("sensor_type", ct.c_int),
                ("timestamp_us", ct.c_uint64), ("frame_index", ct.c_int),
                ("width", ct.c_int), ("height", ct.c_int), ("video_mode", VideoMode),
                ("cropping", ct.c_int), ("crop_x", ct.c_int), ("crop_y", ct.c_int),
                ("stride", ct.c_int)]


class CameraParams(ct.Structure):
    _fields_ = [("depth_intrinsics", ct.c_float * 4), ("color_intrinsics", ct.c_float * 4),
                ("rotation", ct.c_float * 9), ("translation", ct.c_float * 3),
                ("depth_distortion", ct.c_float * 5), ("color_distortion", ct.c_float * 5)]


class NativeVersion(ct.Structure):
    _fields_ = [(name, ct.c_int) for name in ("major", "minor", "maintenance", "build")]


def factory_color_intrinsics(params):
    values = np.array([v for name, _ in CameraParams._fields_ for v in getattr(params, name)])
    fx, fy, cx, cy = params.color_intrinsics
    if (not np.isfinite(values).all() or not 100 < fx < 3000 or not 100 < fy < 3000
            or not 0 <= cx < 640 or not 0 <= cy < 480):
        raise DepthStrikeError("Astra factory calibration is not valid for the supported 640x480 grid")
    return Intrinsics(640, 480, fx, fy, cx, cy, "brown_conrady", tuple(params.color_distortion))


def copy_depth_frame(frame):
    """Validate native sizes before dereferencing memory; own the resulting data."""
    if (not frame.data or frame.sensor_type != 3 or frame.video_mode.pixel_format != 100
            or (frame.width, frame.height) != (640, 480) or frame.cropping
            or frame.crop_x or frame.crop_y or frame.stride < 1280 or frame.stride > 4096
            or frame.stride % 2 or frame.data_size != frame.stride * frame.height):
        raise DepthStrikeError("Unexpected Astra depth format, grid, crop or native buffer size")
    data = ct.cast(frame.data, ct.POINTER(ct.c_uint16))
    view = np.ctypeslib.as_array(data, shape=(frame.data_size // 2,))
    return view.reshape(frame.height, frame.stride // 2)[:, :frame.width].copy()


@dataclass(frozen=True)
class DepthSample:
    millimeters: np.ndarray
    timestamp_us: int
    frame_index: int


class OpenNI2Depth:
    def __init__(self, config, directory=None):
        self._closed = False
        self._initialized = False
        self._device = ct.c_void_p()
        self._stream = ct.c_void_p()
        self._dll_directory = None
        self.config = config
        self._last_timestamp = self._last_index = -1
        try:
            if os.name != "nt" or ct.sizeof(ct.c_void_p) != 8:
                raise DepthStrikeError("This Astra OpenNI adapter requires Windows x64")
            folder = Path(directory or ".cache/openni2").resolve()
            dll = folder / "OpenNI2.dll"
            if not dll.is_file() or not (folder / "OpenNI2/Drivers/orbbec.dll").is_file():
                raise DepthStrikeError("Astra OpenNI runtime missing. See docs/RUNNING.md; specify --openni-dir containing OpenNI2.dll and OpenNI2/Drivers.")
            self._dll_directory = os.add_dll_directory(str(folder))
            self.lib = ct.CDLL(str(dll))
            self._bind_api()
            version = self.lib.oniGetVersion()
            if tuple(getattr(version, name) for name, _ in NativeVersion._fields_) != (2, 3, 0, 86):
                raise DepthStrikeError("This Astra native layout requires official OpenNI 2.3.0.86 beta6; see docs/RUNNING.md")
            self._check(self.lib.oniInitialize(2003), "initialize OpenNI 2.3")
            self._initialized = True
            devices, count = ct.POINTER(DeviceInfo)(), ct.c_int()
            self._check(self.lib.oniGetDeviceList(ct.byref(devices), ct.byref(count)), "enumerate devices")
            try:
                matches = [bytes(devices[n].uri) for n in range(count.value)
                           if devices[n].vid == 0x2bc5 and devices[n].pid == 0x060f]
            finally:
                if devices:
                    self.lib.oniReleaseDeviceList(devices)
            if len(matches) != 1:
                raise DepthStrikeError(f"Expected one Astra 2bc5:060f depth device; found {len(matches)}. Check the official Astra driver, USB connection and device ownership.")
            self._check(self.lib.oniDeviceOpen(matches[0], ct.byref(self._device)), "open Astra depth device")
            info = self.lib.oniDeviceGetSensorInfo(self._device, 3)
            if not info or not 0 < info.contents.mode_count <= 256:
                raise DepthStrikeError("Astra did not expose a usable depth sensor")
            modes = info.contents.modes[:info.contents.mode_count]
            if not any((m.pixel_format, m.width, m.height, m.fps) == (100, 640, 480, 30) for m in modes):
                raise DepthStrikeError("Astra requires 640x480/30 depth in millimeters")
            self._check(self.lib.oniDeviceCreateStream(self._device, 3, ct.byref(self._stream)), "create depth stream")
            mode = VideoMode(100, 640, 480, 30)
            self._set_stream(3, mode)
            self._set_stream(7, ct.c_int(0))
            mirror = self._get_stream_int(7)
            if mirror != 0:
                raise DepthStrikeError("Astra depth mirroring could not be disabled")
            if not self.lib.oniDeviceIsImageRegistrationModeSupported(self._device, 1):
                raise DepthStrikeError("Astra does not support factory depth-to-color registration")
            self._set_device(5, ct.c_int(1))
            registration = ct.c_int()
            self._get_device(5, registration)
            if registration.value != 1:
                raise DepthStrikeError("Astra depth-to-color registration was not enabled")
            params = CameraParams()
            self._get_device(14, params)
            self.intrinsics = factory_color_intrinsics(params)
            self.metadata = {"device": "Astra 2bc5:060f", "openni_version": ".".join(str(getattr(version, n)) for n, _ in NativeVersion._fields_),
                "openni_dll_sha256": hashlib.sha256(dll.read_bytes()).hexdigest(),
                "depth_mode": "640x480/30 DEPTH_1_MM", "registration_readback": registration.value,
                "intrinsics": vars(self.intrinsics)}
            self._check(self.lib.oniStreamStart(self._stream), "start Astra depth")
        except BaseException as exc:
            self.close()
            if isinstance(exc, (OSError, AttributeError)):
                raise DepthStrikeError(f"Astra OpenNI runtime could not load: {exc}. Check the official Win64 runtime and VC++ dependencies.") from exc
            raise

    def _bind_api(self):
        pointer = ct.c_void_p
        signatures = {
            "oniInitialize": (ct.c_int, [ct.c_int]), "oniShutdown": (None, []),
            "oniGetVersion": (NativeVersion, []), "oniGetExtendedError": (ct.c_char_p, []),
            "oniGetDeviceList": (ct.c_int, [ct.POINTER(ct.POINTER(DeviceInfo)), ct.POINTER(ct.c_int)]),
            "oniReleaseDeviceList": (ct.c_int, [ct.POINTER(DeviceInfo)]),
            "oniDeviceOpen": (ct.c_int, [ct.c_char_p, ct.POINTER(pointer)]),
            "oniDeviceClose": (ct.c_int, [pointer]),
            "oniDeviceGetSensorInfo": (ct.POINTER(SensorInfo), [pointer, ct.c_int]),
            "oniDeviceCreateStream": (ct.c_int, [pointer, ct.c_int, ct.POINTER(pointer)]),
            "oniDeviceIsImageRegistrationModeSupported": (ct.c_int, [pointer, ct.c_int]),
            "oniDeviceGetProperty": (ct.c_int, [pointer, ct.c_int, pointer, ct.POINTER(ct.c_int)]),
            "oniDeviceSetProperty": (ct.c_int, [pointer, ct.c_int, pointer, ct.c_int]),
            "oniStreamGetProperty": (ct.c_int, [pointer, ct.c_int, pointer, ct.POINTER(ct.c_int)]),
            "oniStreamSetProperty": (ct.c_int, [pointer, ct.c_int, pointer, ct.c_int]),
            "oniStreamStart": (ct.c_int, [pointer]), "oniStreamStop": (None, [pointer]),
            "oniStreamDestroy": (None, [pointer]),
            "oniWaitForAnyStream": (ct.c_int, [ct.POINTER(pointer), ct.c_int, ct.POINTER(ct.c_int), ct.c_int]),
            "oniStreamReadFrame": (ct.c_int, [pointer, ct.POINTER(ct.POINTER(NativeFrame))]),
            "oniFrameRelease": (None, [ct.POINTER(NativeFrame)]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, args

    def _check(self, status, action):
        if status:
            detail = (self.lib.oniGetExtendedError() or b"").decode(errors="replace")
            raise DepthStrikeError(f"Astra could not {action}: OpenNI {status}: {detail}")

    def _set_stream(self, prop, value):
        self._check(self.lib.oniStreamSetProperty(self._stream, prop, ct.byref(value), ct.sizeof(value)), f"set stream property {prop}")

    def _set_device(self, prop, value):
        self._check(self.lib.oniDeviceSetProperty(self._device, prop, ct.byref(value), ct.sizeof(value)), f"set device property {prop}")

    def _get_device(self, prop, value):
        size = ct.c_int(ct.sizeof(value))
        self._check(self.lib.oniDeviceGetProperty(self._device, prop, ct.byref(value), ct.byref(size)), f"read device property {prop}")
        if size.value != ct.sizeof(value):
            raise DepthStrikeError("Unexpected Astra calibration/property layout")

    def _get_stream_int(self, prop):
        value, size = ct.c_int(), ct.c_int(ct.sizeof(ct.c_int))
        self._check(self.lib.oniStreamGetProperty(self._stream, prop, ct.byref(value), ct.byref(size)), f"read stream property {prop}")
        return value.value

    def read(self):
        if self._closed:
            raise DepthStrikeError("Astra depth source already closed")
        streams, index = (ct.c_void_p * 1)(self._stream.value), ct.c_int()
        status = self.lib.oniWaitForAnyStream(streams, 1, ct.byref(index), self.config.camera_timeout_ms)
        if status == 102:
            raise FrameTimeout("Waiting for Astra depth")
        self._check(status, "wait for depth")
        frame = ct.POINTER(NativeFrame)()
        self._check(self.lib.oniStreamReadFrame(self._stream, ct.byref(frame)), "read depth")
        try:
            if not frame:
                raise DepthStrikeError("Astra returned a null depth frame")
            value = frame.contents
            if value.timestamp_us <= self._last_timestamp or value.frame_index <= self._last_index:
                raise FrameTimeout("Repeated or reversed Astra depth frame")
            result = DepthSample(copy_depth_frame(value), int(value.timestamp_us), value.frame_index)
            self._last_timestamp, self._last_index = result.timestamp_us, result.frame_index
            return result
        finally:
            if frame:
                self.lib.oniFrameRelease(frame)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._stream:
                self.lib.oniStreamStop(self._stream)
                self.lib.oniStreamDestroy(self._stream)
            if self._device:
                self.lib.oniDeviceClose(self._device)
            if self._initialized:
                self.lib.oniShutdown()
        finally:
            if self._dll_directory is not None:
                self._dll_directory.close()
