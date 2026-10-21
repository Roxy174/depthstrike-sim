"""Common skeleton input boundary: live capture, deterministic demo or replay."""
import numpy as np

from .capture import GeminiSource
from .fusion import fuse_skeleton
from .pose import PoseEstimator
from .types import Joint3D, SkeletonFrame


class CameraPoseSource:
    def __init__(self, config, *, capture=None, estimator=None):
        self.config = config
        self.capture = self.estimator = None
        self.last_rgbd = None
        self.last_landmarks = {}
        self.actions = []
        try:
            self.capture = capture if capture is not None else GeminiSource(config)
            self.estimator = estimator if estimator is not None else PoseEstimator(config)
        except BaseException:
            self.close()
            raise

    def read(self):
        frame = self.capture.read()
        if frame is None:
            return None
        self.last_rgbd = frame
        self.last_landmarks = self.estimator.detect(frame)
        return fuse_skeleton(frame, self.last_landmarks, self.config)

    def describe(self):
        return self.capture.describe() if hasattr(self.capture, "describe") else {"source": "rgbd-replay"}

    def close(self):
        try:
            if self.estimator is not None:
                self.estimator.close()
        finally:
            if self.capture is not None:
                self.capture.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class DemoPoseSource:
    """Analytic upper-body motion, explicitly not a camera or model evaluation."""
    def __init__(self, fps=30., total_frames=None):
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError("Demo fps must be positive")
        self.fps, self.total_frames = fps, total_frames
        self.index = 0
        self.closed = False
        self.actions = []
        self.last_rgbd = None

    def read(self):
        if self.closed or self.total_frames is not None and self.index >= self.total_frames:
            return None
        t = self.index/self.fps
        cycle = max(0., t-1.2)/1.2
        phase = (cycle % 1)*1.2
        reach = 0.
        if t >= 1.2:
            if .25 <= phase < .45: reach = (phase-.25)/.2
            elif .45 <= phase < .65: reach = 1.
            elif .65 <= phase < .95: reach = 1-(phase-.65)/.3
        left_z = 1.85-.5*reach if int(cycle) % 2 == 0 else 1.85
        right_z = 1.85-.5*reach if int(cycle) % 2 else 1.85
        values = {"nose": (0, -.25, 1.98),
                  "left_shoulder": (-.2, 0, 2.), "right_shoulder": (.2, 0, 2.),
                  "left_elbow": (-.24, .2, (2+left_z)/2), "right_elbow": (.24, .2, (2+right_z)/2),
                  "left_wrist": (-.2, .04, left_z), "right_wrist": (.2, .04, right_z),
                  "left_hip": (-.15, .5, 2.), "right_hip": (.15, .5, 2.)}
        result = SkeletonFrame(self.index, t, {name: Joint3D(value, .99) for name, value in values.items()})
        self.index += 1
        return result

    def describe(self): return {"source": "synthetic demo", "fps": self.fps}
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
