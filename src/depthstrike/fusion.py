"""Conservative surface-depth fusion, never inferred world landmarks."""
import numpy as np

from .config import AppConfig
from .masks import person_mask_2d
from .types import Intrinsics, Joint3D, Landmark, RGBDFrame, SkeletonFrame, vector3


def deproject_pixel(u: float, v: float, z: float, intrinsics: Intrinsics) -> np.ndarray:
    i = intrinsics
    if i.distortion_model in ("none", "pinhole_approximation"):
        if any(abs(x) > 1e-12 for x in i.distortion):
            raise ValueError("Nonzero distortion declared with a pinhole model")
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


def estimate_joint(landmark: Landmark, frame: RGBDFrame, config: AppConfig, *, mask=None, previous=None) -> Joint3D:
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
    center_valid = np.isfinite(center_depth) and config.min_depth_m <= center_depth <= config.max_depth_m
    if not center_valid and config.fusion_mode == "conservative":
        return Joint3D(None, invalid_reason="invalid_depth")
    r = config.depth_window_px // 2
    patch = frame.depth_m[max(0, y-r):min(i.height, y+r+1),
                          max(0, x-r):min(i.width, x+r+1)]
    supported = np.isfinite(patch) & (patch >= config.min_depth_m) & (patch <= config.max_depth_m)
    if config.fusion_mode == "masked":
        mask = person_mask_2d(mask, frame.depth_m.shape)
        if mask is None:
            return Joint3D(None, invalid_reason="missing_mask")
        local_mask = np.asarray(mask)[max(0, y-r):min(i.height, y+r+1), max(0, x-r):min(i.width, x+r+1)]
        if not np.isfinite(mask[y, x]) or mask[y, x] < config.confidence_threshold:
            return Joint3D(None, invalid_reason="outside_person")
        supported &= np.isfinite(local_mask) & (local_mask >= config.confidence_threshold)
    valid = patch[supported]
    if valid.size < patch.size*config.depth_min_valid_ratio:
        return Joint3D(None, invalid_reason="insufficient_depth")
    if np.ptp(np.quantile(valid, [.1, .9])) > config.depth_max_spread_m:
        return Joint3D(None, invalid_reason="depth_discontinuity")
    z = float(np.median(valid))
    if center_valid and abs(z-center_depth) > config.depth_max_spread_m:
        return Joint3D(None, invalid_reason="depth_discontinuity")
    if not center_valid and (previous is None or previous.provenance != "observed" or not previous.is_observed
            or abs(z-previous.position[2]) > config.depth_max_spread_m):
        return Joint3D(None, invalid_reason="invalid_depth")
    position = frame.deproject(u, v, z) if frame.deproject else deproject_pixel(u, v, z, i)
    if not center_valid and np.linalg.norm(position-previous.position) > config.depth_max_spread_m:
        return Joint3D(None, invalid_reason="invalid_depth")
    quality = valid.size/patch.size * (1 - min(1., float(np.std(valid))/config.depth_max_spread_m))
    return Joint3D(position, landmark.confidence, provenance="observed" if center_valid else "depth_patch",
                   depth_quality=float(quality) * (1. if center_valid else .8))


def fuse_skeleton(frame: RGBDFrame, landmarks: dict[str, Landmark], config: AppConfig, *, mask=None, previous=None) -> SkeletonFrame:
    history = previous.joints if (previous is not None and
        0 < frame.timestamp_s-previous.timestamp_s <= config.max_track_gap_s) else {}
    return SkeletonFrame(frame.frame_id, frame.timestamp_s,
                         {name: estimate_joint(point, frame, config, mask=mask, previous=history.get(name))
                          for name, point in landmarks.items()})
