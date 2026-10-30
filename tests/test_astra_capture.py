from types import SimpleNamespace

import numpy as np
import pytest

from depthstrike.astra_capture import AstraSource
from depthstrike.config import AppConfig
from depthstrike.openni_capture import CameraParams, DepthSample, NativeFrame, VideoMode, copy_depth_frame, factory_color_intrinsics
from depthstrike.types import DepthStrikeError, FrameTimeout, Intrinsics


class Depth:
    def __init__(self):
        self.intrinsics = Intrinsics(640, 480, 545., 546., 324., 235., "brown_conrady", (0.,) * 5)
        self.metadata = {"device": "test Astra", "registration_readback": 1}
        self.array = np.full((480, 640), 1250, np.uint16)
        self.closed = 0

    def read(self):
        return DepthSample(self.array, 100000, 4)

    def close(self): self.closed += 1


class Color:
    def __init__(self):
        self.bgr = np.full((480, 640, 3), (10, 20, 30), np.uint8)
        self.released = 0

    def isOpened(self): return True
    def set(self, *args): return True
    def read(self): return True, self.bgr
    def release(self): self.released += 1


def source(*, times=(0., .1, .11), cameras=None, color=None, depth=None):
    depth, color = depth or Depth(), color or Color()
    opened = []
    def open_color(index, backend):
        opened.append((index, backend))
        return color
    cv = SimpleNamespace(CAP_DSHOW=700, CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4,
                         CAP_PROP_FPS=5, VideoCapture=open_color)
    rows = cameras if cameras is not None else [SimpleNamespace(index=7, vid=0x2bc5, pid=0x050f)]
    ticks = iter(times)
    capture = AstraSource(AppConfig(), depth=depth, cv2_module=cv,
                          enumerate_devices=lambda backend: rows, clock=lambda: next(ticks))
    return capture, depth, color, opened


def test_astra_pairs_measured_depth_and_matching_color_without_choosing_index_zero():
    capture, depth, color, opened = source()
    with capture:
        frame = capture.read()
        assert opened == [(7, 700)]
        assert frame.timestamp_s == pytest.approx(.105)
        assert frame.color_rgb[0, 0].tolist() == [30, 20, 10]
        assert frame.depth_m[0, 0] == pytest.approx(1.25)
        depth.array[:] = 0
        color.bgr[:] = 0
        assert frame.depth_m[0, 0] == pytest.approx(1.25)
        assert frame.color_rgb[0, 0].tolist() == [30, 20, 10]
        assert capture.describe()["evidence"] == "unverified"
        assert frame.intrinsics.distortion_model == "brown_conrady"
    capture.close()
    assert depth.closed == color.released == 1


@pytest.mark.parametrize("cameras", [[], [SimpleNamespace(index=0, vid=123, pid=456)],
    [SimpleNamespace(index=n, vid=0x2bc5, pid=0x050f) for n in (0, 1)]])
def test_absent_or_ambiguous_astra_color_closes_depth_and_never_uses_a_webcam(cameras):
    depth = Depth()
    with pytest.raises(DepthStrikeError, match="Expected one Astra"):
        source(cameras=cameras, depth=depth)
    assert depth.closed == 1


def test_late_host_pair_is_rejected_and_next_pair_can_recover():
    capture, depth, color, _ = source(times=(0., .1, .2, .3, .31))
    with capture:
        with pytest.raises(FrameTimeout, match="too far apart"):
            capture.read()
        frame = capture.read()
        assert frame.frame_id == 0
        assert frame.timestamp_s == pytest.approx(.305)
    assert depth.closed == color.released == 1


@pytest.mark.parametrize("side", ["color", "depth"])
def test_changed_capture_grid_fails_instead_of_resizing_a_depth_map(side):
    depth, color = Depth(), Color()
    if side == "color": color.bgr = np.zeros((240, 320, 3), np.uint8)
    else: depth.array = np.zeros((240, 320), np.uint16)
    capture, _, _, _ = source(depth=depth, color=color)
    with capture, pytest.raises(DepthStrikeError, match="grid/dtype changed"):
        capture.read()
    assert depth.closed == color.released == 1


