"""Explicit Astra RGB-D experience: OpenNI D2C depth plus its UVC color sensor.

Read completion times bound host delivery separation. They do not measure or
verify exposure synchronization between the two independent interfaces.
"""
import time

import numpy as np

from .openni_capture import OpenNI2Depth
from .types import DepthStrikeError, FrameTimeout, RGBDFrame


class AstraSource:
    def __init__(self, config, directory=None, *, depth=None, cv2_module=None,
                 enumerate_devices=None, clock=time.monotonic):
        self.config, self.clock = config, clock
        self.depth = self.cap = None
        self._closed = False
        self._frame_id, self._last_t = 0, -1.
        self._started = clock()
        self.last_pair_host_delta_s = None
        try:
            self.depth = depth if depth is not None else OpenNI2Depth(config, directory)
            if cv2_module is None:
                import cv2 as cv2_module
            self.cv2 = cv2_module
            if enumerate_devices is None:
                try:
                    from cv2_enumerate_cameras import enumerate_cameras
                except ImportError as exc:
                    raise DepthStrikeError('Install Astra dependencies: python -m pip install -e ".[astra]"') from exc
                enumerate_devices = enumerate_cameras
            cameras = [c for c in enumerate_devices(self.cv2.CAP_DSHOW)
                       if c.vid == 0x2bc5 and c.pid == 0x050f]
            if len(cameras) != 1:
                raise DepthStrikeError(f"Expected one Astra 2bc5:050f color interface; found {len(cameras)}. Connect a single Astra and close other camera programs.")
            self.cap = self.cv2.VideoCapture(cameras[0].index, self.cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                raise DepthStrikeError("Astra color interface could not open")
            for prop, value in ((self.cv2.CAP_PROP_FRAME_WIDTH, 640),
                                (self.cv2.CAP_PROP_FRAME_HEIGHT, 480), (self.cv2.CAP_PROP_FPS, 30)):
                self.cap.set(prop, value)
        except BaseException as exc:
            self.close()
            if isinstance(exc, Exception) and not isinstance(exc, DepthStrikeError):
                raise DepthStrikeError(f"Astra initialization failed: {exc}. Check the OpenNI runtime and install .[astra].") from exc
            raise

    def read(self):
        try:
            return self._read()
        except (FrameTimeout, DepthStrikeError):
            raise
        except Exception as exc:
            raise DepthStrikeError(f"Astra RGB-D capture failed: {exc}. Check USB connection and device ownership.") from exc

    def _read(self):
        if self._closed:
            raise DepthStrikeError("Astra source already closed")
        ok, bgr = self.cap.read()
        color_completed = self.clock()
        if not ok or bgr is None:
            raise FrameTimeout("Waiting for Astra color")
        if bgr.shape != (480, 640, 3) or bgr.dtype != np.uint8:
            raise DepthStrikeError("Astra color grid/dtype changed; expected uint8 BGR 640x480")
        depth = self.depth.read()
        depth_completed = self.clock()
        self.last_pair_host_delta_s = abs(depth_completed - color_completed)
        if self.last_pair_host_delta_s > self.config.frame_sync_tolerance_s:
            raise FrameTimeout("Astra host read completions too far apart; exposure synchronization remains unverified")
        if depth.millimeters.shape != (480, 640) or depth.millimeters.dtype != np.uint16:
            raise DepthStrikeError("Astra depth grid/dtype changed; expected uint16 millimeters 640x480")
        timestamp = (color_completed + depth_completed) / 2 - self._started
        if not np.isfinite(timestamp) or timestamp < 0 or timestamp <= self._last_t:
            raise FrameTimeout("Nonincreasing Astra host clock")
        result = RGBDFrame(self._frame_id, timestamp, bgr[..., ::-1].copy(),
                          depth.millimeters.astype(np.float32) / 1000., self.depth.intrinsics)
        self._frame_id += 1
        self._last_t = timestamp
        return result

    def describe(self):
        return {"source": "Astra OpenNI experience", "capture_backend": "openni2_astra_uvc",
                "evidence": "unverified", "unit": "m", "depth_backend": dict(self.depth.metadata),
                "timestamp_source": "host_monotonic_read_completion_midpoint",
                "synchronization": "unverified_independent_OpenNI_depth_and_UVC_color",
                "alignment": "factory_OpenNI_D2C_requested_and_read_back_not_independently_measured",
                "calibration_scope": "factory_color_Brown_Conrady_640x480_not_independent_accuracy",
                "intrinsics": vars(self.depth.intrinsics)}

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.cap is not None:
                self.cap.release()
        finally:
            if self.depth is not None:
                self.depth.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
