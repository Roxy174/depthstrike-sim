"""Conservative surface-depth fusion, never inferred world landmarks."""
import numpy as np

from .config import AppConfig
from .types import Intrinsics, Joint3D, Landmark, RGBDFrame, SkeletonFrame, vector3


def deproject_pixel(u: float, v: float, z: float, intrinsics: Intrinsics) -> np.ndarray:
    i = intrinsics
    if i.distortion_model == "none":
        if any(abs(x) > 1e-12 for x in i.distortion):
            raise ValueError("Nonzero distortion declared with model 'none'")
        x, y = (u-i.cx)/i.fx, (v-i.cy)/i.fy
    elif i.distortion_model == "brown_conrady":
        if len(i.distortion) not in (4, 5, 8):
            raise ValueError("Unsupported Brown-Conrady distortion coefficients")
        import cv2
        camera = np.array([[i.fx, 0, i.cx], [0, i.fy, i.cy], [0, 0, 1.]])
        x, y = cv2.undistortPoints(np.array([[[u, v]]], dtype=float), camera,
                                  np.asarray(i.distortion)).reshape(2)
    else:
        raise ValueError(f"Unsupported distortion model: {i.distortion_model}")
    return vector3((x*z, y*z, z))


def estimate_joint(landmark: Landmark, frame: RGBDFrame, config: AppConfig) -> Joint3D:
    if (not np.isfinite(landmark.confidence)
            or not config.confidence_threshold <= landmark.confidence <= 1):
        return Joint3D(None, invalid_reason="low_confidence")
    if (not np.isfinite((landmark.u, landmark.v)).all()
            or not (0 <= landmark.u < 1 and 0 <= landmark.v < 1)):
        return Joint3D(None, invalid_reason="out_of_frame")
    i = frame.intrinsics
    u, v = landmark.u*i.width, landmark.v*i.height
    x, y = min(round(u), i.width-1), min(round(v), i.height-1)
    center_depth = float(frame.depth_m[y, x])
    # A valid neighboring background is not evidence for an occluded joint.
    if not np.isfinite(center_depth) or not config.min_depth_m <= center_depth <= config.max_depth_m:
        return Joint3D(None, invalid_reason="invalid_depth")
    r = config.depth_window_px // 2
    patch = frame.depth_m[max(0, y-r):min(i.height, y+r+1),
                          max(0, x-r):min(i.width, x+r+1)]
    valid = patch[np.isfinite(patch) & (patch >= config.min_depth_m) & (patch <= config.max_depth_m)]
    if valid.size < patch.size*config.depth_min_valid_ratio:
        return Joint3D(None, invalid_reason="insufficient_depth")
    if np.ptp(np.quantile(valid, [.1, .9])) > config.depth_max_spread_m:
        return Joint3D(None, invalid_reason="depth_discontinuity")
    z = float(np.median(valid))
    if abs(z-center_depth) > config.depth_max_spread_m:
        return Joint3D(None, invalid_reason="depth_discontinuity")
    position = frame.deproject(u, v, z) if frame.deproject else deproject_pixel(u, v, z, i)
    return Joint3D(position, landmark.confidence)


def fuse_skeleton(frame: RGBDFrame, landmarks: dict[str, Landmark], config: AppConfig) -> SkeletonFrame:
    return SkeletonFrame(frame.frame_id, frame.timestamp_s,
                         {name: estimate_joint(point, frame, config) for name, point in landmarks.items()})