def test_native_color_exception_is_actionable_and_both_interfaces_are_released():
    class BackendError(Exception): pass
    class BrokenColor(Color):
        def read(self): raise BackendError("device disconnected")
    capture, depth, color, _ = source(color=BrokenColor())
    with capture, pytest.raises(DepthStrikeError, match="device disconnected"):
        capture.read()
    assert depth.closed == color.released == 1


def native_frame(buffer, stride):
    frame = NativeFrame()
    frame.data = buffer.ctypes.data
    frame.data_size = buffer.nbytes
    frame.sensor_type = 3
    frame.width, frame.height, frame.stride = 640, 480, stride
    frame.video_mode = VideoMode(100, 640, 480, 30)
    return frame


def test_native_depth_stride_padding_is_removed_and_frame_memory_is_not_retained():
    buffer = np.full((480, 641), 2345, np.uint16)
    buffer[:, -1] = 65535
    result = copy_depth_frame(native_frame(buffer, buffer.strides[0]))
    buffer[:] = 0
    assert result.shape == (480, 640)
    assert np.all(result == 2345)


@pytest.mark.parametrize("field,value", [("data", None), ("data_size", 2), ("stride", 1278),
                                        ("width", 320), ("cropping", 1), ("sensor_type", 2)])
def test_invalid_native_buffers_are_rejected_before_reading_memory(field, value):
    frame = native_frame(np.zeros((480, 640), np.uint16), 1280)
    setattr(frame, field, value)
    with pytest.raises(DepthStrikeError, match="native buffer"):
        copy_depth_frame(frame)


def test_factory_color_distortion_is_preserved_and_invalid_calibration_is_rejected():
    params = CameraParams()
    params.color_intrinsics[:] = (545., 546., 324., 235.)
    params.color_distortion[:] = (.1, -.2, .002, -.003, .09)
    intrinsics = factory_color_intrinsics(params)
    assert intrinsics.distortion == pytest.approx((.1, -.2, .002, -.003, .09))
    params.color_intrinsics[0] = float("nan")
    with pytest.raises(DepthStrikeError, match="factory calibration"):
        factory_color_intrinsics(params)


def test_astra_provenance_warning_survives_pose_transcription(monkeypatch, tmp_path, capsys):
    from depthstrike import cli
    from depthstrike.recording import PoseReplaySource
    from depthstrike.sources import DemoPoseSource
    class FakeAstra(DemoPoseSource):
        def __init__(self, config, directory): super().__init__(config=config)
        def describe(self):
            return {"capture_backend": "openni2_astra_uvc", "evidence": "unverified"}
    monkeypatch.setattr(cli, "AstraSource", FakeAstra)
    monkeypatch.setattr(cli, "CameraPoseSource", lambda config, capture, metrics: capture)
    first, second = tmp_path/"first.jsonl", tmp_path/"second.jsonl"
    assert cli.main(["--source", "astra-camera", "--headless", "--frames", "2", "--record", str(first)]) == 0
    assert "ASTRA EXPERIENCE" in capsys.readouterr().err
    assert cli.main(["--source", "replay", "--input", str(first), "--headless", "--record", str(second)]) == 0
    assert "ASTRA EXPERIENCE" in capsys.readouterr().err
    with PoseReplaySource(second) as recording:
        assert recording.metadata["capture_backend"] == "openni2_astra_uvc"
        assert recording.metadata["evidence"] == "unverified"


def test_openni_option_requires_the_explicit_astra_source(capsys):
    from depthstrike.cli import main
    assert main(["--source", "demo", "--openni-dir", "unused", "--headless"]) == 2
    assert "only applies to astra-camera" in capsys.readouterr().err
