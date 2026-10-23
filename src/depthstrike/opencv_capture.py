"""Explicit LAB3-style experience capture, not hardware-synchronized metrology."""
import importlib
import time

import numpy as np

from .types import DepthStrikeError, FrameTimeout, Intrinsics, RGBDFrame


class OpenCVSource:
    def __init__(self, config, *, cv2_module=None, clock=time.monotonic):
        self.config, self.clock = config, clock
        self.cap = None
        self._closed = False
        self._frame_id = 0
        self._last_t = -1.
        self._intrinsics = None
        self._started = clock()
        try:
            self.cv2 = cv2_module if cv2_module is not None else importlib.import_module("cv2")
            self.cap = self.cv2.VideoCapture(0, self.cv2.CAP_OBSENSOR)
            if not self.cap.isOpened():
                raise DepthStrikeError("OpenCV OBSENSOR could not open Gemini. Check USB 3 and close other camera programs.")
            self._parameters = tuple(float(self.cap.get(getattr(self.cv2, "CAP_PROP_OBSENSOR_INTRINSIC_"+name)))
                                     for name in ("FX", "FY", "CX", "CY"))
            if not np.isfinite(self._parameters).all() or min(self._parameters[:2]) <= 0:
                raise DepthStrikeError("OpenCV returned invalid camera intrinsics")
        except Exception as exc:
            self.close()
            if isinstance(exc, DepthStrikeError): raise
            raise DepthStrikeError(f"OpenCV OBSENSOR initialization failed: {exc}") from exc

    def read(self):
        if self._closed: raise DepthStrikeError("OpenCV camera already closed")
        try:
            if not self.cap.grab(): raise FrameTimeout("Waiting for OpenCV RGB-D pair")
            ok_color, bgr = self.cap.retrieve(None, self.cv2.CAP_OBSENSOR_BGR_IMAGE)
            ok_depth, depth = self.cap.retrieve(None, self.cv2.CAP_OBSENSOR_DEPTH_MAP)
            if not ok_color or not ok_depth or bgr is None or depth is None or not bgr.size or not depth.size:
                raise FrameTimeout("Incomplete OpenCV RGB-D pair")
            if (depth.ndim != 2 or bgr.shape != (*depth.shape, 3)
                    or bgr.dtype != np.uint8 or depth.dtype != np.uint16):
                raise DepthStrikeError("OpenCV RGB-D grid or dtype mismatch; expected uint8 BGR and uint16 millimeter depth")
            h, w = depth.shape
            if self._intrinsics is None:
                # This explicit model must not be confused with verified zero distortion.
                self._intrinsics = Intrinsics(w, h, *self._parameters, "pinhole_approximation")
            elif (w, h) != (self._intrinsics.width, self._intrinsics.height):
                raise DepthStrikeError("OpenCV image dimensions changed; restart capture")
            timestamp = self.clock()-self._started
            if not np.isfinite(timestamp) or timestamp < 0 or timestamp <= self._last_t:
                raise FrameTimeout("Nonincreasing OpenCV host read clock")
            frame = RGBDFrame(self._frame_id, float(timestamp), bgr[..., ::-1].copy(),
                              depth.astype(np.float32)/1000., self._intrinsics)
            self._frame_id += 1
            self._last_t = timestamp
            return frame
        except (FrameTimeout, DepthStrikeError):
            raise
        except Exception as exc:
            raise DepthStrikeError(f"OpenCV OBSENSOR read failed: {exc}") from exc

    def describe(self):
        return {"source": "OpenCV Gemini experience", "capture_backend": "opencv_obsensor",
            "opencv_version": self.cv2.__version__, "evidence": "unverified", "unit": "m",
            "timestamp_source": "host_monotonic_read_completion",
            "synchronization": "unverified_no_device_timestamps",
            "alignment": "backend_D2C_same_grab_grid_check_only",
            "calibration_scope": "backend_intrinsics_pinhole_approximation",
            "intrinsics": None if self._intrinsics is None else vars(self._intrinsics),
            "backend_intrinsics_fx_fy_cx_cy": self._parameters}

    def close(self):
        if not self._closed:
            self._closed = True
            if self.cap is not None: self.cap.release()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
