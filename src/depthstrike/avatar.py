"""Procedural upper-body character; every part is display-only camera geometry."""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np


SKIN = (.95, .73, .55)
SHIRT = (.10, .48, .52)
WHITE = (.96, .97, .94)
DARK = (.12, .17, .23)
GLOVES = {'left': (.15, .39, .76), 'right': (.81, .41, .18)}
PART_NAMES = ('torso', 'badge', 'neck', 'head', 'hair', 'nose', 'mouth',
              *(f'{part}_{hand}' for hand in ('left', 'right')
                for part in ('eye_white', 'eye', 'shoulder', 'upper_arm', 'elbow', 'forearm', 'cuff', 'glove')))


@dataclass(frozen=True)
class AvatarPart:
    name: str
    center: np.ndarray
    basis: np.ndarray
    radii: np.ndarray
    color: tuple
    estimated: bool = False

    @property
    def shape(self):
        return 'torso' if self.name == 'torso' else 'ellipsoid'

    @property
    def transform(self):
        return self.basis * self.radii

    @property
    def display_color(self):
        return (.62, .65, .67) if self.estimated else self.color


def _unit(vector):
    length = np.linalg.norm(vector)
    return vector / length if length > 1e-6 else None


def _basis(right, down):
    right = _unit(right)
    if right is None: return None
    down = _unit(down - right * np.dot(right, down))
    if down is None: return None
    return np.column_stack((right, down, np.cross(right, down)))


def _limb(name, start, end, radius, color, estimated=False):
    axis = end - start
    length = np.linalg.norm(axis)
    if length < .005: return None
    down = axis / length
    reference = np.eye(3)[np.argmin(np.abs(down))]
    right = _unit(np.cross(down, reference))
    basis = np.column_stack((right, down, np.cross(right, down)))
    return AvatarPart(name, (start + end) / 2, basis,
                      np.array((radius, length / 2 + radius * .35, radius)), color, estimated)


