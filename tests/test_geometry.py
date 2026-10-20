import math

import pytest


@pytest.mark.parametrize("start,end,center,radius,want", [
    ((-1, 0, 1), (1, 0, 1), (0, 0, 1), .1, .45),
    ((-1, 0, 2), (1, 0, 2), (0, 0, 1), .1, None),
    ((-1, 1, 0), (1, 1, 0), (0, 0, 0), 1, .5),
    ((0, 0, 0), (2, 0, 0), (0, 0, 0), 1, 0),
    ((0, 0, 0), (0, 0, 0), (0, 0, 0), 1, 0),
    ((2, 0, 0), (2, 0, 0), (0, 0, 0), 1, None),
])
def test_earliest_swept_contact(start, end, center, radius, want):
    from depthstrike.geometry import segment_sphere_intersection
    result = segment_sphere_intersection(start, end, center, radius)
    assert result == (pytest.approx(want) if want is not None else None)


@pytest.mark.parametrize("point,radius", [((math.nan, 0, 0), 1), ((0, 0, 0), -1)])
def test_invalid_geometry_rejected(point, radius):
    from depthstrike.geometry import segment_sphere_intersection
    with pytest.raises(ValueError):
        segment_sphere_intersection(point, (0, 0, 0), (0, 0, 0), radius)
