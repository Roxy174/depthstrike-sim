"""Common skeleton input boundary: live capture, deterministic demo or replay."""
from .capture import GeminiSource
from .fusion import fuse_skeleton
from .pose import PoseEstimator


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
