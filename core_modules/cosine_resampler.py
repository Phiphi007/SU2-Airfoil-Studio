"""上下表面共点数的 Cosine 重采样。

Cosine 分布按 ``x = 0.5*(1-cos(theta))`` 在弦向加密前缘与后缘，
使翼型两端（前缘驻点区、尖后缘区）的网格节点天然更密。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def resample_surface_cosine(
    surface: FloatArray,
    point_count: int,
) -> FloatArray:
    """把一条开放表面按弦向 Cosine 分布重采样为 ``point_count`` 个点。

    ``surface`` 要求按“后缘 -> 前缘”或“前缘 -> 后缘”顺序排列，
    返回的点保持与输入相同的方向（首个点坐标不变）。
    """
    surface = np.asarray(surface, dtype=float)
    if surface.ndim != 2 or surface.shape[1] != 2:
        raise ValueError("表面坐标必须是 (N, 2) 数组。")
    if point_count < 8:
        raise ValueError("每侧表面点数至少为 8。")
    if len(surface) < 2:
        raise ValueError("表面至少需要两个点。")

    x_min, x_max = float(np.min(surface[:, 0])), float(np.max(surface[:, 0]))
    span = x_max - x_min
    if span <= 0.0:
        raise ValueError("表面弦向跨度必须大于 0。")

    # 决定插值方向：若输入从后缘（x 最大）开始，则翻转后用反向插值。
    reversed_input = surface[0, 0] > surface[-1, 0]
    ordered = surface[::-1] if reversed_input else surface

    theta = np.linspace(0.0, np.pi, point_count)
    cosine_x = 0.5 * (1.0 - np.cos(theta)) * span + x_min
    resampled = np.column_stack(
        (
            cosine_x,
            np.interp(cosine_x, ordered[:, 0], ordered[:, 1]),
        )
    )
    # 两端强制取原始端点坐标，避免插值把尖后缘/前缘点挪动。
    resampled[0] = ordered[0]
    resampled[-1] = ordered[-1]
    return resampled[::-1] if reversed_input else resampled


def resample_surfaces_cosine(
    upper: FloatArray,
    lower: FloatArray,
    surface_point_count: int,
) -> tuple[FloatArray, FloatArray]:
    """上下表面使用同一个 ``surface_point_count`` 做 Cosine 重采样。

    输入为“尖后缘 -> 前缘”方向的上下表面；返回同样方向的 (N, 2) 数组，
    上下表面允许不同原始点数；返回时均为 N 点并共享前缘。有限厚度后缘
    仍保留为两个独立端点，供后续尖后缘拟合使用。
    """
    upper_resampled = resample_surface_cosine(upper, surface_point_count)
    lower_resampled = resample_surface_cosine(lower, surface_point_count)
    # 防御：把下表面统一为“尖后缘 -> 前缘”方向，端点平均才不会错位。
    if lower_resampled[0, 0] < lower_resampled[-1, 0]:
        lower_resampled = lower_resampled[::-1]
    if len(upper_resampled) != len(lower_resampled):
        raise ValueError("上下表面重采样后点数不一致。")
    # 前缘是两条曲线的公共端点；后缘可能有有限厚度，不能在拟合前合并。
    shared_leading = 0.5 * (upper_resampled[-1] + lower_resampled[-1])
    upper_resampled = upper_resampled.copy()
    lower_resampled = lower_resampled.copy()
    upper_resampled[-1] = lower_resampled[-1] = shared_leading
    return upper_resampled, lower_resampled
