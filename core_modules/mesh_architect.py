"""直接生成二维翼型严格尖后缘、全结构化多块 C-H 型网格。

翼型壁面从上侧尖后缘连续绕过唯一前缘点到下侧尖后缘；两个后缘逻辑端在
物理坐标上严格重合。近壁 C 形附面层与半椭圆外部 C 块连接，后方上下两个
H 块沿同一水平尾迹切线共形连接。四个块保持共形，所有体单元均为四边形。
首层高度、附面层厚度、扩张比、三个局部尺寸、尾迹加密与全局加密系数共同
决定节点分布。

网格同时写出 SU2 原生格式与 Gmsh 2.2 ASCII 格式。Gmsh 只用于可选预览，
不是生成网格的依赖。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from numpy.typing import ArrayLike, NDArray

from core_modules.process_control import ProcessController
from core_modules.surface_curve import reconstruct_perimeter

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

MARKER_ORDER = ("airfoil", "farfield_inlet", "farfield_outlet")
GLOBAL_REFINEMENT_MIN = 0.05
GLOBAL_REFINEMENT_MAX = 10.0
WAKE_REFINEMENT_MIN = 1.0
WAKE_REFINEMENT_MAX = 12.0
DOMAIN_SCALE_MIN = 0.25
DOMAIN_SCALE_MAX = 10.0


def _load_gmsh() -> Any:
    """仅为可选的 GUI 预览加载 Gmsh。"""
    import importlib
    import os
    import sys

    override = os.environ.get("SU2_STUDIO_GMSH_PYTHON_PATH")
    if override:
        module_dir = Path(override).expanduser().resolve()
        if not module_dir.is_dir():
            raise FileNotFoundError(f"Gmsh Python directory does not exist: {module_dir}")
        if str(module_dir) not in sys.path:
            sys.path.insert(0, str(module_dir))
        # Do not retain a module imported from a previous configured runtime.
        sys.modules.pop("gmsh", None)
        importlib.invalidate_caches()
    try:
        import gmsh  # type: ignore
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "无法加载 Gmsh 预览器。网格已经生成，可直接打开 mesh.msh；"
            "如需内置预览，请设置 SU2_STUDIO_GMSH_PYTHON_PATH，"
            "或安装 requirements.txt 中的 gmsh。"
        ) from exc
    return gmsh


def _rotate_to_chord_axis(
    x_values: FloatArray,
    y_values: FloatArray,
) -> tuple[FloatArray, FloatArray, float]:
    """旋转坐标使弦线沿 +x，返回旋转坐标、弦线中点与弦长。"""
    points = np.column_stack((x_values, y_values))
    leading = points[np.argmin(points[:, 0])]
    trailing_candidates = points[points[:, 0] >= np.max(points[:, 0]) - 1.0e-10]
    trailing = np.mean(trailing_candidates, axis=0)
    chord_vector = trailing - leading
    chord = float(np.linalg.norm(chord_vector))
    if chord <= 0.0:
        raise ValueError("翼型弦长必须大于 0。")
    theta = float(np.arctan2(chord_vector[1], chord_vector[0]))
    rotation = np.array(
        [[np.cos(theta), np.sin(theta)], [-np.sin(theta), np.cos(theta)]]
    )
    rotated = points @ rotation.T
    center = 0.5 * (leading + trailing) @ rotation.T
    return rotated, center, chord


def _signed_polygon_area(points: FloatArray) -> float:
    return 0.5 * float(
        np.sum(
            points[:, 0] * np.roll(points[:, 1], -1)
            - np.roll(points[:, 0], -1) * points[:, 1]
        )
    )


def _clean_sharp_boundary(points: FloatArray, chord: float) -> FloatArray:
    """清理尖后缘壁面，同时保留首末两个重合的逻辑端点。"""
    tolerance = max(chord, 1.0) * 1.0e-12
    step = np.linalg.norm(np.diff(points, axis=0), axis=1)
    points = points[np.r_[True, step > tolerance]]
    if len(points) < 15:
        raise ValueError("清理后的尖后缘翼型边界点不足 15 个。")
    if np.linalg.norm(points[0] - points[-1]) > 1.0e-8 * max(chord, 1.0):
        raise ValueError("翼型首末点必须是同一个尖后缘；请先执行尖后缘重构。")
    if _signed_polygon_area(points) < 0.0:
        points = points[::-1]
    return points




def _resample_open_section(
    path: FloatArray,
    start_size: float,
    end_size: float,
    middle_size: float,
    refinement: float,
    minimum_intervals: int,
    curvature_weight: float,
    start_effective_size: float | None = None,
    end_effective_size: float | None = None,
) -> FloatArray:
    """按两端目标尺寸和曲率度量重采样一条翼型分段。"""
    segment = np.diff(path, axis=0)
    length = np.linalg.norm(segment, axis=1)
    cumulative_length = np.r_[0.0, np.cumsum(length)]
    total_length = float(cumulative_length[-1])
    if total_length <= 0.0:
        raise ValueError("翼型分段长度必须大于 0。")
    parameter = cumulative_length / total_length
    geometric_end_sizes = np.exp(
        (1.0 - parameter) * np.log(start_size)
        + parameter * np.log(end_size)
    )
    middle_reference = np.sqrt(start_size * end_size)
    bump = 4.0 * parameter * (1.0 - parameter)
    desired_size = geometric_end_sizes * (
        middle_size / max(middle_reference, 1.0e-300)
    ) ** bump
    desired_size /= refinement

    previous = path - np.roll(path, 1, axis=0)
    following = np.roll(path, -1, axis=0) - path
    denominator = np.maximum(
        np.linalg.norm(previous, axis=1) * np.linalg.norm(following, axis=1),
        1.0e-300,
    )
    turn = np.arccos(
        np.clip(np.sum(previous * following, axis=1) / denominator, -1.0, 1.0)
    )
    turn[[0, -1]] = 0.0
    curvature = np.zeros(len(path))
    curvature[1:-1] = turn[1:-1] / np.maximum(.5 * (length[:-1] + length[1:]), 1e-300)
    curvature[0], curvature[-1] = curvature[1], curvature[-2]
    segment_metric = length / np.maximum(
        0.5 * (desired_size[:-1] + desired_size[1:]), 1.0e-300
    )
    segment_metric += curvature_weight * length * .5 * (curvature[:-1] + curvature[1:])
    # Limit the spatial gradient of the *effective* size (including curvature).
    # A smooth analytic curve alone does not prevent abrupt cell-size changes
    # where a curvature peak meets a coarse user target. Forward/backward
    # propagation only refines the requested field and bounds dh/ds by 0.10.
    effective_size = length / np.maximum(segment_metric, 1e-300)
    if start_effective_size is not None:
        effective_size[0] = start_effective_size
    if end_effective_size is not None:
        effective_size[-1] = end_effective_size
    midpoint = .5 * (cumulative_length[:-1] + cumulative_length[1:])
    for index in range(1, len(effective_size)):
        effective_size[index] = min(
            effective_size[index], effective_size[index-1] + .10 * (midpoint[index]-midpoint[index-1]))
    for index in range(len(effective_size)-2, -1, -1):
        effective_size[index] = min(
            effective_size[index], effective_size[index+1] + .10 * (midpoint[index+1]-midpoint[index]))
    segment_metric = length / np.maximum(effective_size, 1e-300)
    metric_cumulative = np.r_[0.0, np.cumsum(segment_metric)]
    interval_count = max(minimum_intervals, int(np.ceil(metric_cumulative[-1])))
    targets = np.linspace(0.0, metric_cumulative[-1], interval_count + 1)
    indices = np.searchsorted(metric_cumulative, targets, side="right") - 1
    indices = np.clip(indices, 0, len(segment_metric) - 1)
    local = (targets - metric_cumulative[indices]) / np.maximum(
        segment_metric[indices], 1.0e-300
    )
    sampled = path[indices] + local[:, None] * segment[indices]
    sampled[0] = path[0]
    sampled[-1] = path[-1]
    return sampled


def _wall_spacing_statistics(
    boundary: FloatArray,
    leading_index: int,
    chord: float,
) -> dict[str, float | int]:
    """Return wall-spacing diagnostics relevant to leading-edge striping."""
    edge = np.linalg.norm(np.diff(boundary, axis=0), axis=1)
    adjacent_ratio = np.maximum(
        edge[1:] / np.maximum(edge[:-1], 1.0e-300),
        edge[:-1] / np.maximum(edge[1:], 1.0e-300),
    )
    leading_x = float(boundary[leading_index, 0])
    front_limit = leading_x + 0.05 * chord
    upper_front = int(np.count_nonzero(boundary[: leading_index + 1, 0] <= front_limit))
    lower_front = int(np.count_nonzero(boundary[leading_index:, 0] <= front_limit))
    return {
        "leading_edge_nodes_upper_5pct": upper_front,
        "leading_edge_nodes_lower_5pct": lower_front,
        "wall_spacing_min_pct": float(np.min(edge) / chord),
        "wall_spacing_median_pct": float(np.median(edge) / chord),
        "wall_spacing_max_pct": float(np.max(edge) / chord),
        "wall_spacing_max_adjacent_ratio": float(np.max(adjacent_ratio)),
    }


def _uniform_farfield_body_angles(
    surface_nodes: int,
    leading_index: int,
) -> FloatArray:
    """Map C-grid columns to an index-uniform semicircular farfield.

    Wall nodes deliberately cluster at the leading edge.  Reusing wall arc
    length as the outer-boundary parameter carries that clustering all the way
    to the farfield and creates alternating dense/sparse radial sectors.  The
    block already has a smooth Hermite transition, so only the wall end should
    retain the clustered distribution; the farfield end is equiangular on
    each side of the unique leading-edge column.
    """
    if not 1 < leading_index < surface_nodes - 2:
        raise ValueError("前缘索引不足以构造均匀远场分布。")
    upper = np.linspace(0.5 * np.pi, np.pi, leading_index + 1)
    lower = np.linspace(
        np.pi,
        1.5 * np.pi,
        surface_nodes - leading_index,
    )
    return np.r_[upper, lower[1:]]


def _resample_sharp_airfoil(
    points: FloatArray,
    chord: float,
    leading_edge_size_pct: float,
    trailing_upper_size_pct: float,
    trailing_lower_size_pct: float,
    global_refinement: float,
) -> tuple[FloatArray, dict[str, int]]:
    """以一个前缘点和两个重合后缘逻辑端点重采样尖后缘翼型。"""
    leading_index = int(np.argmin(points[:, 0]))
    if leading_index <= 1 or leading_index >= len(points) - 2:
        raise ValueError("无法在尖后缘 C 形壁面上识别唯一前缘。")
    smooth, smooth_leading, _ = reconstruct_perimeter(points, chord)
    upper_path = smooth[: smooth_leading + 1]
    lower_path = smooth[smooth_leading:]
    leading_size = leading_edge_size_pct * chord
    smooth_edges = np.diff(smooth, axis=0)
    smooth_lengths = np.linalg.norm(smooth_edges, axis=1)
    unit_edges = smooth_edges / np.maximum(smooth_lengths[:, None], 1e-300)
    smooth_turn = np.arccos(np.clip(np.sum(unit_edges[:-1]*unit_edges[1:], axis=1), -1, 1))
    smooth_curvature = smooth_turn / np.maximum(.5*(smooth_lengths[:-1]+smooth_lengths[1:]), 1e-300)
    front = smooth[1:-1, 0] < smooth[smooth_leading, 0] + .01 * chord
    nose_curvature = float(np.max(smooth_curvature[front])) if np.any(front) else 0.
    # Both sides meet at the same physical nose and must use the same metric
    # size there. Independently extrapolated curvature on cambered sections
    # caused a coarse-grid size jump precisely at the LE seam.
    nose_metric_size = 1. / max(global_refinement / leading_size + 8.*nose_curvature, 1e-300)
    te_upper_size = trailing_upper_size_pct * chord
    te_lower_size = trailing_lower_size_pct * chord
    # A 0.012c mid-chord target keeps the circumferential lines considerably
    # more uniform than the old 0.018c value.  Together with the finer default
    # LE target this prevents a small set of leading-edge rays from feeding a
    # much coarser body grid, which was visible as alternating radial bands.
    surface_middle_size = 0.012 * chord
    sampled_upper = _resample_open_section(
        upper_path,
        te_upper_size,
        leading_size,
        surface_middle_size,
        global_refinement,
        48,
        8.0,
        end_effective_size=nose_metric_size,
    )
    sampled_lower = _resample_open_section(
        lower_path,
        leading_size,
        te_lower_size,
        surface_middle_size,
        global_refinement,
        48,
        8.0,
        start_effective_size=nose_metric_size,
    )
    boundary = np.vstack((sampled_upper, sampled_lower[1:]))
    boundary[-1] = boundary[0]
    control_indices = {
        "te_upper": 0,
        "leading": len(sampled_upper) - 1,
        "te_lower": len(boundary) - 1,
    }
    return boundary, control_indices


def _open_boundary_normals(points: FloatArray, center: FloatArray) -> FloatArray:
    """计算尖后缘开口 C 形壁面的流体侧法向，端点使用单侧切线。"""
    segment = np.diff(points, axis=0)
    segment /= np.maximum(np.linalg.norm(segment, axis=1)[:, None], 1.0e-300)
    tangent = np.empty_like(points)
    tangent[0] = segment[0]
    tangent[-1] = segment[-1]
    tangent[1:-1] = segment[:-1] + segment[1:]
    # Smooth the direction field, not the wall coordinates.  A compact
    # binomial stencil suppresses one-cell changes of radial-line angle near
    # the nose while preserving the unique LE point and the exact airfoil.
    kernel = np.array([1.0, 4.0, 6.0, 4.0, 1.0], dtype=float) / 16.0
    padded = np.pad(tangent, ((2, 2), (0, 0)), mode="edge")
    tangent = np.column_stack(
        [np.convolve(padded[:, component], kernel, mode="valid") for component in range(2)]
    )
    tangent[0] = segment[0]
    tangent[-1] = segment[-1]
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1)[:, None], 1.0e-300)
    normals = np.column_stack((tangent[:, 1], -tangent[:, 0]))
    if float(np.median(np.sum(normals * (points - center), axis=1))) < 0.0:
        normals = -normals
    return normals / np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1.0e-300)




def _geometric_sum(first: float, ratio: float, count: int) -> float:
    if abs(ratio - 1.0) < 1.0e-12:
        return first * count
    return first * (ratio**count - 1.0) / (ratio - 1.0)


def _solve_growth_ratio(first: float, total: float, count: int) -> float:
    if first * count >= total:
        return 1.0
    lower, upper = 1.0, 1.1
    while _geometric_sum(first, upper, count) < total and upper < 4.0:
        upper *= 1.15
    if upper >= 4.0 and _geometric_sum(first, upper, count) < total:
        raise ValueError("径向层数过少，无法在附面层厚度内保持合理扩张。")
    for _ in range(80):
        middle = 0.5 * (lower + upper)
        if _geometric_sum(first, middle, count) < total:
            lower = middle
        else:
            upper = middle
    return 0.5 * (lower + upper)


def _boundary_layer_distances(
    first_height: float,
    thickness: float,
    requested_ratio: float,
    refinement: float,
) -> tuple[FloatArray, float]:
    base_layers = 1
    while _geometric_sum(first_height, requested_ratio, base_layers) < thickness:
        base_layers += 1
        if base_layers > 10000:
            raise ValueError("附面层参数会产生过多径向层。")
    layer_count = max(3, int(np.ceil(base_layers * refinement)))
    # A coarse global factor may reduce surface and far-field resolution, but
    # it must not turn the viscous layer into a handful of cells.  Ratios near
    # two produced acceptable geometric metrics while over-predicting drag by
    # more than 100% in the NASA NACA0012 check.
    coarse_ratio_cap = min(1.30, max(requested_ratio, 1.01))
    while _geometric_sum(first_height, coarse_ratio_cap, layer_count) < thickness:
        layer_count += 1
    actual_ratio = _solve_growth_ratio(first_height, thickness, layer_count)
    # 低全局密度不能破坏近壁层的物理约束。必要时只把径向层数抬到
    # “实际扩张比 <= 2”所需的最低值，其余切向/外场密度仍按用户系数降低。
    while actual_ratio > coarse_ratio_cap and layer_count < base_layers:
        layer_count += 1
        actual_ratio = _solve_growth_ratio(first_height, thickness, layer_count)
    cells = first_height * actual_ratio ** np.arange(layer_count, dtype=float)
    # 第一层严格保持 first_height，只用末层吸收极小的求根舍入误差。
    cells[-1] += thickness - float(np.sum(cells))
    return np.r_[0.0, np.cumsum(cells)], actual_ratio


def estimate_mesh_counts(
    X_coord: ArrayLike,
    Y_coord: ArrayLike,
    delta_y: float,
    *,
    farfield_chords: float = 20.0,
    domain_scale: float = 1.0,
    boundary_layer_thickness_pct: float = 0.08,
    growth_ratio: float = 1.15,
    farfield_size_pct: float = 0.4,
    global_refinement: float = 1.0,
    leading_edge_size_pct: float = 0.0015,
    trailing_upper_size_pct: float = 0.0015,
    trailing_lower_size_pct: float = 0.0015,
    wake_refinement: float = 2.0,
) -> dict[str, int | float]:
    """Cheaply estimate the structured-grid size without constructing blocks.

    Circumferential, boundary-layer and wake counts use the same routines as the
    real generator.  Only the external C-block radial count is approximated,
    so the displayed total is labelled as an estimate until generation ends.
    """
    x_values = np.asarray(X_coord, dtype=float).reshape(-1)
    y_values = np.asarray(Y_coord, dtype=float).reshape(-1)
    rotated, _, chord = _rotate_to_chord_axis(x_values, y_values)
    boundary = _clean_sharp_boundary(rotated, chord)
    inner, controls = _resample_sharp_airfoil(
        boundary,
        chord,
        leading_edge_size_pct,
        trailing_upper_size_pct,
        trailing_lower_size_pct,
        global_refinement,
    )
    del controls
    effective_farfield = farfield_chords * domain_scale
    radius = effective_farfield * chord
    bl_thickness = boundary_layer_thickness_pct * chord
    distances, _ = _boundary_layer_distances(
        delta_y, bl_thickness, growth_ratio, global_refinement
    )
    bl_cells = len(distances) - 1
    last_bl_height = float(distances[-1] - distances[-2])
    domain_coarsening = max(1.0, effective_farfield / 20.0)
    target_outer_size = (
        farfield_size_pct * chord * domain_coarsening / global_refinement
    )
    external_path = max(radius - bl_thickness, 0.1 * chord)
    outer_cells = len(
        _outer_weights(external_path, last_bl_height, target_outer_size)
    ) - 1
    wake_first_size = (
        np.sqrt(trailing_upper_size_pct * trailing_lower_size_pct)
        * chord
        / (global_refinement * wake_refinement)
    )
    wake_target_size = target_outer_size / wake_refinement
    wake_cells = len(_outer_weights(radius, wake_first_size, wake_target_size)) - 1
    radial_cells = bl_cells + outer_cells
    surface_cells = len(inner) - 1
    quadrilateral_cells = radial_cells * (surface_cells + 2 * wake_cells)
    # Euler's relation for this conformal multi-block topology makes node and
    # cell counts close.  Include the boundary surplus for a useful memory hint.
    estimated_nodes = quadrilateral_cells + surface_cells + 2 * wake_cells + 1
    return {
        "surface_nodes": len(inner),
        "radial_nodes": radial_cells + 1,
        "wake_streamwise_nodes": wake_cells + 1,
        "quadrilateral_cells": int(quadrilateral_cells),
        "total_nodes": int(estimated_nodes),
        "effective_farfield_chords": float(effective_farfield),
    }


def _outer_weights(
    path_length: float,
    first_size: float,
    target_size: float,
) -> FloatArray:
    first_size = max(first_size, path_length * 1.0e-8)
    target_size = max(target_size, first_size)
    if target_size / first_size < 1.0 + 1.0e-9:
        mean_size = first_size
    else:
        mean_size = (target_size - first_size) / np.log(target_size / first_size)
    count = max(12, int(np.ceil(path_length / max(mean_size, 1.0e-12))))
    weights = np.geomspace(first_size, target_size, count)
    weights *= path_length / float(np.sum(weights))
    return np.r_[0.0, np.cumsum(weights) / path_length]


def _quad_connectivity(radial_nodes: int, circumferential_nodes: int) -> IntArray:
    quads = np.empty(((radial_nodes - 1) * circumferential_nodes, 4), dtype=np.int64)
    cursor = 0
    for j in range(radial_nodes - 1):
        inner = j * circumferential_nodes
        outer = (j + 1) * circumferential_nodes
        for i in range(circumferential_nodes):
            following = (i + 1) % circumferential_nodes
            # 1 基索引，逆时针：内层当前 -> 外层当前 -> 外层下一点 -> 内层下一点。
            quads[cursor] = (
                inner + i + 1,
                outer + i + 1,
                outer + following + 1,
                inner + following + 1,
            )
            cursor += 1
    return quads


def _quality_metrics(nodes: FloatArray, quads: IntArray) -> dict[str, float]:
    polygons = nodes[quads - 1, :2]
    x = polygons[:, :, 0]
    y = polygons[:, :, 1]
    signed_area = 0.5 * np.sum(
        x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y,
        axis=1,
    )
    edge = np.roll(polygons, -1, axis=1) - polygons
    edge_length = np.linalg.norm(edge, axis=2)
    minimum_angles: list[FloatArray] = []
    scaled_jacobians: list[FloatArray] = []
    for corner in range(4):
        to_previous = polygons[:, (corner - 1) % 4] - polygons[:, corner]
        to_next = polygons[:, (corner + 1) % 4] - polygons[:, corner]
        denominator = np.maximum(
            np.linalg.norm(to_previous, axis=1) * np.linalg.norm(to_next, axis=1),
            1.0e-300,
        )
        cosine = np.sum(to_previous * to_next, axis=1) / denominator
        angle = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
        # Signed corner Jacobians are essential: taking abs() made a concave
        # or locally inverted corner appear valid despite positive total area.
        cross = (
            to_previous[:, 1] * to_next[:, 0]
            - to_previous[:, 0] * to_next[:, 1]
        ) / denominator
        angle = np.where(cross < 0.0, 360.0 - angle, angle)
        minimum_angles.append(angle)
        scaled_jacobians.append(cross)
    all_angles = np.column_stack(minimum_angles)
    all_jacobians = np.column_stack(scaled_jacobians)
    aspect = np.max(edge_length, axis=1) / np.maximum(
        np.min(edge_length, axis=1), 1.0e-300
    )
    return {
        "minimum_signed_area": float(np.min(signed_area)),
        "maximum_signed_area": float(np.max(signed_area)),
        "minimum_angle_deg": float(np.min(all_angles)),
        "maximum_angle_deg": float(np.max(all_angles)),
        "minimum_scaled_jacobian": float(np.min(all_jacobians)),
        "median_scaled_jacobian": float(np.median(all_jacobians)),
        "maximum_aspect_ratio": float(np.max(aspect)),
    }


def _structured_block_quads(
    rows: int,
    columns: int,
    periodic_columns: bool = False,
) -> IntArray:
    """生成一个结构块的 0 基四边形连通性。"""
    column_cells = columns if periodic_columns else columns - 1
    row_index = np.arange(rows - 1, dtype=np.int64)[:, None]
    column_index = np.arange(column_cells, dtype=np.int64)[None, :]
    following = (column_index + 1) % columns
    lower = row_index * columns
    upper = (row_index + 1) * columns
    return np.stack(
        (
            lower + column_index,
            upper + column_index,
            upper + following,
            lower + following,
        ),
        axis=2,
    ).reshape(-1, 4)


def _oriented_block_quads(
    grid: FloatArray,
    chord: float,
    periodic_columns: bool = False,
) -> IntArray:
    """返回统一为正面积的块连通性，并拒绝块内局部折叠。"""
    quads = _structured_block_quads(
        len(grid), len(grid[0]), periodic_columns=periodic_columns
    )
    polygons = grid.reshape(-1, 2)[quads]
    x = polygons[:, :, 0]
    y = polygons[:, :, 1]
    area = 0.5 * np.sum(
        x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y,
        axis=1,
    )
    if float(np.median(area)) < 0.0:
        quads = quads[:, [0, 3, 2, 1]]
        area = -area
    if float(np.min(area)) <= 1.0e-16 * chord**2:
        raise ValueError("结构块内部出现折叠或零面积单元。")
    return quads


def _coons_patch(
    left: FloatArray,
    right: FloatArray,
    lower: FloatArray,
    upper: FloatArray,
) -> FloatArray:
    """由四条共角边界生成一个二维 Coons 结构块。"""
    if not (
        np.allclose(left[0], lower[0])
        and np.allclose(right[0], lower[-1])
        and np.allclose(left[-1], upper[0])
        and np.allclose(right[-1], upper[-1])
    ):
        raise ValueError("Coons 块的四条边界角点不一致。")
    vertical = np.linspace(0.0, 1.0, len(left))[:, None, None]
    horizontal = np.linspace(0.0, 1.0, len(lower))[None, :, None]
    side_blend = (1.0 - horizontal) * left[:, None, :] + horizontal * right[:, None, :]
    end_blend = (1.0 - vertical) * lower[None, :, :] + vertical * upper[None, :, :]
    bilinear = (
        (1.0 - vertical) * (1.0 - horizontal) * left[0]
        + (1.0 - vertical) * horizontal * right[0]
        + vertical * (1.0 - horizontal) * left[-1]
        + vertical * horizontal * right[-1]
    )
    patch = side_blend + end_blend - bilinear
    patch[:, 0] = left
    patch[:, -1] = right
    patch[0] = lower
    patch[-1] = upper
    return patch


def _hermite_grid(
    start: FloatArray,
    end: FloatArray,
    start_direction: FloatArray,
    end_direction: FloatArray,
    weights: FloatArray,
    tangent_scale: float,
) -> FloatArray:
    """在两条等点数边界间建立带端部方向约束的结构线族。"""
    path = np.linalg.norm(end - start, axis=1)[:, None]
    tangent_start = tangent_scale * start_direction * path
    tangent_end = tangent_scale * end_direction * path
    parameter = weights[:, None, None]
    h00 = 2.0 * parameter**3 - 3.0 * parameter**2 + 1.0
    h10 = parameter**3 - 2.0 * parameter**2 + parameter
    h01 = -2.0 * parameter**3 + 3.0 * parameter**2
    h11 = parameter**3 - parameter**2
    grid = (
        h00 * start[None, :, :]
        + h10 * tangent_start[None, :, :]
        + h01 * end[None, :, :]
        + h11 * tangent_end[None, :, :]
    )
    grid[0] = start
    grid[-1] = end
    return grid


def _interface_matched_hermite_grid(
    start: FloatArray,
    end: FloatArray,
    start_direction: FloatArray,
    end_direction: FloatArray,
    reference_height: FloatArray,
    path_length: float,
    target_size: float,
    tangent_scale: float,
) -> tuple[FloatArray, FloatArray]:
    """建立 Hermite 块，并迭代匹配接口两侧的典型单元高度。"""
    path = np.maximum(np.linalg.norm(end - start, axis=1), 1.0e-300)
    reference = np.maximum(np.asarray(reference_height, dtype=float), 1.0e-300)

    # 保持同一块内导数场光顺，只校正共同的首排步长。逐点强行拉伸导数会
    # 在尖后缘附近制造锯齿状网格线，反而破坏 H 型尾迹的平行性。
    requested_first_size = (
        float(np.median(reference))
        * path_length
        / max(
            tangent_scale * float(np.median(path)),
            1.0e-300,
        )
    )
    grid: FloatArray | None = None
    weights: FloatArray | None = None
    for _ in range(6):
        weights = _outer_weights(
            path_length,
            requested_first_size,
            target_size,
        )
        grid = _hermite_grid(
            start,
            end,
            start_direction,
            end_direction,
            weights,
            tangent_scale,
        )
        ratio = np.linalg.norm(grid[1] - grid[0], axis=1) / reference
        median_ratio = float(np.median(ratio))
        if 0.995 <= median_ratio <= 1.005:
            break
        requested_first_size *= float(
            np.clip(1.0 / max(median_ratio, 1.0e-12), 0.25, 4.0)
        )
    assert grid is not None and weights is not None
    return grid, weights


def _combine_block_quality(
    blocks: list[tuple[str, FloatArray, bool]],
    chord: float,
) -> tuple[FloatArray, IntArray, dict[str, float]]:
    """不合并接口节点地快速评估所有结构块；单元集合与合并后完全相同。"""
    nodes: list[FloatArray] = []
    quads: list[IntArray] = []
    offset = 0
    for _, grid, periodic in blocks:
        local_nodes = grid.reshape(-1, 2)
        local_quads = _oriented_block_quads(
            grid, chord, periodic_columns=periodic
        )
        nodes.append(local_nodes)
        quads.append(local_quads + offset + 1)
        offset += len(local_nodes)
    joined_nodes = np.vstack(nodes)
    joined_quads = np.vstack(quads)
    return joined_nodes, joined_quads, _quality_metrics(joined_nodes, joined_quads)


def _merge_structured_blocks(
    blocks: list[tuple[str, FloatArray, bool]],
    chord: float,
) -> tuple[FloatArray, IntArray, dict[str, IntArray]]:
    """合并共形块接口节点，返回全局节点、单元与每个块的节点编号阵列。"""
    tolerance = max(chord, 1.0) * 1.0e-11
    lookup: dict[tuple[int, int], int] = {}
    nodes: list[FloatArray] = []
    block_ids: dict[str, IntArray] = {}
    quads: list[IntArray] = []
    for name, grid, periodic in blocks:
        ids = np.empty(grid.shape[:2], dtype=np.int64)
        flat_ids = ids.reshape(-1)
        for index, point in enumerate(grid.reshape(-1, 2)):
            key = (
                int(np.rint(point[0] / tolerance)),
                int(np.rint(point[1] / tolerance)),
            )
            node_id = lookup.get(key)
            if node_id is None:
                node_id = len(nodes) + 1
                lookup[key] = node_id
                nodes.append(np.asarray(point, dtype=float))
            flat_ids[index] = node_id
        block_ids[name] = ids
        local_quads = _oriented_block_quads(
            grid, chord, periodic_columns=periodic
        )
        quads.append(flat_ids[local_quads])
    return np.asarray(nodes), np.vstack(quads), block_ids




def _build_strict_sharp_ch_grid(
    inner: FloatArray,
    center: FloatArray,
    chord: float,
    farfield_chords: float,
    delta_y: float,
    boundary_layer_thickness_pct: float,
    growth_ratio: float,
    farfield_size_pct: float,
    global_refinement: float,
    leading_edge_size_pct: float,
    trailing_upper_size_pct: float,
    trailing_lower_size_pct: float,
    wake_refinement: float,
    progress_callback: Callable[[float, str], None] | None = None,
) -> tuple[FloatArray, IntArray, dict[str, IntArray], dict[str, float | int | str]]:
    """生成尖后缘三块 C-H 外场与一个贴壁 C 形附面层块。"""
    progress = progress_callback or (lambda value, label: None)
    _, _, reconstruction = reconstruct_perimeter(inner, chord)
    progress(15, "连续壁面重建与前缘修复")
    inner, control_indices = _resample_sharp_airfoil(
        inner,
        chord,
        leading_edge_size_pct,
        trailing_upper_size_pct,
        trailing_lower_size_pct,
        global_refinement,
    )
    surface_nodes = len(inner)
    leading = control_indices["leading"]
    wall_spacing = _wall_spacing_statistics(inner, leading, chord)
    # Manual deformation can create strongly varying source-point density or
    # local curvature.  The mesher always resamples the wall independently of
    # those source points, then rejects a boundary whose physical edge spacing
    # still changes too abruptly.  This prevents a formally valid volume mesh
    # from producing the visible alternating radial bands seen in CFD plots.
    if (
        wall_spacing["leading_edge_nodes_upper_5pct"] < 12
        or wall_spacing["leading_edge_nodes_lower_5pct"] < 12
        or wall_spacing["wall_spacing_max_adjacent_ratio"] > 1.20
    ):
        raise RuntimeError(
            "手调翼型的壁面重采样未通过均匀性门槛：前缘前 5% 弦长每侧至少 "
            "12 个节点，且相邻壁面边长比不得超过 1.20。"
            f"当前为上/下 {wall_spacing['leading_edge_nodes_upper_5pct']}/"
            f"{wall_spacing['leading_edge_nodes_lower_5pct']} 个节点，最大边长比 "
            f"{wall_spacing['wall_spacing_max_adjacent_ratio']:.3f}。"
            "请减小局部尖锐变形或提高全局加密后重试。"
        )
    trailing_x = float(inner[0, 0])
    trailing_y = float(inner[0, 1])
    farfield_radius = farfield_chords * chord
    farfield_center = np.array([trailing_x, center[1]], dtype=float)
    outlet_x = trailing_x + farfield_radius

    # 一个真实前缘索引贯通上下表面，不再在前缘附近人为切出两个控制点。
    body_angles = _uniform_farfield_body_angles(surface_nodes, leading)
    outer_body = farfield_center + farfield_radius * np.column_stack(
        (np.cos(body_angles), np.sin(body_angles))
    )

    bl_thickness = boundary_layer_thickness_pct * chord
    distances, actual_growth = _boundary_layer_distances(
        delta_y, bl_thickness, growth_ratio, global_refinement
    )
    normals = _open_boundary_normals(inner, center)
    front_mask = inner[:, 0] <= float(inner[leading, 0]) + 0.05 * chord
    normal_step = np.degrees(
        np.arccos(
            np.clip(np.sum(normals[:-1] * normals[1:], axis=1), -1.0, 1.0)
        )
    )
    front_pairs = front_mask[:-1] & front_mask[1:]
    front_normal_step = normal_step[front_pairs]
    if len(front_normal_step) and float(np.max(front_normal_step)) > 8.0:
        raise RuntimeError(
            "前缘径向方向变化超过 8°；请减小前缘目标尺寸或提高全局加密。"
            f"当前最大变化 {np.max(front_normal_step):.2f}°。"
        )
    desired_direction = outer_body - inner
    desired_direction /= np.maximum(
        np.linalg.norm(desired_direction, axis=1)[:, None], 1.0e-300
    )
    domain_coarsening = max(1.0, farfield_chords / 20.0)
    target_outer_size = (
        farfield_size_pct * chord * domain_coarsening / global_refinement
    )

    # 尾迹流向首格直接继承后缘切向目标尺寸；加密系数同时减小首格与远端
    # 目标尺寸，使整个尾迹而不只是后缘附近得到加密。
    wake_first_size = (
        np.sqrt(trailing_upper_size_pct * trailing_lower_size_pct)
        * chord
        / (global_refinement * wake_refinement)
    )
    wake_target_size = target_outer_size / wake_refinement
    wake_weights = _outer_weights(
        farfield_radius,
        wake_first_size,
        wake_target_size,
    )
    wake_x = trailing_x + wake_weights * farfield_radius
    wake_centerline = np.column_stack(
        (wake_x, np.full(len(wake_x), trailing_y))
    )
    upper_far = np.column_stack(
        (wake_x, np.full(len(wake_x), center[1] + farfield_radius))
    )
    lower_far = np.column_stack(
        (wake_x, np.full(len(wake_x), center[1] - farfield_radius))
    )

    best: tuple[
        list[tuple[str, FloatArray, bool]],
        dict[str, float],
        float,
        float,
        float,
        FloatArray,
    ] | None = None
    failed_blocks: set[str] = set()
    blend_candidates = (
        (0.20, 0.80),
        (0.30, 0.80),
        (0.20, 0.70),
        (0.30, 0.70),
        (0.55, 0.70),
        (0.20, 0.60),
        (0.25, 0.60),
        (0.30, 0.60),
        (0.35, 0.60),
        (0.20, 0.65),
        (0.25, 0.65),
        (0.30, 0.65),
        (0.35, 0.65),
        (0.25, 0.55),
        (0.30, 0.55),
        (0.35, 0.55),
        (0.20, 0.45),
        (0.30, 0.45),
        (0.55, 0.45),
        (0.35, 0.35),
        (0.55, 0.35),
    )
    progress(28, "构造贴壁层与外场连接")
    for candidate_index, (blend_power, terminal_blend) in enumerate(blend_candidates):
        progress(30 + 40 * candidate_index / len(blend_candidates), "优化多块网格连接")
        bl_rings: list[FloatArray] = []
        for distance in distances:
            fraction = distance / max(bl_thickness, 1.0e-300)
            near_wall = np.clip(fraction / 0.12, 0.0, 1.0)
            near_wall = near_wall**2 * (3.0 - 2.0 * near_wall)
            blend = terminal_blend * fraction**blend_power * near_wall
            direction = (1.0 - blend) * normals + blend * desired_direction
            direction /= np.maximum(
                np.linalg.norm(direction, axis=1)[:, None], 1.0e-300
            )
            bl_rings.append(inner + distance * direction)
        bl_grid = np.asarray(bl_rings)
        try:
            _oriented_block_quads(bl_grid, chord, periodic_columns=False)
        except ValueError:
            failed_blocks.add("boundary_layer_c")
            continue

        bl_outer = bl_grid[-1]
        exit_direction = bl_grid[-1] - bl_grid[-2]
        exit_direction /= np.maximum(
            np.linalg.norm(exit_direction, axis=1)[:, None], 1.0e-300
        )
        body_end_direction = outer_body - farfield_center
        body_end_direction /= np.maximum(
            np.linalg.norm(body_end_direction, axis=1)[:, None], 1.0e-300
        )
        body_mean_path = float(
            np.mean(np.linalg.norm(outer_body - bl_outer, axis=1))
        )
        body_reference_height = np.linalg.norm(
            bl_grid[-1] - bl_grid[-2], axis=1
        )

        for tangent_scale in (
            1.0,
            0.70,
            0.50,
            0.35,
            0.25,
            0.18,
            0.12,
            0.08,
            0.05,
            0.03,
        ):
            main_grid, _ = _interface_matched_hermite_grid(
                bl_outer,
                outer_body,
                exit_direction,
                body_end_direction,
                body_reference_height,
                body_mean_path,
                target_outer_size,
                tangent_scale,
            )

            # C 块的上下开口由尖点经附面层和外场径向线延伸到远场；
            # 两个 H 块在完全水平的尾迹中心线上共形连接。
            upper_left = np.vstack((bl_grid[:, 0], main_grid[1:, 0]))
            lower_left = np.vstack((bl_grid[:, -1], main_grid[1:, -1]))
            upper_arc = np.r_[
                0.0,
                np.cumsum(np.linalg.norm(np.diff(upper_left, axis=0), axis=1)),
            ]
            lower_arc = np.r_[
                0.0,
                np.cumsum(np.linalg.norm(np.diff(lower_left, axis=0), axis=1)),
            ]
            upper_fraction = upper_arc / max(float(upper_arc[-1]), 1.0e-300)
            lower_fraction = lower_arc / max(float(lower_arc[-1]), 1.0e-300)
            upper_right = np.column_stack(
                (
                    np.full(len(upper_fraction), outlet_x),
                    trailing_y
                    + upper_fraction
                    * (center[1] + farfield_radius - trailing_y),
                )
            )
            lower_right = np.column_stack(
                (
                    np.full(len(lower_fraction), outlet_x),
                    trailing_y
                    + lower_fraction
                    * (center[1] - farfield_radius - trailing_y),
                )
            )
            try:
                upper_wake = _coons_patch(
                    upper_left,
                    upper_right,
                    wake_centerline,
                    upper_far,
                )
                lower_wake = _coons_patch(
                    lower_left,
                    lower_right,
                    wake_centerline,
                    lower_far,
                )
            except ValueError:
                failed_blocks.update(("upper_h_wake", "lower_h_wake"))
                continue
            blocks = [
                ("boundary_layer_c", bl_grid, False),
                ("c_body", main_grid, False),
                ("upper_h_wake", upper_wake, False),
                ("lower_h_wake", lower_wake, False),
            ]
            try:
                _, _, quality = _combine_block_quality(blocks, chord)
            except ValueError:
                for failed_name, failed_grid, failed_periodic in blocks:
                    try:
                        _oriented_block_quads(
                            failed_grid,
                            chord,
                            periodic_columns=failed_periodic,
                        )
                    except ValueError:
                        failed_blocks.add(failed_name)
                continue

            transition = np.linalg.norm(
                main_grid[1] - main_grid[0], axis=1
            ) / np.maximum(body_reference_height, 1.0e-300)
            transition_median = float(np.median(transition))
            if (
                not 0.80 <= transition_median <= 1.20
                or float(np.percentile(transition, 5.0)) < 0.65
                or float(np.percentile(transition, 95.0)) > 1.50
            ):
                continue
            score = quality["minimum_scaled_jacobian"]
            if best is None or score > best[1]["minimum_scaled_jacobian"]:
                best = (
                    blocks,
                    quality,
                    terminal_blend,
                    blend_power,
                    tangent_scale,
                    transition,
                )
        if best is not None and best[1]["minimum_scaled_jacobian"] >= 0.60:
            break

    if best is None:
        raise RuntimeError(
            "严格尖后缘 C-H 多块网格出现折叠。请减小附面层总厚度、"
            "放宽远场尺寸或提高全局加密后重试。"
            f"未通过的块：{', '.join(sorted(failed_blocks)) or '未知'}。"
        )
    (
        blocks,
        quality,
        selected_blend,
        selected_power,
        selected_scale,
        transition_ratio,
    ) = best
    if (
        quality["minimum_angle_deg"] < 30.0
        or quality["minimum_scaled_jacobian"] < 0.40
    ):
        block_quality_text = ", ".join(
            f"{name}={_quality_metrics(grid.reshape(-1, 2), _oriented_block_quads(grid, chord, periodic) + 1)['minimum_angle_deg']:.1f}°"
            for name, grid, periodic in blocks
        )
        raise RuntimeError(
            "严格尖后缘 C-H 网格未通过质量门槛：最小角必须不小于 30°，"
            "最小缩放 Jacobian 必须不小于 0.40。"
            f"当前为 {quality['minimum_angle_deg']:.2f}° / "
            f"{quality['minimum_scaled_jacobian']:.4f}；"
            f"各块最小角：{block_quality_text}。"
        )

    progress(75, "合并网格并检查 Jacobian")
    nodes, quads, block_ids = _merge_structured_blocks(blocks, chord)
    quality = _quality_metrics(nodes, quads)
    bl_grid = next(grid for name, grid, _ in blocks if name == "boundary_layer_c")
    wall_tangent = np.diff(bl_grid[0], axis=0)
    first_radial = .5 * ((bl_grid[1] - bl_grid[0])[:-1]
                         + (bl_grid[1] - bl_grid[0])[1:])
    orthogonality = np.degrees(np.arcsin(np.clip(np.abs(np.sum(
        wall_tangent * first_radial, axis=1)) / np.maximum(
            np.linalg.norm(wall_tangent, axis=1) * np.linalg.norm(first_radial, axis=1), 1e-300), 0, 1)))

    def open_edges(ids: IntArray) -> IntArray:
        return np.column_stack((ids[:-1], ids[1:])).astype(np.int64)

    wall_ids = block_ids["boundary_layer_c"][0]
    airfoil_edges = open_edges(wall_ids)
    inlet = np.vstack(
        (
            open_edges(block_ids["c_body"][-1]),
            open_edges(block_ids["upper_h_wake"][-1]),
            open_edges(block_ids["lower_h_wake"][-1]),
        )
    )
    outlet = np.vstack(
        (
            open_edges(block_ids["upper_h_wake"][:, -1]),
            open_edges(block_ids["lower_h_wake"][:, -1]),
        )
    )
    markers = {
        "airfoil": airfoil_edges,
        "farfield_inlet": inlet,
        "farfield_outlet": outlet,
    }
    block_map = {name: grid for name, grid, _ in blocks}
    bl_grid = block_map["boundary_layer_c"]
    main_grid = block_map["c_body"]
    upper_wake = block_map["upper_h_wake"]
    full_radial_nodes = len(upper_wake)
    bl_last_height = np.linalg.norm(bl_grid[-1] - bl_grid[-2], axis=1)
    external_first_height = np.linalg.norm(
        main_grid[1] - main_grid[0], axis=1
    )
    metadata: dict[str, float | int | str] = {
        "topology": "strict_sharp_te_multiblock_c_h_grid",
        "sharp_trailing_edge": "true",
        "trailing_edge_gap": float(np.linalg.norm(inner[0] - inner[-1])),
        "surface_nodes": surface_nodes,
        "circumferential_nodes": surface_nodes,
        "radial_nodes": full_radial_nodes,
        "boundary_layer_cells": (len(distances) - 1) * (surface_nodes - 1),
        "outer_field_cells": len(quads)
        - (len(distances) - 1) * (surface_nodes - 1),
        "quadrilateral_cells": len(quads),
        "total_nodes": len(nodes),
        "global_refinement": global_refinement,
        "wake_refinement": wake_refinement,
        "wake_length_chords": farfield_chords,
        "wake_boundary_spreading_angle_deg": 0.0,
        "wake_streamwise_nodes": len(wake_x),
        "wake_streamwise_first_cell_pct": float((wake_x[1] - wake_x[0]) / chord),
        "wake_streamwise_last_cell_pct": float((wake_x[-1] - wake_x[-2]) / chord),
        "wake_centerline_layers_per_side": len(distances) - 1,
        "upper_h_wake_cells": (upper_wake.shape[0] - 1)
        * (upper_wake.shape[1] - 1),
        "lower_h_wake_cells": (upper_wake.shape[0] - 1)
        * (upper_wake.shape[1] - 1),
        "c_body_cells": (main_grid.shape[0] - 1) * (main_grid.shape[1] - 1),
        "te_upper_control_index": control_indices["te_upper"],
        "leading_control_index": control_indices["leading"],
        "te_lower_control_index": control_indices["te_lower"],
        "leading_edge_target_size_pct": leading_edge_size_pct,
        "leading_edge_radial_direction_max_step_deg": float(
            np.max(front_normal_step) if len(front_normal_step) else 0.0
        ),
        "leading_edge_radial_direction_p95_step_deg": float(
            np.percentile(front_normal_step, 95.0) if len(front_normal_step) else 0.0
        ),
        "farfield_upper_angular_step_ratio": float(
            np.max(np.diff(body_angles[: leading + 1]))
            / max(np.min(np.diff(body_angles[: leading + 1])), 1.0e-300)
        ),
        "farfield_lower_angular_step_ratio": float(
            np.max(np.diff(body_angles[leading:]))
            / max(np.min(np.diff(body_angles[leading:])), 1.0e-300)
        ),
        "trailing_upper_target_size_pct": trailing_upper_size_pct,
        "trailing_lower_target_size_pct": trailing_lower_size_pct,
        "quality_gate_minimum_angle_deg": 30.0,
        "quality_gate_minimum_scaled_jacobian": 0.40,
        "quality_gate_minimum_leading_edge_nodes_per_side": 12,
        "quality_gate_maximum_wall_spacing_adjacent_ratio": 1.20,
        "quality_gate_maximum_leading_direction_step_deg": 8.0,
        "quality_gate_maximum_farfield_angular_step_ratio": 1.000001,
        "wall_first_layer_max_nonorthogonality_deg": float(np.max(orthogonality)),
        "wall_first_layer_p95_nonorthogonality_deg": float(np.percentile(orthogonality, 95)),
        "first_layer_height": delta_y,
        "boundary_layer_thickness": bl_thickness,
        "actual_boundary_layer_growth_ratio": actual_growth,
        "selected_radial_blend": selected_blend,
        "selected_radial_blend_power": selected_power,
        "selected_outer_tangent_scale": selected_scale,
        "median_boundary_layer_outer_cell_height": float(
            np.median(bl_last_height)
        ),
        "median_external_first_cell_height": float(
            np.median(external_first_height)
        ),
        "median_bl_to_external_height_ratio": float(
            np.median(transition_ratio)
        ),
        "p05_bl_to_external_height_ratio": float(
            np.percentile(transition_ratio, 5.0)
        ),
        "p95_bl_to_external_height_ratio": float(
            np.percentile(transition_ratio, 95.0)
        ),
        **wall_spacing,
        **reconstruction,
        **quality,
    }
    return nodes, quads, markers, metadata


def _write_su2_file(
    mesh_path: Path,
    nodes: FloatArray,
    triangles: IntArray,
    quads: IntArray,
    markers: dict[str, IntArray],
) -> None:
    """写出 SU2 原生二维网格；输入连通性采用 1 基索引。"""
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    quads = np.asarray(quads, dtype=np.int64).reshape(-1, 4)
    lines = ["NDIME= 2", f"NELEM= {len(triangles) + len(quads)}"]
    for triangle in triangles - 1:
        lines.append(f"5 {triangle[0]} {triangle[1]} {triangle[2]} 0")
    for quad in quads - 1:
        lines.append(f"9 {quad[0]} {quad[1]} {quad[2]} {quad[3]} 0")
    lines.append(f"NPOIN= {len(nodes)}")
    for node in nodes:
        lines.append(f"{node[0]:.15g} {node[1]:.15g}")
    lines.append(f"NMARK= {len(MARKER_ORDER)}")
    for name in MARKER_ORDER:
        edges = np.asarray(markers[name], dtype=np.int64).reshape(-1, 2) - 1
        lines.append(f"MARKER_TAG= {name}")
        lines.append(f"MARKER_ELEMS= {len(edges)}")
        for edge in edges:
            lines.append(f"3 {edge[0]} {edge[1]}")
    mesh_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_gmsh_file(
    mesh_path: Path,
    nodes: FloatArray,
    quads: IntArray,
    markers: dict[str, IntArray],
) -> None:
    """写出便于 Gmsh/ParaView 检查的 MSH 2.2 ASCII 文件。"""
    physical = {"airfoil": 2, "farfield_inlet": 3, "farfield_outlet": 4}
    element_count = len(quads) + sum(len(markers[name]) for name in MARKER_ORDER)
    lines = [
        "$MeshFormat",
        "2.2 0 8",
        "$EndMeshFormat",
        "$PhysicalNames",
        "4",
        '2 1 "fluid"',
        '1 2 "airfoil"',
        '1 3 "farfield_inlet"',
        '1 4 "farfield_outlet"',
        "$EndPhysicalNames",
        "$Nodes",
        str(len(nodes)),
    ]
    for index, node in enumerate(nodes, start=1):
        lines.append(f"{index} {node[0]:.15g} {node[1]:.15g} 0")
    lines.extend(("$EndNodes", "$Elements", str(element_count)))
    element_id = 1
    for name in MARKER_ORDER:
        tag = physical[name]
        for edge in markers[name]:
            lines.append(f"{element_id} 1 2 {tag} {tag} {edge[0]} {edge[1]}")
            element_id += 1
    for quad in quads:
        lines.append(
            f"{element_id} 3 2 1 1 {quad[0]} {quad[1]} {quad[2]} {quad[3]}"
        )
        element_id += 1
    lines.extend(("$EndElements", ""))
    mesh_path.write_text("\n".join(lines), encoding="utf-8")


def generate_mesh(
    X_coord: ArrayLike,
    Y_coord: ArrayLike,
    delta_y: float,
    output_dir: str | Path = "output_results",
    farfield_chords: float = 20.0,
    domain_scale: float = 1.0,
    boundary_layer_thickness_pct: float = 0.08,
    growth_ratio: float = 1.15,
    wall_size_pct: float = 0.008,
    farfield_size_pct: float = 0.4,
    global_refinement: float = 1.0,
    trailing_edge_radius_pct: float | None = None,
    leading_upper_size_pct: float | None = None,
    leading_lower_size_pct: float | None = None,
    trailing_upper_size_pct: float = 0.0015,
    trailing_lower_size_pct: float = 0.0015,
    wake_refinement: float = 2.0,
    show_gui: bool = False,
    terminal_output: bool = True,
    leading_edge_size_pct: float | None = None,
) -> Path:
    """生成严格尖后缘多块 C-H 型全四边形网格并写出 ``mesh.su2``。"""
    del wall_size_pct  # 兼容旧调用；全结构网格的切向尺寸由全局加密系数控制。
    del trailing_edge_radius_pct  # 兼容旧调用；当前几何始终使用严格尖后缘。
    if leading_edge_size_pct is None:
        legacy_upper = leading_upper_size_pct or 0.0015
        legacy_lower = leading_lower_size_pct or 0.0015
        leading_edge_size_pct = float(np.sqrt(legacy_upper * legacy_lower))
    x_values = np.asarray(X_coord, dtype=float).reshape(-1)
    y_values = np.asarray(Y_coord, dtype=float).reshape(-1)
    if len(x_values) != len(y_values) or len(x_values) < 15:
        raise ValueError("X_coord、Y_coord 必须等长且至少包含 15 个点。")
    if not np.all(np.isfinite(x_values)) or not np.all(np.isfinite(y_values)):
        raise ValueError("翼型坐标中存在 NaN 或无穷值。")
    if delta_y <= 0.0:
        raise ValueError("首层高度 delta_y 必须大于 0。")
    if not DOMAIN_SCALE_MIN <= domain_scale <= DOMAIN_SCALE_MAX:
        raise ValueError(
            f"流场域缩放系数应处于 [{DOMAIN_SCALE_MIN}, {DOMAIN_SCALE_MAX}]。"
        )
    effective_farfield_chords = farfield_chords * domain_scale
    if effective_farfield_chords < 5.0:
        raise ValueError("缩放后的远场距离至少应为 5 倍弦长。")
    if not 1.0 < growth_ratio <= 2.0:
        raise ValueError("附面层扩张比应处于 (1, 2]。")
    if not 0.0 < boundary_layer_thickness_pct <= 0.5:
        raise ValueError("附面层总厚度比例应处于 (0, 0.5]。")
    if not 0.0 < farfield_size_pct <= 5.0:
        raise ValueError("远场目标尺寸比例应处于 (0, 5]。")
    if not GLOBAL_REFINEMENT_MIN <= global_refinement <= GLOBAL_REFINEMENT_MAX:
        raise ValueError(
            f"全局加密系数应处于 [{GLOBAL_REFINEMENT_MIN}, {GLOBAL_REFINEMENT_MAX}]。"
        )
    control_sizes = (
        leading_edge_size_pct,
        trailing_upper_size_pct,
        trailing_lower_size_pct,
    )
    if any(not 0.0 < size <= 0.05 for size in control_sizes):
        raise ValueError("前缘、后缘上和后缘下尺寸比例都应处于 (0, 0.05]。")
    if not WAKE_REFINEMENT_MIN <= wake_refinement <= WAKE_REFINEMENT_MAX:
        raise ValueError(
            f"尾迹加密系数应处于 [{WAKE_REFINEMENT_MIN}, {WAKE_REFINEMENT_MAX}]。"
        )

    def progress(value: float, label: str) -> None:
        if terminal_output:
            print(f"MESH_PROGRESS|{value:.0f}|{label}", flush=True)

    progress(5, "检查输入几何")
    rotated, center, chord = _rotate_to_chord_axis(x_values, y_values)
    boundary = _clean_sharp_boundary(rotated, chord)
    if delta_y >= boundary_layer_thickness_pct * chord:
        raise ValueError("首层高度必须小于附面层总厚度。")

    nodes, quads, markers, metadata = _build_strict_sharp_ch_grid(
        boundary,
        center,
        chord,
        effective_farfield_chords,
        delta_y,
        boundary_layer_thickness_pct,
        growth_ratio,
        farfield_size_pct,
        global_refinement,
        leading_edge_size_pct,
        trailing_upper_size_pct,
        trailing_lower_size_pct,
        wake_refinement,
        progress_callback=progress,
    )
    metadata["farfield_base_chords"] = farfield_chords
    metadata["domain_scale"] = domain_scale
    metadata["effective_farfield_chords"] = effective_farfield_chords
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    mesh_path = output_path / "mesh.su2"
    msh_path = output_path / "mesh.msh"
    empty_triangles = np.empty((0, 3), dtype=np.int64)
    progress(84, "写入 SU2 网格")
    _write_su2_file(mesh_path, nodes, empty_triangles, quads, markers)
    progress(90, "写入预览与质量数据")
    _write_gmsh_file(msh_path, nodes, quads, markers)
    np.savez_compressed(
        output_path / "mesh_preview.npz", nodes=nodes,
        quads=quads - 1, wall_edges=markers["airfoil"] - 1,
        source_boundary=boundary,
    )
    (output_path / "mesh_quality.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if terminal_output:
        print(
            "Pointwise 风格全结构化 C-H 网格完成："
            f"{metadata['circumferential_nodes']} × {metadata['radial_nodes']} 节点，"
            f"{metadata['quadrilateral_cells']} 个四边形"
        )
        print(
            "质量："
            f"最小角 {metadata['minimum_angle_deg']:.2f}°，"
            f"最小缩放 Jacobian {metadata['minimum_scaled_jacobian']:.4f}"
        )
    progress(100, "网格完成")

    if show_gui:
        gmsh = _load_gmsh()
        initialized = False
        try:
            gmsh.initialize()
            initialized = True
            gmsh.option.setNumber("General.Terminal", 1 if terminal_output else 0)
            gmsh.open(str(msh_path))
            gmsh.fltk.run()
        finally:
            if initialized:
                gmsh.finalize()

    if not mesh_path.is_file() or mesh_path.stat().st_size == 0:
        raise RuntimeError("未生成有效的 mesh.su2。")
    return mesh_path


def generate_mesh_subprocess(
    X_coord: ArrayLike,
    Y_coord: ArrayLike,
    delta_y: float,
    output_dir: str | Path = "output_results",
    farfield_chords: float = 20.0,
    domain_scale: float = 1.0,
    boundary_layer_thickness_pct: float = 0.08,
    growth_ratio: float = 1.15,
    wall_size_pct: float = 0.008,
    farfield_size_pct: float = 0.4,
    global_refinement: float = 1.0,
    trailing_edge_radius_pct: float | None = None,
    leading_upper_size_pct: float | None = None,
    leading_lower_size_pct: float | None = None,
    trailing_upper_size_pct: float = 0.0015,
    trailing_lower_size_pct: float = 0.0015,
    wake_refinement: float = 2.0,
    show_gui: bool = False,
    log_callback: Callable[[str], None] | None = None,
    stop_event: threading.Event | None = None,
    process_control: ProcessController | None = None,
    python_executable: str | Path | None = None,
    leading_edge_size_pct: float | None = None,
) -> Path:
    """在独立进程中生成/预览网格，保持桌面界面响应。"""
    del trailing_edge_radius_pct
    if leading_edge_size_pct is None:
        legacy_upper = leading_upper_size_pct or 0.0015
        legacy_lower = leading_lower_size_pct or 0.0015
        leading_edge_size_pct = float(np.sqrt(legacy_upper * legacy_lower))
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    input_path = output / ".mesh_input.npz"
    np.savez(
        input_path,
        x=np.asarray(X_coord, dtype=float),
        y=np.asarray(Y_coord, dtype=float),
    )
    from .runtime_paths import resource_root, mesh_worker_command
    project_root = resource_root()
    prefix = ([str(python_executable), "-m", "core_modules.mesh_worker"]
              if python_executable else mesh_worker_command())
    command = prefix + [
        "--input",
        str(input_path),
        "--output",
        str(output),
        "--delta-y",
        f"{delta_y:.17g}",
        "--farfield",
        f"{farfield_chords:.17g}",
        "--domain-scale",
        f"{domain_scale:.17g}",
        "--bl-thickness",
        f"{boundary_layer_thickness_pct:.17g}",
        "--growth-ratio",
        f"{growth_ratio:.17g}",
        "--wall-size",
        f"{wall_size_pct:.17g}",
        "--farfield-size",
        f"{farfield_size_pct:.17g}",
        "--global-refinement",
        f"{global_refinement:.17g}",
        "--leading-edge-size",
        f"{leading_edge_size_pct:.17g}",
        "--trailing-upper-size",
        f"{trailing_upper_size_pct:.17g}",
        "--trailing-lower-size",
        f"{trailing_lower_size_pct:.17g}",
        "--wake-refinement",
        f"{wake_refinement:.17g}",
    ]
    if show_gui:
        command.append("--show-gui")

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creation_flags,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
    )
    if process_control:
        process_control.attach(process)
    captured_output: list[str] = []

    def read_output() -> None:
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            message = line.rstrip("\r\n")
            captured_output.append(message)
            if log_callback:
                log_callback(message)

    reader = threading.Thread(target=read_output, daemon=True, name="MeshOutputReader")
    reader.start()
    try:
        while process.poll() is None:
            if stop_event and stop_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise RuntimeError("全结构化网格生成已取消。")
            time.sleep(0.08)
        reader.join(timeout=2)
        return_code = int(process.returncode or 0)
    finally:
        if process_control:
            process_control.detach(process)
        if process.stdout:
            process.stdout.close()
        input_path.unlink(missing_ok=True)

    if return_code != 0:
        detail = captured_output[-1] if captured_output else "未返回错误详情"
        raise RuntimeError(f"网格子进程失败，退出码 {return_code}。\n{detail}")
    mesh_path = output / "mesh.su2"
    if not mesh_path.is_file() or mesh_path.stat().st_size == 0:
        raise RuntimeError("网格子进程未生成有效的 mesh.su2。")
    return mesh_path
