"""统一组织坐标读取、Cosine 加密、缩放和尖后缘重构。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from . import cosine_resampler, geo_surgeon

FloatArray = NDArray[np.float64]
BUILTIN_NACA0012 = "builtin://naca0012"


def generate_naca4_surfaces(
    designation: str = "0012",
    source_count: int = 401,
) -> tuple[FloatArray, FloatArray]:
    """生成 NACA 四位数翼型的闭合尖后缘上下表面（Selig 方向：后缘 -> 前缘）。

    ``designation`` 形如 "2412"：最大弯度 2%、最大弯度位置 40%、厚度 12%。
    先用 ``source_count`` 个 Cosine 源点按解析公式描述几何，保证前缘圆钝；
    上下表面首点（后缘）与末点（前缘）分别重合。
    """
    if source_count < 101:
        raise ValueError("NACA 翼型源点数至少为 101。")
    digits = designation.strip().lower().replace("naca", "")
    if len(digits) != 4 or not digits.isdigit():
        raise ValueError(
            f"NACA 四位编号无效: {designation!r}，应为形如 0012、2412 的四位数字。"
        )
    max_camber = int(digits[0]) / 100.0
    camber_position = int(digits[1]) / 10.0
    thickness_ratio = int(digits[2:4]) / 100.0

    theta = np.linspace(0.0, np.pi, source_count)
    x = 0.5 * (1.0 - np.cos(theta))

    camber_line = np.empty_like(x)
    camber_slope = np.empty_like(x)
    if max_camber > 0.0:
        # 有弯度时位置必须严格处于 (0, 1)；对称翼型的该位为 0，直接跳过。
        if camber_position <= 0.0 or camber_position >= 1.0:
            raise ValueError("最大弯度位置必须处于 (0, 1)。")
        front = x < camber_position
        camber_line[front] = (
            max_camber
            / camber_position**2
            * (2.0 * camber_position * x[front] - x[front] ** 2)
        )
        camber_line[~front] = (
            max_camber
            / (1.0 - camber_position) ** 2
            * (
                (1.0 - 2.0 * camber_position)
                + 2.0 * camber_position * x[~front]
                - x[~front] ** 2
            )
        )
        camber_slope[front] = (
            2.0 * max_camber / camber_position**2 * (camber_position - x[front])
        )
        camber_slope[~front] = (
            2.0
            * max_camber
            / (1.0 - camber_position) ** 2
            * (camber_position - x[~front])
        )
    else:
        camber_line.fill(0.0)
        camber_slope.fill(0.0)

    y_thickness = 5.0 * thickness_ratio * (
        0.2969 * np.sqrt(x)
        - 0.1260 * x
        - 0.3516 * x**2
        + 0.2843 * x**3
        - 0.1036 * x**4
    )
    angle = np.arctan(camber_slope)
    upper = np.column_stack(
        (x - y_thickness * np.sin(angle), camber_line + y_thickness * np.cos(angle))
    )
    lower = np.column_stack(
        (x + y_thickness * np.sin(angle), camber_line - y_thickness * np.cos(angle))
    )
    # 统一为“后缘 -> 前缘”方向。
    return upper[::-1], lower[::-1]


def generate_naca0012_surfaces(source_count: int = 401) -> tuple[FloatArray, FloatArray]:
    """生成闭合尖后缘的解析 NACA0012 上下表面（Selig 方向：后缘 -> 前缘）。"""
    return generate_naca4_surfaces("0012", source_count)


@dataclass(frozen=True)
class ProcessedAirfoil:
    """GUI 预览和网格模块共同使用的翼型处理结果。"""

    x: FloatArray
    y: FloatArray
    upper: FloatArray
    lower: FloatArray
    trailing_edge: FloatArray
    trailing_edge_radius: float
    original_upper_count: int
    original_lower_count: int
    scale_factor: float

    @property
    def chord(self) -> float:
        return float(np.ptp(self.x))


def process_airfoil(
    filepath: str | Path | None,
    scale_factor: float = 1.0,
    surface_point_count: int = 100,
    trailing_edge_radius_pct: float | None = None,
) -> ProcessedAirfoil:
    """执行 GUI 所需的完整翼型预处理并返回可复用结果。

    流程：读取/生成 -> 拆分 -> Cosine 重采样 -> 缩放 -> 尾段拟合 ->
    统一尖后缘，最后拼接成带两个重合逻辑端点的逆时针开口 C 形壁面。

    ``trailing_edge_radius_pct`` 仅为兼容旧调用保留，尖后缘模式不会使用它。
    """
    if scale_factor <= 0.0:
        raise ValueError("坐标缩放系数必须大于 0。")

    source = str(filepath or BUILTIN_NACA0012).strip().lower()
    is_builtin = source.startswith("builtin://naca")
    if source.startswith("builtin://naca") and len(source) == len("builtin://naca") + 4:
        # 通用内置协议：builtin://naca<四位编号>，如 builtin://naca2412。
        original_upper, original_lower = generate_naca4_surfaces(source[-4:])
    elif source == BUILTIN_NACA0012:
        original_upper, original_lower = generate_naca0012_surfaces()
    else:
        raw_points = geo_surgeon.load_airfoil(str(filepath))
        original_upper, original_lower = geo_surgeon.split_surfaces(raw_points)
    upper, lower = cosine_resampler.resample_surfaces_cosine(
        original_upper,
        original_lower,
        surface_point_count,
    )

    # 缩放同时作用于 X/Y，保持翼型厚度比和弯度比不变。
    upper = upper * scale_factor
    lower = lower * scale_factor
    # 用户导入/手调的已闭合翼型必须保持原有尾缘形状；再次做直线拟合会在
    # 强弯度曲线上放大微小尾缘扰动。内置 NACA 基准仍沿用经过多翼型网格
    # 回归验证的尾缘整形，以维持 C-H 网格质量兼容性。
    upper, lower = geo_surgeon.sharpen_surfaces(
        upper,
        lower,
        preserve_existing_sharp=not is_builtin,
    )
    del trailing_edge_radius_pct
    if len(upper) != len(lower):
        raise ValueError("尖后缘重构后上下表面点数不一致。")

    # 上侧尖后缘 -> 前缘 -> 下侧尖后缘。首末坐标相同但逻辑点不同，
    # 供严格 C-grid 在后缘引出上下两条尾迹切线。
    boundary = np.vstack((upper, lower[::-1][1:]))
    trailing_edge = np.vstack((upper[0], lower[0]))
    x_coord, y_coord = boundary[:, 0], boundary[:, 1]
    return ProcessedAirfoil(
        x=x_coord,
        y=y_coord,
        upper=upper,
        lower=lower,
        trailing_edge=trailing_edge,
        trailing_edge_radius=0.0,
        original_upper_count=len(original_upper),
        original_lower_count=len(original_lower),
        scale_factor=scale_factor,
    )
