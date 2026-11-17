"""Endpoint-safe adaptive compact C-infinity brush dictionary."""

from __future__ import annotations

import numpy as np

from .common import apply_shape_mode, metric_descent, orthonormal_span


def compact_bump(x: np.ndarray, center: float, half_width: float) -> np.ndarray:
    r = (x - center) / half_width
    result = np.zeros_like(x)
    active = np.abs(r) < 1.0
    result[active] = np.exp(1.0 - 1.0 / (1.0 - r[active] ** 2))
    return result


def dictionary(
    x: np.ndarray,
    side: np.ndarray,
    *,
    candidates: int,
    endpoint_margin: float,
    endpoint_taper: bool,
    mode: str,
) -> tuple[np.ndarray, list[dict[str, float]]]:
    center_count = max(11, int(np.sqrt(candidates * 3.0)))
    width_count = max(7, int(np.ceil(candidates / center_count)))
    columns: list[np.ndarray] = []
    metadata: list[dict[str, float]] = []
    for center in np.linspace(0.04, 0.96, center_count):
        for width in np.linspace(0.035, 0.30, width_count):
            if center - width < endpoint_margin or center + width > 1.0 - endpoint_margin:
                continue
            value = compact_bump(x, float(center), float(width))
            if endpoint_taper:
                value *= np.sqrt(np.clip(x, 0.0, 1.0)) * (1.0 - np.clip(x, 0.0, 1.0))
            if np.count_nonzero(value > 1.0e-12) < 3:
                continue
            columns.append(value)
            metadata.append({"center": float(center), "half_width": float(width)})
    if not columns:
        raise RuntimeError("BCE dictionary is empty; reduce endpoint_margin")
    base = np.column_stack(columns)
    return apply_shape_mode(base, side, mode), metadata


def select(
    candidates: np.ndarray, gradient: np.ndarray, count: int
) -> tuple[list[int], np.ndarray, float]:
    normalized = candidates / np.maximum(np.linalg.norm(candidates, axis=0), 1.0e-14)
    selected: list[int] = []
    q = np.empty((len(gradient), 0))
    for _ in range(min(count, candidates.shape[1])):
        residual = gradient - q @ (q.T @ gradient) if q.shape[1] else gradient
        scores = np.abs(normalized.T @ residual)
        if selected:
            scores[selected] = -1.0
        index = int(np.argmax(scores))
        selected.append(index)
        q = orthonormal_span(candidates[:, selected])
    direction, capture = metric_descent(candidates[:, selected], gradient)
    return selected, direction, capture
