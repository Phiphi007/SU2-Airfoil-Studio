"""Original three-Bezier BCE editor with an optional compact D-BCE handoff."""

from __future__ import annotations

import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .deformation import write_selig
from .parameterizations.bce import compact_bump


INITIAL_PARAMETERS = np.array(
    [0.05, 0.10, 0.12, 0.15, 0.12, 0.08, 0.02]
    + [0.0, 1.0, 3.0, 3.0, 1.0, 0.0, 0.0]
    + [25.0, 20.0, 15.0, 10.0, 8.0, 5.0]
    + [1.0],
    dtype=float,
)
NACA2412_PARAMETERS = np.array([
    0.0561370927, 0.0682674466, 0.0831709064, 0.1437005270, 0.2373503900,
    -0.0159562586, 0.3474526175, 19.2630088388, 12.8170169392,
    12.4347897730, 10.5958166763, 14.7526168569, 4.8337859649,
    3.5027553321, 15.6264398068, 47.6144341201, 2.0017995078,
    41.8288835444, 3.8500410261, 7.8864131835, 1.7535660121,
])
LOWER_BOUNDS = np.array([-0.35] * 7 + [-60.0] * 7 + [2.0] * 6 + [0.3])
UPPER_BOUNDS = np.array([0.60] * 7 + [60.0] * 7 + [80.0] * 6 + [3.0])
MODE_LABELS = {
    "自由变形": "Free",
    "锁定厚度": "Lock thickness",
    "锁定弯度": "Lock camber",
}
SENSITIVITY_SCALE = {
    "精细（0.35×）": 0.35,
    "标准（0.8×）": 0.8,
    "快速（1.5×）": 1.5,
    "Fine (0.35x)": 0.35,
    "Standard (0.8x)": 0.8,
    "Fast (1.5x)": 1.5,
}
PLOT_EN = {
    "载入翼型后显示原 BCE 三函数控制界面": "Load an airfoil to display the legacy BCE controls",
    "当前翼型": "Current airfoil",
    "导入目标": "Imported target",
    "旧 BCE 上表面": "Legacy BCE upper",
    "旧 BCE 下表面": "Legacy BCE lower",
    "中弧线": "Camber line",
    "厚度因子 h(x)": "Thickness factor h(x)",
    "弯度因子 α(x)": "Camber factor α(x)",
    "饱满度因子 β(x)": "Fullness factor β(x)",
}


def bezier_2d(control_x: np.ndarray, control_y: np.ndarray, samples: int = 360) -> tuple[np.ndarray, np.ndarray]:
    degree = len(control_x) - 1
    parameter = np.linspace(0.0, 1.0, samples)
    basis = np.asarray([
        math.comb(degree, index) * parameter**index * (1.0 - parameter) ** (degree - index)
        for index in range(degree + 1)
    ])
    return np.asarray(control_x) @ basis, np.asarray(control_y) @ basis


def legacy_functions(parameters: np.ndarray, samples: int = 360):
    gamma = float(parameters[20])
    height_x = (np.arange(8) / 7.0) ** gamma
    alpha_x = (np.arange(7) / 6.0) ** gamma
    beta_x = (np.arange(6) / 5.0) ** gamma
    height = bezier_2d(height_x, np.r_[parameters[:7], 0.0], samples)
    alpha = bezier_2d(alpha_x, parameters[7:14], samples)
    beta = bezier_2d(beta_x, parameters[14:20], samples)
    controls = {
        "h": (height_x, np.r_[parameters[:7], 0.0]),
        "a": (alpha_x, parameters[7:14]),
        "b": (beta_x, parameters[14:20]),
    }
    return height, alpha, beta, controls


