"""Time-aware filtering that never keeps invalid interaction points alive."""
import math

from .config import AppConfig
from .types import Joint3D, SkeletonFrame


class SkeletonTracker:
    def __init__(self, config: AppConfig):
        self.config = config
        self.reset()

    def reset(self):
        self._previous = None

    def update(self, frame: SkeletonFrame) -> SkeletonFrame:
        previous = self._previous
        dt = frame.timestamp_s-previous.timestamp_s if previous else None
        if dt is not None and dt <= 0:
            self.reset()
            return SkeletonFrame(frame.frame_id, frame.timestamp_s,
                                 {name: Joint3D(None, invalid_reason="timestamp_invalid") for name in frame.joints})
        connected = dt is not None and dt <= self.config.max_track_gap_s
        alpha = 1-math.exp(-dt/self.config.smoothing_tau_s) if connected and self.config.smoothing_tau_s else 1.
        joints = {}
        for name, joint in frame.joints.items():
            if joint.position is None or joint.confidence < self.config.confidence_threshold:
                joints[name] = Joint3D(None, invalid_reason=joint.invalid_reason or
                                       ("low_confidence" if joint.position is not None else "missing_joint"))
                continue
            old = previous.joints.get(name) if connected else None
            position = joint.position
            if old is not None and old.position is not None:
                position = old.position + alpha*(position-old.position)
            joints[name] = Joint3D(position, joint.confidence)
        result = SkeletonFrame(frame.frame_id, frame.timestamp_s, joints)
        self._previous = result
        return result
