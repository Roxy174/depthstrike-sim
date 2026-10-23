"""Synchronous MediaPipe VIDEO pose inference on the exact paired RGB frame."""
from pathlib import Path
import hashlib

import numpy as np

from .config import AppConfig
from .types import DepthStrikeError, FrameTimeout, Landmark, RGBDFrame

JOINT_INDICES = {"nose": 0, "left_shoulder": 11, "right_shoulder": 12,
                 "left_elbow": 13, "right_elbow": 14, "left_wrist": 15,
                 "right_wrist": 16, "left_pinky": 17, "right_pinky": 18,
                 "left_index": 19, "right_index": 20, "left_thumb": 21, "right_thumb": 22,
                 "left_hip": 23, "right_hip": 24}


def video_timestamp_ms(timestamp_s, previous_ms):
    timestamp = round(timestamp_s*1000.)
    if timestamp <= previous_ms:
        raise FrameTimeout("Pose VIDEO input timestamps must increase strictly")
    return timestamp


def landmarks_from_result(result, width, height) -> dict[str, Landmark]:
    if not result.pose_landmarks:
        return {}
    points = result.pose_landmarks[0]
    mask = result.segmentation_masks[0].numpy_view() if result.segmentation_masks else None
    landmarks = {}
    for name, index in JOINT_INDICES.items():
        point = points[index]
        confidence = min(float(point.visibility or 0), float(point.presence or 0))
        if mask is not None and 0 <= point.x < 1 and 0 <= point.y < 1:
            y, x = min(int(point.y*height), height-1), min(int(point.x*width), width-1)
            confidence = min(confidence, float(mask[y, x]))
        landmarks[name] = Landmark(point.x, point.y, confidence)
    return landmarks


class PoseEstimator:
    def __init__(self, config: AppConfig):
        path = Path(config.model_path)
        if not path.is_file():
            raise DepthStrikeError(f"Pose model missing: {path}. Run: python scripts/download_pose_model.py")
        try:
            import mediapipe as mp
            self.mp = mp
            model_data = path.read_bytes()
            self.metadata = {"filename": path.name, "sha256": hashlib.sha256(model_data).hexdigest(),
                             "mediapipe_version": mp.__version__}
            options = mp.tasks.vision.PoseLandmarkerOptions(
                # Native fopen in some Windows builds cannot open non-ASCII paths.
                base_options=mp.tasks.BaseOptions(model_asset_buffer=model_data),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
                min_pose_detection_confidence=config.confidence_threshold,
                min_pose_presence_confidence=config.confidence_threshold,
                min_tracking_confidence=config.confidence_threshold,
                output_segmentation_masks=True)
            self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        except Exception as exc:
            raise DepthStrikeError(f"MediaPipe/model initialization failed: {exc}. Install the pinned camera dependencies and verify the model.") from exc
        self._last_ms = -1
        self._closed = False
        self.last_mask = None

    def detect(self, frame: RGBDFrame) -> dict[str, Landmark]:
        timestamp = video_timestamp_ms(frame.timestamp_s, self._last_ms)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame.color_rgb))
        result = self.detector.detect_for_video(image, timestamp)
        self.last_mask = result.segmentation_masks[0].numpy_view().copy() if result.segmentation_masks else None
        self._last_ms = timestamp
        return landmarks_from_result(result, frame.intrinsics.width, frame.intrinsics.height)

    def close(self):
        if not self._closed:
            self._closed = True
            self.detector.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
