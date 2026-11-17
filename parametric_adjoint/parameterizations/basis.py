"""Unified CST, adaptive BCE, hybrid and CST-to-BCE relay directions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import Parameterization
from . import bce, cst
from .common import condition_number, metric_descent, normalize_rms, surface_sides


@dataclass(frozen=True)
class DirectionResult:
    values: np.ndarray
    stage: str
    capture_fraction: float
    condition: float
    details: dict[str, Any]


def _modes(shape_mode: str) -> list[str]:
    return ["camber", "thickness"] if shape_mode == "both" else [shape_mode]


def _split(total: int, count: int) -> list[int]:
    values = [total // count] * count
    for index in range(total % count):
        values[index] += 1
    return [max(1, value) for value in values]


def _cst_blocks(
    x: np.ndarray, side: np.ndarray, cfg: Parameterization
) -> tuple[np.ndarray, dict[str, Any]]:
    modes = _modes(cfg.shape_mode)
    counts = _split(cfg.cst_variables, len(modes))
    blocks = [cst.matrix(x, side, count, mode) for count, mode in zip(counts, modes)]
    return np.column_stack(blocks), {"modes": modes, "variables_per_mode": counts}


def _bce_selected(
    x: np.ndarray, side: np.ndarray, gradient: np.ndarray, cfg: Parameterization
) -> tuple[np.ndarray, np.ndarray, float, dict[str, Any]]:
    modes = _modes(cfg.shape_mode)
    counts = _split(cfg.bce_variables, len(modes))
    matrices: list[np.ndarray] = []
    selected_metadata: list[dict[str, Any]] = []
    for count, mode in zip(counts, modes):
        candidates, metadata = bce.dictionary(
            x,
            side,
            candidates=cfg.bce_candidates,
            endpoint_margin=cfg.endpoint_margin,
            endpoint_taper=cfg.endpoint_taper,
            mode=mode,
        )
        selected, _, _ = bce.select(candidates, gradient, count)
        matrices.append(candidates[:, selected])
        selected_metadata.extend([
            {"mode": mode, **metadata[index]} for index in selected
        ])
    matrix = np.column_stack(matrices)
    direction, capture = metric_descent(matrix, gradient)
    return matrix, direction, capture, {
        "modes": modes,
        "selected_brushes": selected_metadata,
        "dictionary_candidates_per_mode": int(candidates.shape[1]),
    }


def build_direction(
    x: np.ndarray,
    y: np.ndarray,
    gradient: np.ndarray,
    cfg: Parameterization,
    accepted_step: int,
) -> DirectionResult:
    side = surface_sides(x, y)
    requested = cfg.mode
    stage = "cst" if requested == "relay" and accepted_step <= cfg.relay_cst_steps else requested
    if requested == "relay" and stage != "cst":
        stage = "bce"

    if stage == "cst":
        matrix, details = _cst_blocks(x, side, cfg)
        direction, capture = metric_descent(matrix, gradient)
    elif stage == "bce":
        matrix, direction, capture, details = _bce_selected(x, side, gradient, cfg)
    elif stage == "hybrid":
        cst_matrix, cst_details = _cst_blocks(x, side, cfg)
        cst_direction, cst_capture = metric_descent(cst_matrix, gradient)
        bce_matrix, bce_direction, bce_capture, bce_details = _bce_selected(
            x, side, gradient, cfg
        )
        direction = normalize_rms(
            cfg.hybrid_cst_weight * cst_direction
            + cfg.hybrid_bce_weight * bce_direction
        )
        matrix = np.column_stack((cst_matrix, bce_matrix))
        capture = float(np.linalg.norm(matrix @ np.linalg.lstsq(matrix, gradient, rcond=None)[0]))
        capture /= max(float(np.linalg.norm(gradient)), 1.0e-30)
        details = {
            "block_weights": {
                "cst": cfg.hybrid_cst_weight,
                "bce": cfg.hybrid_bce_weight,
            },
            "cst_capture": cst_capture,
            "bce_capture": bce_capture,
            "cst": cst_details,
            "bce": bce_details,
        }
    else:
        raise ValueError(f"Unknown parameterization stage: {stage}")

    direction = normalize_rms(direction)
    details.update({
        "requested_mode": requested,
        "active_columns": int(matrix.shape[1]),
        "support_points": int(np.count_nonzero(np.abs(direction) > 1.0e-10)),
        "max_over_rms": float(np.max(np.abs(direction))),
    })
    return DirectionResult(
        values=direction,
        stage=stage,
        capture_fraction=float(capture),
        condition=condition_number(matrix),
        details=details,
    )
