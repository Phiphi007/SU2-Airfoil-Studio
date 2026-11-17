"""依据目标 Y+ 计算 Gmsh 附面层第一层高度。"""

from __future__ import annotations

from dataclasses import dataclass
from math import log10, sqrt


@dataclass(frozen=True)
class WallEstimate:
    """便于日志展示的壁面物理量估计。"""

    reynolds_number: float
    skin_friction_coefficient: float
    friction_velocity: float
    first_layer_height: float


def estimate_wall_spacing(
    V: float,
    L: float,
    nu: float,
    Y_target: float = 1.0,
) -> WallEstimate:
    """使用 Schlichting 平板关联式计算首层高度及中间物理量。

    - ``V``：来流速度（m/s）
    - ``L``：特征长度（m，此处为弦长）
    - ``nu``：运动黏度（m²/s）
    - ``Y_target``：目标 Y+
    """
    if V <= 0.0 or L <= 0.0 or nu <= 0.0 or Y_target <= 0.0:
        raise ValueError("V、L、nu 和 Y_target 均必须大于 0。")

    reynolds_number = V * L / nu
    if reynolds_number < 1.0e4:
        raise ValueError("Re < 1e4，超出了当前湍流平板关联式的合理使用范围。")

    # Schlichting 平板平均摩擦系数关联式。
    skin_friction = (2.0 * log10(reynolds_number) - 0.65) ** -2.3
    friction_velocity = V * sqrt(skin_friction / 2.0)
    first_layer_height = Y_target * nu / friction_velocity
    return WallEstimate(
        reynolds_number=reynolds_number,
        skin_friction_coefficient=skin_friction,
        friction_velocity=friction_velocity,
        first_layer_height=first_layer_height,
    )


def calculate_first_layer_height(
    V: float,
    L: float,
    nu: float,
    Y_target: float = 1.0,
) -> float:
    """返回绝对第一层高度 delta_y，单位与 L、nu 所用单位一致。"""
    return estimate_wall_spacing(V, L, nu, Y_target).first_layer_height


# 规划文档中的函数名别名，保留后续脚本调用兼容性。
calculate_yplus_height = calculate_first_layer_height
