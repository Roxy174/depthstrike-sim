"""Local geometric contact suggestions; not a whole-body motion prescription."""
import numpy as np

from .geometry import segment_sphere_intersection
from .types import vector3


def analyze_segment(start, end, target, hand_radius, shoulder, comfortable_reach, min_depth, max_depth):
    start, end, center, shoulder = map(vector3, (start, end, target.center, shoulder))
    delta = end - start
    length2 = float(delta @ delta)
    fraction = float(np.clip((center-start) @ delta / length2, 0, 1)) if length2 > 1e-16 else 0.
    closest = start + fraction * delta
    distance = float(np.linalg.norm(closest-center))
    radius = hand_radius + target.radius
    gap = distance - radius
    result = {"closest_point_m": closest.tolist(), "fraction": fraction, "surface_gap_m": gap,
              "segment_m": [start.tolist(), end.tolist()], "counterfactual": None}
    if gap <= 1e-9 or distance <= 1e-12:
        return result
    translation = (center-closest) / distance * (gap + .001)
    shifted = (start + translation, end + translation)
    if not all(min_depth + hand_radius <= p[2] <= max_depth-hand_radius
               and np.linalg.norm(p-shoulder) <= comfortable_reach + hand_radius for p in shifted):
        return result
    if segment_sphere_intersection(*shifted, center, radius) is not None:
        result["counterfactual"] = {"scope": "local_geometry_only", "delta_m": translation.tolist(),
            "segment_m": [p.tolist() for p in shifted], "verified_contact": True}
    return result
