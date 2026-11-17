"""Bounded, arc-length cubic reconstruction of an open airfoil perimeter.

No SciPy runtime is required.  Redundant collinear DAT nodes are removed before
interpolation so their arbitrary density cannot imprint flat facets on the wall
normals. The leading edge and the two trailing-edge endpoints remain anchors.
"""
from __future__ import annotations

import numpy as np


def _simplify(points: np.ndarray, tolerance: float) -> np.ndarray:
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        first, last = pending.pop()
        if last <= first + 1:
            continue
        chord = points[last] - points[first]
        fraction = np.clip(
            (points[first + 1:last] - points[first]) @ chord
            / max(float(chord @ chord), 1e-30), 0.0, 1.0
        )
        distance = np.linalg.norm(
            points[first + 1:last] - points[first] - fraction[:, None] * chord,
            axis=1,
        )
        local = int(np.argmax(distance))
        if distance[local] > tolerance:
            middle = first + 1 + local
            keep.add(middle)
            pending.extend(((first, middle), (middle, last)))
    return np.array(sorted(keep), dtype=int)


def cubic_curve(points: np.ndarray, query: np.ndarray,
                start_derivative: np.ndarray | None = None,
                end_derivative: np.ndarray | None = None) -> np.ndarray:
    """Evaluate a parametric cubic with natural or clamped endpoint tangents."""
    points = np.asarray(points, dtype=float)
    knots = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    widths = np.diff(knots)
    if np.any(widths <= 0):
        raise ValueError("Curve contains duplicate consecutive anchors")
    count = len(points)
    diagonal = np.ones(count)
    lower = np.zeros(count)
    upper = np.zeros(count)
    rhs = np.zeros_like(points)
    diagonal[1:-1] = 2 * (widths[:-1] + widths[1:])
    lower[1:-1] = widths[:-1]
    upper[1:-1] = widths[1:]
    rhs[1:-1] = 6 * (
        np.diff(points, axis=0)[1:] / widths[1:, None]
        - np.diff(points, axis=0)[:-1] / widths[:-1, None]
    )
    if start_derivative is not None:
        diagonal[0], upper[0] = 2 * widths[0], widths[0]
        rhs[0] = 6 * ((points[1] - points[0]) / widths[0] - start_derivative)
    if end_derivative is not None:
        diagonal[-1], lower[-1] = 2 * widths[-1], widths[-1]
        rhs[-1] = 6 * (end_derivative - (points[-1] - points[-2]) / widths[-1])
    for index in range(1, count):
        factor = lower[index] / diagonal[index - 1]
        diagonal[index] -= factor * upper[index - 1]
        rhs[index] -= factor * rhs[index - 1]
    second = np.empty_like(points)
    second[-1] = rhs[-1] / diagonal[-1]
    for index in range(count - 2, -1, -1):
        second[index] = (rhs[index] - upper[index] * second[index + 1]) / diagonal[index]
    segment = np.clip(np.searchsorted(knots, query, side="right") - 1, 0, count - 2)
    h = widths[segment]
    a = (knots[segment + 1] - query) / h
    b = (query - knots[segment]) / h
    return (
        a[:, None] * points[segment] + b[:, None] * points[segment + 1]
        + ((a**3 - a)[:, None] * second[segment]
           + (b**3 - b)[:, None] * second[segment + 1]) * h[:, None]**2 / 6
    )


