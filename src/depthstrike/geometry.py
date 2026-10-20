"""Continuous contact of spherical proxies along a linear time segment."""
import math

import numpy as np

from .types import vector3


def segment_sphere_intersection(start, end, center, radius) -> float | None:
    start, end, center = (vector3(v) for v in (start, end, center))
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Radius must be finite and positive")
    offset, delta = start - center, end - start
    c = float(offset @ offset - radius * radius)
    if c <= 0:
        return 0.0
    a = float(delta @ delta)
    if a <= np.finfo(float).eps:
        return None
    b = 2 * float(offset @ delta)
    discriminant = b * b - 4 * a * c
    tolerance = 1e-12 * max(1., b*b, abs(4*a*c))
    if discriminant < -tolerance:
        return None
    t = (-b - math.sqrt(max(0., discriminant))) / (2*a)
    return float(np.clip(t, 0, 1)) if -1e-12 <= t <= 1+1e-12 else None