def legacy_airfoil(parameters: np.ndarray, x_target: np.ndarray, samples: int = 260):
    height_curve, alpha_curve, beta_curve, _ = legacy_functions(parameters, samples)
    center_x = np.linspace(0.0, 1.0, samples)
    height = np.interp(center_x, *height_curve)
    alpha = np.radians(np.interp(center_x, *alpha_curve))
    beta = np.radians(np.maximum(np.interp(center_x, *beta_curve), 0.1))
    denominator = np.maximum(np.cos(beta) ** 2 - np.sin(alpha) ** 2, 1.0e-4)
    center_y = height * np.sin(alpha) * np.cos(alpha) / denominator
    radius_y = height * np.sin(beta) * np.cos(beta) / denominator
    radius_x = np.maximum(
        np.abs(height * np.sin(beta) / np.sqrt(denominator)), 1.0e-6
    )
    left, right = center_x - radius_x, center_x + radius_x
    leading_index, trailing_index = int(np.argmin(left)), int(np.argmax(right))
    leading_x, trailing_x = left[leading_index], right[trailing_index]
    leading_y, trailing_y = center_y[leading_index], center_y[trailing_index]
    chord = max(float(np.hypot(trailing_x - leading_x, trailing_y - leading_y)), 1.0e-8)
    rotation = -np.arctan2(trailing_y - leading_y, trailing_x - leading_x)
    raw_x = np.linspace(leading_x, trailing_x, samples)
    distance = (raw_x[:, None] - center_x[None, :]) / radius_x[None, :]
    active = np.abs(distance) <= 1.0
    ordinate = np.sqrt(np.maximum(0.0, 1.0 - distance**2))
    upper = np.max(np.where(active, center_y + radius_y * ordinate, -np.inf), axis=1)
    lower = np.min(np.where(active, center_y - radius_y * ordinate, np.inf), axis=1)
    empty = ~np.any(active, axis=1)
    upper[empty] = lower[empty] = np.interp(raw_x[empty], center_x, center_y)

    def transform(y_value: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        shifted_x, shifted_y = raw_x - leading_x, y_value - leading_y
        return (
            (shifted_x * np.cos(rotation) - shifted_y * np.sin(rotation)) / chord,
            (shifted_x * np.sin(rotation) + shifted_y * np.cos(rotation)) / chord,
        )

    upper_x, upper_y = transform(upper)
    lower_x, lower_y = transform(lower)

    def ordered_interp(source_x: np.ndarray, source_y: np.ndarray) -> np.ndarray:
        order = np.argsort(source_x)
        return np.interp(x_target, source_x[order], source_y[order])

    final_upper = ordered_interp(upper_x, upper_y)
    final_lower = ordered_interp(lower_x, lower_y)
    return final_upper, final_lower, 0.5 * (final_upper + final_lower)


def validate_airfoil(upper: np.ndarray, lower: np.ndarray) -> tuple[bool, str]:
    if not np.all(np.isfinite(upper)) or not np.all(np.isfinite(lower)):
        return False, "翼型含非有限坐标"
    thickness = upper - lower
    interior = thickness[max(2, len(thickness) // 100): min(len(thickness) - 2, len(thickness) - len(thickness) // 100)]
    if len(interior) and float(np.min(interior)) <= 2.0e-5:
        return False, "局部厚度过小或上下表面交叉"
    if float(np.max(thickness)) > 0.45:
        return False, "最大厚度超过 0.45c"
    if float(np.max(np.abs(np.r_[upper, lower]))) > 0.5:
        return False, "纵坐标超过 ±0.5c"
    return True, "几何有效"


def fit_legacy_bce(
    x: np.ndarray, upper: np.ndarray, lower: np.ndarray, iterations: int = 20
) -> tuple[np.ndarray, float]:
    """Small bounded Gauss-Newton fit; avoids the old SciPy runtime dependency."""
    camber_level = float(np.max(np.abs(0.5 * (upper + lower))))
    parameters = (
        NACA2412_PARAMETERS.copy() if camber_level > 0.006 else INITIAL_PARAMETERS.copy()
    )
    sample_x = np.linspace(0.0, 1.0, min(91, len(x)))
    target_upper = np.interp(sample_x, x, upper)
    target_lower = np.interp(sample_x, x, lower)
    weight = np.ones_like(sample_x)
    weight[: max(5, len(sample_x) // 8)] = 2.5

    def residual(p: np.ndarray) -> np.ndarray:
        fit_upper, fit_lower, _ = legacy_airfoil(p, sample_x, samples=190)
        result = np.r_[(fit_upper - target_upper) * weight, (fit_lower - target_lower) * weight]
        return np.nan_to_num(result, nan=1.0, posinf=1.0, neginf=-1.0)

    best = parameters.copy()
    best_residual = residual(best)
    best_cost = float(best_residual @ best_residual)
    damping = 1.0e-3
    scales = np.r_[np.full(7, 2.0e-4), np.full(7, 0.08), np.full(6, 0.08), 0.004]
    step_limits = np.r_[np.full(7, 0.04), np.full(7, 5.0), np.full(6, 6.0), 0.15]
    for _ in range(max(1, iterations)):
        jacobian = np.empty((len(best_residual), len(best)))
        for column, step in enumerate(scales):
            perturbed = best.copy()
            perturbed[column] = np.clip(
                perturbed[column] + step, LOWER_BOUNDS[column], UPPER_BOUNDS[column]
            )
            actual_step = perturbed[column] - best[column]
            jacobian[:, column] = (
                (residual(perturbed) - best_residual) / actual_step
                if abs(actual_step) > 1.0e-14 else 0.0
            )
        lhs = jacobian.T @ jacobian + damping * np.eye(len(best))
        rhs = -(jacobian.T @ best_residual)
        try:
            delta = np.linalg.solve(lhs, rhs)
        except np.linalg.LinAlgError:
            delta = np.linalg.lstsq(lhs, rhs, rcond=1.0e-10)[0]
        delta = np.clip(delta, -step_limits, step_limits)
        candidate = np.clip(best + delta, LOWER_BOUNDS, UPPER_BOUNDS)
        candidate_residual = residual(candidate)
        candidate_cost = float(candidate_residual @ candidate_residual)
        if candidate_cost < best_cost:
            best, best_residual, best_cost = candidate, candidate_residual, candidate_cost
            damping = max(1.0e-7, damping * 0.35)
        else:
            damping = min(1.0e5, damping * 8.0)
    fit_upper, fit_lower, _ = legacy_airfoil(best, x)
    rmse = float(np.sqrt(np.mean(np.r_[fit_upper - upper, fit_lower - lower] ** 2)))
    return best, rmse


def compact_dbce_refit(
    x: np.ndarray,
    baseline_upper: np.ndarray,
    baseline_lower: np.ndarray,
    target_upper: np.ndarray,
    target_lower: np.ndarray,
    variables_per_field: int = 10,
) -> tuple[np.ndarray, np.ndarray, float, int]:
    """Project a legacy BCE edit into a smooth endpoint-safe compact basis.

    Earlier builds used unregularized OMP with supports as narrow as ``0.05c``.
    Every individual bump was smooth, but several narrow bumps could cancel one
    another and leave visible shoulders in curvature.  The hand-off now uses a
    deliberately overlapping dictionary and solves a curvature-regularized
    least-squares problem after every sparse selection.  The supports remain
    strictly inside the chord, therefore both endpoint displacement and slope
    stay unchanged.
    """
    xn = (x - float(np.min(x))) / max(float(np.ptp(x)), 1.0e-12)
    columns: list[np.ndarray] = []
    metadata: list[tuple[float, float]] = []
    # Widths below 0.10c are intentionally excluded from the hand-off fit.
    # They are useful during late-stage optimization, but too easy to combine
    # into a visually wavy representation of an already smooth manual edit.
    for center in np.linspace(0.06, 0.94, 45):
        for width in (0.10, 0.14, 0.20, 0.28, 0.38):
            if center - width < 0.002 or center + width > 0.998:
                continue
            value = compact_bump(xn, float(center), float(width))
            norm = float(np.linalg.norm(value))
            if norm > 1.0e-12:
                columns.append(value / norm)
                metadata.append((float(center), float(width)))
    dictionary = np.column_stack(columns)

    # A uniform auxiliary grid gives the curvature term a physical meaning;
    # fitting still takes place at the original cosine-clustered airfoil nodes.
    dense_x = np.linspace(0.0, 1.0, 401)
    dense_columns = []
    for center, width in metadata:
        value = compact_bump(dense_x, center, width)
        original_norm = float(np.linalg.norm(compact_bump(xn, center, width)))
        dense_columns.append(value / max(original_norm, 1.0e-12))
    dense_dictionary = np.column_stack(dense_columns)

    order = np.argsort(xn)
    sorted_x = xn[order]
    quadrature = np.empty_like(sorted_x)
    quadrature[1:-1] = 0.5 * (sorted_x[2:] - sorted_x[:-2])
    quadrature[0] = 0.5 * (sorted_x[1] - sorted_x[0])
    quadrature[-1] = 0.5 * (sorted_x[-1] - sorted_x[-2])
    original_quadrature = np.empty_like(quadrature)
    original_quadrature[order] = quadrature
    data_weights = np.sqrt(np.maximum(quadrature, 1.0e-8))
    dense_step = float(dense_x[1] - dense_x[0])

    def regularized_solution(selected: list[int], target: np.ndarray, smoothness: float):
        matrix = dictionary[:, selected]
        dense_matrix = dense_dictionary[:, selected]
        curvature = np.gradient(
            np.gradient(dense_matrix, dense_step, axis=0), dense_step, axis=0
        )
        weighted_matrix = data_weights[:, None] * matrix[order]
        system = np.vstack(
            (
                weighted_matrix,
                math.sqrt(smoothness * dense_step) * curvature,
                1.0e-7 * np.eye(len(selected)),
            )
        )
        rhs = np.r_[data_weights * target[order], np.zeros(len(dense_x) + len(selected))]
        coefficients = np.linalg.lstsq(system, rhs, rcond=1.0e-11)[0]
        return matrix @ coefficients

    def sparse_fit(target: np.ndarray, smoothness: float) -> np.ndarray:
        selected: list[int] = []
        approximation = np.zeros_like(target)
        for _ in range(min(variables_per_field, dictionary.shape[1])):
            residual = target - approximation
            scores = np.abs(dictionary.T @ (original_quadrature * residual))
            if selected:
                scores[selected] = -1.0
            selected.append(int(np.argmax(scores)))
            approximation = regularized_solution(selected, target, smoothness)
        return approximation

    upper_delta = target_upper - baseline_upper
    lower_delta = target_lower - baseline_lower
    camber_delta = sparse_fit(0.5 * (upper_delta + lower_delta), 1.5e-5)
    thickness_delta = sparse_fit(0.5 * (upper_delta - lower_delta), 3.0e-6)
    fitted_upper = baseline_upper + camber_delta + thickness_delta
    fitted_lower = baseline_lower + camber_delta - thickness_delta
    rmse = float(np.sqrt(np.mean(np.r_[fitted_upper - target_upper, fitted_lower - target_lower] ** 2)))
    return fitted_upper, fitted_lower, rmse, 2 * variables_per_field


class LegacyBCEDeformationPanel(ttk.Frame):
    """Embeddable version of the original h/alpha/beta Bezier editor."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        workdir_var: tk.StringVar,
        current_airfoil_provider: Callable[[], tuple[str, np.ndarray, np.ndarray] | None],
        apply_callback: Callable[[Path], None],
    ) -> None:
        super().__init__(master, padding=10)
        self.workdir_var = workdir_var
        self.current_airfoil_provider = current_airfoil_provider
        self.apply_callback = apply_callback
        self.name = ""
        self.x = np.asarray([], dtype=float)
        self.target_upper = np.asarray([], dtype=float)
        self.target_lower = np.asarray([], dtype=float)
        self.parameters = INITIAL_PARAMETERS.copy()
        self.baseline_parameters = self.parameters.copy()
        self.thickness_reference = np.asarray([], dtype=float)
        self.camber_reference = np.asarray([], dtype=float)
        self.active_index: int | None = None
        self.selected_index: int | None = None
        self.drag_origin_y: float | None = None
        self.drag_origin_value: float | None = None
        self.drag_snapshot: np.ndarray | None = None
        self.drag_changed = False
        self.undo_stack: list[np.ndarray] = []
        self.language_code = "zh"
        self.mode_var = tk.StringVar(value="自由变形")
        self.sensitivity_var = tk.StringVar(value="标准（0.8×）")
        self.status_var = tk.StringVar(value="载入翼型后可拖动 h、α、β 三条贝塞尔曲线的红色控制点。")
        self.control_artists: list[tuple[object, object, int]] = []
        self.geometry_ylim = (-0.14, 0.14)
        self.control_ylims = {
            "h": (-0.05, 0.35), "a": (-15.0, 15.0), "b": (0.0, 45.0)
        }
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_controls()
        self._build_figure()

    @property
    def loaded(self) -> bool:
        return len(self.x) >= 8

    def _build_controls(self) -> None:
        project = ttk.LabelFrame(self, text="项目工作目录与翼型来源", padding=10)
        project.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        project.columnconfigure(1, weight=1)
        ttk.Label(project, text="工作目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(project, textvariable=self.workdir_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(project, text="选择…", command=self._choose_workdir).grid(row=0, column=2)
        ttk.Button(project, text="拟合主程序当前翼型", command=self.load_current_airfoil).grid(row=1, column=0, pady=(8, 0), sticky="ew")
        ttk.Button(project, text="导入并拟合 DAT", command=self._import_dat).grid(row=1, column=1, pady=(8, 0), padx=6, sticky="w")
        ttk.Label(project, text="第一层：旧 BCE 人工设计；第二层：新 D-BCE 高效优化", foreground="#9A9A9A").grid(row=1, column=2, pady=(8, 0), sticky="e")

        controls = ttk.LabelFrame(self, text="原 BCE 三函数手动控制", padding=10)
        controls.grid(row=1, column=0, sticky="nsw", padx=(0, 8))
        ttk.Label(controls, text="约束模式").pack(anchor="w")
        for label in MODE_LABELS:
            ttk.Radiobutton(
                controls, text=label, value=label, variable=self.mode_var,
                command=self._change_mode,
            ).pack(anchor="w", pady=2)
        ttk.Label(controls, text="拖动灵敏度").pack(anchor="w", pady=(9, 2))
        self.sensitivity_combo = ttk.Combobox(
            controls,
            textvariable=self.sensitivity_var,
            values=("精细（0.35×）", "标准（0.8×）", "快速（1.5×）"),
            state="readonly",
            width=17,
        )
        self.sensitivity_combo.pack(fill="x")
        ttk.Separator(controls).pack(fill="x", pady=10)
        ttk.Button(controls, text="重置预览范围", command=self._reset_view).pack(fill="x", pady=3)
        ttk.Button(controls, text="撤销上一次拖动", command=self._undo).pack(fill="x", pady=3)
        ttk.Button(controls, text="恢复初始拟合", command=self._reset).pack(fill="x", pady=3)
        ttk.Button(controls, text="导出旧 BCE 手调 DAT…", command=self._export).pack(fill="x", pady=3)
        ttk.Button(controls, text="精确使用手调翼型进入网格", command=self._apply_exact).pack(fill="x", pady=3)
        ttk.Button(
            controls,
            text="用新 D-BCE 重拟合并进入网格",
            style="Accent.TButton",
            command=self._apply_compact,
        ).pack(fill="x", pady=3)
        ttk.Label(
            controls,
            text="拖动红点修改 h(x)、α(x)、β(x)。\n重拟合按钮使用端点安全紧支撑基，随后可继续 CFD 与伴随优化。",
            wraplength=255,
        ).pack(anchor="w", pady=(10, 0))
        ttk.Label(controls, textvariable=self.status_var, wraplength=255).pack(anchor="w", pady=(10, 0))

    def _build_figure(self) -> None:
        host = ttk.Frame(self)
        host.grid(row=1, column=1, sticky="nsew")
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        # Fixed subplot positions are deliberate: constrained_layout recalculates
        # on every mouse move and makes the airfoil appear to jump while dragging.
        self.figure = Figure(figsize=(11, 7), dpi=100, facecolor="#1E1E1E")
        grid = self.figure.add_gridspec(
            2, 6, height_ratios=(0.82, 1.18), hspace=0.38, wspace=0.30
        )
        # The geometry view is intentionally centred and narrower.  The full
        # width is reserved for the three editing curves where pointer accuracy
        # matters more.
        # Reserve the last grid column for a vertical legend.  Keeping the
        # legend outside the data axes prevents it from covering camber or the
        # upper surface after a large manual deformation.
        self.geometry_axis = self.figure.add_subplot(grid[0, 0:5])
        self.height_axis = self.figure.add_subplot(grid[1, 0:2])
        self.alpha_axis = self.figure.add_subplot(grid[1, 2:4])
        self.beta_axis = self.figure.add_subplot(grid[1, 4:6])
        self.figure.subplots_adjust(
            left=0.065, right=0.985, bottom=0.09, top=0.94, hspace=0.42, wspace=0.30
        )
        self.canvas = FigureCanvasTkAgg(self.figure, master=host)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(self.canvas, host, pack_toolbar=False)
        try:
            toolbar.configure(background="#252526", borderwidth=0, highlightthickness=0)
        except tk.TclError:
            pass
        for child in toolbar.winfo_children():
            try:
                child.configure(background="#252526", foreground="#D4D4D4",
                                activebackground="#343437", activeforeground="#FFFFFF",
                                borderwidth=0, highlightthickness=0)
            except tk.TclError:
                try:
                    child.configure(background="#252526")
                except tk.TclError:
                    pass
        toolbar.update()
        toolbar.grid(row=1, column=0, sticky="ew")
        self.canvas.mpl_connect("button_press_event", self._press)
        self.canvas.mpl_connect("motion_notify_event", self._drag)
        self.canvas.mpl_connect("button_release_event", self._release)
        self._draw()

    def _plot_text(self, chinese: str) -> str:
        return PLOT_EN.get(chinese, chinese) if self.language_code == "en" else chinese

    def set_language(self, language_code: str) -> None:
        """Update non-Tk plot text and bilingual sensitivity choices."""
        old_value = self.sensitivity_var.get()
        old_gain = SENSITIVITY_SCALE.get(old_value, 0.8)
        self.language_code = "en" if language_code == "en" else "zh"
        values = (
            ("Fine (0.35x)", "Standard (0.8x)", "Fast (1.5x)")
            if self.language_code == "en"
            else ("精细（0.35×）", "标准（0.8×）", "快速（1.5×）")
        )
        self.sensitivity_combo.configure(values=values)
        self.sensitivity_var.set(next(label for label in values if SENSITIVITY_SCALE[label] == old_gain))
        if self.loaded:
            if self.language_code == "en":
                self.status_var.set("Legacy BCE fit ready. Drag the three red control-point groups.")
            else:
                self.status_var.set("旧 BCE 拟合完成；可拖动三组红色控制点。")
        self._draw()

    @staticmethod
    def _axis(axis, title: str, ylabel: str = "") -> None:
        axis.set_title(title, loc="left", fontsize=10, fontweight="bold", color="#E8E8E8")
        axis.set_xlabel("x/c")
        axis.set_ylabel(ylabel)
        axis.set_facecolor("#252526")
        axis.grid(True, color="#3A3A3A", linestyle=":", linewidth=0.6)
        axis.tick_params(colors="#B8B8B8", labelsize=8)
        axis.xaxis.label.set_color("#D4D4D4")
        axis.yaxis.label.set_color("#D4D4D4")
        axis.title.set_color("#E8E8E8")
        for spine in axis.spines.values():
            spine.set_color("#555555")

    def _current(self):
        upper, lower, camber = legacy_airfoil(self.parameters, self.x)
        half_thickness = 0.5 * (upper - lower)
        mode = MODE_LABELS[self.mode_var.get()]
        if mode == "Lock thickness" and len(self.thickness_reference) == len(self.x):
            half_thickness = self.thickness_reference.copy()
        elif mode == "Lock camber" and len(self.camber_reference) == len(self.x):
            camber = self.camber_reference.copy()
        return camber + half_thickness, camber - half_thickness, camber

    def _change_mode(self) -> None:
        if self.loaded:
            upper, lower, camber = legacy_airfoil(self.parameters, self.x)
            self.thickness_reference = 0.5 * (upper - lower)
            self.camber_reference = camber.copy()
            self.status_var.set(f"已切换到{self.mode_var.get()}；参考场已锁定。")
            self._draw()

    def _draw(self) -> None:
        for axis in (self.geometry_axis, self.height_axis, self.alpha_axis, self.beta_axis):
            axis.clear()
        self.control_artists = []
        if not self.loaded:
            self.geometry_axis.text(0.5, 0.5, self._plot_text("载入翼型后显示原 BCE 三函数控制界面"), ha="center", va="center", color="#D4D4D4", transform=self.geometry_axis.transAxes)
            self.canvas.draw_idle()
            return
        upper, lower, camber = self._current()
        self._axis(self.geometry_axis, f"{self._plot_text('当前翼型')} · {self.name}", "y/c")
        self.geometry_axis.plot(self.x, self.target_upper, "--", color="#858585", lw=1.1, label=self._plot_text("导入目标"))
        self.geometry_axis.plot(self.x, self.target_lower, "--", color="#858585", lw=1.1)
        self.geometry_axis.plot(self.x, upper, color="#4FC1FF", lw=1.7, label=self._plot_text("旧 BCE 上表面"))
        self.geometry_axis.plot(self.x, lower, color="#007ACC", lw=1.7, label=self._plot_text("旧 BCE 下表面"))
        self.geometry_axis.plot(self.x, camber, "--", color="#D98A2B", lw=1.0, label=self._plot_text("中弧线"))
        self.geometry_axis.set_xlim(-0.12, 1.12)
        self.geometry_axis.set_ylim(*self.geometry_ylim)
        self.geometry_axis.set_aspect("equal", adjustable="box")
        self.geometry_axis.legend(
            ncol=1,
            fontsize=8,
            loc="center left",
            bbox_to_anchor=(1.015, 0.5),
            borderaxespad=0.0,
            facecolor="#252526",
            edgecolor="#555555",
            labelcolor="#D4D4D4",
            framealpha=0.9,
        )

        height, alpha, beta, controls = legacy_functions(self.parameters)
        specifications = (
            (self.height_axis, height, controls["h"], self._plot_text("厚度因子 h(x)"), "h", 0, 7),
            (self.alpha_axis, alpha, controls["a"], self._plot_text("弯度因子 α(x)"), "α / deg", 7, 14),
            (self.beta_axis, beta, controls["b"], self._plot_text("饱满度因子 β(x)"), "β / deg", 14, 20),
        )
        for axis, curve, control, title, ylabel, start, stop in specifications:
            self._axis(axis, title, ylabel)
            axis.plot(*curve, color="#C8C8C8", lw=1.4)
            axis.plot(*control, color="#d9534f", lw=0.8, alpha=0.45)
            visible = stop - start
            artist, = axis.plot(control[0][:visible], control[1][:visible], "o", color="#d9534f", ms=6, picker=8)
            self.control_artists.append((axis, artist, start))
            axis.set_xlim(-0.03, 1.03)
            if self.selected_index is not None and start <= self.selected_index < stop:
                local = self.selected_index - start
                axis.plot(
                    [control[0][local]], [control[1][local]], "o",
                    color="#ffb000", markeredgecolor="white", markeredgewidth=1.2,
                    ms=10, zorder=8,
                )
        self.height_axis.set_ylim(*self.control_ylims["h"])
        self.alpha_axis.set_ylim(*self.control_ylims["a"])
        self.alpha_axis.axhline(0.0, color="#8492a6", lw=0.8, zorder=0)
        self.beta_axis.set_ylim(*self.control_ylims["b"])
        self.canvas.draw_idle()

    def _press(self, event) -> None:
        if getattr(getattr(self.canvas, "toolbar", None), "mode", ""):
            return
        for axis, artist, offset in self.control_artists:
            if event.inaxes is axis:
                contains, details = artist.contains(event)
                if contains:
                    index = offset + int(details["ind"][0])
                    mode = MODE_LABELS[self.mode_var.get()]
                    if mode == "Lock thickness" and index < 7:
                        self.status_var.set("厚度已锁定")
                        return
                    if mode == "Lock camber" and 7 <= index < 14:
                        self.status_var.set("弯度已锁定")
                        return
                    self.active_index = index
                    self.selected_index = index
                    self.drag_origin_y = float(event.ydata) if event.ydata is not None else None
                    self.drag_origin_value = float(self.parameters[index])
                    self.drag_snapshot = self.parameters.copy()
                    self.drag_changed = False
                    self._draw()
                    return

    def _drag(self, event) -> None:
        if self.active_index is None or event.ydata is None:
            return
        index = self.active_index
        if self.drag_origin_y is None or self.drag_origin_value is None:
            return
        gain = SENSITIVITY_SCALE[self.sensitivity_var.get()]
        requested = self.drag_origin_value + gain * (
            float(event.ydata) - self.drag_origin_y
        )
        if index < 7:
            value = float(np.clip(requested, LOWER_BOUNDS[index], UPPER_BOUNDS[index]))
        elif index < 14:
            value = float(np.clip(requested, -60.0, 60.0))
        else:
            value = float(np.clip(requested, 2.0, 80.0))
        previous = float(self.parameters[index])
        self.parameters[index] = value
        upper, lower, _ = self._current()
        valid, reason = validate_airfoil(upper, lower)
        if not valid:
            self.parameters[index] = previous
            self.status_var.set(f"已阻止无效变形：{reason}")
            return
        self.status_var.set("旧 BCE 控制点已更新，可导出或转入新 D-BCE。")
        self.drag_changed = self.drag_changed or abs(value - previous) > 1.0e-14
        self._ensure_geometry_visible(upper, lower)
        self._draw()

    def _release(self, _event) -> None:
        if self.drag_changed and self.drag_snapshot is not None:
            self.undo_stack.append(self.drag_snapshot.copy())
            self.undo_stack = self.undo_stack[-40:]
        self.active_index = None
        self.drag_origin_y = None
        self.drag_origin_value = None
        self.drag_snapshot = None
        self.drag_changed = False

    def _undo(self) -> None:
        if not self.undo_stack:
            self.status_var.set("没有可撤销的拖动。")
            return
        self.parameters = self.undo_stack.pop()
        self.selected_index = None
        self.status_var.set("已撤销上一次拖动。")
        self._draw()

    def _load(self, name: str, upper: np.ndarray, lower: np.ndarray) -> None:
        upper = np.asarray(upper, dtype=float)
        lower = np.asarray(lower, dtype=float)
        x_min = max(float(np.min(upper[:, 0])), float(np.min(lower[:, 0])))
        x_max = min(float(np.max(upper[:, 0])), float(np.max(lower[:, 0])))
        chord = x_max - x_min
        if chord <= 1.0e-8:
            raise ValueError("翼型弦长无效")
        self.x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, 141)))

        def interpolate(surface: np.ndarray) -> np.ndarray:
            order = np.argsort(surface[:, 0])
            sx = (surface[order, 0] - x_min) / chord
            sy = surface[order, 1] / chord
            unique, indices = np.unique(sx, return_index=True)
            return np.interp(self.x, unique, sy[indices])

        self.target_upper = interpolate(upper)
        self.target_lower = interpolate(lower)
        if np.any(self.target_upper[1:-1] <= self.target_lower[1:-1]):
            raise ValueError("导入翼型存在负厚度或表面交叉")
        self.name = name
        self.status_var.set("正在用原 BCE 三函数拟合导入翼型…")
        self.update_idletasks()
        self.parameters, rmse = fit_legacy_bce(self.x, self.target_upper, self.target_lower)
        self.baseline_parameters = self.parameters.copy()
        base_upper, base_lower, base_camber = legacy_airfoil(self.parameters, self.x)
        self.thickness_reference = 0.5 * (base_upper - base_lower)
        self.camber_reference = base_camber.copy()
        self._set_fixed_view_limits()
        self.undo_stack.clear()
        self.selected_index = None
        self.status_var.set(f"旧 BCE 拟合完成：RMSE={rmse:.3e}；可拖动三组红色控制点。")
        self._draw()

    def load_current_airfoil(self, silent: bool = False) -> None:
        payload = self.current_airfoil_provider()
        if payload is None:
            if not silent:
                messagebox.showinfo("尚无当前翼型", "请等待主程序完成翼型预览。", parent=self)
            return
        try:
            self._load(*payload)
        except Exception as exc:
            if not silent:
                messagebox.showerror("旧 BCE 拟合失败", str(exc), parent=self)

    def _import_dat(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="导入 Selig 翼型", filetypes=[("Airfoil DAT", "*.dat *.txt")])
        if not path:
            return
        points = []
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            fields = line.replace(",", " ").split()
            try:
                points.append((float(fields[0]), float(fields[1])))
            except (ValueError, IndexError):
                continue
        try:
            coordinates = np.asarray(points, dtype=float)
            leading = int(np.argmin(coordinates[:, 0]))
            self._load(Path(path).stem, coordinates[: leading + 1], coordinates[leading:][::-1])
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)

    def _choose_workdir(self) -> None:
        path = filedialog.askdirectory(parent=self, title="选择项目工作目录")
        if path:
            self.workdir_var.set(path)

    def _reset(self) -> None:
        if self.loaded and not np.array_equal(self.parameters, self.baseline_parameters):
            self.undo_stack.append(self.parameters.copy())
        self.parameters = self.baseline_parameters.copy()
        base_upper, base_lower, base_camber = legacy_airfoil(self.parameters, self.x)
        self.thickness_reference = 0.5 * (base_upper - base_lower)
        self.camber_reference = base_camber.copy()
        self.selected_index = None
        self.status_var.set("已恢复导入翼型的原 BCE 初始拟合。")
        self._set_fixed_view_limits()
        self._draw()

    def _reset_view(self) -> None:
        """Fit the view to the current geometry without changing the shape."""
        if not self.loaded:
            return
        self._set_fixed_view_limits()
        self.status_var.set("预览范围已按当前翼型重新居中。")
        self._draw()

    @staticmethod
    def _stable_limits(values: np.ndarray, minimum_span: float, lower_floor: float | None = None) -> tuple[float, float]:
        low, high = float(np.min(values)), float(np.max(values))
        span = max(minimum_span, (high - low) * 1.8)
        center = 0.5 * (low + high)
        result = (center - 0.5 * span, center + 0.5 * span)
        if lower_floor is not None and result[0] < lower_floor:
            result = (lower_floor, lower_floor + span)
        return result

    def _set_fixed_view_limits(self) -> None:
        """Choose limits once after fitting; never change them during dragging."""
        upper, lower, _ = legacy_airfoil(self.parameters, self.x)
        ordinate = max(
            float(np.max(np.abs(self.target_upper))),
            float(np.max(np.abs(self.target_lower))),
            float(np.max(np.abs(upper))),
            float(np.max(np.abs(lower))),
        )
        half_height = float(np.clip(1.45 * ordinate + 0.008, 0.095, 0.30))
        half_height = math.ceil(half_height / 0.025) * 0.025
        self.geometry_ylim = (-half_height, half_height)
        height, alpha, beta, controls = legacy_functions(self.parameters)
        self.control_ylims = {
            "h": self._stable_limits(np.r_[height[1], controls["h"][1]], 0.28),
            "a": self._stable_limits(np.r_[alpha[1], controls["a"][1]], 24.0),
            "b": self._stable_limits(np.r_[beta[1], controls["b"][1]], 35.0, 0.0),
        }

    def _ensure_geometry_visible(self, upper: np.ndarray, lower: np.ndarray) -> None:
        """Expand the y view in stable 0.025c steps; never shrink while dragging."""
        ordinate = float(np.max(np.abs(np.r_[upper, lower])))
        current = max(abs(self.geometry_ylim[0]), abs(self.geometry_ylim[1]))
        if ordinate <= 0.88 * current:
            return
        enlarged = min(0.50, math.ceil((1.28 * ordinate + 0.008) / 0.025) * 0.025)
        if enlarged > current:
            self.geometry_ylim = (-enlarged, enlarged)

    def _write(self, path: Path, upper: np.ndarray, lower: np.ndarray, suffix: str) -> None:
        write_selig(path, f"{self.name}_{suffix}", self.x, upper, lower)

    def _export(self) -> None:
        if not self.loaded:
            return
        path = filedialog.asksaveasfilename(parent=self, title="导出旧 BCE 手调翼型", defaultextension=".dat", initialfile=f"{self.name}_legacy_bce.dat", filetypes=[("Airfoil DAT", "*.dat")])
        if path:
            upper, lower, _ = self._current()
            self._write(Path(path), upper, lower, "legacy_bce")
            self.status_var.set(f"已导出旧 BCE 手调 DAT：{path}")

    def _target_path(self, suffix: str) -> Path:
        raw = self.workdir_var.get().strip()
        if not raw:
            raise ValueError("请先选择项目工作目录")
        return Path(raw).expanduser().resolve() / "airfoil_designs" / f"{self.name}_{suffix}.dat"

    def _apply_exact(self) -> None:
        if not self.loaded:
            return
        upper, lower, _ = self._current()
        valid, reason = validate_airfoil(upper, lower)
        if not valid:
            messagebox.showerror("几何无效", reason, parent=self)
            return
        try:
            path = self._target_path("legacy_bce")
            self._write(path, upper, lower, "legacy_bce")
        except (OSError, ValueError) as exc:
            messagebox.showerror("无法应用翼型", str(exc), parent=self)
            return
        self.apply_callback(path)
        self.status_var.set("旧 BCE 手调结果已精确送入网格流程。")

    def _apply_compact(self) -> None:
        if not self.loaded:
            return
        upper, lower, _ = self._current()
        baseline_upper, baseline_lower, _ = legacy_airfoil(
            self.baseline_parameters, self.x
        )
        fitted_upper, fitted_lower, rmse, variables = compact_dbce_refit(
            self.x, baseline_upper, baseline_lower, upper, lower
        )
        # Keep the hand-edited Bezier geometry as the exact D-BCE baseline.
        # Compact brushes define the later optimization directions; replacing
        # this smooth shape by an approximate projection can create visible
        # alternating curvature waves even when the coordinate RMSE is small.
        handoff_upper = upper.copy()
        handoff_lower = lower.copy()
        valid, reason = validate_airfoil(handoff_upper, handoff_lower)
        if not valid:
            messagebox.showerror("新 D-BCE 重拟合无效", reason, parent=self)
            return
        try:
            path = self._target_path("dbce_refit")
            self._write(path, handoff_upper, handoff_lower, "dbce_refit")
        except (OSError, ValueError) as exc:
            messagebox.showerror("无法应用翼型", str(exc), parent=self)
            return
        self.apply_callback(path)
        self.status_var.set(
            f"已保形进入新 D-BCE：手调几何零改动；{variables} 个紧支撑方向已就绪"
            f"（投影诊断 RMSE={rmse:.3e}，未用于替换翼型）。"
        )