def build_avatar(state, config):
    """Return bounded observed/predicted geometry without altering tracked joints."""
    if state.skeleton is None: return ()
    points, predicted = {}, set()
    for name, joint in state.skeleton.joints.items():
        if joint.is_observed and joint.confidence >= config.confidence_threshold:
            points[name] = joint.position
    for name, joint in state.display_joints.items():
        if (name not in points and joint.position is not None and joint.provenance == 'predicted'
                and 0 <= joint.age_s <= config.prediction_horizon_s):
            points[name] = joint.position
            predicted.add(name)
    parts = []
    identity = np.eye(3)
    scale = 1.

    def add(name, center, radii, color, basis=identity, estimated=False):
        parts.append(AvatarPart(name, np.asarray(center).copy(), basis, np.asarray(radii), color, estimated))

    shoulders = [points.get(f'{hand}_shoulder') for hand in ('left', 'right')]
    if all(point is not None for point in shoulders):
        left, right = shoulders
        width = float(np.linalg.norm(right - left))
        if .12 <= width <= .9:
            scale = float(np.clip(width / .4, .75, 1.35))
            shoulder = (left + right) / 2
            hips = [points.get(f'{hand}_hip') for hand in ('left', 'right')]
            down = (sum(hips) / 2 - shoulder if all(p is not None for p in hips) else np.array((0., 1., 0.)))
            basis = _basis(right - left, down)
            if basis is not None:
                side, vertical, face = basis[:, 0], basis[:, 1], -basis[:, 2]
                height = float(np.clip(np.linalg.norm(down), .25, .75)) if all(p is not None for p in hips) else width * 1.15
                estimated = any(f'{hand}_shoulder' in predicted for hand in ('left', 'right'))
                center = shoulder + vertical * height * .48
                add('torso', center, (width * .54, height * .53, width * .24), SHIRT, basis, estimated)
                add('badge', center - vertical * height * .13 + face * width * .25,
                    (.035 * scale, .043 * scale, .009 * scale), WHITE, basis, estimated)
                nose = points.get('nose')
                head = (nose - vertical * .02 * scale - face * .035 * scale if nose is not None else
                        shoulder - vertical * .27 * scale)
                head_estimated = estimated or nose is None or 'nose' in predicted
                neck = _limb('neck', shoulder - vertical * .015 * scale,
                             head + vertical * .095 * scale, .043 * scale, SKIN, head_estimated)
                if neck is not None: parts.append(neck)
                add('head', head, np.array((.11, .135, .10)) * scale, SKIN, basis, head_estimated)
                add('hair', head - vertical * .105 * scale,
                    np.array((.112, .06, .093)) * scale, DARK, basis, head_estimated)
                for hand, sign in (('left', -1), ('right', 1)):
                    eye = head + (side * sign * .035 - vertical * .018 + face * .092) * scale
                    add(f'eye_white_{hand}', eye, np.array((.018, .022, .011)) * scale, WHITE, basis, head_estimated)
                    add(f'eye_{hand}', eye + face * .013 * scale,
                        np.array((.008, .011, .006)) * scale, DARK, basis, head_estimated)
                add('nose', head + (face * .108 + vertical * .008) * scale,
                    np.array((.018, .020, .023)) * scale, (.88, .60, .43), basis, head_estimated)
                add('mouth', head + (vertical * .055 + face * .092) * scale,
                    np.array((.030, .007, .010)) * scale, DARK, basis, head_estimated)

    for hand in ('left', 'right'):
        shoulder, elbow, wrist = (points.get(f'{hand}_{name}') for name in ('shoulder', 'elbow', 'wrist'))
        arm_estimated = any(f'{hand}_{name}' in predicted for name in ('shoulder', 'elbow', 'wrist'))
        if shoulder is not None:
            add(f'shoulder_{hand}', shoulder, np.full(3, .057 * scale), SHIRT,
                estimated=f'{hand}_shoulder' in predicted)
        if shoulder is not None and elbow is not None:
            part = _limb(f'upper_arm_{hand}', shoulder, elbow, .047 * scale, SHIRT, arm_estimated)
            if part is not None: parts.append(part)
        if elbow is not None:
            add(f'elbow_{hand}', elbow, np.full(3, .041 * scale), SKIN,
                estimated=f'{hand}_elbow' in predicted)
        if elbow is not None and wrist is not None:
            part = _limb(f'forearm_{hand}', elbow, wrist, .037 * scale, SKIN, arm_estimated)
            if part is not None: parts.append(part)
        fist = state.fists.get(hand)
        glove = (fist.position if fist is not None and fist.is_observed
                 and fist.confidence >= config.confidence_threshold else None)
        glove_estimated = False
        if glove is None and f'{hand}_wrist' in predicted:
            glove, glove_estimated = wrist, True
        if glove is not None:
            # The glove center AND radius are the actual scoring proxy. Body
            # proportions never scale or displace a valid interaction point.
            add(f'glove_{hand}', glove, np.full(3, config.hand_radius_m), GLOVES[hand],
                estimated=glove_estimated)
            if elbow is not None:
                direction = _unit(elbow - glove)
                if direction is not None:
                    cuff = _limb(f'cuff_{hand}', glove + direction * .055,
                                 glove + direction * .085, .043 * scale, WHITE,
                                 glove_estimated or f'{hand}_elbow' in predicted)
                    if cuff is not None: parts.append(cuff)
    return tuple(parts)


@lru_cache(maxsize=2)
def surface_samples(shape):
    angles = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    latitude = np.linspace(-np.pi / 2, np.pi / 2, 9)
    vertices = np.array([(np.cos(a) * np.cos(b), np.sin(b), np.sin(a) * np.cos(b))
                         for b in latitude for a in angles])
    if shape == 'torso': vertices = np.sign(vertices) * np.abs(vertices) ** .65
    return vertices


def draw_avatar(image, parts, intrinsics):
    """Project all surfaces in one batch; no Open3D dependency in the main HUD."""
    if not parts or intrinsics.distortion_model not in ('none', 'pinhole_approximation', 'brown_conrady'): return
    import cv2
    from .spatial import project
    surfaces = [(part, surface_samples(part.shape) @ part.transform.T + part.center) for part in parts]
    surfaces = [(part, vertices) for part, vertices in surfaces if np.all(vertices[:, 2] > .05)]
    if not surfaces: return
    pixels = project(np.concatenate([vertices for _, vertices in surfaces]), intrinsics)
    polygons, start = [], 0
    for part, vertices in surfaces:
        uv = pixels[start:start + len(vertices)]
        start += len(vertices)
        if not np.isfinite(uv).all() or np.max(np.abs(uv)) > 100000: continue
        hull = cv2.convexHull(np.rint(uv).astype(np.int32))
        polygons.append((part, hull))
    for part, hull in sorted(polygons, key=lambda pair: pair[0].center[2], reverse=True):
        color = tuple(round(channel * 255) for channel in part.display_color[::-1])
        cv2.fillConvexPoly(image, hull, color, cv2.LINE_AA)
        cv2.polylines(image, [hull], True, tuple(round(c * .7) for c in color), 1, cv2.LINE_AA)
