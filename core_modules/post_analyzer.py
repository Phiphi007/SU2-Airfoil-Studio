"""读取 SU2 CSV 输出并生成综合气动分析画板。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from . import font_config


REPORT_PANELS: tuple[tuple[str, str, str], ...] = (
    ("convergence", "收敛历史", "01_Convergence_History.png"),
    ("pressure", "表面压力系数", "02_Surface_Pressure.png"),
    ("friction", "摩阻与分离", "03_Skin_Friction.png"),
    ("geometry", "翼型几何", "04_Airfoil_Geometry.png"),
)
REPORT_PANEL_FILES = {key: filename for key, _, filename in REPORT_PANELS}
REPORT_PANEL_TITLES_EN = {
    "convergence": "Convergence & Coefficients",
    "pressure": "Surface Pressure Coefficient",
    "friction": "Skin Friction & Separation",
    "geometry": "Airfoil Geometry",
}


def report_panel_title(key: str, language: str = "zh") -> str:
    if language == "en":
        return REPORT_PANEL_TITLES_EN.get(key, key)
    return next((title for item, title, _ in REPORT_PANELS if item == key), key)


def _text(language: str, chinese: str, english: str) -> str:
    return english if language == "en" else chinese


def _load_plot_dependencies() -> tuple[Any, Any, Any]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd
        from matplotlib.gridspec import GridSpec
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "后处理依赖未安装。请执行: python -m pip install -r requirements.txt"
        ) from exc
    return pd, plt, GridSpec


def _normalize_column(name: object) -> str:
    text = str(name).strip().strip('"').lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _find_column(
    frame: Any, candidates: Iterable[str], required: bool = True
) -> str | None:
    normalized = {
        _normalize_column(column): str(column) for column in frame.columns
    }
    for candidate in candidates:
        key = _normalize_column(candidate)
        if key in normalized:
            return normalized[key]
    if required:
        raise KeyError(
            f"找不到列 {tuple(candidates)}；文件实际列为: {', '.join(map(str, frame.columns))}"
        )
    return None


def _read_su2_csv(pd: Any, path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"找不到 SU2 输出文件: {path}")
    frame = pd.read_csv(path, skipinitialspace=True)
    frame.columns = [str(column).strip().strip('"') for column in frame.columns]
    if frame.empty:
        raise ValueError(f"CSV 文件没有数据行: {path}")
    return frame


def _numeric(frame: Any, column: str) -> np.ndarray:
    values = np.asarray(frame[column], dtype=float)
    return values[np.isfinite(values)] if values.ndim == 1 else values


def _split_surface_indices(
    x: np.ndarray, y: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """按壁面拓扑优先拆分上下表面，并让每个分支按 X 递增排列。

    本程序生成的 SU2 网格会把壁面节点按“后缘 -> 前缘 -> 后缘”连续写入，
    SU2 的 surface CSV 因而通常保留这条拓扑顺序。大弯度翼型的下表面可能
    整段位于几何弦线上方，不能仅靠相对弦线的正负号分类，否则上下表面会被
    交替连接成厚度量级的高频假震荡。只有无法识别连续拓扑时，才回退到弦线
    两侧分类，以兼容无序导入网格的表面 CSV。
    """
    chord = float(np.ptp(x))
    if chord <= 0.0:
        raise ValueError("表面坐标的弦长必须大于 0。")
    x_min, x_max = float(np.min(x)), float(np.max(x))

    # 优先利用轮廓拓扑。允许极少量浮点扰动，但不接受真正无序的点列。
    leading_index = int(np.argmin(x))
    monotone_tolerance = max(chord * 1.0e-9, 1.0e-13)
    if 1 <= leading_index < len(x) - 1:
        first_dx = np.diff(x[: leading_index + 1])
        second_dx = np.diff(x[leading_index:])
        violations = int(np.count_nonzero(first_dx > monotone_tolerance))
        violations += int(np.count_nonzero(second_dx < -monotone_tolerance))
        allowed_violations = max(1, int(0.005 * max(len(x) - 2, 1)))
        first = np.arange(0, leading_index + 1, dtype=int)
        second = np.arange(leading_index, len(x), dtype=int)
        if violations <= allowed_violations and len(first) >= 3 and len(second) >= 3:
            # 用两个分支在相同 x 范围的中位纵坐标判断上下表面。不能使用
            # 相对直弦符号，因为强弯度时上下表面可能位于直弦同一侧。
            first_level = float(np.median(y[first]))
            second_level = float(np.median(y[second]))
            upper, lower = (
                (first, second)
                if first_level >= second_level
                else (second, first)
            )
            return upper[np.argsort(x[upper])], lower[np.argsort(x[lower])]

    # 无序数据后备：适用于普通弯度、但 CSV 行序或导入网格节点号不连续的情况。
    endpoint_band = max(chord * 1.0e-4, 1.0e-12)
    leading_y = float(np.mean(y[np.abs(x - x_min) <= endpoint_band]))
    trailing_values = y[np.abs(x - x_max) <= endpoint_band]
    trailing_y = float(0.5 * (np.min(trailing_values) + np.max(trailing_values)))
    chord_y = leading_y + (trailing_y - leading_y) * (x - x_min) / chord
    signed_height = y - chord_y
    height_tolerance = max(float(np.ptp(y)) * 1.0e-7, chord * 1.0e-10)

    upper = np.flatnonzero(signed_height > height_tolerance)
    lower = np.flatnonzero(signed_height < -height_tolerance)
    # 前缘和后缘公共点同时加入两条曲线，使 Cp/Cf 分支在端点完整闭合。
    neutral_endpoints = np.flatnonzero(
        (np.abs(signed_height) <= height_tolerance)
        & ((x <= x_min + endpoint_band) | (x >= x_max - endpoint_band))
    )
    upper = np.unique(np.r_[upper, neutral_endpoints])
    lower = np.unique(np.r_[lower, neutral_endpoints])
    if len(upper) < 3 or len(lower) < 3:
        raise ValueError(
            "无法依据弦线可靠拆分上下表面，请检查 surface_flow.csv 坐标。"
        )
    return upper[np.argsort(x[upper])], lower[np.argsort(x[lower])]


def _read_run_mach(output: Path) -> float | None:
    """从本次 run.cfg 读取 Mach，仅用于决定是否进行激波检测。"""
    config_path = output / "run.cfg"
    if not config_path.is_file():
        return None
    match = re.search(
        r"^\s*MACH_NUMBER\s*=\s*([-+0-9.eE]+)",
        config_path.read_text(encoding="utf-8", errors="replace"),
        flags=re.MULTILINE,
    )
    return float(match.group(1)) if match else None


def _shock_location(x: np.ndarray, cp: np.ndarray) -> tuple[float, float] | None:
    order = np.argsort(x)
    x_sorted, cp_sorted = x[order], cp[order]
    unique = np.r_[True, np.diff(x_sorted) > max(np.ptp(x_sorted), 1.0) * 1.0e-8]
    x_sorted, cp_sorted = x_sorted[unique], cp_sorted[unique]
    if len(x_sorted) < 7:
        return None
    gradient = np.gradient(cp_sorted, x_sorted)
    interior = (x_sorted > np.min(x_sorted) + 0.08 * np.ptp(x_sorted)) & (
        x_sorted < np.max(x_sorted) - 0.03 * np.ptp(x_sorted)
    )
    if not np.any(interior):
        return None
    candidates = np.flatnonzero(interior)
    index = int(candidates[np.argmax(np.abs(gradient[candidates]))])
    # 只有足够陡的压力跃变才标成疑似激波，避免把普通压力恢复误报为激波。
    if abs(float(gradient[index])) < 4.0 / max(float(np.ptp(x_sorted)), 1.0e-12):
        return None
    return float(x_sorted[index]), float(cp_sorted[index])


def smooth_surface_for_display(
    values: np.ndarray, passes: int = 2, strength: float = 0.55
) -> np.ndarray:
    """对沿翼面排列的标量做轻度双边平滑，仅供曲线显示。

    五点邻域会削弱交替锯齿；数值差异较大的点权重自动降低，因此前缘峰值、
    停滞点和可能的激波不会被普通移动平均大幅抹平。端部两个点保持原值。
    """
    original = np.asarray(values, dtype=float)
    if passes <= 0 or len(original) < 7:
        return original.copy()
    finite = original[np.isfinite(original)]
    if len(finite) < 7:
        return original.copy()
    span = float(np.percentile(finite, 95.0) - np.percentile(finite, 5.0))
    changes = np.abs(np.diff(original))
    changes = changes[np.isfinite(changes)]
    typical_change = float(np.median(changes)) if len(changes) else 0.0
    range_scale = max(
        0.03 * max(span, 0.0),
        1.5 * typical_change,
        np.finfo(float).eps * max(float(np.max(np.abs(finite))), 1.0),
    )
    spatial_weight = np.asarray([1.0, 2.0, 3.0, 2.0, 1.0])
    blend = float(np.clip(strength, 0.0, 0.8))
    smoothed = original.copy()
    for _ in range(passes):
        updated = smoothed.copy()
        for index in range(2, len(smoothed) - 2):
            window = smoothed[index - 2 : index + 3]
            if not np.all(np.isfinite(window)):
                continue
            range_weight = np.exp(
                -0.5 * np.square((window - smoothed[index]) / range_scale)
            )
            weight = spatial_weight * range_weight
            local_mean = float(np.sum(weight * window) / np.sum(weight))
            updated[index] = (1.0 - blend) * smoothed[index] + blend * local_mean
        smoothed = updated
    return smoothed


def generate_report(
    output_dir: str | Path = "output_results",
    report_name: str = "Aerodynamic_Report.png",
    language: str = "zh",
) -> Path:
    """在独立子目录生成四张高清报告图，并返回第一张图的路径。"""
    if language not in {"zh", "en"}:
        raise ValueError("language must be 'zh' or 'en'.")
    pd, plt, _ = _load_plot_dependencies()
    output = Path(output_dir).expanduser().resolve()
    history = _read_su2_csv(pd, output / "history.csv")
    surface = _read_su2_csv(pd, output / "surface_flow.csv")

    iteration_col = _find_column(
        history, ("Inner_Iter", "Outer_Iter", "Time_Iter", "Iteration", "Iter")
    )
    residual_col = _find_column(
        history, ("RMS_Density", "rms[Rho]", "RMS_Rho", "Res_Density")
    )
    cl_col = _find_column(history, ("CL", "Lift", "Total_CL"), required=False)
    cd_col = _find_column(history, ("CD", "Drag", "Total_CD"), required=False)
    x_col = _find_column(surface, ("x", "x_coord", "Coordinate_x"))
    y_col = _find_column(surface, ("y", "y_coord", "Coordinate_y"))
    cp_col = _find_column(surface, ("Pressure_Coefficient", "Cp"))
    cf_col = _find_column(
        surface,
        (
            "Skin_Friction_Coefficient_x",
            "Skin_Friction_Coefficient",
            "Cf_x",
            "Cf",
        ),
        required=False,
    )

    iterations = np.asarray(history[iteration_col], dtype=float)
    residual = np.asarray(history[residual_col], dtype=float)
    x = np.asarray(surface[x_col], dtype=float)
    y = np.asarray(surface[y_col], dtype=float)
    cp = np.asarray(surface[cp_col], dtype=float)
    valid_surface = np.isfinite(x) & np.isfinite(y) & np.isfinite(cp)
    x, y, cp = x[valid_surface], y[valid_surface], cp[valid_surface]
    if len(x) < 6:
        raise ValueError("surface_flow.csv 中有效表面点少于 6 个。")
    upper_idx, lower_idx = _split_surface_indices(x, y)
    plt.style.use("seaborn-v0_8-whitegrid")
    font_config.configure_matplotlib_font()
    # 四张图分别使用完整画布。rcParams 是进程全局的，结束后必须恢复，
    # 避免影响 GUI 的实时曲线和云图画布。
    font_keys = (
        "axes.titlesize",
        "axes.labelsize",
        "xtick.labelsize",
        "ytick.labelsize",
        "legend.fontsize",
    )
    font_backup = {key: plt.rcParams[key] for key in font_keys}
    plt.rcParams.update(
        {
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )
    try:
        report_directory = output / Path(report_name).stem
        report_directory.mkdir(parents=True, exist_ok=True)
        panel_paths = {
            key: report_directory / filename
            for key, _, filename in REPORT_PANELS
        }

        convergence_figure, convergence_ax = plt.subplots(
            figsize=(12.0, 7.6), constrained_layout=True
        )

        finite_history = np.isfinite(iterations) & np.isfinite(residual)
        if np.all(residual[finite_history] > 0.0):
            convergence_ax.semilogy(
                iterations[finite_history],
                residual[finite_history],
                color="#246a73",
                label=_text(language, "SU2 密度残差", "SU2 density residual"),
            )
            convergence_ax.set_ylabel(_text(language, "残差", "Residual"))
        else:
            convergence_ax.plot(
                iterations[finite_history],
                residual[finite_history],
                color="#246a73",
                label=_text(language, "SU2 密度残差", "SU2 density residual"),
            )
            convergence_ax.set_ylabel(_text(language, "log10 残差", "log10 residual"))
        convergence_ax.set_xlabel(_text(language, "迭代步", "Iteration"))
        convergence_ax.set_title(_text(language, "收敛历史与气动力系数", "Convergence and Aerodynamic Coefficients"))

        coefficient_ax = convergence_ax.twinx()
        if cl_col:
            coefficient_ax.plot(
                iterations, history[cl_col], color="#d1495b", linewidth=1.2, label="SU2 CL"
            )
        if cd_col:
            coefficient_ax.plot(
                iterations, history[cd_col], color="#edae49", linewidth=1.2, label="SU2 CD"
            )
        coefficient_ax.set_ylabel(_text(language, "气动力系数", "Aerodynamic coefficient"))
        lines = convergence_ax.lines + coefficient_ax.lines
        if lines:
            convergence_ax.legend(
                lines, [line.get_label() for line in lines], loc="best"
            )
        convergence_figure.suptitle(
            _text(
                language,
                "SU2 AutoFoil：收敛历史与气动力系数",
                "SU2 AutoFoil: Convergence and Aerodynamic Coefficients",
            ),
            fontsize=18,
            fontweight="bold",
        )
        convergence_figure.savefig(
            panel_paths["convergence"], dpi=200, bbox_inches="tight"
        )
        plt.close(convergence_figure)

        pressure_figure, cp_ax = plt.subplots(
            figsize=(12.0, 7.6), constrained_layout=True
        )
        upper_cp_raw = cp[upper_idx]
        lower_cp_raw = cp[lower_idx]
        upper_cp = smooth_surface_for_display(upper_cp_raw)
        lower_cp = smooth_surface_for_display(lower_cp_raw)
        cp_ax.scatter(
            x[upper_idx], upper_cp_raw, s=8, color="#2563a6", alpha=0.24
        )
        cp_ax.scatter(
            x[lower_idx], lower_cp_raw, s=8, color="#d1495b", alpha=0.24
        )
        cp_ax.plot(
            x[upper_idx], upper_cp, color="#2563a6", linewidth=1.8,
            label=_text(language, "SU2 上表面（显示平滑）", "SU2 upper (display smoothing)"),
        )
        cp_ax.plot(
            x[lower_idx], lower_cp, color="#d1495b", linewidth=1.8,
            label=_text(language, "SU2 下表面（显示平滑）", "SU2 lower (display smoothing)"),
        )
        cp_ax.invert_yaxis()  # 气动领域惯例：负 Cp 位于图的上方。
        cp_ax.set_xlabel("x")
        cp_ax.set_ylabel("Cp")
        cp_ax.set_title(_text(language, "表面压力系数", "Surface Pressure Coefficient"))
        cp_ax.legend()
        stagnation_index = int(np.nanargmax(cp))
        cp_ax.scatter(x[stagnation_index], cp[stagnation_index], color="#111827", s=35, zorder=5)
        cp_ax.annotate(
            _text(language, "停滞点", "Stagnation"),
            (x[stagnation_index], cp[stagnation_index]),
            xytext=(7, 7),
            textcoords="offset points",
        )
        mach_number = _read_run_mach(output)
        shock = (
            _shock_location(x[upper_idx], cp[upper_idx])
            if mach_number and mach_number >= 0.65
            else None
        )
        if shock:
            cp_ax.scatter(*shock, marker="x", color="#b91c1c", s=55, zorder=6)
            cp_ax.annotate(
                _text(language, "疑似激波", "Possible shock"), shock,
                xytext=(7, -14), textcoords="offset points",
            )
        cp_ax.text(
            0.01,
            0.02,
            _text(
                language,
                "实线仅做轻度显示平滑；淡色点为原始 SU2 值。",
                "Solid lines are lightly smoothed for display; faint markers are raw SU2 values.",
            ),
            transform=cp_ax.transAxes,
            color="#596773",
            fontsize=9,
        )
        pressure_figure.suptitle(
            _text(
                language,
                "SU2 AutoFoil：表面压力系数",
                "SU2 AutoFoil: Surface Pressure Coefficient",
            ),
            fontsize=18,
            fontweight="bold",
        )
        pressure_figure.savefig(panel_paths["pressure"], dpi=200, bbox_inches="tight")
        plt.close(pressure_figure)

        friction_figure, cf_ax = plt.subplots(
            figsize=(12.0, 7.6), constrained_layout=True
        )
        if cf_col:
            cf_all = np.asarray(surface.loc[valid_surface, cf_col], dtype=float)
            cf_ax.plot(x[upper_idx], cf_all[upper_idx], color="#2563a6", label=_text(language, "SU2 上表面", "SU2 upper"))
            cf_ax.plot(x[lower_idx], cf_all[lower_idx], color="#d1495b", label=_text(language, "SU2 下表面", "SU2 lower"))
            separated = np.isfinite(cf_all) & (cf_all < 0.0)
            cf_ax.scatter(
                x[separated],
                cf_all[separated],
                facecolors="none",
                edgecolors="#b91c1c",
                s=35,
                label="Cf < 0",
            )
            cf_ax.legend()
        else:
            cf_ax.text(
                0.5,
                0.5,
                _text(language, "SU2 未输出 Cf 列", "SU2 Cf column unavailable"),
                ha="center",
                va="center",
                transform=cf_ax.transAxes,
            )
        cf_ax.axhline(0.0, color="#111827", linewidth=0.8)
        cf_ax.set_xlabel("x")
        cf_ax.set_ylabel("Cf")
        cf_ax.set_title(_text(language, "摩阻与分离（SU2）", "Skin Friction and Separation (SU2)"))
        friction_figure.suptitle(
            _text(
                language,
                "SU2 AutoFoil：摩阻与分离",
                "SU2 AutoFoil: Skin Friction and Separation",
            ),
            fontsize=18,
            fontweight="bold",
        )
        friction_figure.savefig(panel_paths["friction"], dpi=200, bbox_inches="tight")
        plt.close(friction_figure)

        geometry_figure, geometry_ax = plt.subplots(
            figsize=(12.0, 7.6), constrained_layout=True
        )
        geometry_ax.plot(x[upper_idx], y[upper_idx], color="#2563a6", linewidth=1.7)
        geometry_ax.plot(x[lower_idx], y[lower_idx], color="#d1495b", linewidth=1.7)
        # 两个分支均按 X 递增；下表面反向后再拼接成无自交的填充多边形。
        polygon_x = np.r_[x[upper_idx], x[lower_idx][::-1]]
        polygon_y = np.r_[y[upper_idx], y[lower_idx][::-1]]
        geometry_ax.fill(polygon_x, polygon_y, color="#cbd5e1", alpha=0.45)
        geometry_ax.set_aspect("equal", adjustable="datalim")
        geometry_ax.set_xlabel("x")
        geometry_ax.set_ylabel("y")
        geometry_ax.set_title(_text(language, "翼型几何", "Airfoil Geometry"))
        geometry_figure.suptitle(
            _text(language, "SU2 AutoFoil：处理后尖后缘翼型", "SU2 AutoFoil: Processed Sharp-TE Airfoil"),
            fontsize=18,
            fontweight="bold",
        )
        geometry_figure.savefig(panel_paths["geometry"], dpi=200, bbox_inches="tight")
        plt.close(geometry_figure)
        return panel_paths["convergence"]
    finally:
        plt.rcParams.update(font_backup)
