from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from depthstrike.config import AppConfig
from depthstrike.types import DepthStrikeError, FrameTimeout


class VideoFrame:
    def __init__(self, data, fmt="RGB", timestamp=1000., scale=1.):
        self.data, self.fmt, self.timestamp, self.scale = data, fmt, timestamp, scale
    def get_data(self): return self.data.tobytes()
    def get_format(self): return self.fmt
    def get_width(self): return 4
    def get_height(self): return 3
    def get_timestamp(self): return self.timestamp
    def get_depth_scale(self): return self.scale
    def get_stream_profile(self): return self
    def as_video_stream_profile(self): return self
    def get_intrinsic(self): return SimpleNamespace(width=4, height=3, fx=6., fy=6., cx=2., cy=1.5)
    def get_distortion(self): return SimpleNamespace(model="NONE", k1=0, k2=0, k3=0, k4=0, k5=0, k6=0, p1=0, p2=0)


@pytest.mark.parametrize("fmt,pixel", [("RGB", (10, 20, 30)), ("BGR", (30, 20, 10))])
def test_color_and_millimeter_conversion(fmt, pixel):
    from depthstrike.capture import convert_frames
    color = VideoFrame(np.tile(pixel, (3, 4, 1)).astype(np.uint8), fmt)
    depth = VideoFrame(np.full((3, 4), 4000, np.uint16), "Y16", scale=.5)
    frame = convert_frames(color, depth, 0, AppConfig())
    assert tuple(frame.color_rgb[0, 0]) == (10, 20, 30)
    assert frame.depth_m[0, 0] == 2.
    assert frame.timestamp_s == 1.


def test_mjpg_decodes_to_rgb():
    cv2 = pytest.importorskip("cv2")
    from depthstrike.capture import decode_color
    ok, encoded = cv2.imencode(".jpg", np.full((3, 4, 3), (20, 40, 80), np.uint8))
    assert ok
    assert tuple(map(int, decode_color(VideoFrame(encoded, "MJPG"))[0, 0])) == pytest.approx((80, 40, 20), abs=3)


def test_mismatched_timestamps_and_invalid_scale_rejected():
    from depthstrike.capture import convert_frames
    color = VideoFrame(np.zeros((3, 4, 3), np.uint8))
    depth = VideoFrame(np.zeros((3, 4), np.uint16), "Y16", timestamp=1100)
    with pytest.raises(FrameTimeout):
        convert_frames(color, depth, 0, AppConfig())


def test_legacy_sdk_unknown_nonzero_distortion_requires_explicit_model():
    from depthstrike.capture import convert_frames
    color = VideoFrame(np.zeros((3, 4, 3), np.uint8))
    depth = VideoFrame(np.ones((3, 4), np.uint16), "Y16")
    color.get_distortion = lambda: SimpleNamespace(k1=.1, k2=0, k3=0, k4=0, k5=0, k6=0, p1=0, p2=0)
    with pytest.raises(ValueError, match="legacy_sdk_distortion_model"):
        convert_frames(color, depth, 0, AppConfig())
    verified = replace(AppConfig(), legacy_sdk_distortion_model="brown_conrady")
    assert convert_frames(color, depth, 0, verified).intrinsics.distortion_model == "brown_conrady"
    depth.timestamp, depth.scale = 1000, 0
    with pytest.raises(ValueError, match="scale"):
        convert_frames(color, depth, 0, AppConfig())


def test_no_device_has_actionable_error():
    from depthstrike.capture import GeminiSource
    sdk = SimpleNamespace(Context=lambda: SimpleNamespace(query_devices=lambda: SimpleNamespace(get_count=lambda: 0)))
    with pytest.raises(DepthStrikeError, match="USB|camera|Gemini"):
        GeminiSource(AppConfig(), sdk=sdk)


def sdk_boundary(fail_start=False):
    class Pipeline:
        stopped = False
        def get_stream_profile_list(self, sensor): return self
        def get_video_stream_profile(self, *args): return self
        def get_default_video_stream_profile(self): return self
        def enable_frame_sync(self): pass
        def start(self, config):
            if fail_start: raise RuntimeError("busy")
        def stop(self): self.stopped = True
        def wait_for_frames(self, timeout): return None
    pipeline = Pipeline()
    sdk = SimpleNamespace(
        Context=lambda: SimpleNamespace(query_devices=lambda: SimpleNamespace(get_count=lambda: 1)),
        Pipeline=lambda: pipeline,
        Config=lambda: SimpleNamespace(enable_stream=lambda p: None, set_frame_aggregate_output_mode=lambda m: None),
        OBFormat=SimpleNamespace(RGB="RGB"),
        OBSensorType=SimpleNamespace(COLOR_SENSOR=1, DEPTH_SENSOR=2),
        OBStreamType=SimpleNamespace(COLOR_STREAM=1),
        OBFrameAggregateOutputMode=SimpleNamespace(FULL_FRAME_REQUIRE=1),
        AlignFilter=lambda **kw: SimpleNamespace(process=lambda f: f),
    )
    return sdk, pipeline


