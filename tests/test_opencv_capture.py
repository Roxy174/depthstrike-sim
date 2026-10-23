from types import SimpleNamespace

import numpy as np
import pytest

from depthstrike.config import AppConfig
from depthstrike.types import DepthStrikeError, FrameTimeout


class Capture:
    def __init__(self):
        self.closed = False
        self.opened = True
        self.grabbed = True
        self.color = np.full((3, 4, 3), (10, 20, 30), np.uint8)
        self.depth = np.full((3, 4), 2000, np.uint16)
        self.intrinsics = {1: 6., 2: 6., 3: 2., 4: 1.5}
        self.channels = []

    def isOpened(self): return self.opened
    def get(self, key): return self.intrinsics[key]
    def grab(self): return self.grabbed
    def retrieve(self, _, channel):
        self.channels.append(channel)
        return True, self.color if channel == 10 else self.depth
    def release(self): self.closed = True


def backend(capture):
    def open_camera(index, api):
        assert (index, api) == (0, 2600)
        return capture
    return SimpleNamespace(VideoCapture=open_camera, CAP_OBSENSOR=2600,
        CAP_OBSENSOR_BGR_IMAGE=10, CAP_OBSENSOR_DEPTH_MAP=11,
        CAP_PROP_OBSENSOR_INTRINSIC_FX=1, CAP_PROP_OBSENSOR_INTRINSIC_FY=2,
        CAP_PROP_OBSENSOR_INTRINSIC_CX=3, CAP_PROP_OBSENSOR_INTRINSIC_CY=4,
        __version__="test-boundary")


def test_opencv_pair_converts_mm_and_bgr_with_explicit_host_time_and_approximation():
    from depthstrike.opencv_capture import OpenCVSource
    capture = Capture()
    times = iter((100., 100.1, 100.2))
    with OpenCVSource(AppConfig(), cv2_module=backend(capture), clock=lambda: next(times)) as source:
        first, second = source.read(), source.read()
        assert (first.frame_id, second.frame_id) == (0, 1)
        assert (first.timestamp_s, second.timestamp_s) == pytest.approx((.1, .2))
        assert tuple(first.color_rgb[0, 0]) == (30, 20, 10)
        assert first.depth_m[0, 0] == pytest.approx(2.)
        assert capture.channels == [10, 11, 10, 11]
        assert first.intrinsics.distortion_model == "pinhole_approximation"
        metadata = source.describe()
        assert metadata["timestamp_source"] == "host_monotonic_read_completion"
        assert metadata["synchronization"] == "unverified_no_device_timestamps"
        assert metadata["calibration_scope"] == "backend_intrinsics_pinhole_approximation"
        assert metadata["evidence"] == "unverified"
    assert capture.closed


@pytest.mark.parametrize("problem", ["missing", "wrong_shape", "wrong_depth_type", "wrong_color_type"])
def test_opencv_missing_or_malformed_pairs_do_not_produce_a_frame(problem):
    from depthstrike.opencv_capture import OpenCVSource
    capture = Capture()
    if problem == "missing": capture.depth = None
    elif problem == "wrong_shape": capture.depth = np.ones((2, 4), np.uint16)
    elif problem == "wrong_depth_type": capture.depth = capture.depth.astype(float)
    elif problem == "wrong_color_type": capture.color = capture.color.astype(float)
    with OpenCVSource(AppConfig(), cv2_module=backend(capture)) as source:
        with pytest.raises(FrameTimeout if problem == "missing" else DepthStrikeError): source.read()
    assert capture.closed


def test_opencv_nonincreasing_host_clock_does_not_fabricate_a_timestamp():
    from depthstrike.opencv_capture import OpenCVSource
    capture = Capture()
    with OpenCVSource(AppConfig(), cv2_module=backend(capture), clock=lambda: 100.) as source:
        source.read()
        with pytest.raises(FrameTimeout): source.read()


@pytest.mark.parametrize("problem", ["not_open", "bad_intrinsics"])
def test_opencv_initialization_failure_releases_camera(problem):
    from depthstrike.opencv_capture import OpenCVSource
    capture = Capture()
    if problem == "not_open": capture.opened = False
    else: capture.intrinsics[1] = 0
    with pytest.raises(DepthStrikeError): OpenCVSource(AppConfig(), cv2_module=backend(capture))
    assert capture.closed


def test_approximate_pinhole_model_is_explicit_and_works_in_projection_consumers():
    from depthstrike.fusion import deproject_pixel
    from depthstrike.visualization import _pixel
    from depthstrike.types import Intrinsics
    intrinsics = Intrinsics(640, 480, 600, 600, 320, 240, "pinhole_approximation")
    assert deproject_pixel(380, 210, 2., intrinsics) == pytest.approx((.2, -.1, 2.))
    assert _pixel((.2, -.1, 2.), intrinsics) == (380, 210)
