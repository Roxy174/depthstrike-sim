"""Gemini RGB-D acquisition using software D2C, with no import-time SDK load."""
from __future__ import annotations

import importlib

import numpy as np

from .config import AppConfig
from .types import DepthStrikeError, FrameTimeout, Intrinsics, RGBDFrame


def decode_color(frame) -> np.ndarray:
    fmt = str(frame.get_format()).split(".")[-1].upper()
    data = np.frombuffer(frame.get_data(), dtype=np.uint8)
    h, w = frame.get_height(), frame.get_width()
    if fmt in ("RGB", "BGR"):
        image = data.reshape(h, w, 3)
        return (image if fmt == "RGB" else image[..., ::-1]).copy()
    if fmt == "MJPG":
        import cv2
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None or image.shape != (h, w, 3):
            raise ValueError("Invalid MJPG color frame")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    raise ValueError(f"Unsupported color format {fmt}; select RGB/BGR/MJPG")


def _intrinsics(profile, legacy_model="unknown") -> Intrinsics:
    profile = profile.as_video_stream_profile()
    intr = profile.get_intrinsic()
    dist = profile.get_distortion()
    coefficients = tuple(float(getattr(dist, k)) for k in ("k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6"))
    if hasattr(dist, "model"):
        model = str(dist.model).split(".")[-1].upper()
    elif not any(abs(k) > 1e-12 for k in coefficients):
        model = "NONE"
    elif legacy_model != "unknown":
        model = legacy_model.upper()
    else:
        raise ValueError("SDK does not expose distortion.model. Verify the device calibration model, then set legacy_sdk_distortion_model in config (e.g. brown_conrady); do not guess.")
    if model in {"NONE", "OB_DISTORTION_NONE"}:
        name = "none"
    elif model in {"BROWN_CONRADY", "OB_DISTORTION_BROWN_CONRADY"}:
        name = "brown_conrady"
    else:
        raise ValueError(f"Unsupported SDK distortion model {model}; calibration must be verified")
    return Intrinsics(intr.width, intr.height, intr.fx, intr.fy, intr.cx, intr.cy, name, coefficients)


def convert_frames(color, depth, frame_id: int, config: AppConfig) -> RGBDFrame:
    color_t, depth_t = color.get_timestamp()/1000., depth.get_timestamp()/1000.
    if not np.isfinite((color_t, depth_t)).all() or abs(color_t-depth_t) > config.frame_sync_tolerance_s:
        raise FrameTimeout("Rejected RGB/depth pair with mismatched timestamps")
    scale = float(depth.get_depth_scale())
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("Depth scale must be finite and positive (SDK mm/unit)")
    if str(depth.get_format()).split(".")[-1].upper() != "Y16":
        raise ValueError("Expected SDK Y16 depth format")
    array = np.frombuffer(depth.get_data(), dtype=np.uint16).reshape(depth.get_height(), depth.get_width())
    depth_m = array.astype(np.float32)*(scale/1000.)
    return RGBDFrame(frame_id, color_t, decode_color(color), depth_m,
                     _intrinsics(color.get_stream_profile(), config.legacy_sdk_distortion_model))


class GeminiSource:
    def __init__(self, config: AppConfig, *, sdk=None):
        self.config = config
        self.pipeline = None
        self._closed = False
        self._frame_id = 0
        self._last_t = -1.
        self._description = {"source": "Gemini 2", "alignment": "software D2C", "unit": "m"}
        try:
            self.sdk = sdk if sdk is not None else importlib.import_module("pyorbbecsdk")
        except (ImportError, OSError) as exc:
            raise DepthStrikeError('Orbbec SDK unavailable; install: python -m pip install -e ".[camera]"; check Windows VC++ runtime') from exc
        try:
            self.context = self.sdk.Context()
            devices = self.context.query_devices()
            if devices.get_count() == 0:
                raise DepthStrikeError("No Orbbec camera found. Connect Gemini 2 via USB 3 and close Orbbec Viewer.")
            self.pipeline = self.sdk.Pipeline()
            stream_config = self.sdk.Config()
            colors = self.pipeline.get_stream_profile_list(self.sdk.OBSensorType.COLOR_SENSOR)
            try:
                color_profile = colors.get_video_stream_profile(640, 480, self.sdk.OBFormat.RGB, 30)
            except Exception:
                color_profile = colors.get_video_stream_profile(0, 0, self.sdk.OBFormat.RGB, 0)
            depths = self.pipeline.get_stream_profile_list(self.sdk.OBSensorType.DEPTH_SENSOR)
            depth_profile = depths.get_default_video_stream_profile()
            stream_config.enable_stream(color_profile)
            stream_config.enable_stream(depth_profile)
            stream_config.set_frame_aggregate_output_mode(self.sdk.OBFrameAggregateOutputMode.FULL_FRAME_REQUIRE)
            self.pipeline.enable_frame_sync()
            self.align_filter = self.sdk.AlignFilter(align_to_stream=self.sdk.OBStreamType.COLOR_STREAM)
            self.pipeline.start(stream_config)
            self._description.update(color_profile=str(color_profile), depth_profile=str(depth_profile))
            if hasattr(self.pipeline, "get_device"):
                info = self.pipeline.get_device().get_device_info()
                self._description.update(name=info.get_name(), firmware=info.get_firmware_version())
        except Exception as exc:
            self.close()
            if isinstance(exc, DepthStrikeError):
                raise
            raise DepthStrikeError(f"Gemini RGB-D start failed: {exc}. Check USB, Viewer ownership, SDK/firmware compatibility.") from exc

    def read(self) -> RGBDFrame:
        if self._closed:
            raise DepthStrikeError("Camera already closed")
        frames = self.pipeline.wait_for_frames(self.config.camera_timeout_ms)
        if frames is None:
            raise FrameTimeout("Waiting for matching RGB-D frames")
        # Check original pair as alignment must not conceal a time mismatch.
        color, depth = frames.get_color_frame(), frames.get_depth_frame()
        if not color or not depth:
            raise FrameTimeout("Incomplete RGB-D frame pair")
        if abs(color.get_timestamp()-depth.get_timestamp())/1000. > self.config.frame_sync_tolerance_s:
            raise FrameTimeout("RGB/depth synchronization mismatch")
        aligned = self.align_filter.process(frames)
        if aligned is None:
            raise FrameTimeout("Depth alignment produced no frame")
        aligned = aligned.as_frame_set()
        color, depth = aligned.get_color_frame(), aligned.get_depth_frame()
        if not color or not depth:
            raise FrameTimeout("Aligned RGB-D pair incomplete")
        result = convert_frames(color, depth, self._frame_id, self.config)
        if result.timestamp_s <= self._last_t:
            raise FrameTimeout("Repeated or reversed camera timestamp")
        self._last_t = result.timestamp_s
        self._frame_id += 1
        self._description["intrinsics"] = vars(result.intrinsics)
        return result

    def describe(self) -> dict:
        return dict(self._description)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                # An unsuccessful start may have nothing running; original error wins.
                pass

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
