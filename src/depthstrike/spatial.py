"""Sampled visible-space checks; not a complete room reconstruction."""
from functools import lru_cache

import numpy as np

from .types import vector3


def project(points, intrinsics):
    i = intrinsics
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if i.distortion_model == "brown_conrady":
        import cv2
        camera = np.array(((i.fx, 0, i.cx), (0, i.fy, i.cy), (0, 0, 1.)))
        return cv2.projectPoints(points, np.zeros(3), np.zeros(3), camera, np.asarray(i.distortion))[0].reshape(-1, 2)
    if i.distortion_model not in ("none", "pinhole_approximation"):
        raise ValueError("Unsupported workspace distortion model")
    return points[:, :2]/points[:, 2:]*np.array((i.fx, i.fy))+np.array((i.cx, i.cy))


class DepthWorkspace:
    def __init__(self, frame):
        self.frame = frame

    def path_status(self, start, end, radius):
        start, end = vector3(start), vector3(end)
        if not np.isfinite(radius) or radius <= 0: raise ValueError("Workspace radius must be positive")
        count = min(500, max(2, int(np.linalg.norm(end-start)/.02)+1))
        centers = np.linspace(start, end, count)
        offsets = np.vstack((np.zeros((1, 3)), np.eye(3)*radius, -np.eye(3)*radius))
        samples = (centers[:, None, :]+offsets).reshape(-1, 3)
        if np.any(samples[:, 2] <= 0): return "unknown"
        i = self.frame.intrinsics
        uv = project(samples, i)
        if not np.isfinite(uv).all() or np.any(uv < 0) or np.any(uv[:, 0] >= i.width) or np.any(uv[:, 1] >= i.height):
            return "unknown"
        uv = np.floor(uv).astype(int)
        depths = self.frame.depth_m[uv[:, 1], uv[:, 0]]
        valid = np.isfinite(depths) & (depths > 0)
        if np.any(valid & (depths < samples[:, 2]+.02)): return "blocked"
        return "clear" if valid.all() else "unknown"


@lru_cache(maxsize=4)
def _rays(i):
    y, x = np.mgrid[:i.height, :i.width]
    uv = np.stack((x, y), axis=-1).astype(float)
    if i.distortion_model == "brown_conrady":
        import cv2
        camera = np.array(((i.fx, 0, i.cx), (0, i.fy, i.cy), (0, 0, 1.)))
        xy = cv2.undistortPoints(uv.reshape(-1, 1, 2), camera, np.asarray(i.distortion)).reshape(i.height, i.width, 2)
    elif i.distortion_model in ("none", "pinhole_approximation"):
        xy = (uv-np.array((i.cx, i.cy)))/np.array((i.fx, i.fy))
    else:
        raise ValueError("Unsupported occlusion distortion model")
    return np.concatenate((xy, np.ones((*xy.shape[:2], 1))), axis=-1)


def target_visibility_mask(frame, center, radius):
    center = vector3(center)
    if not np.isfinite(radius) or radius <= 0: raise ValueError("Invalid target radius")
    rays = _rays(frame.intrinsics)
    a = np.sum(rays*rays, axis=-1)
    b = np.sum(rays*center, axis=-1)
    discriminant = b*b-a*(center@center-radius*radius)
    front_z = (b-np.sqrt(np.maximum(discriminant, 0)))/a
    return ((discriminant >= 0) & (front_z > 0) & np.isfinite(frame.depth_m)
            & (frame.depth_m > front_z+.01))
