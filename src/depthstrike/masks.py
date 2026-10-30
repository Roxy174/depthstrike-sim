"""Normalize only the two supported single-channel person-mask layouts."""
import numpy as np


def person_mask_2d(mask, shape):
    if mask is None:
        return None
    mask = np.asarray(mask)
    if mask.shape == (*shape, 1):
        mask = mask[..., 0]
    return mask if mask.shape == tuple(shape) else None
