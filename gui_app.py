"""SU2 AutoFoil Optimizer Studio desktop interface.

三页结构：

- ``翼型与网格``：翼型输入、自动尖后缘、全结构化网格参数与预览。
- ``求解设置``：物理模型、来流、边界条件、数值格式与运行控制。
- ``计算与结果``：一键计算、实时日志/收敛、云图、综合报告、摘要与文件浏览。
- ``伴随优化``：CST、BCE、混合与接力参数化的 SU2 离散伴随优化。
"""

from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import sys
import threading
import time
import traceback
import ctypes
from core_modules.history_monitor import assess_convergence, read_history_points
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# 便携/缓存 Python 的 Tcl 自动发现并不稳定。项目自带一份运行时缓存，直接
# 运行 gui_app.py 或测试时也应自动使用，不能只依赖 BAT 启动器设置环境变量。
_EARLY_PROJECT_ROOT = Path(__file__).resolve().parent
_LOCAL_TCL = _EARLY_PROJECT_ROOT / ".runtime" / "tcl"
if (_LOCAL_TCL / "tcl8.6" / "init.tcl").is_file():
    os.environ["TCL_LIBRARY"] = str(_LOCAL_TCL / "tcl8.6")
if (_LOCAL_TCL / "tk8.6" / "tk.tcl").is_file():
    os.environ["TK_LIBRARY"] = str(_LOCAL_TCL / "tk8.6")

from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk
from core_modules.ui_layout import ScrollableForm, wrap_to_width
from core_modules.mesh_preview import EmbeddedMeshPreview
from core_modules.runtime_paths import resource_root, data_root

import matplotlib

matplotlib.use("Agg")
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from PIL import Image, ImageTk

from core_modules import (
    airfoil_processor,
    field_visualizer,
    font_config,
    mesh_architect,
    post_analyzer,
    process_control,
    su2_driver,
    su2_mesh_import,
    yplus_calc,
)
from parametric_adjoint.gui import OptimizerPanel
from parametric_adjoint.legacy_deformation import LegacyBCEDeformationPanel

PROJECT_ROOT = resource_root()
DEFAULT_AIRFOIL = PROJECT_ROOT / "input_data" / "naca0012.dat"
DEFAULT_OUTPUT_ROOT = data_root() / "cases"
BUILTIN_AIRFOIL_LABEL = "内置 NACA0012（解析高精度）"
BUILTIN_AIRFOIL_LABEL_EN = "Built-in NACA0012 (analytic)"

# Industrial desktop palette shared by Tk and embedded Matplotlib views.
UI_BG = "#1E1E1E"
UI_PANEL = "#252526"
UI_FIELD = "#1B1B1C"
UI_BORDER = "#3C3C3C"
UI_DIVIDER = "#333333"
UI_TEXT = "#D4D4D4"
UI_MUTED = "#B8B8B8"
UI_BLUE = "#007ACC"
UI_BLUE_ACTIVE = "#1689D4"
UI_ORANGE = "#D98A2B"
UI_DANGER = "#C24B4B"
MONO_FONT_FAMILY = "Consolas"


def _style_industrial_axis(axis: object) -> None:
    """Apply the common dark engineering-plot treatment after an axes clear."""
    axis.set_facecolor(UI_PANEL)
    axis.tick_params(colors="#B8B8B8", labelsize=8)
    axis.xaxis.label.set_color(UI_TEXT)
    axis.yaxis.label.set_color(UI_TEXT)
    axis.title.set_color("#E8E8E8")
    for spine in axis.spines.values():
        spine.set_color("#555555")
        spine.set_linewidth(0.8)
    axis.grid(True, color="#3A3A3A", linewidth=0.55, alpha=0.85)


def _style_mpl_toolbar(toolbar: tk.Misc) -> None:
    """Remove the native light strip around Matplotlib navigation controls."""
    try:
        toolbar.configure(background=UI_PANEL, borderwidth=0, highlightthickness=0)
    except tk.TclError:
        pass
    for child in toolbar.winfo_children():
        try:
            child.configure(background=UI_PANEL, foreground=UI_TEXT,
                            activebackground="#343437", activeforeground="#FFFFFF",
                            borderwidth=0, highlightthickness=0)
        except tk.TclError:
            try:
                child.configure(background=UI_PANEL)
            except tk.TclError:
                pass

INIT_MODES = {
    "指定 Reynolds 数": "REYNOLDS",
    "指定密度与温度": "TD_CONDITIONS",
}
AIRFOIL_BOUNDARIES = {
    "滑移壁面（Euler）": "SLIP",
    "绝热无滑移壁面": "ADIABATIC",
    "等温无滑移壁面": "ISOTHERMAL",
}
FARFIELD_BOUNDARIES = {
    "自由远场（推荐）": "FARFIELD",
    "亚声速入口 + 压力出口": "INLET_OUTLET",
    "超声速入口 + 压力出口": "SUPERSONIC_OUTLET",
}
INIT_MODES_EN = {
    "Specified Reynolds number": "REYNOLDS",
    "Specified density and temperature": "TD_CONDITIONS",
}
AIRFOIL_BOUNDARIES_EN = {
    "Slip wall (Euler)": "SLIP",
    "Adiabatic no-slip wall": "ADIABATIC",
    "Isothermal no-slip wall": "ISOTHERMAL",
}
FARFIELD_BOUNDARIES_EN = {
    "Farfield (recommended)": "FARFIELD",
    "Subsonic inlet + pressure outlet": "INLET_OUTLET",
    "Supersonic inlet + pressure outlet": "SUPERSONIC_OUTLET",
}
CONTOUR_RANGE_MODES = {"自动": "AUTO", "自定义": "CUSTOM"}
CONTOUR_RANGE_MODES_EN = {"Auto": "AUTO", "Custom": "CUSTOM"}

UI_EN = {
    "二维翼型全结构化网格、一键求解与气动后处理": "2D structured meshing, one-click solving and aerodynamic post-processing",
    "翼型与网格": "Airfoil & Mesh",
    "旧 BCE 手调 → 新 D-BCE 优化": "Legacy BCE Editing → New D-BCE Optimization",
    "求解设置": "Solver Settings",
    "计算与结果": "Run & Results",
    "伴随优化": "Adjoint Optimization",
    "使用当前正问题算例": "Use Current Direct Case",
    "翼型输入": "Airfoil Input",
    "浏览...": "Browse...",
    "默认": "Default",
    "后缘处理": "Trailing-edge treatment",
    "自动拟合上下尾段并统一到同一尖点": "Fit both trailing segments to one common sharp point",
    "坐标缩放系数": "Coordinate scale factor",
    "翼型几何采样": "Airfoil Geometry Sampling",
    "几何采样点数（每侧）": "Geometry samples (per side)",
    "原始点数": "Original points",
    "处理后点数": "Processed points",
    "更新预览": "Update Preview",
    "导出处理坐标": "Export Coordinates",
    "C-H 全结构化网格": "C-H Structured Mesh",
    "全局加密系数（0.05–10.0，小于1为粗网格）": "Global refinement (0.05–10.0; below 1 is coarse)",
    "控制尺寸 前缘,后上,后下": "Local sizes: LE, upper TE, lower TE",
    "尾迹加密系数（1–12）": "Wake refinement (1–12)",
    "目标 Y+": "Target Y+",
    "基准远场半径 / 弦长": "Base farfield radius / chord",
    "流场域缩放系数（0.25–10.0）": "Flow-domain scale (0.25–10.0)",
    "附面层参考扩张比": "Boundary-layer growth ratio",
    "附面层总厚度 / 弦长": "Boundary-layer thickness / chord",
    "远场目标尺寸 / 弦长": "Farfield target size / chord",
    "默认参数": "Defaults",
    "生成并预览全结构网格": "Generate & Preview Mesh",
    "坐标与点分布预览": "Geometry & Point Distribution Preview",
    "物理模型与来流": "Physics & Freestream",
    "求解器": "Solver",
    "湍流模型": "Turbulence model",
    "来流初始化": "Freestream initialization",
    "来流 Mach": "Freestream Mach",
    "攻角 AoA / deg": "Angle of attack / deg",
    "密度 / kg·m⁻³": "Density / kg·m⁻³",
    "温度 / K": "Temperature / K",
    "Reynolds 数": "Reynolds number",
    "翼型壁面条件": "Airfoil wall condition",
    "等温壁面温度 / K": "Isothermal wall temperature / K",
    "远场边界条件": "Farfield boundary condition",
    "离散格式与限制器": "Discretization & Limiter",
    "对流通量格式": "Convective flux scheme",
    "斜率限制器": "Slope limiter",
    "Venkat 限制器系数": "Venkat limiter coefficient",
    "限制器冻结迭代步": "Limiter freeze iteration",
    "CFL 数": "CFL number",
    "CFL 自适应": "Adaptive CFL",
    "线性求解器": "Linear solver",
    "线性残差阈值": "Linear residual tolerance",
    "线性最大迭代": "Maximum linear iterations",
    "运行与收敛控制": "Run & Convergence Control",
    "RMS 残差目标指数": "RMS residual target exponent",
    "最大迭代步数": "Maximum iterations",
    "OpenMP 线程数": "OpenMP threads",
    "算例名称": "Case name",
    "结果根目录": "Results root directory",
    "开始计算": "Start Calculation",
    "一键完成：网格 → SU2 求解 → 报告与云图。每次计算使用独立结果子目录。": "One click: mesh → SU2 → report and contours. Each run uses its own folder.",
    "尺寸按“前缘、后缘上、后缘下”输入；前缘连续通过，不再拆成两个点。Y+ 决定首层高度；尖后缘引出共线的上下 H 型尾迹，附面层末层与外场首层会自动匹配并执行质量门槛检查。": "Enter sizes for the leading edge, upper TE and lower TE. The leading edge remains continuous. Y+ controls the first layer; the sharp TE feeds aligned upper/lower H-type wake blocks, with automatic outer-layer matching and quality checks.",
    "暂停": "Pause",
    "继续": "Resume",
    "终止": "Stop",
    "打开结果目录": "Open Results Folder",
    "实时日志": "Live Log",
    "实时收敛": "Live Convergence",
    "实时监控": "Live Monitor",
    "几何预览": "Geometry",
    "网格检查": "Mesh Inspector",
    "翼型附近": "Airfoil",
    "前缘": "Leading edge",
    "后缘": "Trailing edge",
    "整个流场域": "Full domain",
    "取消网格生成": "Cancel Meshing",
    "云图": "Contours",
    "气动报告": "Aerodynamic Report",
    "收敛历史": "Convergence & Coefficients",
    "表面压力系数": "Surface Pressure Coefficient",
    "摩阻与分离": "Skin Friction & Separation",
    "翼型几何": "Airfoil Geometry",
    "结果摘要": "Summary",
    "结果文件": "Files",
    "场变量": "Field",
    "配色": "Colormap",
    "生成云图": "Render Contour",
    "色阶范围": "Color range",
    "最小值": "Minimum",
    "最大值": "Maximum",
    "应用色阶": "Apply Range",
    "自动：0.5%–99.5%稳健范围；自定义只改变显示，不修改SU2数据": "Auto: robust 0.5%–99.5% range; custom affects display only",
    "滚轮缩放（以光标为中心），左键拖动平移；计算完成后自动显示 Mach 云图。": "Scroll to zoom around the cursor; drag to pan. Mach contours appear automatically after the run.",
    "指标": "Metric",
    "结果": "Result",
    "文件": "File",
    "大小": "Size",
    "修改时间": "Modified",
    "项目工作目录与翼型来源": "Project Directory & Airfoil Source",
    "工作目录": "Working directory",
    "选择…": "Browse...",
    "拟合主程序当前翼型": "Fit Current Airfoil",
    "导入并拟合 DAT": "Import & Fit DAT",
    "第一层：旧 BCE 人工设计；第二层：新 D-BCE 高效优化": "Stage 1: manual legacy BCE; Stage 2: efficient D-BCE optimization",
    "原 BCE 三函数手动控制": "Legacy BCE Three-Function Editor",
    "约束模式": "Constraint mode",
    "自由变形": "Free deformation",
    "锁定厚度": "Lock thickness",
    "锁定弯度": "Lock camber",
    "拖动灵敏度": "Drag sensitivity",
    "重置预览范围": "Reset View",
    "撤销上一次拖动": "Undo Last Drag",
    "恢复初始拟合": "Restore Initial Fit",
    "导出旧 BCE 手调 DAT…": "Export Legacy BCE DAT...",
    "精确使用手调翼型进入网格": "Use Edited Shape Directly",
    "用新 D-BCE 重拟合并进入网格": "Refit with D-BCE & Continue",
    "拖动红点修改 h(x)、α(x)、β(x)。\n重拟合按钮使用端点安全紧支撑基，随后可继续 CFD 与伴随优化。": "Drag the red points to edit h(x), α(x), and β(x).\nD-BCE refitting uses endpoint-safe compact bases before CFD and adjoint optimization.",
}

STATUS_EN = {
    "就绪": "Ready",
    "已恢复全结构化网格推荐参数": "Recommended mesh settings restored",
    "正在生成预览网格": "Generating preview mesh",
    "网格预览完成": "Mesh preview complete",
    "网格生成失败": "Mesh generation failed",
    "计算已暂停": "Calculation paused",
    "计算中": "Calculating",
    "正在终止并整理最后结果...": "Stopping and collecting the last valid result...",
    "计算完成": "Calculation complete",
    "正在生成云图": "Rendering contour",
    "云图生成失败": "Contour rendering failed",
}


UI_FONT_FAMILY = font_config.register_bundled_font()
_PLOT_LANGUAGE = "zh"


def _configure_plot_font() -> bool:
    font_config.configure_matplotlib_font()
    return font_config.BUNDLED_FONT.is_file()


PLOT_HAS_CHINESE_FONT = _configure_plot_font()


def _plot_text(chinese: str, english: str) -> str:
    return english if _PLOT_LANGUAGE == "en" else chinese


def _sutherland_viscosity(temperature: float) -> float:
    """按 SU2 默认 Sutherland 常数计算动力黏度。"""
    reference_mu = 1.716e-5
    reference_temperature = 273.15
    sutherland_constant = 110.4
    return reference_mu * (temperature / reference_temperature) ** 1.5 * (
        reference_temperature + sutherland_constant
    ) / (temperature + sutherland_constant)


@dataclass(frozen=True)
class CaseSettings:
    """从界面一次性读取的不可变算例设置，避免后台线程访问 Tk 变量。"""

    airfoil_path: str
    scale_factor: float
    surface_point_count: int
    leading_edge_size_pct: float
    trailing_upper_size_pct: float
    trailing_lower_size_pct: float
    wake_refinement: float
    y_plus: float
    global_refinement: float
    farfield_chords: float
    domain_scale: float
    growth_ratio: float
    boundary_layer_thickness_pct: float
    farfield_size_pct: float
    airfoil_boundary: str
    farfield_boundary: str
    wall_temperature: float
    solver: str
    turbulence_model: str
    init_option: str
    mach: float
    aoa: float
    density: float
    temperature: float
    reynolds: float
    flow_scheme: str
    slope_limiter: str
    limiter_coeff: float
    limiter_iter: int
    cfl_number: float
    cfl_adapt: bool
    linear_solver: str
    linear_solver_error: float
    linear_solver_iter: int
    residual_min: float
    iterations: int
    threads: int
    case_name: str
    output_root: str
    language: str
    imported_mesh_path: str = ""
    imported_wall_marker: str = ""
    imported_farfield_markers: str = ""
    imported_boundary_cfg: str = ""
    low_mach_multigrid: bool = False

    def physical_values(self, chord: float) -> tuple[float, float, float, float]:
        """返回速度、运动黏度、有效 Reynolds 数和压力。"""
        gas_constant = 287.05
        velocity = self.mach * math.sqrt(1.4 * gas_constant * self.temperature)
        pressure = self.density * gas_constant * self.temperature
        if self.init_option == "TD_CONDITIONS":
            dynamic_viscosity = _sutherland_viscosity(self.temperature)
            kinematic_viscosity = dynamic_viscosity / self.density
            effective_reynolds = velocity * chord / kinematic_viscosity
        else:
            effective_reynolds = self.reynolds
            kinematic_viscosity = velocity * chord / effective_reynolds
        return velocity, kinematic_viscosity, effective_reynolds, pressure

    def su2_parameters(self, chord: float, imported_mesh=None) -> dict[str, float | int | str]:
        _, _, effective_reynolds, pressure = self.physical_values(chord)
        turbulence = self.turbulence_model if self.solver == "RANS" else "NONE"
        turbulence_options = (
            "SA_OPTIONS= NEGATIVE, EXPERIMENTAL"
            if self.solver == "RANS" and turbulence == "SA"
            else ""
        )
        if self.airfoil_boundary == "SLIP":
            boundary = "MARKER_EULER= ( airfoil )"
        elif self.airfoil_boundary == "ADIABATIC":
            boundary = "MARKER_HEATFLUX= ( airfoil, 0.0 )"
        else:
            boundary = f"MARKER_ISOTHERMAL= ( airfoil, {self.wall_temperature:.12g} )"
        if self.farfield_boundary == "FARFIELD":
            farfield = "MARKER_FAR= ( farfield_inlet, farfield_outlet )"
        elif self.farfield_boundary == "INLET_OUTLET":
            total_temperature = self.temperature * (1.0 + 0.2 * self.mach**2)
            total_pressure = pressure * (1.0 + 0.2 * self.mach**2) ** 3.5
            farfield = (
                "INLET_TYPE= TOTAL_CONDITIONS\n"
                "MARKER_INLET= ( farfield_inlet, "
                f"{total_temperature:.12g}, {total_pressure:.12g}, 1.0, 0.0, 0.0 )\n"
                f"MARKER_OUTLET= ( farfield_outlet, {pressure:.12g} )"
            )
        else:
            velocity, _, _, _ = self.physical_values(chord)
            aoa_radians = math.radians(self.aoa)
            velocity_x = velocity * math.cos(aoa_radians)
            velocity_y = velocity * math.sin(aoa_radians)
            farfield = (
                "MARKER_SUPERSONIC_INLET= ( farfield_inlet, "
                f"{self.temperature:.12g}, {pressure:.12g}, "
                f"{velocity_x:.12g}, {velocity_y:.12g}, 0.0 )\n"
                f"MARKER_OUTLET= ( farfield_outlet, {pressure:.12g} )"
            )
        parameters = {
            "SOLVER": self.solver,
            "TURBULENCE_MODEL": turbulence,
            "TURBULENCE_OPTIONS": turbulence_options,
            "INIT_OPTION": self.init_option,
            "MACH": self.mach,
            "AOA": self.aoa,
            "PRESSURE": pressure,
            "TEMPERATURE": self.temperature,
            "DENSITY": self.density,
            "REYNOLDS": effective_reynolds,
            "REYNOLDS_LENGTH": chord,
            "ITERATIONS": self.iterations,
            "AIRFOIL_BOUNDARY": boundary,
            "FARFIELD_BOUNDARY": farfield,
            "CFL_NUMBER": self.cfl_number,
            "CFL_ADAPT": "YES" if self.cfl_adapt else "NO",
            "CFL_ADAPT_PARAM": "( 0.1, 2.0, 1.0, 100.0 )",
            "LINEAR_SOLVER": self.linear_solver,
            "LINEAR_SOLVER_ERROR": self.linear_solver_error,
            "LINEAR_SOLVER_ITER": self.linear_solver_iter,
            "FLOW_SCHEME": self.flow_scheme,
            "MUSCL_FLOW": "NO" if self.flow_scheme == "JST" else "YES",
            "MUSCL_TURB": "YES" if self.solver == "RANS" else "NO",
            "SLOPE_LIMITER": self.slope_limiter,
            "LIMITER_COEFF": self.limiter_coeff,
            "LIMITER_ITER": self.limiter_iter,
            "RESIDUAL_MIN": self.residual_min,
            "SCREEN_OUTPUT": "( INNER_ITER, RMS_DENSITY, LIFT, DRAG )",
        }
        if self.imported_mesh_path:
            mesh = imported_mesh or su2_mesh_import.read_mesh(self.imported_mesh_path)
            if not self.imported_boundary_cfg and self.farfield_boundary != "FARFIELD":
                raise ValueError("导入网格的入口/出口条件请通过配套边界.cfg明确指定。")
            parameters["IMPORTED_BOUNDARY_CONFIG"] = su2_mesh_import.boundary_config(
                mesh, self.imported_wall_marker, self.imported_farfield_markers,
                cfg=self.imported_boundary_cfg, wall_type=self.airfoil_boundary,
                temperature=self.wall_temperature, solver=self.solver)
            parameters["REFERENCE_AREA"] = chord
            parameters["REFERENCE_ORIGIN_X"] = float(mesh.wall(self.imported_wall_marker)[0][:, 0].min()) + .25 * chord
        if self.low_mach_multigrid:
            if self.solver != "RANS" or turbulence != "SA" or self.flow_scheme != "ROE" or not 0 < self.mach <= .3:
                raise ValueError("低马赫数多重网格预设适用于 Mach ≤ 0.30、RANS-SA 和 Roe 格式。")
            parameters.update({
                "REFERENCE_SCALING": "FREESTREAM_PRESS_EQ_ONE",
                "ADDITIONAL_NUMERICS": ("MGLEVEL= 2\nMGCYCLE= V_CYCLE\nLOW_MACH_CORR= YES\n"
                                        "MUSCL_KAPPA_FLOW= 0.5\nMUSCL_KAPPA_TURB= 0.0"),
                "CONVERGENCE_FIELDS": "( RMS_DENSITY, RMS_MOMENTUM-X, RMS_MOMENTUM-Y, RMS_ENERGY, RMS_NU_TILDE, LIFT, DRAG )",
                "CAUCHY_EPS": 4e-7,
            })
        return parameters