def reconstruct_perimeter(
    points: np.ndarray, chord: float, tolerance: float = 2e-4
) -> tuple[np.ndarray, int, dict[str, float | int]]:
    """Reconstruct a continuous curve within a measured source-node bound.

    Check distances in both directions against the supplied polygon. A faceted
    leading-edge corner may be rounded within 0.001c, reported separately. This
    is a geometric repair, not an exact preservation of the source polygon.
    """
    leading = int(np.argmin(points[:, 0]))
    limit = tolerance * chord
    source_arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    incoming = points[leading] - points[leading - 1]
    outgoing = points[leading + 1] - points[leading]
    leading_turn = float(np.degrees(np.arccos(np.clip(
        incoming @ outgoing / (np.linalg.norm(incoming) * np.linalg.norm(outgoing)), -1, 1))))
    repair_nose = leading_turn > 12.0

    def deviations(query_points, path):
        edges = np.diff(path, axis=0)
        norm2 = np.maximum(np.sum(edges**2, axis=1), 1e-30)
        result = np.empty(len(query_points))
        for start in range(0, len(query_points), 64):
            delta = query_points[start:start+64, None, :] - path[None, :-1, :]
            t = np.clip(np.sum(delta * edges[None, :, :], axis=2) / norm2, 0, 1)
            result[start:start+64] = np.sqrt(np.min(np.sum(
                (delta - t[:, :, None] * edges[None, :, :])**2, axis=2), axis=1))
        return result

    def bounds(query_points):
        front = query_points[:, 0] < points[leading, 0] + 0.02 * chord
        return np.where(front, 0.001 * chord, limit)
    selected = None
    for factor in (0.5, 0.25, 0.125, 0.0):
        up = _simplify(points[:leading + 1], limit * factor)
        down = _simplify(points[leading:], limit * factor) + leading
        ids = np.r_[up, down[1:]]
        if repair_nose:
            ids = ids[(np.abs(source_arc[ids] - source_arc[leading]) > 0.015 * chord)
                      | (ids == leading)]
        anchors = points[ids]
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(anchors, axis=0), axis=1))]
        leading_anchor = int(np.flatnonzero(ids == leading)[0])
        leading_arc = arc[leading_anchor]
        query = np.unique(np.r_[np.linspace(0, arc[-1], max(4001, len(points)*24)), arc, leading_arc])
        curve = cubic_curve(anchors, query)
        # A cambered source polygon need not put its LE anchor at the minimum
        # of the reconstructed curve. Re-anchor the smooth nose with a C2
        # compact translation, rather than clamping two independent splines
        # (which introduced a curvature and density jump at their join).
        # Correct the *derivative*, not the position, at the original LE anchor.
        # This C2 correction keeps that coordinate fixed, enforces a vertical
        # tangent, and avoids different one-sided curvatures from split splines.
        probe = 1e-5 * chord
        values = cubic_curve(anchors, np.array([leading_arc-probe, leading_arc+probe]))
        nose_slope_x = (values[1, 0] - values[0, 0]) / (2 * probe)
        local = (query - leading_arc) / (.015 * chord)
        weight = np.maximum(0., 1. - local**2)**3
        curve[:, 0] -= weight * (query - leading_arc) * nose_slope_x
        new_leading = int(np.argmin(curve[:, 0]))
        distances = deviations(points, curve)
        reverse_distances = deviations(curve, points)
        acceptable = (np.all(distances <= bounds(points))
                      and np.all(reverse_distances <= bounds(curve)))
        selected = curve, new_leading, distances, len(anchors)
        if acceptable:
            break
    curve, new_leading, distances, anchor_count = selected
    if not acceptable:
        raise ValueError(
            f"翼型局部折角过大，连续壁面修复超过允许偏差（普通区域 {tolerance:.4g}c，"
            "前缘修复区域 0.001c）。请增加原始几何采样或减小尖锐变形。"
            f"源点偏差 {np.max(distances)/chord:.3e}c，"
            f"曲线偏差 {np.max(reverse_distances)/chord:.3e}c。"
        )
    curve[0], curve[-1] = points[0], points[-1]
    curve[new_leading, 0] = points[leading, 0]
    return curve, new_leading, {
        "wall_reconstruction_max_source_deviation_pct": float(np.max(distances) / chord),
        "wall_reconstruction_tolerance_pct": tolerance,
        "wall_reconstruction_max_curve_deviation_pct": float(np.max(reverse_distances) / chord),
        "leading_edge_repair_applied": int(repair_nose or np.max(reverse_distances) > limit),
        "leading_edge_source_turn_deg": leading_turn,
        "leading_edge_repair_tolerance_pct": 0.001,
        "leading_edge_anchor_shift_pct": float(np.linalg.norm(curve[new_leading] - points[leading]) / chord),
        "wall_reconstruction_anchors": anchor_count,
    }
