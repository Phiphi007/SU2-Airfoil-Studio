"""坐标读取、上下表面拆分，以及后缘拟合与尖点重构。

几何约定（见 docs/ARCHITECTURE.md）：

- 输入 DAT 顺序为：上后缘 -> 前缘 -> 下后缘（Selig 顺序）。
- 后缘只有“尖后缘”一种处理：用最后 5% 弦长内的上下表面直线拟合出尖点。
- 尖点通常位于原始坐标下游，超出原始 X 范围的尾部坐标必须沿拟合直线外推。
- 得到新尖点后，按“前缘到新尖点”的新弦长重新生成 Cosine 横坐标，
  防止最后一段异常拉长。
- 网格几何直接使用拟合后的数学尖点。旧版 ``round_trailing_edge`` 仅为兼容
  外部调用保留，不再进入软件默认流程。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

_TRAILING_FIT_FRACTION = 0.05
_TAIL_EXTEND_FRACTION = 0.001  # 平行退化情形下尖点相对弦长的下游推进量。
_MAX_TAIL_EXTEND_FRACTION = 0.02  # 防止噪声尾段交点把弦长非物理地拉长。
_TAIL_BLEND_START_FRACTION = 0.85  # 原始曲线与拟合直线开始平滑过渡的位置。


def load_airfoil(filepath: str | Path) -> FloatArray:
    """读取 Selig 顺序的翼型 DAT，返回 (N, 2) 坐标数组。"""
    path = Path(filepath).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到翼型文件: {path}")
    raw: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            values = [float(value) for value in text.replace(",", " ").split()]
        except ValueError:
            continue  # 跳过标题行等非坐标内容
        if len(values) >= 2:
            raw.append((values[0], values[1]))
    points = np.asarray(raw, dtype=float).reshape(-1, 2)
    if len(points) < 15:
        raise ValueError(f"翼型文件有效坐标点不足 15 个: {path}")
    if not np.all(np.isfinite(points)):
        raise ValueError(f"翼型坐标包含 NaN 或无穷值: {path}")
    return points


def split_surfaces(points: FloatArray) -> tuple[FloatArray, FloatArray]:
    """把 Selig 轮廓拆成两条可具有不同原始点数的表面。

    返回方向统一为“各自后缘 -> 共享前缘”。有限厚度后缘在这里保留，
    待两侧独立重采样后再由 :func:`sharpen_surfaces` 拟合成同一尖点。
    """
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("翼型坐标必须是 (N, 2) 数组。")
    chord_scale = float(np.ptp(points[:, 0]))
    if chord_scale <= 0.0:
        raise ValueError("翼型弦长必须大于 0。")
    tolerance = max(chord_scale, 1.0) * 1.0e-11

    step_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    points = points[np.r_[True, step_lengths > tolerance]]

    leading_index = int(np.argmin(points[:, 0]))
    if leading_index == 0 or leading_index == len(points) - 1:
        raise ValueError("无法识别前缘；坐标应为上后缘 -> 前缘 -> 下后缘。")
    upper = points[: leading_index + 1].copy()
    lower = points[leading_index:][::-1].copy()
    if len(upper) < 3 or len(lower) < 3:
        raise ValueError("上下表面都至少需要 3 个坐标点。")
    # 数值文件常把数学尖点写成 1e-4 弦长量级的小缝。它不包含可用的
    # 有限厚度尾缘几何信息，可安全合并；更大的真实厚度留给后续直线拟合。
    trailing_gap = float(np.linalg.norm(upper[0] - lower[0]))
    if trailing_gap <= max(2.0e-4 * chord_scale, tolerance):
        shared_trailing = 0.5 * (upper[0] + lower[0])
        upper[0] = lower[0] = shared_trailing
    if np.linalg.norm(upper[-1] - lower[-1]) > tolerance:
        raise ValueError("上下表面没有共享同一个前缘点。")
    return upper, lower


def _fit_tail_line(surface: FloatArray) -> tuple[float, float]:
    """对最后 5% 弦长内的表面点做直线拟合，返回 (斜率, 截距)。"""
    x_min = float(np.min(surface[:, 0]))
    cut = x_min + (1.0 - _TRAILING_FIT_FRACTION) * float(np.ptp(surface[:, 0]))
    tail = surface[surface[:, 0] >= cut]
    if len(tail) < 2:
        tail = surface[-2:]
    slope, intercept = np.polyfit(tail[:, 0], tail[:, 1], 1)
    return float(slope), float(intercept)


def _rebuild_sharp_surface(
    surface: FloatArray,
    tip_x: float,
    slope: float,
    intercept: float,
    point_count: int,
) -> FloatArray:
    """生成一条共享尖点、按新弦长 Cosine 分布的“尖后缘 -> 前缘”表面。

    原始区域（x < 过渡区起点）保留原始坐标；尾部区域用拟合直线描述，
    超出原始 X 范围的坐标沿该直线外推。原始曲线与拟合直线之间用
    smoothstep 平滑过渡，避免折角在网格中产生畸变单元。最后按
    “前缘 -> 新尖点”的新弦长重新生成 Cosine 横坐标并插值。
    """
    x_min = float(np.min(surface[:, 0]))
    span = float(np.ptp(surface[:, 0]))
    junction_x = x_min + (1.0 - _TRAILING_FIT_FRACTION) * span
    blend_start_x = x_min + _TAIL_BLEND_START_FRACTION * span

    # 新弦长 Cosine 横坐标：从尖点（x 大）到前缘（x 小）。
    theta = np.linspace(0.0, np.pi, point_count)
    cosine_x = 0.5 * (1.0 - np.cos(theta)) * (tip_x - x_min) + x_min

    # np.interp 需要递增横坐标；表面按“尖后缘 -> 前缘”存放，需先排序。
    order = np.argsort(surface[:, 0])
    original_y = np.interp(cosine_x, surface[order, 0], surface[order, 1])
    line_y = slope * cosine_x + intercept

    # smoothstep 权重：过渡区之前为 0（原始曲线），拟合区之后为 1（直线）。
    blend = np.clip(
        (cosine_x - blend_start_x) / max(junction_x - blend_start_x, 1.0e-12),
        0.0,
        1.0,
    )
    weight = blend**2 * (3.0 - 2.0 * blend)
    line_region = cosine_x >= junction_x
    weight[line_region] = 1.0
    y_values = (1.0 - weight) * original_y + weight * line_y
    # 返回“尖后缘 -> 前缘”方向（X 递减），与模块约定一致。
    return np.column_stack((cosine_x, y_values))[::-1]


def sharpen_surfaces(
    upper: FloatArray,
    lower: FloatArray,
    *,
    preserve_existing_sharp: bool = True,
) -> tuple[FloatArray, FloatArray]:
    """把上下表面重构为共享尖后缘，返回同样点数、同方向的表面。

    输入为“尖后缘 -> 前缘”方向；输出保持该方向。尾部最后 5% 弦长用
    上下两条拟合直线的交点作为尖点（通常位于原始坐标下游）。
    """
    upper = np.asarray(upper, dtype=float)
    lower = np.asarray(lower, dtype=float)
    if len(upper) != len(lower):
        raise ValueError("上下表面点数必须相同才能拟合尖后缘。")
    tolerance = max(float(np.ptp(upper[:, 0])), 1.0) * 1.0e-11
    if np.linalg.norm(upper[-1] - lower[-1]) > tolerance:
        raise ValueError("上下表面前缘不重合，无法拟合尖后缘。")

    # A mathematically sharp input already contains the intended trailing-edge
    # geometry.  Re-fitting its last 5% and blending from 85% was both
    # unnecessary and harmful for strongly cambered/deformed profiles: the
    # C1 smoothstep can introduce a small overshoot and alternating curvature
    # that is then visible in both the airfoil preview and CFD wall contour.
    # Preserve sharp inputs exactly after cosine resampling.  Finite-thickness
    # inputs still use the line-intersection reconstruction below.
    chord = max(float(np.ptp(np.r_[upper[:, 0], lower[:, 0]])), 1.0e-12)
    trailing_gap = float(np.linalg.norm(upper[0] - lower[0]))
    if preserve_existing_sharp and trailing_gap <= max(2.0e-4 * chord, tolerance):
        preserved_upper = upper.copy()
        preserved_lower = lower.copy()
        trailing = 0.5 * (preserved_upper[0] + preserved_lower[0])
        leading = 0.5 * (preserved_upper[-1] + preserved_lower[-1])
        preserved_upper[0] = preserved_lower[0] = trailing
        preserved_upper[-1] = preserved_lower[-1] = leading
        return preserved_upper, preserved_lower

    upper_slope, upper_intercept = _fit_tail_line(upper)
    lower_slope, lower_intercept = _fit_tail_line(lower)

    x_span = float(
        np.ptp(np.r_[upper[:, 0], lower[:, 0]])
    )
    x_max = float(np.max(np.r_[upper[:, 0], lower[:, 0]]))
    if abs(upper_slope - lower_slope) <= 1.0e-14:
        # 上下尾段平行（对称翼型退化情形）：取两直线夹缝中点作尖点。
        tip_x = x_max + _TAIL_EXTEND_FRACTION * x_span
        tip_y = 0.5 * (
            (upper_slope * tip_x + upper_intercept)
            + (lower_slope * tip_x + lower_intercept)
        )
    else:
        tip_x = (lower_intercept - upper_intercept) / (upper_slope - lower_slope)
        tip_y = upper_slope * tip_x + upper_intercept

    # 少量尾段点或局部噪声可能把两条拟合直线的交点推到很远下游，甚至
    # 推回原后缘上游。尖后缘重构不应因此把原翼型弦长改变数个百分点以上。
    unclamped_tip_x = float(tip_x)
    tip_x = float(
        np.clip(
            unclamped_tip_x,
            x_max,
            x_max + _MAX_TAIL_EXTEND_FRACTION * x_span,
        )
    )
    if abs(tip_x - unclamped_tip_x) > 1.0e-12:
        tip_y = 0.5 * (
            (upper_slope * tip_x + upper_intercept)
            + (lower_slope * tip_x + lower_intercept)
        )
        # 保持各自拟合斜率，同时让两条尾线都严格穿过受限后的公共尖点。
        upper_intercept = float(tip_y - upper_slope * tip_x)
        lower_intercept = float(tip_y - lower_slope * tip_x)

    upper_rebuilt = _rebuild_sharp_surface(
        upper, float(tip_x), upper_slope, upper_intercept, len(upper)
    )
    lower_rebuilt = _rebuild_sharp_surface(
        lower, float(tip_x), lower_slope, lower_intercept, len(lower)
    )
    # 强制共享同一尖点与前缘，消除浮点尾差。
    tip = np.array([float(tip_x), float(tip_y)])
    upper_rebuilt[0] = lower_rebuilt[0] = tip
    leading = 0.5 * (upper_rebuilt[-1] + lower_rebuilt[-1])
    upper_rebuilt[-1] = lower_rebuilt[-1] = leading
    return upper_rebuilt, lower_rebuilt


def _surface_y(surface: FloatArray, x_values: FloatArray) -> FloatArray:
    """在给定 X 位置线性插值表面 Y，并自动去除重复 X。"""
    order = np.argsort(surface[:, 0])
    x_sorted = surface[order, 0]
    y_sorted = surface[order, 1]
    unique_x, unique_indices = np.unique(x_sorted, return_index=True)
    return np.interp(x_values, unique_x, y_sorted[unique_indices])


def _blend_surface_to_round_cap(
    surface: FloatArray,
    x_values: FloatArray,
    join_x: float,
    target_y: float,
    blend_start_x: float,
) -> FloatArray:
    """用三次 Hermite 修正在后缘附近把表面平滑接到圆角端点。"""
    original_y = _surface_y(surface, x_values)
    chord = float(np.ptp(surface[:, 0]))
    sample_dx = max(1.0e-5 * chord, 1.0e-9)
    y_at_join = float(_surface_y(surface, np.array([join_x]))[0])
    y_before = float(
        _surface_y(surface, np.array([max(join_x - sample_dx, blend_start_x)]))[0]
    )
    slope = (y_at_join - y_before) / max(
        join_x - max(join_x - sample_dx, blend_start_x), 1.0e-12
    )

    length = max(join_x - blend_start_x, 1.0e-12)
    t = np.clip((x_values - blend_start_x) / length, 0.0, 1.0)
    # Hermite 基函数：修正量在过渡起点的值/斜率均为 0，在圆角端点把
    # 表面移动到 target_y，并把切线斜率收敛到 0（与半圆端点相切）。
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    correction = h01 * (target_y - y_at_join) + h11 * length * (-slope)
    return original_y + correction


def round_trailing_edge(
    upper: FloatArray,
    lower: FloatArray,
    radius_pct: float = 0.002,
) -> tuple[FloatArray, FloatArray, FloatArray, float]:
    """把共享尖后缘自动替换为可控半径的圆角。

    ``upper`` 与 ``lower`` 均为“后缘 -> 前缘”方向。圆角的最下游点保持在
    原尖点 X 位置，因此修改半径不会悄悄改变基准弦长。函数返回重构后的上、
    下表面、从下端点到上端点的圆弧，以及圆角的绝对半径。
    """
    upper = np.asarray(upper, dtype=float)
    lower = np.asarray(lower, dtype=float)
    if upper.shape != lower.shape or upper.ndim != 2 or upper.shape[1] != 2:
        raise ValueError("上下表面必须是形状相同的 (N, 2) 数组。")
    if not 0.0 < radius_pct <= 0.05:
        raise ValueError("后缘圆角半径比例应处于 (0, 0.05]。")

    chord = float(np.ptp(np.r_[upper[:, 0], lower[:, 0]]))
    if chord <= 0.0:
        raise ValueError("翼型弦长必须大于 0。")
    radius = radius_pct * chord
    tip_x = float(max(np.max(upper[:, 0]), np.max(lower[:, 0])))
    leading_x = float(min(np.min(upper[:, 0]), np.min(lower[:, 0])))
    join_x = tip_x - radius
    if join_x <= leading_x + 0.5 * chord:
        raise ValueError("后缘圆角半径过大，已侵入翼型中部。")

    count = len(upper)
    theta = np.linspace(0.0, np.pi, count)
    x_ascending = leading_x + 0.5 * (1.0 - np.cos(theta)) * (
        join_x - leading_x
    )
    x_values = x_ascending[::-1]

    join_sample = np.array([join_x])
    center_y = 0.5 * (
        float(_surface_y(upper, join_sample)[0])
        + float(_surface_y(lower, join_sample)[0])
    )
    blend_length = max(6.0 * radius, 0.03 * chord)
    blend_start_x = max(leading_x + 0.72 * chord, join_x - blend_length)
    upper_y = _blend_surface_to_round_cap(
        upper, x_values, join_x, center_y + radius, blend_start_x
    )
    lower_y = _blend_surface_to_round_cap(
        lower, x_values, join_x, center_y - radius, blend_start_x
    )
    rounded_upper = np.column_stack((x_values, upper_y))
    rounded_lower = np.column_stack((x_values, lower_y))

    # 消除端点累计误差，并保证共享同一个前缘。
    rounded_upper[0] = (join_x, center_y + radius)
    rounded_lower[0] = (join_x, center_y - radius)
    leading = 0.5 * (rounded_upper[-1] + rounded_lower[-1])
    rounded_upper[-1] = rounded_lower[-1] = leading

    # 圆弧从下端点沿最下游点走到上端点。至少 9 个点，避免导出坐标或
    # 低密度网格把圆角退化成明显折线。
    cap_count = max(9, min(65, int(np.ceil(np.pi * radius_pct * count * 4.0)) + 1))
    cap_angle = np.linspace(-0.5 * np.pi, 0.5 * np.pi, cap_count)
    cap = np.column_stack(
        (join_x + radius * np.cos(cap_angle), center_y + radius * np.sin(cap_angle))
    )
    cap[0] = rounded_lower[0]
    cap[-1] = rounded_upper[0]
    return rounded_upper, rounded_lower, cap, radius
