"""Cheap geometry checks applied before SU2 mesh deformation."""

from __future__ import annotations

import numpy as np

from .config import Constraints
from .parameterizations.common import surface_sides


def _unique_curve(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(x)
    xs, ys = x[order], y[order]
    unique, inverse = np.unique(xs, return_inverse=True)
    sums = np.zeros_like(unique)
    counts = np.zeros_like(unique)
    np.add.at(sums, inverse, ys)
    np.add.at(counts, inverse, 1.0)
    return unique, sums / counts


def minimum_thickness(
    x: np.ndarray,
    y: np.ndarray,
    x_min: float,
    x_max: float,
    side: np.ndarray | None = None,
) -> float:
    if side is None:
        side = surface_sides(x, y)
    upper_x, upper_y = _unique_curve(x[side >= 0.0], y[side >= 0.0])
    lower_x, lower_y = _unique_curve(x[side <= 0.0], y[side <= 0.0])
    low = max(x_min, float(upper_x.min()), float(lower_x.min()))
    high = min(x_max, float(upper_x.max()), float(lower_x.max()))
    if high <= low:
        return float("-inf")
    grid = np.linspace(low, high, 401)
    thickness = np.interp(grid, upper_x, upper_y) - np.interp(grid, lower_x, lower_y)
    return float(np.min(thickness))


def check_geometry(
    x: np.ndarray, y: np.ndarray, dy: np.ndarray, cfg: Constraints
) -> tuple[bool, dict[str, float | str]]:
    max_displacement = float(np.max(np.abs(dy)))
    base_side = surface_sides(x, y)
    thickness = minimum_thickness(
        x, y + dy, cfg.thickness_x_min, cfg.thickness_x_max, base_side
    )
    if max_displacement > cfg.max_displacement:
        return False, {
            "reason": "max_displacement",
            "max_displacement": max_displacement,
            "minimum_thickness": thickness,
        }
    if thickness < cfg.min_thickness:
        return False, {
            "reason": "minimum_thickness",
            "max_displacement": max_displacement,
            "minimum_thickness": thickness,
        }
    return True, {
        "reason": "ok",
        "max_displacement": max_displacement,
        "minimum_thickness": thickness,
    }
