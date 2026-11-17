"""Geometry metric, branch classification and basis utilities."""

from __future__ import annotations

import math

import numpy as np


def surface_sides(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Return +1 upper / -1 lower using the ordered marker branches."""
    if len(x) < 6:
        return np.where(y >= np.median(y), 1.0, -1.0)
    leading = int(np.argmin(x))
    first = np.arange(0, leading + 1)
    second = np.arange(leading, len(x))
    first_mean = float(np.mean(y[first]))
    second_mean = float(np.mean(y[second]))
    upper = first if first_mean >= second_mean else second
    side = -np.ones(len(x))
    side[upper] = 1.0
    side[leading] = 0.0
    return side


def apply_shape_mode(base: np.ndarray, side: np.ndarray, mode: str) -> np.ndarray:
    if mode == "camber":
        return base
    if mode == "thickness":
        return base * side[:, None]
    raise ValueError(f"Single block cannot use shape mode {mode!r}")


def orthonormal_span(matrix: np.ndarray, tolerance: float = 1.0e-11) -> np.ndarray:
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        raise ValueError("Basis matrix must have at least one column")
    q, r = np.linalg.qr(matrix, mode="reduced")
    diagonal = np.abs(np.diag(r))
    if not diagonal.size:
        raise RuntimeError("Basis matrix is empty after QR")
    keep = diagonal > tolerance * max(float(diagonal.max()), 1.0)
    if not np.any(keep):
        raise RuntimeError("Basis matrix is numerically rank deficient")
    return q[:, keep]


def metric_descent(matrix: np.ndarray, gradient: np.ndarray) -> tuple[np.ndarray, float]:
    q = orthonormal_span(matrix)
    projected = q @ (q.T @ gradient)
    norm = float(np.linalg.norm(projected))
    full = float(np.linalg.norm(gradient))
    if norm <= 1.0e-15:
        raise RuntimeError("Adjoint gradient is orthogonal to the selected geometry span")
    direction = -projected / norm * math.sqrt(len(gradient))
    return direction, norm / max(full, 1.0e-30)


def condition_number(matrix: np.ndarray) -> float:
    rms = np.sqrt(np.mean(matrix * matrix, axis=0))
    normalized = matrix / np.maximum(rms, 1.0e-14)
    singular = np.linalg.svd(normalized, compute_uv=False)
    positive = singular[singular > singular[0] * 1.0e-12]
    return float(positive[0] / positive[-1]) if positive.size else math.inf


def normalize_rms(direction: np.ndarray) -> np.ndarray:
    rms = float(np.sqrt(np.mean(direction * direction)))
    if rms <= 1.0e-15:
        raise RuntimeError("Zero geometry direction")
    return direction / rms
