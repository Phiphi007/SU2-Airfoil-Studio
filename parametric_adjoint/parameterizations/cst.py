"""CST camber/thickness bases with endpoint-safe class function."""

from __future__ import annotations

import math

import numpy as np

from .common import apply_shape_mode


def matrix(x: np.ndarray, side: np.ndarray, variables: int, mode: str) -> np.ndarray:
    if variables < 1:
        raise ValueError("CST variables must be >= 1")
    degree = variables - 1
    xc = np.clip(x, 0.0, 1.0)
    class_function = np.sqrt(xc) * (1.0 - xc)
    base = np.column_stack([
        class_function
        * math.comb(degree, index)
        * xc ** index
        * (1.0 - xc) ** (degree - index)
        for index in range(variables)
    ])
    return apply_shape_mode(base, side, mode)
