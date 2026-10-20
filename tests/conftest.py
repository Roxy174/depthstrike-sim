import pytest

from depthstrike.types import Joint3D, SkeletonFrame


@pytest.fixture
def skeleton():
    def make(t, left_z=1.85, right_z=1.85, shift=0., invalid=None):
        values = {
            "left_shoulder": (-.2, 0, 2), "right_shoulder": (.2, 0, 2),
            "left_elbow": (-.25, .2, 1.95), "right_elbow": (.25, .2, 1.95),
            "left_wrist": (-.2, .04, left_z), "right_wrist": (.2, .04, right_z),
            "nose": (0, -.25, 1.95), "left_hip": (-.15, .5, 2), "right_hip": (.15, .5, 2),
        }
        joints = {name: Joint3D((x+shift, y, z), .95) for name, (x, y, z) in values.items()}
        if invalid:
            joints[invalid] = Joint3D(None)
        return SkeletonFrame(round(t*1000), t, joints)
    return make