class AutoFoilStudio(tk.Tk):
    """主窗口及计算任务控制器。"""

    def __init__(self, smoke_test: bool = False) -> None:
        super().__init__()
        self.smoke_test = smoke_test
        from core_modules.runtime_paths import APP_VERSION
        self.title(f"SU2 AutoFoil Optimizer Studio · V{APP_VERSION}")
        self._fit_initial_window()
        self.configure(background=UI_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._report_tk_exception

        self.processed_airfoil: airfoil_processor.ProcessedAirfoil | None = None
        self.active_case_dir: Path | None = None
        self.running = False
        self.closing_requested = False
        self.worker_thread: threading.Thread | None = None
        self.mesh_preview_running = False
        self.mesh_preview_thread: threading.Thread | None = None
        self.mesh_preview_stop_event = threading.Event()
        self.stop_event = threading.Event()
        self.process_control = process_control.ProcessController()
        self.paused = False
        self.last_streamed_result: tuple[int, float, float, float] | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.report_canvases: dict[str, tk.Canvas] = {}
        self.report_photos: dict[str, ImageTk.PhotoImage] = {}
        self.report_sources: dict[str, Image.Image] = {}
        self.report_placeholder_message = "计算完成后将在这里显示气动报告"
        self.contour_thread: threading.Thread | None = None
        self.contour_colorbar = None
        self.contour_data: dict | None = None
        self.contour_field_shown = ""
        self.file_paths: dict[str, Path] = {}
        self.live_iterations: list[int] = []
        self.live_residuals: list[float] = []
        self.live_cl: list[float] = []
        self.live_cd: list[float] = []
        self.language_code = "zh"
        self._widget_text_sources: dict[int, str] = {}
        self._notebook_tab_sources: dict[tuple[int, str], str] = {}
        self._mesh_estimate_after_id: str | None = None

        self._create_variables()
        self._configure_style()
        self._build_window()
        self._apply_language(regenerate_report=False)
        self._event_poll_after_id = self.after(100, self._drain_events)
        if not self.smoke_test:
            self.after(80, self._prompt_work_directory)
        self._initial_preview_after_id = self.after(180, self._initialize_airfoil_project)

    def destroy(self) -> None:
        if self._mesh_estimate_after_id is not None:
            try:
                self.after_cancel(self._mesh_estimate_after_id)
            except tk.TclError:
                pass
            self._mesh_estimate_after_id = None
        super().destroy()

    # ---------------- 变量与界面骨架 ----------------

    def _fit_initial_window(self) -> None:
        left, top = 0, 0
        width, height = self.winfo_screenwidth(), self.winfo_screenheight()
        if sys.platform == "win32":
            from ctypes import wintypes
            area = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
                left, top = area.left, area.top
                width, height = area.right - area.left, area.bottom - area.top
        # Reserve space for the window frame and taskbar on laptop displays.
        width, height = max(1, width - 24), max(1, height - 64)
        self.minsize(min(960, width), min(540, height))
        self.geometry(f"{min(1360, width)}x{min(880, height)}+{left + 12}+{top + 12}")

    def _create_variables(self) -> None:
        self.language_var = tk.StringVar(value="中文")
        self.airfoil_path_var = tk.StringVar(value=BUILTIN_AIRFOIL_LABEL)
        self.scale_factor_var = tk.StringVar(value="1.0")
        self.surface_point_count_var = tk.StringVar(value="100")
        self.original_count_var = tk.StringVar(value="上表面 --  /  下表面 --")
        self.processed_count_var = tk.StringVar(value="上表面 --  /  下表面 --")
        self.chord_var = tk.StringVar(value="处理后弦长 --")

        self.y_plus_var = tk.StringVar(value="1.0")
        self.imported_mesh = None
        self.import_mesh_path_var = tk.StringVar(value="")
        self.import_wall_var = tk.StringVar(value="")
        self.import_farfield_var = tk.StringVar(value="")
        self.import_bc_var = tk.StringVar(value="")
        self.input_source_var = tk.StringVar(value="当前输入：翼型几何 → 自动划分网格")
        self.global_refinement_var = tk.StringVar(value="1.0")
        self.control_point_sizes_var = tk.StringVar(
            value="0.0015, 0.0015, 0.0015"
        )
        self.wake_refinement_var = tk.StringVar(value="2.0")
        self.farfield_var = tk.StringVar(value="20")
        self.domain_scale_var = tk.StringVar(value="1.0")
        self.mesh_count_var = tk.StringVar(value="预计网格总量：等待翼型预览")
        self.growth_ratio_var = tk.StringVar(value="1.15")
        self.bl_thickness_var = tk.StringVar(value="0.08")
        self.farfield_size_var = tk.StringVar(value="0.4")

        self.airfoil_boundary_var = tk.StringVar(value="绝热无滑移壁面")
        self.farfield_boundary_var = tk.StringVar(value="自由远场（推荐）")
        self.wall_temperature_var = tk.StringVar(value="288.15")

        self.solver_var = tk.StringVar(value="RANS")
        self.turbulence_var = tk.StringVar(value="SA")
        self.init_mode_var = tk.StringVar(value="指定 Reynolds 数")
        self.mach_var = tk.StringVar(value="0.15")
        self.aoa_var = tk.StringVar(value="2.0")
        self.density_var = tk.StringVar(value="1.225")
        self.temperature_var = tk.StringVar(value="288.15")
        self.reynolds_var = tk.StringVar(value="3000000")
        self.physics_summary_var = tk.StringVar(value="速度 --  |  压力 --  |  有效 Re --")

        self.flow_scheme_var = tk.StringVar(value="ROE")
        self.low_mach_multigrid_var = tk.BooleanVar(value=False)
        self.limiter_var = tk.StringVar(value="VENKATAKRISHNAN")
        self.limiter_coeff_var = tk.StringVar(value="0.05")
        self.limiter_iter_var = tk.StringVar(value="999999")
        self.cfl_var = tk.StringVar(value="20.0")
        self.cfl_adapt_var = tk.BooleanVar(value=False)
        self.linear_solver_var = tk.StringVar(value="FGMRES")
        self.linear_error_var = tk.StringVar(value="1e-8")
        self.linear_iter_var = tk.StringVar(value="20")
        self.residual_min_var = tk.StringVar(value="-8")
        self.iterations_var = tk.StringVar(value="2000")
        self.threads_var = tk.StringVar(value="1")

        self.case_name_var = tk.StringVar(value="NACA0012")
        self.output_root_var = tk.StringVar(value=str(DEFAULT_OUTPUT_ROOT))
        self.status_var = tk.StringVar(value="就绪")

        for variable in (
            self.mach_var,
            self.density_var,
            self.temperature_var,
            self.reynolds_var,
            self.init_mode_var,
            self.scale_factor_var,
        ):
            variable.trace_add("write", lambda *_: self._update_physics_summary())
        for variable in (
            self.surface_point_count_var,
            self.global_refinement_var,
            self.control_point_sizes_var,
            self.wake_refinement_var,
            self.y_plus_var,
            self.farfield_var,
            self.domain_scale_var,
            self.growth_ratio_var,
            self.bl_thickness_var,
            self.farfield_size_var,
            self.mach_var,
            self.temperature_var,
            self.density_var,
            self.reynolds_var,
        ):
            variable.trace_add("write", lambda *_: self._schedule_mesh_estimate())

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=UI_BG, foreground=UI_TEXT, bordercolor=UI_BORDER,
                        darkcolor=UI_BORDER, lightcolor=UI_BORDER,
                        font=(UI_FONT_FAMILY, 9))
        style.configure("TFrame", background=UI_BG)
        style.configure("TLabel", background=UI_BG, foreground="#E2E2E2", padding=0,
                        font=(UI_FONT_FAMILY, 9, "bold"))
        style.configure("TLabelframe", background=UI_PANEL, bordercolor=UI_BORDER,
                        borderwidth=1, relief="solid", padding=4)
        style.configure("TLabelframe.Label", background=UI_PANEL, foreground="#E6E6E6",
                        font=(UI_FONT_FAMILY, 9, "bold"), padding=(3, 0))
        style.configure("TButton", background="#2D2D30", foreground=UI_TEXT,
                        bordercolor=UI_BORDER, borderwidth=1, relief="flat",
                        font=(UI_FONT_FAMILY, 9), padding=(6, 3))
        style.map("TButton", background=[("active", "#3A3A3D"), ("pressed", "#202022"),
                                         ("disabled", "#303034")],
                  foreground=[("disabled", "#A0A0A0")],
                  bordercolor=[("disabled", "#4A4A4E"), ("focus", UI_BLUE)])
        style.configure("Accent.TButton", background=UI_BLUE, foreground="#FFFFFF",
                        bordercolor="#1989CA", font=(UI_FONT_FAMILY, 9, "bold"))
        style.map("Accent.TButton", background=[("active", UI_BLUE_ACTIVE),
                                                ("pressed", "#0063A5"),
                                                ("disabled", "#314755")],
                  foreground=[("disabled", "#B8C7CF")],
                  bordercolor=[("disabled", "#496270")])
        style.configure("Danger.TButton", background="#3A2929", foreground="#F0B0B0",
                        bordercolor="#6E3B3B")
        style.map("Danger.TButton", background=[("active", "#593131"),
                                                ("pressed", "#2B2020")])
        style.configure("TEntry", fieldbackground=UI_FIELD, foreground=UI_TEXT,
                        insertcolor="#FFFFFF", bordercolor=UI_BORDER, borderwidth=1,
                        padding=(4, 2), font=(MONO_FONT_FAMILY, 9))
        style.map("TEntry", bordercolor=[("focus", UI_BLUE)],
                  fieldbackground=[("disabled", "#252526")],
                  foreground=[("disabled", "#777777")])
        style.configure("TCombobox", fieldbackground=UI_FIELD, background="#2D2D30",
                        foreground=UI_TEXT, arrowcolor="#BEBEBE", bordercolor=UI_BORDER,
                        borderwidth=1, padding=(4, 2), font=(UI_FONT_FAMILY, 9))
        style.map("TCombobox", bordercolor=[("focus", UI_BLUE)],
                  fieldbackground=[("readonly", UI_FIELD)],
                  selectbackground=[("readonly", UI_FIELD)],
                  selectforeground=[("readonly", UI_TEXT)])
        # ``clam`` renders selected indicators as an X on some Windows/Tk
        # builds.  Explicit images keep the familiar check mark everywhere.
        self._checkbox_unchecked_image = tk.PhotoImage(width=14, height=14)
        self._checkbox_checked_image = tk.PhotoImage(width=14, height=14)
        for image, fill in (
            (self._checkbox_unchecked_image, UI_FIELD),
            (self._checkbox_checked_image, UI_BLUE),
        ):
            image.put(UI_BORDER, to=(0, 0, 14, 14))
            image.put(fill, to=(1, 1, 13, 13))
        for x, y in ((3, 7), (4, 8), (5, 9), (6, 8), (7, 7), (8, 6), (9, 5), (10, 4)):
            self._checkbox_checked_image.put("#FFFFFF", to=(x, y, x + 2, y + 2))
        style.element_create(
            "Industrial.Checkbutton.indicator",
            "image",
            self._checkbox_unchecked_image,
            ("selected", self._checkbox_checked_image),
        )
        style.layout(
            "Industrial.TCheckbutton",
            [("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Industrial.Checkbutton.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"}),
                ]}),
            ]})],
        )
        style.configure("Industrial.TCheckbutton", background=UI_PANEL, foreground="#E2E2E2",
                        padding=(2, 1), font=(UI_FONT_FAMILY, 9, "bold"))
        style.map("Industrial.TCheckbutton", background=[("active", UI_PANEL)])
        style.configure("TNotebook", background=UI_BG, bordercolor=UI_DIVIDER,
                        borderwidth=1, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background="#2D2D30", foreground="#B8B8B8",
                        bordercolor=UI_DIVIDER, font=(UI_FONT_FAMILY, 9), padding=(9, 4))
        style.map("TNotebook.Tab", background=[("selected", UI_PANEL), ("active", "#343437")],
                  foreground=[("selected", "#FFFFFF")],
                  bordercolor=[("selected", UI_BLUE)])
        style.configure("Treeview", background=UI_FIELD, fieldbackground=UI_FIELD,
                        foreground=UI_TEXT, bordercolor=UI_BORDER, rowheight=22,
                        font=(MONO_FONT_FAMILY, 9))
        style.map("Treeview", background=[("selected", "#094771")],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("Treeview.Heading", background="#2D2D30", foreground=UI_TEXT,
                        bordercolor=UI_BORDER, relief="flat", font=(UI_FONT_FAMILY, 9, "bold"),
                        padding=(3, 2))
        style.configure("TScrollbar", background="#333333", troughcolor=UI_BG,
                        bordercolor=UI_BG, arrowcolor="#A0A0A0", width=12)
        style.configure("Horizontal.TProgressbar", troughcolor=UI_FIELD,
                        background=UI_BLUE, bordercolor=UI_BORDER, thickness=8)
        self.option_add("*TCombobox*Listbox.background", UI_FIELD)
        self.option_add("*TCombobox*Listbox.foreground", UI_TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", "#094771")
        self.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    def _build_window(self) -> None:
        # 页眉高度由标题和副标题的实际字体行高决定。Noto CJK 在 Windows
        # 高 DPI 缩放下会比 Tk 默认字体更高，固定像素高度会裁掉副标题下半部。
        self.header = tk.Frame(self, background="#202020", highlightbackground=UI_DIVIDER,
                               highlightthickness=1)
        self.header.pack(fill="x")
        self.header.columnconfigure(0, weight=1)
        title_block = tk.Frame(self.header, background="#202020")
        title_block.grid(row=0, column=0, sticky="ew", padx=8, pady=4)
        self.header_title_label = tk.Label(
            title_block,
            text="SU2 AutoFoil Optimizer Studio",
            background="#202020",
            foreground="white",
            font=(UI_FONT_FAMILY, 13, "bold"),
        )
        self.header_title_label.configure(wraplength=600, justify="left", anchor="w")
        self.header_title_label.pack(fill="x")
        wrap_to_width(self.header_title_label)
        self.header_subtitle_label = tk.Label(
            title_block,
            text="二维翼型全结构化网格、SU2 求解、气动后处理与伴随优化",
            background="#202020",
            foreground=UI_MUTED,
            font=(UI_FONT_FAMILY, 8),
        )
        self.header_subtitle_label.configure(wraplength=480, justify="left", anchor="w")
        self.header_subtitle_label.pack(fill="x", pady=(2, 0))
        wrap_to_width(self.header_subtitle_label)
        self.status_badge = tk.Label(
            self.header,
            textvariable=self.status_var,
            background=UI_BLUE,
            foreground="white",
            font=(UI_FONT_FAMILY, 9, "bold"),
            padx=8,
            pady=3,
        )
        self.status_badge.grid(row=0, column=2, padx=(4, 8), pady=4)
        self.language_combo = ttk.Combobox(
            self.header,
            textvariable=self.language_var,
            values=("中文", "English"),
            state="readonly",
            width=9,
        )
        self.language_combo.grid(row=0, column=1, pady=4)
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

        self.main_notebook = ttk.Notebook(self)
        self.main_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.project_tab = ttk.Frame(self.main_notebook, padding=0)
        self.geometry_tab = ttk.Frame(self.main_notebook, padding=4)
        self.solver_tab = ttk.Frame(self.main_notebook, padding=4)
        self.results_tab = ttk.Frame(self.main_notebook, padding=4)
        self.optimization_tab = ttk.Frame(self.main_notebook, padding=0)
        self.main_notebook.add(self.project_tab, text="旧 BCE 手调 → 新 D-BCE 优化")
        self.main_notebook.add(self.geometry_tab, text="翼型与网格")
        self.main_notebook.add(self.solver_tab, text="求解设置")
        self.main_notebook.add(self.results_tab, text="计算与结果")
        self.main_notebook.add(self.optimization_tab, text="伴随优化")

        self.project_panel = LegacyBCEDeformationPanel(
            self.project_tab,
            workdir_var=self.output_root_var,
            current_airfoil_provider=self._current_airfoil_for_deformation,
            apply_callback=self._apply_project_airfoil,
        )
        self.project_panel.pack(fill="both", expand=True)
        self._build_geometry_tab()
        self._build_solver_tab()
        self._build_results_tab()
        self.optimizer_panel = OptimizerPanel(
            self.optimization_tab,
            current_case_provider=lambda: self.active_case_dir,
        )
        self.optimizer_panel.pack(fill="both", expand=True)
        if self.smoke_test:
            # Existing headless layout tests inspect the geometry page directly.
            self.main_notebook.select(self.geometry_tab)

    def _prompt_work_directory(self) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            title="首先选择项目工作目录",
            initialdir=self.output_root_var.get(),
        )
        if selected:
            self.output_root_var.set(selected)
            self.status_var.set("已选择项目工作目录")
        self.main_notebook.select(self.project_tab)

    def _initialize_airfoil_project(self) -> None:
        self._preview_airfoil(show_error=not self.smoke_test)
        if self.processed_airfoil is not None:
            self.project_panel.load_current_airfoil(silent=True)

    def _current_airfoil_for_deformation(
        self,
    ) -> tuple[str, np.ndarray, np.ndarray] | None:
        if self.processed_airfoil is None:
            return None
        source = self.airfoil_path_var.get()
        name = "NACA0012" if source in {BUILTIN_AIRFOIL_LABEL, BUILTIN_AIRFOIL_LABEL_EN} else Path(source).stem
        return name, self.processed_airfoil.upper.copy(), self.processed_airfoil.lower.copy()

    def _apply_project_airfoil(self, path: Path) -> None:
        self.airfoil_path_var.set(str(path))
        self._preview_airfoil(show_error=True)
        self.main_notebook.select(self.geometry_tab)
        self.status_var.set("BCE 设计翼型已送入网格与计算流程")

    @staticmethod
    def _choice_code(value: str, *mappings: dict[str, str]) -> str:
        for mapping in mappings:
            if value in mapping:
                return mapping[value]
        raise KeyError(value)

    @staticmethod
    def _choice_label(code: str, mapping: dict[str, str]) -> str:
        return next(label for label, item_code in mapping.items() if item_code == code)

    def _translate_widget_tree(self, widget: tk.Misc) -> None:
        for child in widget.winfo_children():
            try:
                current = str(child.cget("text"))
            except (tk.TclError, AttributeError):
                current = ""
            if current:
                source = self._widget_text_sources.setdefault(id(child), current)
                child.configure(
                    text=UI_EN.get(source, source) if self.language_code == "en" else source
                )
            if isinstance(child, ttk.Notebook):
                for tab_id in child.tabs():
                    key = (id(child), str(tab_id))
                    source = self._notebook_tab_sources.setdefault(
                        key, str(child.tab(tab_id, "text"))
                    )
                    child.tab(
                        tab_id,
                        text=UI_EN.get(source, source)
                        if self.language_code == "en"
                        else source,
                    )
            self._translate_widget_tree(child)

    def _apply_language(self, regenerate_report: bool = True) -> None:
        global _PLOT_LANGUAGE
        requested = self.language_var.get()
        self.language_code = "en" if requested == "English" else "zh"
        _PLOT_LANGUAGE = self.language_code

        if self.airfoil_path_var.get() in {
            BUILTIN_AIRFOIL_LABEL,
            BUILTIN_AIRFOIL_LABEL_EN,
        }:
            self.airfoil_path_var.set(
                BUILTIN_AIRFOIL_LABEL_EN
                if self.language_code == "en"
                else BUILTIN_AIRFOIL_LABEL
            )

        choice_specs = (
            (self.init_mode_var, INIT_MODES, INIT_MODES_EN, self.init_mode_combo),
            (
                self.airfoil_boundary_var,
                AIRFOIL_BOUNDARIES,
                AIRFOIL_BOUNDARIES_EN,
                self.airfoil_boundary_combo,
            ),
            (
                self.farfield_boundary_var,
                FARFIELD_BOUNDARIES,
                FARFIELD_BOUNDARIES_EN,
                self.farfield_boundary_combo,
            ),
            (
                self.contour_range_mode_var,
                CONTOUR_RANGE_MODES,
                CONTOUR_RANGE_MODES_EN,
                self.contour_range_combo,
            ),
        )
        for variable, chinese, english, combo in choice_specs:
            code = self._choice_code(variable.get(), chinese, english)
            target = english if self.language_code == "en" else chinese
            combo.configure(values=tuple(target))
            variable.set(self._choice_label(code, target))

        self._translate_widget_tree(self)
        if hasattr(self, "project_panel"):
            self.project_panel.set_language(self.language_code)
        current_status = self.status_var.get()
        if self.language_code == "en":
            self.status_var.set(STATUS_EN.get(current_status, current_status))
        else:
            reverse_status = {english: chinese for chinese, english in STATUS_EN.items()}
            self.status_var.set(reverse_status.get(current_status, current_status))
        self.summary_tree.heading(
            "metric", text=_plot_text("指标", "Metric")
        )
        self.summary_tree.heading("value", text=_plot_text("结果", "Result"))
        self.files_tree.heading("name", text=_plot_text("文件", "File"))
        self.files_tree.heading("size", text=_plot_text("大小", "Size"))
        self.files_tree.heading(
            "modified", text=_plot_text("修改时间", "Modified")
        )
        self._translate_plot_axes()
        if self.processed_airfoil is not None:
            self._draw_airfoil_preview(self.processed_airfoil)
        if (
            regenerate_report
            and self.active_case_dir is not None
            and (self.active_case_dir / "history.csv").is_file()
            and (self.active_case_dir / "surface_flow.csv").is_file()
        ):
            try:
                report = post_analyzer.generate_report(
                    self.active_case_dir, language=self.language_code
                )
                self._load_report(report)
            except Exception as exc:
                self._append_log(
                    _plot_text(
                        f"切换报告语言时未能重绘：{exc}",
                        f"Could not redraw the report after switching language: {exc}",
                    )
                )

    def _on_language_changed(self, _event: object | None = None) -> None:
        self._apply_language(regenerate_report=True)

    def _translate_plot_axes(self) -> None:
        if not hasattr(self, "live_residual_ax"):
            return
        self.live_residual_line.set_label(
            _plot_text("SU2 密度 RMS 残差", "SU2 density RMS residual")
        )
        self.live_residual_ax.set_title(
            _plot_text("SU2 实时残差", "Live SU2 residual"), fontweight="bold"
        )
        self.live_residual_ax.set_ylabel(_plot_text("log10 残差", "log10 residual"))
        self.live_coefficient_ax.set_title(
            _plot_text("实时气动力系数", "Live aerodynamic coefficients"),
            fontweight="bold",
        )
        self.live_coefficient_ax.set_xlabel(_plot_text("迭代步", "Iteration"))
        self.live_coefficient_ax.set_ylabel(_plot_text("系数", "Coefficient"))
        for axis in (self.live_residual_ax, self.live_coefficient_ax):
            axis.legend(loc="best", frameon=False, labelcolor=UI_TEXT, fontsize=8)
        self.live_canvas.draw_idle()

    @staticmethod
    def _add_field(
        parent: tk.Misc,
        row: int,
        label: str,
        variable: tk.Variable,
        width: int = 16,
        stacked: bool = False,
    ) -> ttk.Entry:
        if stacked:
            caption = ttk.Label(parent, text=label, wraplength=260, justify="left")
            caption.grid(row=2 * row, column=0, sticky="ew", padx=8, pady=(6, 2))
            wrap_to_width(caption)
            entry = ttk.Entry(parent, textvariable=variable, width=width)
            entry.grid(row=2 * row + 1, column=0, sticky="ew", padx=8, pady=(0, 4))
            return entry
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(8, 10), pady=5)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=5)
        return entry

    # ---------------- 翼型与网格页 ----------------

    def _build_geometry_tab(self) -> None:
        self.geometry_tab.columnconfigure(1, weight=1)
        self.geometry_tab.rowconfigure(0, weight=1)
        self.geometry_controls = ttk.Frame(self.geometry_tab, width=460)
        self.geometry_controls.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.geometry_controls.grid_propagate(False)
        self.geometry_controls.columnconfigure(0, weight=1)
        self.geometry_controls.rowconfigure(0, weight=1)
        self.geometry_form = ScrollableForm(self.geometry_controls)
        self.geometry_form.grid(row=0, column=0, sticky="nsew")
        controls = self.geometry_form.content
        controls.columnconfigure(0, weight=1)
        self.geometry_tab.bind("<Configure>", self._resize_geometry_controls)

        input_box = ttk.LabelFrame(controls, text="翼型输入", padding=10)
        input_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        input_box.columnconfigure(0, weight=1)
        path_row = ttk.Frame(input_box)
        path_row.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 7))
        path_row.columnconfigure((0, 1), weight=1, uniform="file_actions")
        ttk.Entry(path_row, textvariable=self.airfoil_path_var).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(path_row, text="浏览...", width=0, command=self._browse_airfoil).grid(row=1, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(path_row, text="默认", width=0, command=self._restore_builtin_airfoil).grid(row=1, column=1, sticky="ew", padx=(3, 0))
        ttk.Button(path_row, text="导入 .su2…", width=0, command=self._browse_su2_mesh).grid(row=2,column=0,sticky="ew",pady=3)
        ttk.Button(path_row, text="用翼型划网格", width=0, command=self._use_geometry_input).grid(row=2,column=1,sticky="ew",pady=3)
        input_status = ttk.Label(path_row, textvariable=self.input_source_var,
                                 foreground=UI_BLUE_ACTIVE, wraplength=320)
        input_status.grid(row=3, column=0, columnspan=2, sticky="ew")
        wrap_to_width(input_status)
        ttk.Entry(path_row,textvariable=self.import_mesh_path_var,state="readonly").grid(row=4,column=0,columnspan=2,sticky="ew")
        ttk.Label(path_row,text="导入网格：翼型壁面标记").grid(row=5,column=0,sticky="w")
        self.import_wall_combo=ttk.Combobox(path_row,textvariable=self.import_wall_var,state="readonly",width=16)
        self.import_wall_combo.grid(row=5,column=1,sticky="ew")
        ttk.Label(path_row,text="远场标记（逗号分隔）").grid(row=6,column=0,sticky="w")
        ttk.Entry(path_row,textvariable=self.import_farfield_var).grid(row=6,column=1,sticky="ew")
        ttk.Entry(path_row,textvariable=self.import_bc_var).grid(row=7,column=0,sticky="ew")
        ttk.Button(path_row,text="读入边界 .cfg…",width=0,command=self._browse_boundary_cfg).grid(row=7,column=1,sticky="ew")

        form = ttk.Frame(input_box)
        form.grid(row=1, column=0, sticky="ew")
        form.columnconfigure(0, weight=1)
        ttk.Label(form, text="后缘处理").grid(row=0, column=0, sticky="w", padx=8, pady=(5, 0))
        treatment = ttk.Label(form, text="自动拟合上下尾段并统一到同一尖点", foreground=UI_BLUE_ACTIVE, wraplength=300)
        treatment.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 5))
        wrap_to_width(treatment)
        self._add_field(form, 1, "坐标缩放系数", self.scale_factor_var, stacked=True)

        cosine_box = ttk.LabelFrame(controls, text="翼型几何采样", padding=10)
        cosine_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        cosine_box.columnconfigure(0, weight=1)
        self._add_field(
            cosine_box, 0, "几何采样点数（每侧）", self.surface_point_count_var, stacked=True
        )
        ttk.Label(cosine_box, text="原始点数", foreground=UI_MUTED).grid(row=2, column=0, sticky="w", padx=8, pady=(7, 2))
        original_count = ttk.Label(cosine_box, textvariable=self.original_count_var, wraplength=300)
        original_count.grid(row=3, column=0, sticky="ew", padx=8)
        wrap_to_width(original_count)
        ttk.Label(cosine_box, text="处理后点数", foreground=UI_MUTED).grid(row=4, column=0, sticky="w", padx=8, pady=(7, 2))
        processed_count = ttk.Label(cosine_box, textvariable=self.processed_count_var, wraplength=300)
        processed_count.grid(row=5, column=0, sticky="ew", padx=8)
        wrap_to_width(processed_count)
        chord_label = ttk.Label(cosine_box, textvariable=self.chord_var, foreground=UI_BLUE_ACTIVE, wraplength=300)
        chord_label.grid(row=6, column=0, sticky="ew", padx=8, pady=(4, 6))
        wrap_to_width(chord_label)
        button_row = ttk.Frame(cosine_box)
        button_row.grid(row=7, column=0, sticky="ew", padx=8, pady=(4, 2))
        ttk.Button(button_row, text="更新预览", style="Accent.TButton", command=self._preview_airfoil).pack(fill="x")
        ttk.Button(button_row, text="导出处理坐标", command=self._export_processed_airfoil).pack(fill="x", pady=(4, 0))

        mesh_box = ttk.LabelFrame(
            controls,
            text="C-H 全结构化网格",
            padding=10,
        )
        mesh_box.grid(row=2, column=0, sticky="ew")
        mesh_box.columnconfigure(0, weight=1)
        self._add_field(mesh_box, 0, "全局加密系数（0.05–10.0，小于1为粗网格）", self.global_refinement_var, stacked=True)
        self._add_field(
            mesh_box,
            1,
            "控制尺寸 前缘,后上,后下",
            self.control_point_sizes_var,
            width=30,
            stacked=True,
        )
        self._add_field(mesh_box, 2, "尾迹加密系数（1–12）", self.wake_refinement_var, stacked=True)
        self._add_field(mesh_box, 3, "目标 Y+", self.y_plus_var, stacked=True)
        self._add_field(mesh_box, 4, "基准远场半径 / 弦长", self.farfield_var, stacked=True)
        self._add_field(mesh_box, 5, "流场域缩放系数（0.25–10.0）", self.domain_scale_var, stacked=True)
        self._add_field(mesh_box, 6, "附面层参考扩张比", self.growth_ratio_var, stacked=True)
        self._add_field(mesh_box, 7, "附面层总厚度 / 弦长", self.bl_thickness_var, stacked=True)
        self.mesh_last_entry = self._add_field(mesh_box, 8, "远场目标尺寸 / 弦长", self.farfield_size_var, stacked=True)
        mesh_count = ttk.Label(
            mesh_box,
            textvariable=self.mesh_count_var,
            foreground=UI_BLUE_ACTIVE,
            wraplength=430,
            justify="left",
        )
        mesh_count.grid(row=18, column=0, sticky="ew", padx=8, pady=(8, 2))
        wrap_to_width(mesh_count)
        # Keep actions outside the scrolling form so they always remain reachable.
        mesh_button_row = ttk.Frame(self.geometry_controls, padding=(0, 8, 0, 0))
        mesh_button_row.grid(row=1, column=0, sticky="ew")
        mesh_button_row.columnconfigure(0, weight=1)
        self.mesh_defaults_button = ttk.Button(
            mesh_button_row,
            text="默认参数",
            command=self._restore_mesh_defaults,
        )
        self.mesh_defaults_button.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.mesh_preview_button = ttk.Button(
            mesh_button_row,
            text="生成并预览全结构网格",
            style="Accent.TButton",
            command=self._generate_mesh_preview,
        )
        self.mesh_preview_button.grid(row=1, column=0, sticky="ew")
        self.mesh_stage_value = tk.DoubleVar(value=0)
        self.mesh_stage_text = tk.StringVar(value="等待生成网格")
        ttk.Progressbar(mesh_button_row, variable=self.mesh_stage_value,
                        maximum=100, mode="determinate").grid(row=2, column=0, sticky="ew", pady=3)
        ttk.Label(mesh_button_row, textvariable=self.mesh_stage_text,
                  foreground=UI_TEXT, font=(MONO_FONT_FAMILY, 9)).grid(row=3, column=0, sticky="w")
        self.mesh_cancel_button = ttk.Button(
            mesh_button_row, text="取消网格生成", state="disabled",
            command=lambda: self.mesh_preview_stop_event.set())
        self.mesh_cancel_button.grid(row=4, column=0, sticky="ew", pady=2)
        note = ttk.Label(
            mesh_box,
            text=(
                "尺寸按“前缘、后缘上、后缘下”输入；前缘连续通过，不再拆成两个点。"
                "Y+ 决定首层高度；尖后缘引出共线的上下 H 型尾迹，附面层末层与外场"
                "首层会自动匹配并执行质量门槛检查。"
            ),
            foreground=UI_MUTED,
            wraplength=430,
            justify="left",
        )
        note.grid(row=19, column=0, sticky="ew", padx=8, pady=(6, 4))
        wrap_to_width(note)
        self.geometry_form.enable_scrolling()

        preview_box = ttk.LabelFrame(self.geometry_tab, text="坐标与点分布预览", padding=8)
        preview_box.grid(row=0, column=1, sticky="nsew")
        preview_box.columnconfigure(0, weight=1)
        preview_box.rowconfigure(0, weight=1)
        self.geometry_preview_notebook = ttk.Notebook(preview_box)
        self.geometry_preview_notebook.grid(row=0, column=0, sticky="nsew")
        geometry_view = ttk.Frame(self.geometry_preview_notebook)
        geometry_view.columnconfigure(0, weight=1)
        geometry_view.rowconfigure(0, weight=1)
        self.geometry_preview_notebook.add(geometry_view, text="几何预览")
        self.mesh_viewer = EmbeddedMeshPreview(self.geometry_preview_notebook)
        self.geometry_preview_notebook.add(self.mesh_viewer, text="网格检查")
        _style_mpl_toolbar(self.mesh_viewer.toolbar)
        self.preview_figure = Figure(figsize=(8.5, 6.5), dpi=100, facecolor=UI_BG)
        self.preview_canvas = FigureCanvasTkAgg(self.preview_figure, master=geometry_view)
        self.preview_canvas.get_tk_widget().configure(width=1, height=1)
        self.preview_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar_frame = ttk.Frame(geometry_view)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        self.preview_toolbar = NavigationToolbar2Tk(self.preview_canvas, toolbar_frame, pack_toolbar=False)
        _style_mpl_toolbar(self.preview_toolbar)
        self.preview_toolbar.update()
        self.preview_toolbar.pack(side="left")

    def _resize_geometry_controls(self, event: tk.Event) -> None:
        width = min(650, max(380, int(event.width * 0.45)))
        self.geometry_controls.configure(width=width)

    # ---------------- 求解设置页 ----------------

    def _build_solver_tab(self) -> None:
        self.solver_tab.columnconfigure((0, 1, 2), weight=1, uniform="solver")
        self.solver_tab.rowconfigure(0, weight=1)

        physics_box = ttk.LabelFrame(self.solver_tab, text="物理模型与来流", padding=14)
        physics_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        physics_box.columnconfigure(1, weight=1)
        ttk.Label(physics_box, text="求解器").grid(row=0, column=0, sticky="w", padx=(8, 10), pady=6)
        solver_combo = ttk.Combobox(
            physics_box,
            textvariable=self.solver_var,
            values=("EULER", "NAVIER_STOKES", "RANS"),
            state="readonly",
        )
        solver_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=6)
        solver_combo.bind("<<ComboboxSelected>>", lambda _: self._toggle_solver_controls())
        ttk.Label(physics_box, text="湍流模型").grid(row=1, column=0, sticky="w", padx=(8, 10), pady=6)
        self.turbulence_combo = ttk.Combobox(
            physics_box,
            textvariable=self.turbulence_var,
            values=("SA", "SST"),
            state="readonly",
        )
        self.turbulence_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=6)
        ttk.Label(physics_box, text="来流初始化").grid(row=2, column=0, sticky="w", padx=(8, 10), pady=6)
        self.init_mode_combo = ttk.Combobox(
            physics_box,
            textvariable=self.init_mode_var,
            values=list(INIT_MODES),
            state="readonly",
        )
        self.init_mode_combo.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=6)
        self._add_field(physics_box, 3, "来流 Mach", self.mach_var)
        self._add_field(physics_box, 4, "攻角 AoA / deg", self.aoa_var)
        self._add_field(physics_box, 5, "密度 / kg·m⁻³", self.density_var)
        self._add_field(physics_box, 6, "温度 / K", self.temperature_var)
        self.reynolds_entry = self._add_field(physics_box, 7, "Reynolds 数", self.reynolds_var)
        ttk.Label(physics_box, text="翼型壁面条件").grid(row=8, column=0, sticky="w", padx=(8, 10), pady=6)
        self.airfoil_boundary_combo = ttk.Combobox(
            physics_box,
            textvariable=self.airfoil_boundary_var,
            values=list(AIRFOIL_BOUNDARIES),
            state="readonly",
        )
        self.airfoil_boundary_combo.grid(row=8, column=1, sticky="ew", padx=(0, 8), pady=6)
        self.airfoil_boundary_combo.bind("<<ComboboxSelected>>", lambda _: self._toggle_boundary_controls())
        self.wall_temperature_entry = self._add_field(
            physics_box, 9, "等温壁面温度 / K", self.wall_temperature_var
        )
        ttk.Label(physics_box, text="远场边界条件").grid(row=10, column=0, sticky="w", padx=(8, 10), pady=6)
        self.farfield_boundary_combo = ttk.Combobox(
            physics_box,
            textvariable=self.farfield_boundary_var,
            values=list(FARFIELD_BOUNDARIES),
            state="readonly",
        )
        self.farfield_boundary_combo.grid(row=10, column=1, sticky="ew", padx=(0, 8), pady=6)
        ttk.Separator(physics_box).grid(row=11, column=0, columnspan=2, sticky="ew", padx=8, pady=12)
        ttk.Label(
            physics_box,
            textvariable=self.physics_summary_var,
            foreground=UI_BLUE_ACTIVE,
            wraplength=340,
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=8)

        numerical_box = ttk.LabelFrame(self.solver_tab, text="离散格式与限制器", padding=14)
        numerical_box.grid(row=0, column=1, sticky="nsew", padx=8)
        numerical_box.columnconfigure(1, weight=1)
        ttk.Label(numerical_box, text="对流通量格式").grid(row=0, column=0, sticky="w", padx=(8, 10), pady=6)
        scheme_combo = ttk.Combobox(
            numerical_box,
            textvariable=self.flow_scheme_var,
            values=("JST", "ROE", "AUSM", "HLLC"),
            state="readonly",
        )
        scheme_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=6)
        ttk.Label(numerical_box, text="斜率限制器").grid(row=1, column=0, sticky="w", padx=(8, 10), pady=6)
        limiter_combo = ttk.Combobox(
            numerical_box,
            textvariable=self.limiter_var,
            values=("VENKATAKRISHNAN", "VENKATAKRISHNAN_WANG", "BARTH_JESPERSEN", "NONE"),
            state="readonly",
        )
        limiter_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=6)
        self._add_field(numerical_box, 2, "Venkat 限制器系数", self.limiter_coeff_var)
        self._add_field(numerical_box, 3, "限制器冻结迭代步", self.limiter_iter_var)
        self._add_field(numerical_box, 4, "CFL 数", self.cfl_var)
        ttk.Label(numerical_box, text="CFL 自适应").grid(row=5, column=0, sticky="w", padx=(8, 10), pady=6)
        ttk.Checkbutton(
            numerical_box,
            variable=self.cfl_adapt_var,
            style="Industrial.TCheckbutton",
        ).grid(row=5, column=1, sticky="w", pady=6)
        ttk.Label(numerical_box, text="线性求解器").grid(row=6, column=0, sticky="w", padx=(8, 10), pady=6)
        linear_combo = ttk.Combobox(
            numerical_box,
            textvariable=self.linear_solver_var,
            values=("FGMRES", "BCGSTAB", "RESTARTED_FGMRES"),
            state="readonly",
        )
        linear_combo.grid(row=6, column=1, sticky="ew", padx=(0, 8), pady=6)
        self._add_field(numerical_box, 7, "线性残差阈值", self.linear_error_var)
        self._add_field(numerical_box, 8, "线性最大迭代", self.linear_iter_var)
        ttk.Checkbutton(numerical_box, text="低马赫数多重网格",
                        variable=self.low_mach_multigrid_var,
                        style="Industrial.TCheckbutton",
                        command=self._apply_low_mach_settings).grid(row=9,column=0,columnspan=2,sticky="w",padx=8,pady=4)

        run_box = ttk.LabelFrame(self.solver_tab, text="运行与收敛控制", padding=14)
        run_box.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        run_box.columnconfigure(1, weight=1)
        self._add_field(run_box, 0, "RMS 残差目标指数", self.residual_min_var)
        self._add_field(run_box, 1, "最大迭代步数", self.iterations_var)
        self._add_field(run_box, 2, "OpenMP 线程数", self.threads_var)
        ttk.Separator(run_box).grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=12)
        self._add_field(run_box, 4, "算例名称", self.case_name_var)
        ttk.Label(run_box, text="结果根目录").grid(row=5, column=0, sticky="w", padx=(8, 10), pady=6)
        output_row = ttk.Frame(run_box)
        output_row.grid(row=5, column=1, sticky="ew", padx=(0, 8), pady=6)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_root_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="...", width=3, command=self._browse_output_root).grid(row=0, column=1, padx=(5, 0))
        ttk.Separator(run_box).grid(row=6, column=0, columnspan=2, sticky="ew", padx=8, pady=12)
        ttk.Button(
            run_box,
            text="开始计算",
            style="Accent.TButton",
            command=self._start_calculation,
        ).grid(row=7, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        ttk.Label(
            run_box,
            text="一键完成：网格 → SU2 求解 → 报告与云图。每次计算使用独立结果子目录。",
            foreground=UI_MUTED,
            wraplength=320,
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 0))
        self._toggle_solver_controls()
        self._toggle_boundary_controls()
        self._update_physics_summary()

    # ---------------- 计算与结果页 ----------------

    def _build_results_tab(self) -> None:
        self.results_tab.columnconfigure(0, weight=1)
        self.results_tab.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self.results_tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.start_button = ttk.Button(toolbar, text="开始计算", style="Accent.TButton", command=self._start_calculation)
        self.start_button.pack(side="left")
        self.pause_button = ttk.Button(
            toolbar, text="暂停", command=self._pause_calculation, state="disabled"
        )
        self.pause_button.pack(side="left", padx=(7, 0))
        self.resume_button = ttk.Button(
            toolbar, text="继续", command=self._resume_calculation, state="disabled"
        )
        self.resume_button.pack(side="left", padx=(7, 0))
        self.terminate_button = ttk.Button(
            toolbar,
            text="终止",
            style="Danger.TButton",
            command=self._terminate_calculation,
            state="disabled",
        )
        self.terminate_button.pack(side="left", padx=7)
        ttk.Button(toolbar, text="打开结果目录", command=self._open_result_folder).pack(side="left")
        self.progress = ttk.Progressbar(
            toolbar, mode="determinate", maximum=100.0, length=220
        )
        self.progress.pack(side="right", padx=(12, 0))
        self.progress_text_var = tk.StringVar(value="0%")
        ttk.Label(
            toolbar,
            textvariable=self.progress_text_var,
            foreground=UI_TEXT,
            font=(MONO_FONT_FAMILY, 9, "bold"),
        ).pack(side="right", padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.status_var, foreground=UI_BLUE_ACTIVE).pack(side="right")

        self.result_notebook = ttk.Notebook(self.results_tab)
        self.result_notebook.grid(row=1, column=0, sticky="nsew")
        self.result_notebook.bind(
            "<<NotebookTabChanged>>",
            lambda _: self._on_result_tab_changed(),
        )
        self.monitor_tab = ttk.Frame(self.result_notebook, padding=5)
        monitor_pane = ttk.Panedwindow(self.monitor_tab, orient="horizontal")
        monitor_pane.pack(fill="both", expand=True)
        log_tab = ttk.Frame(monitor_pane, padding=(0, 0, 4, 0))
        self.live_tab = ttk.Frame(monitor_pane, padding=(4, 0, 0, 0))
        monitor_pane.add(log_tab, weight=2)
        monitor_pane.add(self.live_tab, weight=3)
        self.contour_tab = ttk.Frame(self.result_notebook, padding=5)
        self.report_tab = ttk.Frame(self.result_notebook, padding=5)
        self.summary_tab = ttk.Frame(self.result_notebook, padding=8)
        files_tab = ttk.Frame(self.result_notebook, padding=8)
        self.result_notebook.add(self.monitor_tab, text="实时监控")
        self.result_notebook.add(self.contour_tab, text="云图")
        self.result_notebook.add(self.report_tab, text="气动报告")
        self.result_notebook.add(self.summary_tab, text="结果摘要")
        self.result_notebook.add(files_tab, text="结果文件")

        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_tab,
            state="disabled",
            wrap="none",
            font=(MONO_FONT_FAMILY, 9),
            background="#151515",
            foreground="#D4D4D4",
            insertbackground="#FFFFFF",
            selectbackground="#094771",
            selectforeground="#FFFFFF",
            borderwidth=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=UI_BORDER,
            padx=4,
            pady=3,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(
            log_tab, orient="vertical", command=self.log_text.yview
        )
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.tag_configure("error", foreground="#F48771")
        self.log_text.tag_configure("step", foreground="#4FC1FF")

        self.live_tab.columnconfigure(0, weight=1)
        self.live_tab.rowconfigure(0, weight=1)
        self.live_figure = Figure(figsize=(10, 6.5), dpi=100, facecolor=UI_BG)
        self.live_residual_ax = self.live_figure.add_subplot(2, 1, 1)
        self.live_coefficient_ax = self.live_figure.add_subplot(2, 1, 2)
        (self.live_residual_line,) = self.live_residual_ax.plot(
            [], [], color=UI_BLUE_ACTIVE, linewidth=1.4,
            label=_plot_text("密度 RMS 残差", "Density RMS residual"),
        )
        (self.live_cl_line,) = self.live_coefficient_ax.plot(
            [], [], color="#4FC1FF", linewidth=1.3, label="SU2 CL"
        )
        (self.live_cd_line,) = self.live_coefficient_ax.plot(
            [], [], color=UI_ORANGE, linewidth=1.3, label="SU2 CD"
        )
        self.live_residual_ax.set_title(
            _plot_text("实时残差", "Live residual"), fontweight="bold"
        )
        self.live_residual_ax.set_ylabel(_plot_text("log10 残差", "log10 residual"))
        self.live_coefficient_ax.set_title(
            _plot_text("实时气动力系数", "Live aerodynamic coefficients"),
            fontweight="bold",
        )
        self.live_coefficient_ax.set_xlabel(_plot_text("迭代步", "Iteration"))
        self.live_coefficient_ax.set_ylabel(_plot_text("系数", "Coefficient"))
        for axis in (self.live_residual_ax, self.live_coefficient_ax):
            _style_industrial_axis(axis)
            axis.legend(loc="best", frameon=False, labelcolor=UI_TEXT, fontsize=8)
        self.live_figure.tight_layout(pad=2.0)
        self.live_canvas = FigureCanvasTkAgg(self.live_figure, master=self.live_tab)
        self.live_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        # ---- 云图页：交互式体场云图（可缩放平移，随缩放重新渲染） ----
        self.contour_tab.columnconfigure(0, weight=1)
        self.contour_tab.rowconfigure(2, weight=1)
        contour_toolbar = ttk.Frame(self.contour_tab)
        contour_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        ttk.Label(contour_toolbar, text="场变量").pack(side="left", padx=(2, 6))
        self.contour_field_var = tk.StringVar(value="Mach")
        self.contour_field_combo = ttk.Combobox(
            contour_toolbar,
            textvariable=self.contour_field_var,
            values=list(field_visualizer.CONTOUR_FIELDS),
            state="readonly",
            width=22,
        )
        self.contour_field_combo.pack(side="left", padx=(0, 10))
        ttk.Label(contour_toolbar, text="配色").pack(side="left", padx=(0, 6))
        self.contour_cmap_var = tk.StringVar(value="jet")
        self.contour_cmap_combo = ttk.Combobox(
            contour_toolbar,
            textvariable=self.contour_cmap_var,
            values=("jet", "turbo", "viridis", "coolwarm", "inferno"),
            state="readonly",
            width=10,
        )
        self.contour_cmap_combo.pack(side="left", padx=(0, 10))
        self.contour_button = ttk.Button(
            contour_toolbar,
            text="生成云图",
            style="Accent.TButton",
            command=self._render_contour_requested,
        )
        self.contour_button.pack(side="left")
        ttk.Label(
            contour_toolbar,
            text="滚轮缩放（以光标为中心），左键拖动平移；计算完成后自动显示 Mach 云图。",
            foreground=UI_MUTED,
        ).pack(side="left", padx=14)

        range_toolbar = ttk.Frame(self.contour_tab)
        range_toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        ttk.Label(range_toolbar, text="色阶范围").pack(side="left", padx=(2, 6))
        self.contour_range_mode_var = tk.StringVar(value="自动")
        self.contour_range_combo = ttk.Combobox(
            range_toolbar,
            textvariable=self.contour_range_mode_var,
            values=("自动", "自定义"),
            state="readonly",
            width=8,
        )
        self.contour_range_combo.pack(side="left", padx=(0, 8))
        self.contour_range_combo.bind(
            "<<ComboboxSelected>>", self._on_contour_range_mode_changed
        )
        ttk.Label(range_toolbar, text="最小值").pack(side="left", padx=(0, 4))
        self.contour_vmin_var = tk.StringVar(value="")
        self.contour_vmin_entry = ttk.Entry(
            range_toolbar, textvariable=self.contour_vmin_var, width=13,
            font=(MONO_FONT_FAMILY, 9),
        )
        self.contour_vmin_entry.pack(side="left", padx=(0, 8))
        ttk.Label(range_toolbar, text="最大值").pack(side="left", padx=(0, 4))
        self.contour_vmax_var = tk.StringVar(value="")
        self.contour_vmax_entry = ttk.Entry(
            range_toolbar, textvariable=self.contour_vmax_var, width=13,
            font=(MONO_FONT_FAMILY, 9),
        )
        self.contour_vmax_entry.pack(side="left", padx=(0, 8))
        self.contour_range_apply_button = ttk.Button(
            range_toolbar, text="应用色阶", command=self._apply_contour_range
        )
        self.contour_range_apply_button.pack(side="left")
        ttk.Label(
            range_toolbar,
            text="自动：0.5%–99.5%稳健范围；自定义只改变显示，不修改SU2数据",
            foreground=UI_MUTED,
        ).pack(side="left", padx=12)
        self._toggle_contour_range_controls()

        # 交互式画布：FigureCanvasTkAgg + NavigationToolbar 支持缩放。
        self.contour_figure = Figure(figsize=(9.2, 7.6), dpi=100, facecolor=UI_BG)
        self.contour_ax = self.contour_figure.add_subplot(111)
        self.contour_ax.set_title(
            _plot_text("计算完成后将自动显示 Mach 云图", "Mach contour appears after the run"),
            fontsize=11,
        )
        _style_industrial_axis(self.contour_ax)
        self.contour_figure.tight_layout(pad=1.6)
        self.contour_canvas = FigureCanvasTkAgg(self.contour_figure, master=self.contour_tab)
        self.contour_canvas.get_tk_widget().grid(row=2, column=0, sticky="nsew")
        # 鼠标交互：滚轮以光标为中心缩放，左键拖动平移。
        self.contour_canvas.mpl_connect("scroll_event", self._on_contour_scroll)
        self.contour_canvas.mpl_connect("button_press_event", self._on_contour_press)
        self.contour_canvas.mpl_connect("button_release_event", self._on_contour_release)
        self.contour_canvas.mpl_connect("motion_notify_event", self._on_contour_motion)
        contour_nav_frame = ttk.Frame(self.contour_tab)
        contour_nav_frame.grid(row=3, column=0, sticky="ew")
        self.contour_toolbar = NavigationToolbar2Tk(
            self.contour_canvas, contour_nav_frame, pack_toolbar=False
        )
        _style_mpl_toolbar(self.contour_toolbar)
        self.contour_toolbar.update()
        self.contour_toolbar.pack(side="left")
        self.contour_colorbar = None
        self.contour_data: dict | None = None
        self.contour_field_shown = ""
        self._contour_pan_start: tuple[float, float, float, float, float, float] | None = None
        self._contour_draw_after = None

        self.report_tab.columnconfigure(0, weight=1)
        self.report_tab.rowconfigure(0, weight=1)
        self.report_notebook = ttk.Notebook(self.report_tab)
        self.report_notebook.grid(row=0, column=0, sticky="nsew")
        for panel_key, panel_title, _ in post_analyzer.REPORT_PANELS:
            panel_frame = ttk.Frame(self.report_notebook, padding=5)
            panel_frame.columnconfigure(0, weight=1)
            panel_frame.rowconfigure(0, weight=1)
            canvas = tk.Canvas(
            panel_frame, background=UI_BG, highlightthickness=0
            )
            canvas.grid(row=0, column=0, sticky="nsew")
            canvas.bind(
                "<Configure>",
                lambda _, key=panel_key: self._render_report_image(key),
            )
            self.report_notebook.add(panel_frame, text=panel_title)
            self.report_canvases[panel_key] = canvas

        self.summary_tab.columnconfigure(0, weight=1)
        self.summary_tab.rowconfigure(0, weight=1)
        self.summary_tree = ttk.Treeview(self.summary_tab, columns=("metric", "value"), show="headings")
        self.summary_tree.heading("metric", text="指标")
        self.summary_tree.heading("value", text="结果")
        self.summary_tree.column("metric", width=260, anchor="w")
        self.summary_tree.column("value", width=520, anchor="w")
        self.summary_tree.grid(row=0, column=0, sticky="nsew")

        files_tab.columnconfigure(0, weight=1)
        files_tab.rowconfigure(0, weight=1)
        self.files_tree = ttk.Treeview(files_tab, columns=("name", "size", "modified"), show="headings")
        self.files_tree.heading("name", text="文件")
        self.files_tree.heading("size", text="大小")
        self.files_tree.heading("modified", text="修改时间")
        self.files_tree.column("name", width=420, anchor="w")
        self.files_tree.column("size", width=120, anchor="e")
        self.files_tree.column("modified", width=180, anchor="center")
        self.files_tree.grid(row=0, column=0, sticky="nsew")
        self.files_tree.bind("<Double-1>", self._open_selected_file)

    # ---------------- 设置读取与校验 ----------------

    def _read_float(self, variable: tk.StringVar, label: str, positive: bool = False) -> float:
        try:
            value = float(variable.get().strip())
        except ValueError as exc:
            raise ValueError(f"{label} 必须是有效数字。") from exc
        if not math.isfinite(value) or (positive and value <= 0.0):
            condition = "大于 0" if positive else "有限数值"
            raise ValueError(f"{label} 必须是{condition}。")
        return value

    def _read_int(self, variable: tk.StringVar, label: str, minimum: int = 1) -> int:
        try:
            value = int(variable.get().strip())
        except ValueError as exc:
            raise ValueError(f"{label} 必须是整数。") from exc
        if value < minimum:
            raise ValueError(f"{label} 不能小于 {minimum}。")
        return value

    def _read_control_point_sizes(self) -> tuple[float, float, float]:
        """读取前缘、后缘上、后缘下三个弦长比例。"""
        fields = [
            field
            for field in re.split(
                r"[,，;；\s]+", self.control_point_sizes_var.get().strip()
            )
            if field
        ]
        if len(fields) != 3:
            raise ValueError(
                "控制尺寸必须依次输入 3 个数：前缘、后缘上、后缘下。"
            )
        try:
            values = tuple(float(field) for field in fields)
        except ValueError as exc:
            raise ValueError("控制尺寸必须全部是有效数字。") from exc
        if any(
            not math.isfinite(value) or not 0.0 < value <= 0.05
            for value in values
        ):
            raise ValueError("三个控制尺寸都必须处于 (0, 0.05] 弦长。")
        return values[0], values[1], values[2]

    def _collect_settings(self) -> CaseSettings:
        airfoil_input = self.airfoil_path_var.get().strip()
        external_mesh = self.import_mesh_path_var.get()
        if external_mesh:
            airfoil_path = ""
        elif airfoil_input in {BUILTIN_AIRFOIL_LABEL, BUILTIN_AIRFOIL_LABEL_EN}:
            airfoil_path = airfoil_processor.BUILTIN_NACA0012
        else:
            candidate_path = Path(airfoil_input).expanduser()
            if not candidate_path.is_file():
                raise FileNotFoundError(f"找不到翼型文件: {candidate_path}")
            airfoil_path = str(candidate_path.resolve())
        case_name = re.sub(r"[^0-9A-Za-z_.-]+", "_", self.case_name_var.get().strip()).strip("._")
        if not case_name:
            raise ValueError(
                "算例名称需至少包含一个英文字母或数字；"
                "可使用英文字母、数字、下划线、短横线和英文句点。"
            )
        output_root = Path(self.output_root_var.get()).expanduser()
        solver = self.solver_var.get()
        airfoil_boundary = self._choice_code(
            self.airfoil_boundary_var.get(), AIRFOIL_BOUNDARIES, AIRFOIL_BOUNDARIES_EN
        )
        using_sidecar = bool(self.import_mesh_path_var.get() and self.import_bc_var.get())
        if not using_sidecar and solver == "EULER" and airfoil_boundary != "SLIP":
            raise ValueError("EULER 求解器必须使用滑移壁面。")
        if not using_sidecar and solver in {"NAVIER_STOKES", "RANS"} and airfoil_boundary == "SLIP":
            raise ValueError("黏性求解器应选择绝热或等温无滑移壁面。")
        farfield_boundary = self._choice_code(
            self.farfield_boundary_var.get(), FARFIELD_BOUNDARIES, FARFIELD_BOUNDARIES_EN
        )
        mach = self._read_float(self.mach_var, "Mach 数", positive=True)
        if not using_sidecar and farfield_boundary == "SUPERSONIC_OUTLET" and mach <= 1.0:
            raise ValueError("超声速入口模式要求来流 Mach 大于 1。")
        if external_mesh:
            mesh_settings = dict(scale_factor=1.0, surface_point_count=100,
                                 leading_edge_size_pct=.0015, trailing_upper_size_pct=.0015,
                                 trailing_lower_size_pct=.0015, wake_refinement=2., y_plus=1.,
                                 global_refinement=1., farfield_chords=20., domain_scale=1.,
                                 growth_ratio=1.15, boundary_layer_thickness_pct=.08, farfield_size_pct=.4)
        else:
            mesh_settings = self._collect_mesh_generation_settings()
        return self._collect_solver_settings(airfoil_path, case_name, output_root, solver,
                                             airfoil_boundary, farfield_boundary, mach, mesh_settings)

    def _collect_mesh_generation_settings(self) -> dict:
        (
            leading_edge_size,
            trailing_upper_size,
            trailing_lower_size,
        ) = self._read_control_point_sizes()
        global_refinement = self._read_float(
            self.global_refinement_var, "全局加密系数", positive=True
        )
        if not (
            mesh_architect.GLOBAL_REFINEMENT_MIN
            <= global_refinement
            <= mesh_architect.GLOBAL_REFINEMENT_MAX
        ):
            raise ValueError(
                f"全局加密系数必须处于 {mesh_architect.GLOBAL_REFINEMENT_MIN} "
                f"到 {mesh_architect.GLOBAL_REFINEMENT_MAX}。"
            )
        domain_scale = self._read_float(
            self.domain_scale_var, "流场域缩放系数", positive=True
        )
        if not (
            mesh_architect.DOMAIN_SCALE_MIN
            <= domain_scale
            <= mesh_architect.DOMAIN_SCALE_MAX
        ):
            raise ValueError(
                f"流场域缩放系数必须处于 {mesh_architect.DOMAIN_SCALE_MIN} "
                f"到 {mesh_architect.DOMAIN_SCALE_MAX}。"
            )
        farfield_chords = self._read_float(
            self.farfield_var, "远场距离", positive=True
        )
        if farfield_chords * domain_scale < 5.0:
            raise ValueError("基准远场半径与流场域缩放系数的乘积不能小于 5。")
        wake_refinement = self._read_float(
            self.wake_refinement_var, "尾迹加密系数", positive=True
        )
        if not (
            mesh_architect.WAKE_REFINEMENT_MIN
            <= wake_refinement
            <= mesh_architect.WAKE_REFINEMENT_MAX
        ):
            raise ValueError("尾迹加密系数必须处于 1 到 12。")
        return dict(
            scale_factor=self._read_float(self.scale_factor_var, "坐标缩放系数", positive=True),
            surface_point_count=self._read_int(
                self.surface_point_count_var, "几何采样点数", minimum=8
            ),
            leading_edge_size_pct=leading_edge_size,
            trailing_upper_size_pct=trailing_upper_size,
            trailing_lower_size_pct=trailing_lower_size,
            wake_refinement=wake_refinement,
            y_plus=self._read_float(self.y_plus_var, "目标 Y+", positive=True),
            global_refinement=global_refinement,
            farfield_chords=farfield_chords,
            domain_scale=domain_scale,
            growth_ratio=self._read_float(self.growth_ratio_var, "附面层扩张比", positive=True),
            boundary_layer_thickness_pct=self._read_float(self.bl_thickness_var, "附面层厚度比例", positive=True),
            farfield_size_pct=self._read_float(
                self.farfield_size_var, "远场单元尺寸比例", positive=True
            ),
        )

    def _collect_solver_settings(self, airfoil_path, case_name, output_root, solver,
                                 airfoil_boundary, farfield_boundary, mach, mesh_settings) -> CaseSettings:
        return CaseSettings(
            airfoil_path=str(airfoil_path),
            **mesh_settings,
            airfoil_boundary=airfoil_boundary,
            farfield_boundary=farfield_boundary,
            wall_temperature=self._read_float(
                self.wall_temperature_var, "等温壁面温度", positive=True
            ),
            solver=solver,
            turbulence_model=self.turbulence_var.get(),
            init_option=self._choice_code(
                self.init_mode_var.get(), INIT_MODES, INIT_MODES_EN
            ),
            mach=mach,
            aoa=self._read_float(self.aoa_var, "攻角"),
            density=self._read_float(self.density_var, "密度", positive=True),
            temperature=self._read_float(self.temperature_var, "温度", positive=True),
            reynolds=self._read_float(self.reynolds_var, "Reynolds 数", positive=True),
            flow_scheme=self.flow_scheme_var.get(),
            slope_limiter=self.limiter_var.get(),
            limiter_coeff=self._read_float(self.limiter_coeff_var, "限制器系数", positive=True),
            limiter_iter=self._read_int(self.limiter_iter_var, "限制器冻结迭代步", minimum=0),
            cfl_number=self._read_float(self.cfl_var, "CFL 数", positive=True),
            cfl_adapt=self.cfl_adapt_var.get(),
            linear_solver=self.linear_solver_var.get(),
            linear_solver_error=self._read_float(self.linear_error_var, "线性残差阈值", positive=True),
            linear_solver_iter=self._read_int(self.linear_iter_var, "线性迭代数"),
            residual_min=self._read_float(self.residual_min_var, "RMS 残差目标指数"),
            iterations=self._read_int(self.iterations_var, "最大迭代步数"),
            threads=self._read_int(self.threads_var, "线程数"),
            case_name=case_name,
            output_root=str(output_root.resolve()),
            language=self.language_code,
            imported_mesh_path=self.import_mesh_path_var.get(),
            imported_wall_marker=self.import_wall_var.get(),
            imported_farfield_markers=self.import_farfield_var.get(),
            imported_boundary_cfg=self.import_bc_var.get(),
            low_mach_multigrid=self.low_mach_multigrid_var.get(),
        )

    def _apply_low_mach_settings(self) -> None:
        if self.low_mach_multigrid_var.get():
            self.cfl_var.set("65")
            self.cfl_adapt_var.set(False)
            self.linear_iter_var.set("30")

    def _process_from_settings(self, settings: CaseSettings) -> airfoil_processor.ProcessedAirfoil:
        if settings.imported_mesh_path:
            path=Path(settings.imported_mesh_path)
            if self.imported_mesh is None or self.imported_mesh.path != path.resolve():
                raise ValueError("请先使用“导入.su2网格”读取并检查网格。")
            metadata = path.stat()
            if (metadata.st_size, metadata.st_mtime_ns) != self.imported_mesh.stamp:
                raise ValueError("导入后网格文件已更改，请重新读入。")
            wall,_=self.imported_mesh.wall(settings.imported_wall_marker)
            leading=int(np.argmin(wall[:,0]))
            return airfoil_processor.ProcessedAirfoil(
                x=wall[:,0],y=wall[:,1],upper=wall[:leading+1],lower=wall[leading:][::-1],
                trailing_edge=wall[0],trailing_edge_radius=0.,original_upper_count=leading+1,
                original_lower_count=len(wall)-leading,scale_factor=1.)
        return airfoil_processor.process_airfoil(
            settings.airfoil_path,
            scale_factor=settings.scale_factor,
            surface_point_count=settings.surface_point_count,
        )

    # ---------------- 翼型预览 ----------------

    def _preview_airfoil(self, show_error: bool = True) -> None:
        try:
            settings = self._collect_settings()
            processed = self._process_from_settings(settings)
        except Exception as exc:
            if show_error:
                messagebox.showerror("翼型预览失败", str(exc), parent=self)
            return
        self.processed_airfoil = processed
        self.original_count_var.set(
            f"上表面 {processed.original_upper_count}  /  下表面 {processed.original_lower_count}"
        )
        self.processed_count_var.set(
            f"上表面 {len(processed.upper)}  /  下表面 {len(processed.lower)}  /  尖后缘已闭合"
        )
        self.chord_var.set(
            f"处理后弦长 {processed.chord:.7g}  |  后缘间隙 0"
        )
        self._draw_airfoil_preview(processed)
        self._update_physics_summary()
        self._schedule_mesh_estimate()

    def _draw_airfoil_preview(self, processed: airfoil_processor.ProcessedAirfoil) -> None:
        _configure_plot_font()
        figure = self.preview_figure
        figure.clear()
        grid = figure.add_gridspec(
            2, 6, height_ratios=(2.35, 1.65), hspace=0.52, wspace=0.44
        )
        # Keep the engineering view centred instead of stretching one chord
        # over the complete right pane.  This makes camber/thickness changes
        # easier to read while leaving the LE/TE inspection panes generous.
        main_ax = figure.add_subplot(grid[0, 1:5])
        leading_ax = figure.add_subplot(grid[1, 0:3])
        trailing_ax = figure.add_subplot(grid[1, 3:6])
        colors = ("#2266a6", "#d34c5c")

        for axis in (main_ax, leading_ax, trailing_ax):
            _style_industrial_axis(axis)
        main_ax.plot(
            processed.upper[:, 0], processed.upper[:, 1],
            color=colors[0], linewidth=1.4,
            label=_plot_text("上表面", "Upper"),
        )
        main_ax.plot(
            processed.lower[:, 0], processed.lower[:, 1],
            color=colors[1], linewidth=1.4,
            label=_plot_text("下表面", "Lower"),
        )
        # Sparse markers show point density without making a smooth fitted line
        # look serrated on high-DPI screens.
        marker_stride = max(1, len(processed.upper) // 100)
        main_ax.scatter(processed.upper[::marker_stride, 0], processed.upper[::marker_stride, 1], s=6, color=colors[0], alpha=0.62)
        main_ax.scatter(processed.lower[::marker_stride, 0], processed.lower[::marker_stride, 1], s=6, color=colors[1], alpha=0.62)
        x_min, x_max = float(np.min(processed.x)), float(np.max(processed.x))
        chord = x_max - x_min
        leading_point = 0.5 * (processed.upper[-1] + processed.lower[-1])
        control_points = np.asarray([leading_point, processed.upper[0]])
        control_labels = (
            _plot_text("连续前缘", "LE"),
            _plot_text("尖后缘（上下逻辑端）", "Sharp TE"),
        )
        main_ax.scatter(
            control_points[:, 0],
            control_points[:, 1],
            s=42,
            marker="D",
            color="#f59e0b",
            edgecolor="#7c4a03",
            linewidth=0.7,
            zorder=5,
            label=_plot_text("C-H 拓扑控制点", "C-H control points"),
        )
        for point, label in zip(control_points, control_labels):
            main_ax.annotate(
                label,
                point,
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
                color=UI_ORANGE,
            )
        ordinate_low = float(min(np.min(processed.upper[:, 1]), np.min(processed.lower[:, 1])))
        ordinate_high = float(max(np.max(processed.upper[:, 1]), np.max(processed.lower[:, 1])))
        ordinate_center = 0.5 * (ordinate_low + ordinate_high)
        ordinate_half_span = max(0.075 * chord, 0.68 * (ordinate_high - ordinate_low))
        main_ax.set_xlim(x_min - 0.07 * chord, x_max + 0.07 * chord)
        main_ax.set_ylim(
            ordinate_center - ordinate_half_span,
            ordinate_center + ordinate_half_span,
        )
        # A modest, explicitly labelled vertical magnification makes small
        # camber edits readable; x limits and chord remain unchanged.
        main_ax.set_aspect(1.6, adjustable="box")
        main_ax.set_title(
            _plot_text(
                "翼型几何与自动尖后缘（纵向显示 1.6×）",
                "Airfoil geometry and sharp trailing edge (1.6x vertical display)",
            ),
            fontsize=11,
            fontweight="bold",
        )
        main_ax.set_xlabel("x")
        main_ax.set_ylabel("y")
        main_ax.legend(loc="upper center", ncol=3, fontsize=8, frameon=False,
                       labelcolor=UI_TEXT)

        for axis, center, limits, title in (
            (leading_ax, x_min, (-0.01, 0.08), _plot_text("前缘加密", "Leading-edge refinement")),
            (trailing_ax, x_max, (-0.08, 0.02), _plot_text("统一尖后缘", "Sharp trailing edge")),
        ):
            axis.plot(processed.x, processed.y, color="#C8C8C8", linewidth=1.2)
            axis.scatter(processed.x, processed.y, s=8, color=UI_BLUE_ACTIVE)
            axis.set_xlim(center + limits[0] * chord, center + limits[1] * chord)
            axis.set_title(title, fontsize=9, fontweight="bold")
            axis.tick_params(labelsize=8)
        leading_ax.scatter(
            control_points[:1, 0], control_points[:1, 1], s=38, marker="D", color="#f59e0b", zorder=5
        )
        trailing_ax.scatter(
            control_points[1:, 0], control_points[1:, 1], s=38, marker="D", color="#f59e0b", zorder=5
        )
        figure.subplots_adjust(left=0.08, right=0.98, top=0.91, bottom=0.10)
        self.preview_canvas.draw_idle()

    def _use_geometry_input(self) -> None:
        if self.running or self.mesh_preview_running: return
        self.import_mesh_path_var.set("")
        self.imported_mesh = None
        self.import_wall_var.set("")
        self.import_wall_combo.configure(values=())
        self.import_farfield_var.set("")
        self.import_bc_var.set("")
        self.input_source_var.set("当前输入：翼型几何 → 自动划分网格")
        self.mesh_preview_button.configure(text="生成并预览全结构网格")

    def _browse_boundary_cfg(self) -> None:
        if self.running or self.mesh_preview_running: return
        path=filedialog.askopenfilename(parent=self,title="读入边界条件配置（只读取边界定义）",filetypes=[("SU2 config","*.cfg"),("All files","*.*")])
        if path: self.import_bc_var.set(path)

    def _browse_su2_mesh(self) -> None:
        if self.running or self.mesh_preview_running: return
        path=filedialog.askopenfilename(parent=self,title="导入二维SU2网格",filetypes=[("SU2 mesh","*.su2")])
        if path:self._read_external_mesh(Path(path))

    def _read_external_mesh(self, path: Path) -> None:
        self.mesh_preview_running=True
        self.mesh_preview_stop_event.clear()
        self.mesh_preview_button.configure(state="disabled")
        self.mesh_cancel_button.configure(state="normal")
        self.mesh_stage_value.set(5)
        self.mesh_stage_text.set("5% · 读取导入网格")
        self.geometry_preview_notebook.select(self.mesh_viewer)
        output_root = Path(self.output_root_var.get()).expanduser().resolve()

        def work():
            try:
                mesh=su2_mesh_import.read_mesh(path)
                candidates=[]
                for name in mesh.markers:
                    try:
                        points,_=mesh.wall(name)
                        candidates.append((float(np.ptp(points[:,0])),name))
                    except ValueError:pass
                if not candidates:raise ValueError("没有找到可作为翼型壁面的闭合边界。")
                wall=min(candidates)[1]
                preview=output_root/"mesh_previews"/datetime.now().strftime("import_%Y%m%d_%H%M%S_%f")
                if self.mesh_preview_stop_event.is_set():raise ValueError("网格读入已取消。")
                su2_mesh_import.stage_mesh(mesh,preview,wall)
                if self.mesh_preview_stop_event.is_set():
                    raise ValueError("网格读入已取消。")
                self.events.put(("external_mesh_ready",(mesh,wall,preview)))
            except Exception as exc:self.events.put(("mesh_preview_error",str(exc)))
        self.mesh_preview_thread=threading.Thread(target=work,daemon=True,name="SU2MeshImport")
        self.mesh_preview_thread.start()

    def _browse_airfoil(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择翼型坐标",
            filetypes=(("翼型 DAT", "*.dat"), ("文本文件", "*.txt"), ("全部文件", "*.*")),
        )
        if selected:
            self._use_geometry_input()
            self.airfoil_path_var.set(selected)
            self.case_name_var.set(Path(selected).stem)
            self._preview_airfoil()

    def _restore_builtin_airfoil(self) -> None:
        self._use_geometry_input()
        self.airfoil_path_var.set(
            BUILTIN_AIRFOIL_LABEL_EN
            if self.language_code == "en"
            else BUILTIN_AIRFOIL_LABEL
        )
        self.case_name_var.set("NACA0012")
        self._preview_airfoil()

    def _browse_output_root(self) -> None:
        selected = filedialog.askdirectory(parent=self, title="选择结果根目录")
        if selected:
            self.output_root_var.set(selected)

    def _toggle_solver_controls(self) -> None:
        solver = self.solver_var.get()
        self.turbulence_combo.configure(state="readonly" if solver == "RANS" else "disabled")
        boundary_labels = (
            AIRFOIL_BOUNDARIES_EN if self.language_code == "en" else AIRFOIL_BOUNDARIES
        )
        if solver == "EULER":
            self.airfoil_boundary_var.set(self._choice_label("SLIP", boundary_labels))
        else:
            try:
                current_code = self._choice_code(
                    self.airfoil_boundary_var.get(),
                    AIRFOIL_BOUNDARIES,
                    AIRFOIL_BOUNDARIES_EN,
                )
            except KeyError:
                current_code = "ADIABATIC"
            if current_code == "SLIP":
                self.airfoil_boundary_var.set(
                    self._choice_label("ADIABATIC", boundary_labels)
                )
        self._toggle_boundary_controls()

    def _toggle_boundary_controls(self) -> None:
        try:
            boundary_code = self._choice_code(
                self.airfoil_boundary_var.get(), AIRFOIL_BOUNDARIES, AIRFOIL_BOUNDARIES_EN
            )
        except KeyError:
            boundary_code = ""
        is_isothermal = boundary_code == "ISOTHERMAL"
        self.wall_temperature_entry.configure(state="normal" if is_isothermal else "disabled")

    def _update_physics_summary(self) -> None:
        try:
            mach = float(self.mach_var.get())
            density = float(self.density_var.get())
            temperature = float(self.temperature_var.get())
            scale = float(self.scale_factor_var.get())
            gas_constant = 287.05
            velocity = mach * math.sqrt(1.4 * gas_constant * temperature)
            pressure = density * gas_constant * temperature
            chord = self.processed_airfoil.chord if self.processed_airfoil else scale
            try:
                init_code = self._choice_code(
                    self.init_mode_var.get(), INIT_MODES, INIT_MODES_EN
                )
            except KeyError:
                init_code = "REYNOLDS"
            if init_code == "TD_CONDITIONS":
                reynolds = velocity * chord / (_sutherland_viscosity(temperature) / density)
                mode_text = _plot_text("密度模式", "Density mode")
            else:
                reynolds = float(self.reynolds_var.get())
                mode_text = _plot_text("Re 模式", "Re mode")
            self.physics_summary_var.set(
                f"{mode_text}  |  V={velocity:.4g} m/s  |  p={pressure:.6g} Pa  |  Re={reynolds:.6g}"
            )
            self.reynolds_entry.configure(
                state="normal" if init_code == "REYNOLDS" else "disabled"
            )
        except (ValueError, tk.TclError):
            self.physics_summary_var.set("速度 --  |  压力 --  |  有效 Re --")

    def _schedule_mesh_estimate(self) -> None:
        """Debounce live grid-count estimates while the user edits entries."""
        if self._mesh_estimate_after_id is not None:
            try:
                self.after_cancel(self._mesh_estimate_after_id)
            except tk.TclError:
                pass
        self._mesh_estimate_after_id = self.after(280, self._update_mesh_estimate)

    def _update_mesh_estimate(self) -> None:
        self._mesh_estimate_after_id = None
        if self.processed_airfoil is None:
            self.mesh_count_var.set("预计网格总量：等待翼型预览")
            return
        try:
            global_refinement = float(self.global_refinement_var.get())
            wake_refinement = float(self.wake_refinement_var.get())
            farfield = float(self.farfield_var.get())
            domain_scale = float(self.domain_scale_var.get())
            growth = float(self.growth_ratio_var.get())
            thickness = float(self.bl_thickness_var.get())
            farfield_size = float(self.farfield_size_var.get())
            y_plus = float(self.y_plus_var.get())
            leading, trailing_upper, trailing_lower = self._read_control_point_sizes()
            if not mesh_architect.GLOBAL_REFINEMENT_MIN <= global_refinement <= mesh_architect.GLOBAL_REFINEMENT_MAX:
                raise ValueError
            if not mesh_architect.DOMAIN_SCALE_MIN <= domain_scale <= mesh_architect.DOMAIN_SCALE_MAX:
                raise ValueError
            if farfield * domain_scale < 5.0:
                raise ValueError
            mach = float(self.mach_var.get())
            temperature = float(self.temperature_var.get())
            density = float(self.density_var.get())
            velocity = mach * math.sqrt(1.4 * 287.05 * temperature)
            try:
                init_code = self._choice_code(
                    self.init_mode_var.get(), INIT_MODES, INIT_MODES_EN
                )
            except KeyError:
                init_code = "REYNOLDS"
            if init_code == "TD_CONDITIONS":
                nu = _sutherland_viscosity(temperature) / density
            else:
                nu = velocity * self.processed_airfoil.chord / float(
                    self.reynolds_var.get()
                )
            wall = yplus_calc.estimate_wall_spacing(
                velocity, self.processed_airfoil.chord, nu, y_plus
            )
            estimate = mesh_architect.estimate_mesh_counts(
                self.processed_airfoil.x,
                self.processed_airfoil.y,
                wall.first_layer_height,
                farfield_chords=farfield,
                domain_scale=domain_scale,
                boundary_layer_thickness_pct=thickness,
                growth_ratio=growth,
                farfield_size_pct=farfield_size,
                global_refinement=global_refinement,
                leading_edge_size_pct=leading,
                trailing_upper_size_pct=trailing_upper,
                trailing_lower_size_pct=trailing_lower,
                wake_refinement=wake_refinement,
            )
            cells = int(estimate["quadrilateral_cells"])
            nodes = int(estimate["total_nodes"])
            if cells >= 5_000_000:
                scale_note = "超大网格，建议确认内存与计算时间"
            elif cells >= 1_000_000:
                scale_note = "大型网格"
            elif cells >= 250_000:
                scale_note = "中等网格"
            else:
                scale_note = "粗/小型网格"
            self.mesh_count_var.set(
                f"预计网格总量：{cells:,} 个四边形 / {nodes:,} 个节点"
                f"  |  有效远场 {float(estimate['effective_farfield_chords']):.3g}c"
                f"  |  {scale_note}"
            )
        except (ValueError, ZeroDivisionError, tk.TclError):
            self.mesh_count_var.set("预计网格总量：请完整输入有效参数")

    def _export_processed_airfoil(self) -> None:
        self._preview_airfoil()
        if self.processed_airfoil is None:
            return
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="导出处理后的翼型坐标",
            defaultextension=".dat",
            filetypes=(("翼型 DAT", "*.dat"), ("全部文件", "*.*")),
        )
        if selected:
            coordinates = np.column_stack(
                (self.processed_airfoil.x, self.processed_airfoil.y)
            )
            np.savetxt(
                selected,
                coordinates,
                fmt="%.12e",
                header="Processed by SU2 AutoFoil Studio",
                comments="",
            )

    # ---------------- 网格预览 ----------------

    def _create_case_directory(self, settings: CaseSettings) -> Path:
        output_root = Path(settings.output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        case_dir = output_root / f"{settings.case_name}_{timestamp}"
        counter = 1
        while case_dir.exists():
            case_dir = output_root / f"{settings.case_name}_{timestamp}_{counter:02d}"
            counter += 1
        case_dir.mkdir(parents=True)
        return case_dir

    def _restore_mesh_defaults(self) -> None:
        """恢复经过多翼型全结构化质量测试的推荐参数。"""
        self.surface_point_count_var.set("100")
        self.y_plus_var.set("1.0")
        self.global_refinement_var.set("1.0")
        self.control_point_sizes_var.set("0.0015, 0.0015, 0.0015")
        self.wake_refinement_var.set("2.0")
        self.farfield_var.set("20")
        self.domain_scale_var.set("1.0")
        self.growth_ratio_var.set("1.15")
        self.bl_thickness_var.set("0.08")
        self.farfield_size_var.set("0.4")
        self.status_var.set("已恢复全结构化网格推荐参数")
        self.status_badge.configure(background=UI_BLUE)

    def _generate_mesh_preview(self) -> None:
        if self.mesh_preview_running or self.running:
            return
        try:
            settings = self._collect_settings()
            processed = self._process_from_settings(settings)
        except Exception as exc:
            messagebox.showerror("无法生成网格", str(exc), parent=self)
            return
        preview_dir = Path(self.output_root_var.get()).expanduser().resolve() / "mesh_previews" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        preview_dir.mkdir(parents=True, exist_ok=True)
        self.processed_airfoil = processed
        self.mesh_preview_running = True
        self.mesh_preview_stop_event.clear()
        self.mesh_preview_button.configure(state="disabled")
        self.mesh_cancel_button.configure(state="normal")
        self.geometry_preview_notebook.select(self.mesh_viewer)
        self.status_var.set("正在生成预览网格")
        self.status_badge.configure(background=UI_ORANGE)
        self.mesh_stage_value.set(0)
        self.mesh_stage_text.set("0% · 准备网格")
        self._set_stage_progress(0, "准备网格")
        self.mesh_preview_thread = threading.Thread(
            target=self._mesh_preview_worker,
            args=(settings, processed, preview_dir),
            daemon=True,
            name="GmshPreviewWorker",
        )
        self.mesh_preview_thread.start()

    def _mesh_preview_worker(
        self,
        settings: CaseSettings,
        processed: airfoil_processor.ProcessedAirfoil,
        preview_dir: Path,
    ) -> None:
        try:
            if settings.imported_mesh_path:
                mesh = self.imported_mesh
                if mesh is None:
                    raise ValueError("请重新导入网格。")
                su2_mesh_import.stage_mesh(mesh,preview_dir,settings.imported_wall_marker)
                if self.mesh_preview_stop_event.is_set():
                    raise ValueError("网格预览已取消。")
                self.events.put(("mesh_preview_done",preview_dir/"mesh.su2"))
                return
            self.events.put(("stage_progress", (1, "计算首层高度")))
            velocity, nu, _, _ = settings.physical_values(processed.chord)
            wall = yplus_calc.estimate_wall_spacing(
                velocity,
                processed.chord,
                nu,
                settings.y_plus,
            )
            mesh_path = mesh_architect.generate_mesh_subprocess(
                processed.x,
                processed.y,
                wall.first_layer_height,
                output_dir=preview_dir,
                farfield_chords=settings.farfield_chords,
                domain_scale=settings.domain_scale,
                boundary_layer_thickness_pct=settings.boundary_layer_thickness_pct,
                growth_ratio=settings.growth_ratio,
                farfield_size_pct=settings.farfield_size_pct,
                global_refinement=settings.global_refinement,
                leading_edge_size_pct=settings.leading_edge_size_pct,
                trailing_upper_size_pct=settings.trailing_upper_size_pct,
                trailing_lower_size_pct=settings.trailing_lower_size_pct,
                wake_refinement=settings.wake_refinement,
                show_gui=False,
                log_callback=lambda line: self._handle_mesh_output(line, preview=True),
                stop_event=self.mesh_preview_stop_event,
            )
            self.events.put(("mesh_preview_done", mesh_path))
        except Exception as exc:
            self.events.put(("mesh_preview_error", str(exc)))

    # ---------------- 一键计算 ----------------

    def _start_calculation(self) -> None:
        if self.running or self.mesh_preview_running:
            return
        try:
            settings = self._collect_settings()
            if (
                not settings.imported_mesh_path
                and
                (
                    settings.global_refinement > 4.0
                    or settings.domain_scale > 3.0
                )
                and not self.smoke_test
                and not messagebox.askyesno(
                    _plot_text("高密度网格", "High-density mesh"),
                    _plot_text(
                        "当前加密系数或流场域缩放会显著增加网格规模、内存和计算时间。是否继续？",
                        "The current refinement or domain scale significantly increases mesh size, memory use and run time. Continue?",
                    ),
                    parent=self,
                )
            ):
                return
            processed = self._process_from_settings(settings)
            parameters = settings.su2_parameters(processed.chord, self.imported_mesh)
            case_dir = self._create_case_directory(settings)
        except Exception as exc:
            messagebox.showerror("无法开始计算", str(exc), parent=self)
            return

        self.processed_airfoil = processed
        self.active_case_dir = case_dir
        self.running = True
        self.stop_event.clear()
        self.process_control = process_control.ProcessController()
        self.last_streamed_result = None
        self._set_running_state(True)
        self._clear_results()
        self.main_notebook.select(self.results_tab)
        self.result_notebook.select(self.monitor_tab)
        self._set_stage_progress(2, "准备算例")
        self._append_log(f"算例目录: {case_dir}", "step")
        self.worker_thread = threading.Thread(
            target=self._calculation_worker,
            args=(settings, processed, case_dir, parameters, self.imported_mesh),
            daemon=True,
            name="SU2CalculationWorker",
        )
        self.worker_thread.start()

    def _calculation_worker(
        self,
        settings: CaseSettings,
        processed: airfoil_processor.ProcessedAirfoil,
        case_dir: Path,
        parameters=None,
        imported_mesh=None,
    ) -> None:
        try:
            self.events.put(("stage_progress", (5, "保存算例")))
            self.events.put(("log_step", "[1/5] 保存处理坐标和算例设置"))
            np.savetxt(
                case_dir / "processed_airfoil.dat",
                np.column_stack((processed.x, processed.y)),
                fmt="%.12e",
                header="Processed by SU2 AutoFoil Studio",
                comments="",
            )
            (case_dir / "case_settings.json").write_text(
                json.dumps(asdict(settings), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            try:
                if settings.imported_mesh_path:
                    self.events.put(("stage_progress", (15, "准备导入网格")))
                    self.events.put(("log_step", "[2/5] 使用导入网格"))
                    mesh=imported_mesh or su2_mesh_import.read_mesh(settings.imported_mesh_path)
                    su2_mesh_import.stage_mesh(mesh,case_dir,settings.imported_wall_marker)
                    if settings.imported_boundary_cfg:
                        shutil.copy2(settings.imported_boundary_cfg,case_dir/'imported_boundary.cfg')
                else:
                    self.events.put(("stage_progress", (15, "计算网格参数")))
                    self.events.put(("log_step", "[2/5] 计算目标 Y+ 和生成 C-H 网格"))
                    velocity, nu, effective_reynolds, pressure = settings.physical_values(processed.chord)
                    wall = yplus_calc.estimate_wall_spacing(velocity, processed.chord, nu, settings.y_plus)
                    self.events.put(("log", f"V={velocity:.6g} m/s, p={pressure:.6g} Pa, "
                                     f"Re={effective_reynolds:.6g}, delta_y={wall.first_layer_height:.6e} m"))
                    self._generate_internal_mesh(settings,processed,wall,case_dir)
                self.events.put(("stage_progress", (50, "网格质量检查")))
                quality = json.loads(
                    (case_dir / "mesh_quality.json").read_text(encoding="utf-8")
                )
                self.events.put(("mesh_count_actual", quality))
                self.events.put(("mesh_generated", case_dir / "mesh.su2"))
            except RuntimeError as exc:
                if self.stop_event.is_set():
                    raise su2_driver.CalculationCancelled("计算已由用户取消。") from exc
                raise
            if self.stop_event.is_set():
                raise su2_driver.CalculationCancelled("计算已由用户取消。")

            if parameters is None:
                parameters = settings.su2_parameters(processed.chord, imported_mesh)
            self.events.put(("stage_progress", (56, "生成 SU2 配置")))
            self.events.put(("log_step", "[3/5] 生成 SU2 配置"))
            su2_driver.generate_config(
                parameters,
                template_path=PROJECT_ROOT / "config_template.cfg",
                output_dir=case_dir,
            )
            self.events.put(("log_step", f"[4/5] 启动 SU2_CFD ({settings.solver})"))
            self.events.put(("stage_progress", (65, "SU2 求解")))
            solve_started = time.perf_counter()
            su2_driver.run_cfd_streaming(
                parameters,
                template_path=PROJECT_ROOT / "config_template.cfg",
                output_dir=case_dir,
                threads=settings.threads,
                log_callback=self._handle_su2_output,
                stop_event=self.stop_event,
                process_control=self.process_control,
            )

            solve_seconds = time.perf_counter() - solve_started
            self.events.put(("stage_progress", (90, "生成报告")))
            self.events.put(("log_step", "[5/5] 生成 SU2 气动报告"))
            report_path = self._try_generate_report(case_dir, settings.language)
            summary = self._read_result_summary(
                case_dir,
                fallback_point=self.last_streamed_result,
                residual_target=settings.residual_min,
            )
            summary.insert(1, ("结果状态", "计算结束；显示最后一个有效迭代值"))
            summary.insert(2, ("SU2 求解耗时", f"{solve_seconds:.2f} s"))
            assessment = assess_convergence(case_dir / "history.csv", settings.residual_min,
                                            all_residuals=settings.low_mach_multigrid)
            (case_dir / "convergence.json").write_text(
                json.dumps(assessment, ensure_ascii=False, indent=2), encoding="utf-8")
            converged = assessment["passed"]
            summary = [(key, value) for key, value in summary if key != "收敛状态"]
            summary.append(("收敛状态", "已达到目标（残差与气动力）" if converged else
                            "未达到目标（末步残差与 200 步气动力窗口）"))
            if assessment["samples"]:
                summary.extend([
                    ("窗口 CL 极差", f"{assessment['cl_range']:.4g}"),
                    ("窗口 CD 极差", f"{assessment['cd_range']:.4g}"),
                ])
            self._write_last_result(case_dir, "completed" if converged else "unconverged", summary)
            self.events.put(("done", (case_dir, report_path, summary)))
        except su2_driver.CalculationCancelled as exc:
            available = self._recover_available_result(
                case_dir,
                settings.residual_min,
                "用户终止，结果可能尚未收敛",
                settings.language,
            )
            if available:
                report_path, summary = available
                self.events.put(
                    ("partial_done", (case_dir, report_path, summary, str(exc)))
                )
            else:
                self.events.put(("cancelled", str(exc)))
        except Exception as exc:
            error_log = case_dir / "gui_error.log"
            error_log.write_text(traceback.format_exc(), encoding="utf-8")
            detail = f"{exc}\n详细信息: {error_log}"
            available = self._recover_available_result(
                case_dir,
                settings.residual_min,
                "计算异常结束，结果可能尚未收敛",
                settings.language,
            )
            if available:
                report_path, summary = available
                self.events.put(
                    ("partial_error", (case_dir, report_path, summary, detail))
                )
            else:
                self.events.put(("error", detail))

    def _generate_internal_mesh(self, settings, processed, wall, case_dir):
        return mesh_architect.generate_mesh_subprocess(
            processed.x, processed.y, wall.first_layer_height, output_dir=case_dir,
            farfield_chords=settings.farfield_chords,domain_scale=settings.domain_scale,
            boundary_layer_thickness_pct=settings.boundary_layer_thickness_pct,
            growth_ratio=settings.growth_ratio,farfield_size_pct=settings.farfield_size_pct,
            global_refinement=settings.global_refinement,leading_edge_size_pct=settings.leading_edge_size_pct,
            trailing_upper_size_pct=settings.trailing_upper_size_pct,
            trailing_lower_size_pct=settings.trailing_lower_size_pct,wake_refinement=settings.wake_refinement,
            log_callback=self._handle_mesh_output,stop_event=self.stop_event,process_control=self.process_control)

    def _try_generate_report(self, case_dir: Path, language: str = "zh") -> Path | None:
        if not (case_dir / "history.csv").is_file() or not (
            case_dir / "surface_flow.csv"
        ).is_file():
            return None
        try:
            return post_analyzer.generate_report(case_dir, language=language)
        except Exception as exc:
            self.events.put(("log", f"气动报告暂未生成：{exc}"))
            return None

    def _recover_available_result(
        self, case_dir: Path, residual_target: float, status: str, language: str = "zh"
    ) -> tuple[Path | None, list[tuple[str, str]]] | None:
        try:
            summary = self._read_result_summary(
                case_dir,
                fallback_point=self.last_streamed_result,
                residual_target=residual_target,
            )
        except (FileNotFoundError, ValueError):
            return None
        summary.insert(1, ("结果状态", status))
        self._write_last_result(case_dir, "incomplete", summary)
        return self._try_generate_report(case_dir, language), summary

    @staticmethod
    def _write_last_result(
        case_dir: Path, status: str, summary: list[tuple[str, str]]
    ) -> Path:
        output = case_dir / "last_result.json"
        output.write_text(
            json.dumps(
                {
                    "status": status,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "metrics": {metric: value for metric, value in summary},
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return output

    @staticmethod
    def _read_result_summary(
        case_dir: Path,
        fallback_point: tuple[int, float, float, float] | None = None,
        residual_target: float | None = None,
    ) -> list[tuple[str, str]]:
        import pandas as pd

        def find(frame: object, names: tuple[str, ...]) -> str | None:
            columns = getattr(frame, "columns")
            normalized = {
                re.sub(r"[^a-z0-9]", "", str(column).lower()): str(column)
                for column in columns
            }
            for name in names:
                key = re.sub(r"[^a-z0-9]", "", name.lower())
                if key in normalized:
                    return normalized[key]
            return None

        history_values: dict[str, float] = {}
        history_path = case_dir / "history.csv"
        if history_path.is_file() and history_path.stat().st_size > 0:
            try:
                history = pd.read_csv(
                    history_path, skipinitialspace=True, on_bad_lines="skip"
                )
                history.columns = [
                    str(column).strip().strip('"') for column in history.columns
                ]
                history = history.dropna(how="all")
                if not history.empty:
                    last = history.iloc[-1]
                    for key, names in (
                        ("iteration", ("Inner_Iter", "Iteration", "Iter")),
                        ("residual", ("rms[Rho]", "RMS_Density")),
                        ("cl", ("CL", "Lift")),
                        ("cd", ("CD", "Drag")),
                    ):
                        column = find(history, names)
                        if column:
                            value = float(last[column])
                            if math.isfinite(value):
                                history_values[key] = value
            except (OSError, ValueError, TypeError):
                history_values.clear()

        if fallback_point is not None:
            streamed = {
                "iteration": float(fallback_point[0]),
                "residual": float(fallback_point[1]),
                "cl": float(fallback_point[2]),
                "cd": float(fallback_point[3]),
            }
            if streamed["iteration"] >= history_values.get("iteration", -1.0):
                history_values.update(streamed)
        if not history_values:
            raise FileNotFoundError("尚未产生可读取的 SU2 迭代结果。")

        result: list[tuple[str, str]] = [("算例目录", str(case_dir))]
        for label, key in (
            ("最后有效迭代步", "iteration"),
            ("密度 RMS 残差（log10）", "residual"),
            ("升力系数 CL", "cl"),
            ("阻力系数 CD", "cd"),
        ):
            if key in history_values:
                value = history_values[key]
                result.append((label, f"{int(value)}" if key == "iteration" else f"{value:.8g}"))
        if residual_target is not None and "residual" in history_values:
            residual = history_values["residual"]
            convergence = (
                f"已达到目标 {residual_target:.4g}"
                if residual <= residual_target
                else f"未达到目标 {residual_target:.4g}，仍保留当前结果"
            )
            result.append(("收敛状态", convergence))

        surface_path = case_dir / "surface_flow.csv"
        if surface_path.is_file() and surface_path.stat().st_size > 0:
            try:
                surface = pd.read_csv(surface_path, skipinitialspace=True)
                surface.columns = [
                    str(column).strip().strip('"') for column in surface.columns
                ]
                cp_column = find(surface, ("Pressure_Coefficient", "Cp"))
                yplus_column = find(surface, ("Y_Plus", "YPlus"))
                cf_column = find(
                    surface, ("Skin_Friction_Coefficient_x", "Cf_x", "Cf")
                )
                if cp_column:
                    result.extend(
                        (
                            ("Cp 最小值", f"{float(surface[cp_column].min()):.8g}"),
                            ("Cp 最大值", f"{float(surface[cp_column].max()):.8g}"),
                        )
                    )
                if yplus_column:
                    result.extend(
                        (
                            ("平均 Y+", f"{float(surface[yplus_column].mean()):.8g}"),
                            ("最大 Y+", f"{float(surface[yplus_column].max()):.8g}"),
                        )
                    )
                if cf_column:
                    separation_count = int((surface[cf_column] < 0.0).sum())
                    result.append(("Cf < 0 表面点数", str(separation_count)))
            except (OSError, ValueError, TypeError):
                pass
        return result

    def _handle_su2_output(self, line: str) -> None:
        """后台线程回调：保留原始日志，同时抽取迭代、残差、CL 和 CD。"""
        self.events.put(("log", line))
        match = re.match(
            r"^\|\s*(\d+)\s*\|\s*([-+0-9.eE]+)\s*\|\s*([-+0-9.eE]+)"
            r"\s*\|\s*([-+0-9.eE]+)\s*\|",
            line,
        )
        if match:
            point = (
                int(match.group(1)),
                float(match.group(2)),
                float(match.group(3)),
                float(match.group(4)),
            )
            self.last_streamed_result = point
            self.events.put(
                (
                    "history_point",
                    point,
                )
            )

    def _pause_calculation(self) -> None:
        if not self.running or self.paused:
            return
        try:
            suspended = self.process_control.pause()
        except OSError as exc:
            messagebox.showerror("无法暂停计算", str(exc), parent=self)
            return
        self.paused = True
        self.pause_button.configure(state="disabled")
        self.resume_button.configure(state="normal")
        self.progress_text_var.set(f"{float(self.progress['value']):.0f}% · 已暂停")
        self.status_var.set("计算已暂停")
        detail = (
            "当前计算进程已暂停。"
            if suspended
            else "已登记暂停请求，下一个耗时计算阶段启动后会自动暂停。"
        )
        self._append_log(detail, "step")

    def _resume_calculation(self) -> None:
        if not self.running or not self.paused:
            return
        try:
            self.process_control.resume()
        except OSError as exc:
            messagebox.showerror("无法继续计算", str(exc), parent=self)
            return
        self.paused = False
        self.pause_button.configure(state="normal")
        self.resume_button.configure(state="disabled")
        self.progress_text_var.set(f"{float(self.progress['value']):.0f}%")
        self.status_var.set("计算中")
        self._append_log("计算已继续。", "step")

    def _terminate_calculation(self) -> None:
        if not self.running:
            return
        self.stop_event.set()
        try:
            self.process_control.terminate()
        except OSError as exc:
            self._append_log(f"终止信号发送失败：{exc}", "error")
        self.paused = False
        self.pause_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.terminate_button.configure(state="disabled")
        self.progress_text_var.set(f"{float(self.progress['value']):.0f}% · 终止中")
        self.status_var.set("正在终止并整理最后结果...")
        self._append_log(
            "已请求终止；将保留并显示最后一个有效迭代结果，不要求达到残差目标。",
            "error",
        )

    def _cancel_calculation(self) -> None:
        """兼容旧界面调用；语义已统一为保留结果的终止。"""
        self._terminate_calculation()

    def _set_running_state(self, running: bool) -> None:
        self.running = running
        self.paused = False
        self.start_button.configure(state="disabled" if running else "normal")
        self.pause_button.configure(state="normal" if running else "disabled")
        self.resume_button.configure(state="disabled")
        self.terminate_button.configure(state="normal" if running else "disabled")
        if running:
            self.status_var.set("计算中")
            self.status_badge.configure(background=UI_ORANGE)
        else:
            if float(self.progress["value"]) < 100.0:
                self.progress_text_var.set(f"{float(self.progress['value']):.0f}%")

    def _set_stage_progress(self, value: float, label: str = "") -> None:
        value = max(0.0, min(100.0, float(value)))
        self.progress.configure(mode="determinate", maximum=100.0, value=value)
        suffix = f" · {label}" if label else ""
        self.progress_text_var.set(f"{value:.0f}%{suffix}")

    def _handle_mesh_output(self, line: str, preview: bool = False) -> None:
        if line.startswith("MESH_PROGRESS|"):
            try:
                _, number, label = line.split("|", 2)
                value = float(number)
            except ValueError:
                self.events.put(("log", line))
                return
            self.events.put(("mesh_progress", (value, label)))
            self.events.put(("stage_progress", (value if preview else 15 + .35 * value, label)))
        elif line.strip():
            self.events.put(("mesh_preview_log" if preview else "log", line))

    # ---------------- 事件循环 ----------------

    def _drain_events(self) -> None:
        history_changed = False
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "log_step":
                    self._append_log(str(payload), "step")
                elif kind == "stage_progress":
                    value, label = payload  # type: ignore[misc]
                    self._set_stage_progress(float(value), str(label))
                elif kind == "mesh_progress":
                    value, label = payload
                    self.mesh_stage_value.set(float(value))
                    self.mesh_stage_text.set(f"{float(value):.0f}% · {label}")
                elif kind == "mesh_generated":
                    self._load_embedded_mesh(Path(payload))
                elif kind == "done":
                    case_dir, report_path, summary = payload  # type: ignore[misc]
                    self._finish_success(case_dir, report_path, summary)
                elif kind == "partial_done":
                    case_dir, report_path, summary, detail = payload  # type: ignore[misc]
                    self._finish_partial_result(
                        case_dir, report_path, summary, str(detail), failed=False
                    )
                elif kind == "partial_error":
                    case_dir, report_path, summary, detail = payload  # type: ignore[misc]
                    self._finish_partial_result(
                        case_dir, report_path, summary, str(detail), failed=True
                    )
                elif kind == "cancelled":
                    self._finish_failure("已终止（尚无迭代结果）", str(payload), cancelled=True)
                elif kind == "error":
                    self._finish_failure("计算失败", str(payload))
                elif kind == "mesh_preview_log":
                    if str(payload).strip():
                        self._append_log(str(payload))
                elif kind == "external_mesh_ready":
                    if self.mesh_preview_stop_event.is_set():
                        self._finish_mesh_preview_error("网格导入已取消。")
                        continue
                    mesh,wall,preview=payload
                    self.imported_mesh=mesh
                    self.import_mesh_path_var.set(str(mesh.path))
                    self.import_wall_combo.configure(values=list(mesh.markers))
                    self.import_wall_var.set(wall)
                    self.import_farfield_var.set(", ".join(name for name in mesh.markers if name!=wall))
                    self.import_bc_var.set("")
                    case_stem = re.sub(r"[^0-9A-Za-z_.-]+", "_", mesh.path.stem).strip("._")
                    self.case_name_var.set(case_stem or "ImportedMesh")
                    self.input_source_var.set("当前输入：导入网格（保留原节点）；请核对壁面和边界条件")
                    self.mesh_preview_button.configure(text="预览导入网格")
                    self._finish_mesh_preview(preview/"mesh.su2")
                elif kind == "mesh_preview_done":
                    self._finish_mesh_preview(Path(str(payload)))
                elif kind == "mesh_count_actual":
                    self._show_actual_mesh_count(payload)  # type: ignore[arg-type]
                elif kind == "mesh_preview_error":
                    self._finish_mesh_preview_error(str(payload))
                elif kind == "contour_data":
                    field, prepared = payload  # type: ignore[misc]
                    self._finish_contour(str(field), prepared)
                elif kind == "contour_error":
                    self._finish_contour_error(str(payload))
                elif kind == "history_point":
                    iteration, residual, cl_value, cd_value = payload  # type: ignore[misc]
                    if self.live_iterations and int(iteration) <= self.live_iterations[-1]:
                        continue
                    self.live_iterations.append(int(iteration))
                    self.live_residuals.append(float(residual))
                    self.live_cl.append(float(cl_value))
                    self.live_cd.append(float(cd_value))
                    history_changed = True
        except queue.Empty:
            pass
        # The Windows solver buffers stdout when connected to a pipe. Its CSV
        # is flushed each iteration; use it as the live data source as well.
        if self.running and self.active_case_dir is not None:
            after = self.live_iterations[-1] if self.live_iterations else -1
            for iteration, residual, cl_value, cd_value in read_history_points(
                self.active_case_dir / "history.csv", after
            ):
                self.live_iterations.append(iteration)
                self.live_residuals.append(residual)
                self.live_cl.append(cl_value)
                self.live_cd.append(cd_value)
                self.last_streamed_result = (iteration, residual, cl_value, cd_value)
                history_changed = True
        if history_changed:
            self._draw_live_history()
        if self.winfo_exists():
            self._event_poll_after_id = self.after(100, self._drain_events)

    def _finish_success(
        self,
        case_dir: Path,
        report_path: Path | None,
        summary: list[tuple[str, str]],
    ) -> None:
        self._set_running_state(False)
        self._set_stage_progress(100, "完成")
        unconverged = dict(summary).get("收敛状态", "").startswith("未达到目标")
        self.status_var.set("计算结束 · 未收敛" if unconverged else "计算完成")
        self.status_badge.configure(background=UI_ORANGE if unconverged else UI_BLUE)
        self._append_log(f"计算完成: {case_dir}", "step")
        self._draw_live_history()
        self.live_figure.savefig(case_dir / "Live_Convergence.png", dpi=180, bbox_inches="tight")
        if report_path:
            self._load_report(report_path)
        else:
            self._set_report_placeholder("已显示数值结果；本次没有可用的表面气动报告。")
        self._fill_summary(summary)
        self._refresh_files(case_dir)
        self.optimizer_panel.set_case(case_dir)
        flow_path = case_dir / "flow.vtu"
        if flow_path.is_file():
            # 计算完成且已有场文件时，自动渲染并显示 Mach 云图。
            self.result_notebook.select(self.contour_tab)
            self._refresh_contour_fields(case_dir)
            self._append_log("正在自动生成 Mach 云图...", "step")
            self._render_contour_requested()
        else:
            self.result_notebook.select(self.summary_tab)
        if self.closing_requested:
            self.after(50, self.destroy)

    def _finish_partial_result(
        self,
        case_dir: Path,
        report_path: Path | None,
        summary: list[tuple[str, str]],
        detail: str,
        failed: bool,
    ) -> None:
        self._set_running_state(False)
        self._set_stage_progress(100, "已保留最后结果")
        self.status_var.set("计算异常结束，已显示最后结果" if failed else "已终止，已显示最后结果")
        self.status_badge.configure(background=UI_DANGER if failed else UI_ORANGE)
        self._append_log(detail, "error")
        self._append_log("结果摘要采用最后一个有效迭代值，可能尚未收敛。", "step")
        self._draw_live_history()
        self.live_figure.savefig(
            case_dir / "Live_Convergence.png", dpi=180, bbox_inches="tight"
        )
        if report_path:
            self._load_report(report_path)
        else:
            self._set_report_placeholder(
                "计算提前结束：已显示最后数值结果，但尚无完整表面报告。"
            )
        self._fill_summary(summary)
        self._refresh_files(case_dir)
        self.optimizer_panel.set_case(case_dir)
        if (case_dir / "flow.vtu").is_file():
            self._refresh_contour_fields(case_dir)
        self.result_notebook.select(self.summary_tab)
        if failed and not self.closing_requested:
            messagebox.showwarning(
                "计算提前结束",
                "求解器异常结束，但已保留并显示最后一个有效迭代结果。\n\n" + detail,
                parent=self,
            )
        if self.closing_requested:
            self.after(50, self.destroy)

    def _finish_failure(self, status: str, detail: str, cancelled: bool = False) -> None:
        self._set_running_state(False)
        self.progress_text_var.set(f"{float(self.progress['value']):.0f}% · 未完成")
        self.status_var.set(status)
        self.status_badge.configure(background="#555555" if cancelled else UI_DANGER)
        self._append_log(detail, "error")
        if self.active_case_dir:
            self._refresh_files(self.active_case_dir)
        if not cancelled and not self.closing_requested:
            messagebox.showerror("SU2 AutoFoil", detail, parent=self)
        if self.closing_requested:
            self.after(50, self.destroy)

    def _finish_mesh_preview(self, mesh_path: Path) -> None:
        self.mesh_preview_running = False
        self.mesh_preview_button.configure(state="normal")
        self.mesh_cancel_button.configure(state="disabled")
        if not self.running:
            self._set_stage_progress(100, "网格完成")
            self.status_var.set("网格预览完成")
            self.status_badge.configure(background=UI_BLUE)
        if not self.closing_requested:
            self._load_embedded_mesh(mesh_path)
            self.geometry_preview_notebook.select(self.mesh_viewer)
        self.mesh_stage_value.set(100)
        self.mesh_stage_text.set("100% · 导入网格已就绪" if self.import_mesh_path_var.get()
                                 else "100% · 网格已生成，右侧可检查前缘和后缘")

    def _load_embedded_mesh(self, mesh_path: Path) -> None:
        try:
            self.mesh_viewer.load(mesh_path)
            self._show_actual_mesh_count(self.mesh_viewer.quality)
        except (OSError, ValueError, KeyError) as exc:
            self._append_log(f"网格已生成，但内嵌预览读取失败：{exc}", "error")
            self.mesh_viewer.status_var.set(f"预览读取失败：{exc}")

    def _show_actual_mesh_count(self, quality: dict) -> None:
        """Replace the live estimate with generated counts."""
        if quality.get("imported_mesh"):
            self.mesh_count_var.set(f"导入网格：{quality['total_cells']:,} 单元 / {quality['total_nodes']:,} 节点；原网格保持不变")
            return
        try:
            cells = int(quality["quadrilateral_cells"])
            nodes = int(quality["total_nodes"])
            effective = float(
                quality.get("effective_farfield_chords", quality["wake_length_chords"])
            )
        except (KeyError, TypeError, ValueError):
            return
        self.mesh_count_var.set(
            f"实际网格总量：{cells:,} 个四边形 / {nodes:,} 个节点"
            f"  |  有效远场 {effective:.3g}c"
        )

    def _finish_mesh_preview_error(self, detail: str) -> None:
        self.mesh_preview_running = False
        self.mesh_preview_button.configure(state="normal")
        self.mesh_cancel_button.configure(state="disabled")
        self.mesh_stage_text.set("网格生成已取消" if self.mesh_preview_stop_event.is_set() else "网格生成失败，请检查日志")
        if not self.running:
            self.progress_text_var.set(f"{float(self.progress['value']):.0f}% · 失败")
            self.status_var.set("网格生成失败")
            self.status_badge.configure(background=UI_DANGER)
        if not self.closing_requested and not self.mesh_preview_stop_event.is_set():
            messagebox.showerror("全结构化网格生成失败", detail, parent=self)

    # ---------------- 云图 ----------------

    def _refresh_contour_fields(self, case_dir: Path) -> None:
        """把场变量下拉框过滤为当前 flow.vtu 中真实存在的变量。"""
        try:
            available = field_visualizer.list_available_fields(
                case_dir / "flow.vtu"
            )
        except (OSError, ValueError):
            return
        ordered = [
            name for name in field_visualizer.CONTOUR_FIELDS if name in available
        ]
        if not ordered:
            return
        self.contour_field_combo.configure(values=ordered)
        if self.contour_field_var.get() not in ordered:
            self.contour_field_var.set("Mach" if "Mach" in ordered else ordered[0])

    def _on_result_tab_changed(self) -> None:
        """切到云图页时把场变量下拉框过滤为当前文件真实存在的变量。"""
        current = self.result_notebook.select()
        if str(current) == str(self.contour_tab):
            if self.active_case_dir and (self.active_case_dir / "flow.vtu").is_file():
                self._refresh_contour_fields(self.active_case_dir)

    def _render_contour_requested(self) -> None:
        if self.contour_thread and self.contour_thread.is_alive():
            return
        if self.active_case_dir is None or not (self.active_case_dir / "flow.vtu").is_file():
            messagebox.showinfo(
                "没有可绘制的云图",
                "请先完成一次 SU2 计算，flow.vtu 生成后才能绘制云图。",
                parent=self,
            )
            return
        self._refresh_contour_fields(self.active_case_dir)
        try:
            limits = self._selected_contour_limits()
        except ValueError as exc:
            messagebox.showerror("色阶范围无效", str(exc), parent=self)
            return
        self.contour_button.configure(state="disabled")
        self.status_var.set("正在生成云图")
        self.contour_thread = threading.Thread(
            target=self._contour_worker,
            args=(
                self.contour_field_var.get(),
                self.active_case_dir,
                limits,
            ),
            daemon=True,
            name="ContourRenderWorker",
        )
        self.contour_thread.start()

    def _contour_worker(
        self, field: str, case_dir: Path, limits: tuple[float, float] | None = None
    ) -> None:
        try:
            airfoil_points = field_visualizer.read_airfoil_boundary(case_dir)
            prepared = field_visualizer.prepare_contour_data(
                case_dir / "flow.vtu",
                field,
                airfoil_points=airfoil_points,
            )
            prepared = field_visualizer.rasterize_contour_for_display(prepared)
            prepared["auto_vmin"] = prepared["vmin"]
            prepared["auto_vmax"] = prepared["vmax"]
            if limits is not None:
                prepared["vmin"], prepared["vmax"] = limits
            if field == "Pressure":
                config_path = case_dir / "run.cfg"
                if config_path.is_file() and re.search(
                    r"^\s*REF_DIMENSIONALIZATION\s*=\s*FREESTREAM_PRESS_EQ_ONE\b",
                    config_path.read_text(encoding="utf-8"), re.MULTILINE,
                ):
                    prepared["label"] = "(p − p∞) / p∞"
            result_file = case_dir / "last_result.json"
            if result_file.is_file():
                result = json.loads(result_file.read_text(encoding="utf-8"))
                prepared["unconverged"] = (
                    result.get("status") in ("unconverged", "incomplete")
                    or result.get("metrics", {}).get("收敛状态", "").startswith("未达到目标")
                )
            self.events.put(("contour_data", (field, prepared)))
        except Exception as exc:
            self.events.put(("contour_error", str(exc)))

    def _draw_contour(self, field: str, prepared: dict) -> None:
        """主线程：把云图数据画到交互式画布上并保存 PNG。

        每次重绘都整图重建（figure.clear + 重新 add_subplot）。matplotlib 3.11
        中先 ``axis.clear()`` 再 ``colorbar.remove()`` 会因 subplotspec 已失效
        而崩溃，整图重建可以一并丢掉旧 colorbar，彻底避开该问题。
        """
        _configure_plot_font()
        self.contour_figure.clear()
        axis = self.contour_figure.add_subplot(111)
        self.contour_ax = axis
        _style_industrial_axis(axis)
        if prepared.get("display_rasterized"):
            filled = axis.imshow(
                prepared["raster_values"],
                origin="lower",
                extent=prepared["raster_extent"],
                interpolation="bicubic",
                cmap=self.contour_cmap_var.get(),
                vmin=prepared["vmin"],
                vmax=prepared["vmax"],
            )
        else:
            filled = axis.tripcolor(
                prepared["x"], prepared["y"], prepared["triangles"], prepared["values"],
                shading="gouraud", edgecolors="none", linewidth=0.0,
                cmap=self.contour_cmap_var.get(),
                vmin=prepared["vmin"], vmax=prepared["vmax"],
            )
        if (
            prepared["airfoil_points"] is not None
            and len(prepared["airfoil_points"]) >= 3
        ):
            axis.fill(
                prepared["airfoil_points"][:, 0],
                prepared["airfoil_points"][:, 1],
                color=UI_PANEL,
                zorder=4,
                antialiased=True,
            )
            # Cover the one-pixel raster mask staircase outside the exact wall,
            # then draw the physical wall on top.  This changes display pixels
            # only; the CFD boundary and field values remain untouched.
            axis.plot(
                prepared["airfoil_points"][:, 0],
                prepared["airfoil_points"][:, 1],
                color=UI_PANEL,
                linewidth=3.0,
                solid_joinstyle="round",
                solid_capstyle="round",
                antialiased=True,
                zorder=4.5,
            )
            axis.plot(
                prepared["airfoil_points"][:, 0],
                prepared["airfoil_points"][:, 1],
                color="#D4D4D4",
                linewidth=1.0,
                solid_joinstyle="round",
                solid_capstyle="round",
                antialiased=True,
                zorder=5,
            )
        axis.set_aspect("equal", adjustable="datalim")
        axis.set_xlabel("x")
        axis.set_ylabel("y")
        axis.set_title(
            f"{field}  "
            f"{_plot_text('云图（滚轮缩放 / 拖动平移）', 'contour (scroll zoom / drag pan)')}"
            + (
                _plot_text(" · 高质量抗锯齿", " · high-quality anti-aliasing")
                if prepared.get("display_rasterized")
                else ""
            ),
            fontweight="bold",
        )
        axis.grid(False)
        if prepared.get("unconverged"):
            axis.text(.01, .98, _plot_text("未收敛 · 仅供诊断", "UNCONVERGED · diagnostic only"),
                      transform=axis.transAxes, va="top", color=UI_ORANGE,
                      fontsize=10, fontweight="bold", zorder=8,
                      bbox={"facecolor": UI_PANEL, "edgecolor": UI_ORANGE, "pad": 3})
        self.contour_colorbar = self.contour_figure.colorbar(
            filled, ax=axis, shrink=0.82, pad=0.02
        )
        self.contour_colorbar.set_label(prepared["label"])
        self.contour_colorbar.ax.tick_params(colors="#B8B8B8", labelsize=8)
        self.contour_colorbar.ax.yaxis.label.set_color(UI_TEXT)
        self.contour_colorbar.outline.set_edgecolor("#555555")
        self.contour_figure.tight_layout(pad=1.6)
        self.contour_canvas.draw_idle()
        self.contour_data = prepared
        self.contour_field_shown = field
        if self.contour_range_mode_var.get() == "自动":
            self.contour_vmin_var.set(f"{prepared.get('auto_vmin', prepared['vmin']):.8g}")
            self.contour_vmax_var.set(f"{prepared.get('auto_vmax', prepared['vmax']):.8g}")
        if self.active_case_dir is not None:
            try:
                self.contour_figure.savefig(
                    self.active_case_dir / f"Contour_{field}.png",
                    dpi=150,
                    bbox_inches="tight",
                )
            except OSError:
                pass

    def _contour_box_aspect(self) -> float:
        """返回云图坐标轴框的像素宽高比（宽/高）。

        ``adjustable="datalim"`` 下数据范围会自动扩展以填满坐标轴框，
        因此缩放/平移必须按该比例同步设置 y 范围，否则 matlab 会在
        set_xlim/set_ylim 之间来回调整导致光标漂移。
        """
        bbox = self.contour_ax.get_position()
        figure_width, figure_height = self.contour_figure.get_size_inches()
        if bbox.height <= 0.0:
            return 1.0
        return (bbox.width * figure_width) / (bbox.height * figure_height)

    def _on_contour_scroll(self, event) -> None:
        """滚轮缩放：以鼠标所在位置为中心放大/缩小，并保持视图填满画布。"""
        if (
            self.contour_data is None
            or event.inaxes is None
            or event.xdata is None
            or event.ydata is None
        ):
            return
        base = 1.25
        scale = 1.0 / base if event.button == "up" else base
        x_limits = self.contour_ax.get_xlim()
        y_limits = self.contour_ax.get_ylim()
        width = (x_limits[1] - x_limits[0]) * scale
        # 光标在视图中的相对位置保持不动。
        relative_x = (x_limits[1] - event.xdata) / max(
            x_limits[1] - x_limits[0], 1.0e-300
        )
        relative_y = (y_limits[1] - event.ydata) / max(
            y_limits[1] - y_limits[0], 1.0e-300
        )
        # 必须先取宽高比：get_position() 会触发 apply_aspect()，
        # 若此刻 xlim 已缩放而 ylim 未同步，datalim 调整会把 xlim 改回去。
        box_aspect = self._contour_box_aspect()
        self.contour_ax.set_xlim(
            [event.xdata - width * (1.0 - relative_x), event.xdata + width * relative_x]
        )
        height = width / box_aspect
        self.contour_ax.set_ylim(
            [event.ydata - height * (1.0 - relative_y), event.ydata + height * relative_y]
        )
        self.contour_canvas.draw_idle()

    def _on_contour_press(self, event) -> None:
        """左键按下：准备拖动平移（工具栏缩放/平移模式激活时让位）。"""
        if (
            self.contour_data is None
            or event.inaxes is None
            or event.xdata is None
            or event.ydata is None
        ):
            return
        if getattr(self.contour_toolbar, "mode", "") != "":
            return
        if event.button == 1:
            self._contour_pan_start = (
                float(event.xdata),
                float(event.ydata),
                float(self.contour_ax.get_xlim()[0]),
                float(self.contour_ax.get_xlim()[1]),
                float(self.contour_ax.get_ylim()[0]),
                float(self.contour_ax.get_ylim()[1]),
            )
            try:
                self.contour_canvas.get_tk_widget().configure(cursor="fleur")
            except tk.TclError:
                pass

    def _on_contour_release(self, event) -> None:
        """松开鼠标：结束平移。"""
        del event
        self._contour_pan_start = None
        if self._contour_draw_after is not None:
            try:
                self.after_cancel(self._contour_draw_after)
            except tk.TclError:
                pass
            self._contour_draw_after = None
        self.contour_canvas.draw_idle()
        try:
            self.contour_canvas.get_tk_widget().configure(cursor="")
        except tk.TclError:
            pass

    def _on_contour_motion(self, event) -> None:
        """按住左键拖动：按鼠标位移平移视图，y 范围按画布宽高比同步。"""
        if (
            self._contour_pan_start is None
            or event.inaxes is None
            or event.xdata is None
            or event.ydata is None
        ):
            return
        start_x, start_y, xlim0, xlim1, ylim0, ylim1 = self._contour_pan_start
        delta_x = start_x - float(event.xdata)
        delta_y = start_y - float(event.ydata)
        width = xlim1 - xlim0
        # 先取宽高比（见 _on_contour_scroll：get_position 会触发 apply_aspect）。
        box_aspect = self._contour_box_aspect()
        height = width / box_aspect
        self.contour_ax.set_xlim([xlim0 + delta_x, xlim1 + delta_x])
        center_y = 0.5 * (ylim0 + ylim1) + delta_y
        self.contour_ax.set_ylim([center_y - 0.5 * height, center_y + 0.5 * height])
        # TkAgg image/triangulation redraw is the expensive part.  Limit it to
        # roughly 30 FPS while still updating the mathematical limits for every
        # mouse event, so the cursor remains attached to the view.
        if self._contour_draw_after is None:
            self._contour_draw_after = self.after(33, self._flush_contour_draw)

    def _flush_contour_draw(self) -> None:
        self._contour_draw_after = None
        self.contour_canvas.draw_idle()

    def _toggle_contour_range_controls(self) -> None:
        custom = self._choice_code(
            self.contour_range_mode_var.get(), CONTOUR_RANGE_MODES, CONTOUR_RANGE_MODES_EN
        ) == "CUSTOM"
        state = "normal" if custom else "disabled"
        self.contour_vmin_entry.configure(state=state)
        self.contour_vmax_entry.configure(state=state)
        self.contour_range_apply_button.configure(state=state)
        contour_data = getattr(self, "contour_data", None)
        if not custom and contour_data is not None:
            self.contour_vmin_var.set(
                f"{contour_data.get('auto_vmin', contour_data['vmin']):.8g}"
            )
            self.contour_vmax_var.set(
                f"{contour_data.get('auto_vmax', contour_data['vmax']):.8g}"
            )

    def _on_contour_range_mode_changed(self, event=None) -> None:
        del event
        self._toggle_contour_range_controls()
        if self.contour_data is not None and self.contour_field_shown:
            self._apply_contour_range()

    def _selected_contour_limits(self) -> tuple[float, float] | None:
        if self._choice_code(
            self.contour_range_mode_var.get(), CONTOUR_RANGE_MODES, CONTOUR_RANGE_MODES_EN
        ) != "CUSTOM":
            return None
        try:
            vmin = float(self.contour_vmin_var.get())
            vmax = float(self.contour_vmax_var.get())
        except ValueError as exc:
            raise ValueError("自定义最小值和最大值必须是有效数字。") from exc
        if not math.isfinite(vmin) or not math.isfinite(vmax) or vmin >= vmax:
            raise ValueError("自定义色阶要求有限数值，且最小值必须小于最大值。")
        return vmin, vmax

    def _apply_contour_range(self) -> None:
        if self.contour_data is None or not self.contour_field_shown:
            return
        try:
            limits = self._selected_contour_limits()
        except ValueError as exc:
            messagebox.showerror("色阶范围无效", str(exc), parent=self)
            return
        updated = dict(self.contour_data)
        if limits is None:
            updated["vmin"] = updated.get("auto_vmin", updated["vmin"])
            updated["vmax"] = updated.get("auto_vmax", updated["vmax"])
        else:
            updated["vmin"], updated["vmax"] = limits
        self._draw_contour(self.contour_field_shown, updated)

    def _finish_contour(self, field: str, prepared: dict) -> None:
        self.contour_button.configure(state="normal")
        self._draw_contour(field, prepared)
        self._append_log(
            f"云图已显示并保存: Contour_{field}.png（可用下方工具栏缩放/平移）",
            "step",
        )
        if not self.running:
            unconverged = prepared.get("unconverged", False)
            self.status_var.set(f"云图完成: {field}" + (" · 未收敛" if unconverged else ""))
            self.status_badge.configure(background=UI_ORANGE if unconverged else UI_BLUE)

    def _finish_contour_error(self, detail: str) -> None:
        self.contour_button.configure(state="normal")
        self._append_log(f"云图生成失败: {detail}", "error")
        if not self.running:
            self.status_var.set("云图生成失败")
            self.status_badge.configure(background=UI_DANGER)

    # ---------------- 报告 / 摘要 / 文件 ----------------

    def _append_log(self, message: str, tag: str | None = None) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n", tag or ())
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_results(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        for tree in (self.summary_tree, self.files_tree):
            tree.delete(*tree.get_children())
        for canvas in self.report_canvases.values():
            canvas.delete("all")
        self.report_sources.clear()
        self.report_photos.clear()
        self.report_placeholder_message = "计算完成后将在这里显示气动报告"
        self.contour_figure.clear()
        self.contour_ax = self.contour_figure.add_subplot(111)
        _style_industrial_axis(self.contour_ax)
        self.contour_ax.set_title(
            _plot_text(
                "计算完成后将自动显示 Mach 云图",
                "Mach contour appears after the run",
            ),
            fontsize=11,
        )
        self.contour_colorbar = None
        self.contour_data = None
        self.contour_field_shown = ""
        self.contour_figure.tight_layout(pad=1.6)
        self.contour_canvas.draw_idle()
        self.file_paths.clear()
        self.live_iterations.clear()
        self.live_residuals.clear()
        self.live_cl.clear()
        self.live_cd.clear()
        self._draw_live_history()

    def _draw_live_history(self) -> None:
        _configure_plot_font()
        self.live_residual_line.set_data(self.live_iterations, self.live_residuals)
        self.live_cl_line.set_data(self.live_iterations, self.live_cl)
        self.live_cd_line.set_data(self.live_iterations, self.live_cd)
        for axis in (self.live_residual_ax, self.live_coefficient_ax):
            axis.relim()
            axis.autoscale_view()
        self.live_canvas.draw_idle()

    def _load_report(self, report_path: Path) -> None:
        report_directory = report_path.parent
        self.report_sources.clear()
        self.report_photos.clear()
        for panel_key, _, filename in post_analyzer.REPORT_PANELS:
            panel_path = report_directory / filename
            if not panel_path.is_file():
                continue
            with Image.open(panel_path) as image:
                self.report_sources[panel_key] = image.convert("RGB").copy()
        self.report_placeholder_message = "计算完成后将在这里显示气动报告"
        for panel_key in self.report_canvases:
            self._render_report_image(panel_key)
        if self.report_notebook.tabs():
            self.report_notebook.select(self.report_notebook.tabs()[0])

    def _set_report_placeholder(self, message: str) -> None:
        self.report_sources.clear()
        self.report_photos.clear()
        self.report_placeholder_message = message
        for panel_key in self.report_canvases:
            self._render_report_image(panel_key)

    def _render_report_image(self, panel_key: str) -> None:
        canvas = self.report_canvases[panel_key]
        source = self.report_sources.get(panel_key)
        if source is None:
            canvas.delete("all")
            canvas.create_text(
                max(canvas.winfo_width() // 2, 100),
                max(canvas.winfo_height() // 2, 100),
                text=self.report_placeholder_message,
                fill="#687782",
                font=(UI_FONT_FAMILY, 12),
            )
            return
        width = max(canvas.winfo_width() - 24, 200)
        height = max(canvas.winfo_height() - 24, 200)
        image = source.copy()
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        self.report_photos[panel_key] = photo
        canvas.delete("all")
        canvas.create_image(
            canvas.winfo_width() // 2,
            canvas.winfo_height() // 2,
            image=photo,
            anchor="center",
        )

    def _fill_summary(self, summary: list[tuple[str, str]]) -> None:
        self.summary_tree.delete(*self.summary_tree.get_children())
        for metric, value in summary:
            self.summary_tree.insert("", "end", values=(metric, value))

    def _refresh_files(self, case_dir: Path) -> None:
        self.files_tree.delete(*self.files_tree.get_children())
        self.file_paths.clear()
        for index, path in enumerate(
            sorted(case_dir.rglob("*"), key=lambda item: str(item).lower())
        ):
            if not path.is_file():
                continue
            item_id = f"file_{index}"
            display_name = str(path.relative_to(case_dir))
            size = self._format_size(path.stat().st_size)
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self.files_tree.insert(
                "", "end", iid=item_id, values=(display_name, size, modified)
            )
            self.file_paths[item_id] = path

    @staticmethod
    def _format_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024.0 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024.0
        return f"{size} B"

    def _open_selected_file(self, _: tk.Event[tk.Misc]) -> None:
        selected = self.files_tree.selection()
        if selected and selected[0] in self.file_paths:
            os.startfile(self.file_paths[selected[0]])

    def _open_result_folder(self) -> None:
        target = self.active_case_dir or Path(self.output_root_var.get())
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(target)

    def destroy(self) -> None:
        """撤销排队回调后关闭，避免回调访问已销毁的 Tk 命令。"""
        try:
            # 直接调用 Tcl 的 after cancel，只撤销定时器；不提前删除 Python
            # 注册命令，后续 widget.destroy 可按正常顺序回收这些命令。
            for callback_id in self.tk.call("after", "info"):
                self.tk.call("after", "cancel", callback_id)
        except (AttributeError, tk.TclError):
            pass
        self._event_poll_after_id = None
        self._initial_preview_after_id = None
        super().destroy()

    def _report_tk_exception(
        self, exc_type: type[BaseException], exc: BaseException, tb: object
    ) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        data_root().mkdir(parents=True, exist_ok=True)
        (data_root() / "gui_error.log").write_text(detail, encoding="utf-8")
        messagebox.showerror(
            "界面错误", f"{exc}\n详细信息已写入 gui_error.log", parent=self
        )

    def _on_close(self) -> None:
        if self.running or self.mesh_preview_running or self.optimizer_panel.is_running:
            close = messagebox.askyesno(
                "计算仍在运行",
                "关闭窗口会终止当前正问题、网格预览或伴随优化，确定继续吗？",
                parent=self,
            )
            if not close:
                return
            self.closing_requested = True
            self.stop_event.set()
            try:
                self.process_control.terminate()
            except OSError:
                pass
            self.mesh_preview_stop_event.set()
            self.optimizer_panel.shutdown()
            self.status_var.set("正在停止计算...")
            self._wait_for_worker_before_close()
            return
        self.destroy()

    def _wait_for_worker_before_close(self) -> None:
        """等待计算线程回收 SU2 子进程，避免窗口关闭后遗留孤立进程。"""
        calculation_alive = self.worker_thread and self.worker_thread.is_alive()
        preview_alive = self.mesh_preview_thread and self.mesh_preview_thread.is_alive()
        if calculation_alive or preview_alive:
            self.after(100, self._wait_for_worker_before_close)
            return
        self.destroy()


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    workflow_smoke_test = "--workflow-smoke-test" in sys.argv
    app = AutoFoilStudio(smoke_test=smoke_test or workflow_smoke_test)
    if workflow_smoke_test:
        app.withdraw()
        app.update_idletasks()
        app.iterations_var.set("2")
        app.surface_point_count_var.set("81")
        app.case_name_var.set("gui_workflow_smoke")
        smoke_output_root = os.environ.get(
            "SU2AUTOFOIL_SMOKE_OUTPUT",
            str(data_root() / "gui_validation"),
        )
        app.output_root_var.set(smoke_output_root)
        settings = app._collect_settings()
        processed = app._process_from_settings(settings)
        case_dir = app._create_case_directory(settings)
        app._calculation_worker(settings, processed, case_dir)
        events = []
        while not app.events.empty():
            events.append(app.events.get_nowait())
        done_events = [payload for kind, payload in events if kind == "done"]
        error_events = [payload for kind, payload in events if kind == "error"]
        history_points = [payload for kind, payload in events if kind == "history_point"]
        if error_events:
            app.destroy()
            raise RuntimeError(str(error_events[-1]))
        if not done_events:
            app.destroy()
            raise RuntimeError("GUI workflow smoke test 未收到完成事件。")
        if len(history_points) < 2:
            app.destroy()
            raise RuntimeError("GUI workflow smoke test 未收到实时收敛数据。")
        for iteration, residual, cl_value, cd_value in history_points:
            app.live_iterations.append(int(iteration))
            app.live_residuals.append(float(residual))
            app.live_cl.append(float(cl_value))
            app.live_cd.append(float(cd_value))
        app._draw_live_history()
        live_plot_path = case_dir / "Live_Convergence.png"
        app.live_figure.savefig(live_plot_path, dpi=120, bbox_inches="tight")
        _, report_path, _ = done_events[-1]
        app.destroy()
        print(
            f"GUI workflow smoke test: PASS, history_points={len(history_points)}, "
            f"report={report_path}, live_plot={live_plot_path}"
        )
        return 0
    if smoke_test:
        app.withdraw()
        app.update_idletasks()
        app._preview_airfoil(show_error=False)
        if app.processed_airfoil is None:
            raise RuntimeError("GUI smoke test 未能生成翼型预览。")
        print(
            f"GUI smoke test: PASS, upper={len(app.processed_airfoil.upper)}, "
            f"lower={len(app.processed_airfoil.lower)}"
        )
        app.destroy()
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as startup_error:
        error_detail = traceback.format_exc()
        data_root().mkdir(parents=True, exist_ok=True)
        (data_root() / "gui_error.log").write_text(error_detail, encoding="utf-8")
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                0,
                f"软件启动失败：{startup_error}\n\n详细信息已写入 gui_error.log",
                "SU2 AutoFoil Studio",
                0x10,
            )
        raise