def test_capture_timeout_is_not_eof_and_close_releases_pipeline():
    from depthstrike.capture import GeminiSource
    sdk, pipeline = sdk_boundary()
    with GeminiSource(AppConfig(), sdk=sdk) as source:
        with pytest.raises(FrameTimeout): source.read()
    assert pipeline.stopped


def test_partial_start_failure_releases_pipeline():
    from depthstrike.capture import GeminiSource
    sdk, pipeline = sdk_boundary(fail_start=True)
    with pytest.raises(DepthStrikeError, match="busy"):
        GeminiSource(AppConfig(), sdk=sdk)
    assert pipeline.stopped


def test_missing_model_does_not_download_implicitly(tmp_path):
    from depthstrike.pose import PoseEstimator
    with pytest.raises(DepthStrikeError, match="download_pose_model"):
        PoseEstimator(replace(AppConfig(), model_path=str(tmp_path / "missing.task")))
    assert not list(tmp_path.iterdir())


def test_pose_video_timestamp_and_confidence(skeleton):
    from depthstrike.pose import landmarks_from_result, video_timestamp_ms
    pts = [SimpleNamespace(x=.5, y=.5, visibility=.95, presence=.8) for _ in range(33)]
    result = SimpleNamespace(pose_landmarks=[pts], segmentation_masks=[])
    assert landmarks_from_result(result, 4, 3)["left_wrist"].confidence == .8
    assert video_timestamp_ms(.1, 99) == 100
    with pytest.raises(FrameTimeout): video_timestamp_ms(.1, 100)


def test_inference_failure_closes_source_and_estimator():
    from depthstrike.sources import CameraPoseSource
    from test_fusion import rgbd
    class Capture:
        closed = False
        def read(self): return rgbd()
        def close(self): self.closed = True
    class Pose:
        closed = False
        def detect(self, frame): raise RuntimeError("inference failed")
        def close(self): self.closed = True
    capture, pose = Capture(), Pose()
    with pytest.raises(RuntimeError, match="inference"):
        with CameraPoseSource(AppConfig(), capture=capture, estimator=pose) as source:
            source.read()
    assert capture.closed and pose.closed


def test_explicit_model_download_records_digest_and_never_overwrites(tmp_path):
    import hashlib
    import io
    import runpy
    api = runpy.run_path("scripts/download_pose_model.py")
    data = b"synthetic model download boundary"
    destination = tmp_path / "pose.task"
    result = api["download_model"](destination, opener=lambda url, timeout: io.BytesIO(data))
    assert destination.read_bytes() == data
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    with pytest.raises(FileExistsError):
        api["download_model"](destination, opener=lambda url, timeout: io.BytesIO(b"overwrite"))
    assert destination.read_bytes() == data


def test_real_model_opens_from_unicode_directory(tmp_path):
    from pathlib import Path
    pytest.importorskip("mediapipe")
    from depthstrike.pose import PoseEstimator
    from test_fusion import rgbd
    model = Path("models/pose_landmarker_lite.task")
    if not model.is_file():
        pytest.skip("Optional official model not downloaded")
    target = tmp_path / "模型目录" / "pose.task"
    target.parent.mkdir()
    target.write_bytes(model.read_bytes())
    with PoseEstimator(replace(AppConfig(), model_path=str(target))) as pose:
        assert pose.detect(rgbd()) == {}


def test_rgbd_replay_actions_reach_skeleton_source(tmp_path):
    from depthstrike.recording import RGBDRecorder, RGBDReplaySource
    from depthstrike.sources import CameraPoseSource
    from test_fusion import rgbd
    with RGBDRecorder(tmp_path/"rgbd", AppConfig()) as recorder:
        recorder.write(rgbd(), actions=["pause"])
    estimator = SimpleNamespace(detect=lambda f: {}, close=lambda: None)
    with CameraPoseSource(AppConfig(), capture=RGBDReplaySource(tmp_path/"rgbd"), estimator=estimator) as source:
        source.read()
        assert source.actions == ["pause"]


def test_recording_metadata_identifies_pose_model():
    from depthstrike.sources import CameraPoseSource
    capture = SimpleNamespace(close=lambda: None, describe=lambda: {"firmware": "test"})
    estimator = SimpleNamespace(close=lambda: None, metadata={"sha256": "known-model-digest"})
    with CameraPoseSource(AppConfig(), capture=capture, estimator=estimator) as source:
        assert source.describe()["pose_model"]["sha256"] == "known-model-digest"


def test_sdk_exception_during_capture_is_actionable_and_releases_device():
    from depthstrike.capture import GeminiSource
    class SDKError(Exception): pass
    sdk, pipeline = sdk_boundary()
    def fail(timeout): raise SDKError("device disconnected")
    pipeline.wait_for_frames = fail
    with pytest.raises(DepthStrikeError, match="disconnected"):
        with GeminiSource(AppConfig(), sdk=sdk) as source: source.read()
    assert pipeline.stopped
