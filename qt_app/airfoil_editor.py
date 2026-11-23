from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from matplotlib import rcParams
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core_modules.airfoil_processor import generate_naca0012_surfaces, process_airfoil
from parametric_adjoint.deformation import write_selig
from parametric_adjoint.legacy_deformation import (
    LOWER_BOUNDS,
    UPPER_BOUNDS,
    compact_dbce_refit,
    fit_legacy_bce,
    legacy_airfoil,
    legacy_functions,
    validate_airfoil,
)

rcParams["font.sans-serif"] = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "SimHei",
    "DejaVu Sans",
]
rcParams["axes.unicode_minus"] = False


@lru_cache(maxsize=1)
def _default_naca0012_fit() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """Return the exact analytic NACA0012 target and its legacy-BCE control fit."""
    x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, 181)))
    upper_source, lower_source = generate_naca0012_surfaces(401)
    upper_source = upper_source[::-1]
    lower_source = lower_source[::-1]
    upper = np.interp(x, upper_source[:, 0], upper_source[:, 1])
    lower = np.interp(x, lower_source[:, 0], lower_source[:, 1])
    parameters, rmse = fit_legacy_bce(x, upper, lower)
    return x, upper, lower, parameters, rmse


class BCECanvas(FigureCanvasQTAgg):
    status = Signal(str)
    geometryChanged = Signal(object, object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        self.figure = Figure(figsize=(11.0, 7.0), dpi=100, facecolor="#1E1E1E")
        super().__init__(self.figure)
        self.setParent(parent)
        grid = self.figure.add_gridspec(2, 3, height_ratios=(1.65, 1.0), hspace=0.36, wspace=0.25)
        self.geometry_axis = self.figure.add_subplot(grid[0, :])
        self.control_axes = [self.figure.add_subplot(grid[1, index]) for index in range(3)]
        default_x, default_upper, default_lower, default_parameters, default_rmse = (
            _default_naca0012_fit()
        )
        self.x = default_x.copy()
        self.parameters = default_parameters.copy()
        self.baseline_parameters = default_parameters.copy()
        self.target: tuple[np.ndarray, np.ndarray, np.ndarray] | None = (
            self.x.copy(), default_upper.copy(), default_lower.copy()
        )
        self.target_name = "NACA0012"
        self.initial_fit_rmse = float(default_rmse)
        self.history: list[np.ndarray] = []
        self.sensitivity = 0.8
        self.constraint_mode = "free"
        self.active: tuple[int, int] | None = None
        self.selected: tuple[int, int] | None = None
        self.drag_origin_y = 0.0
        self.drag_origin_value = 0.0
        self.drag_snapshot: np.ndarray | None = None
        self.geometry_ylim = 0.18
        _, upper, lower = self.current_geometry()
        camber = 0.5 * (upper + lower)
        self.thickness_reference = 0.5 * (upper - lower)
        self.camber_reference = camber.copy()
        self.control_ylims: dict[str, tuple[float, float]] = {}
        self.language = "en"
        self.mpl_connect("button_press_event", self._press)
        self.mpl_connect("motion_notify_event", self._motion)
        self.mpl_connect("button_release_event", self._release)
        self._set_fixed_view_limits()
        self._redraw()

    def current_geometry(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        upper, lower, camber = legacy_airfoil(self.parameters, self.x)
        if self.target is not None:
            baseline_upper, baseline_lower, _ = legacy_airfoil(
                self.baseline_parameters, self.x
            )
            # The imported/analytic airfoil is the exact reference geometry.
            # Legacy BCE contributes only its edit relative to the fitted
            # baseline, so opening or resetting never changes NACA0012 (or a
            # user DAT) merely because the old representation is approximate.
            upper = self.target[1] + upper - baseline_upper
            lower = self.target[2] + lower - baseline_lower
            camber = 0.5 * (upper + lower)
        half_thickness = 0.5 * (upper - lower)
        if self.constraint_mode == "lock_thickness":
            half_thickness = self.thickness_reference.copy()
        elif self.constraint_mode == "lock_camber":
            camber = self.camber_reference.copy()
        return self.x.copy(), camber + half_thickness, camber - half_thickness

    def set_constraint_mode(self, mode: str) -> None:
        if mode not in {"free", "lock_thickness", "lock_camber"}:
            raise ValueError(f"Unknown BCE constraint mode: {mode}")
        _, upper, lower = self.current_geometry()
        self.thickness_reference = 0.5 * (upper - lower)
        self.camber_reference = 0.5 * (upper + lower)
        self.constraint_mode = mode
        self._redraw()
        labels = {
            "free": ("自由变形", "Free deformation"),
            "lock_thickness": ("锁定厚度", "Lock thickness"),
            "lock_camber": ("锁定弯度", "Lock camber"),
        }
        self.status.emit(labels[mode][0 if self.language == "zh" else 1])

    def load_airfoil(self, path: str) -> None:
        processed = process_airfoil(path, surface_point_count=181)
        upper = processed.upper[::-1]
        lower = processed.lower[::-1]
        x_min = max(float(upper[:, 0].min()), float(lower[:, 0].min()))
        x_max = min(float(upper[:, 0].max()), float(lower[:, 0].max()))
        x = x_min + (x_max - x_min) * self.x
        upper_y = np.interp(x, upper[:, 0], upper[:, 1])
        lower_y = np.interp(x, lower[:, 0], lower[:, 1])
        chord = max(x_max - x_min, 1.0e-12)
        normalized_x = (x - x_min) / chord
        upper_y = upper_y / chord
        lower_y = lower_y / chord
        fitted, rmse = fit_legacy_bce(normalized_x, upper_y, lower_y)
        self.x = normalized_x
        self.parameters = fitted
        self.baseline_parameters = fitted.copy()
        self.target = (normalized_x.copy(), upper_y.copy(), lower_y.copy())
        self.target_name = Path(path).stem
        _, base_upper, base_lower = self.current_geometry()
        base_camber = 0.5 * (base_upper + base_lower)
        self.thickness_reference = 0.5 * (base_upper - base_lower)
        self.camber_reference = base_camber.copy()
        self.history.clear()
        self.selected = None
        self._set_fixed_view_limits()
        self._redraw()
        self.status.emit(f"Imported and fitted: {Path(path).name} | RMSE={rmse:.3e}")

    def reset(self) -> None:
        self.history.append(self.parameters.copy())
        self.parameters = self.baseline_parameters.copy()
        _, base_upper, base_lower = self.current_geometry()
        base_camber = 0.5 * (base_upper + base_lower)
        self.thickness_reference = 0.5 * (base_upper - base_lower)
        self.camber_reference = base_camber.copy()
        self.selected = None
        self._set_fixed_view_limits()
        self._redraw()

    def undo(self) -> None:
        if self.history:
            self.parameters = self.history.pop()
            self._redraw()
            self.status.emit("Undo complete")

    def export(self, path: Path, name: str = "BCE_Qt_airfoil") -> None:
        x, upper, lower = self.current_geometry()
        write_selig(path, name, x, upper, lower)
        self.status.emit(f"Exported: {path}")

    def dbce_handoff(self, path: Path) -> tuple[float, int]:
        if self.target is None:
            baseline_upper, baseline_lower, _ = legacy_airfoil(
                self.baseline_parameters, self.x
            )
        else:
            baseline_upper, baseline_lower = self.target[1], self.target[2]
        _, target_upper, target_lower = self.current_geometry()
        upper, lower, rmse, variables = compact_dbce_refit(
            self.x, baseline_upper, baseline_lower, target_upper, target_lower
        )
        write_selig(path, "BCE_Qt_D_BCE_handoff", self.x, upper, lower)
        self.status.emit(f"D-BCE handoff: RMSE={rmse:.3e}, variables={variables}")
        return rmse, variables

    @staticmethod
    def _stable_limits(
        values: np.ndarray, minimum_span: float, lower_floor: float | None = None
    ) -> tuple[float, float]:
        low, high = float(np.min(values)), float(np.max(values))
        span = max(minimum_span, (high - low) * 1.8)
        center = 0.5 * (low + high)
        result = (center - 0.5 * span, center + 0.5 * span)
        if lower_floor is not None and result[0] < lower_floor:
            result = (lower_floor, lower_floor + span)
        return result

    def _set_fixed_view_limits(self) -> None:
        _, upper, lower = self.current_geometry()
        target_values = np.r_[upper, lower]
        if self.target is not None:
            target_values = np.r_[target_values, self.target[1], self.target[2]]
        ordinate = float(np.max(np.abs(target_values)))
        self.geometry_ylim = float(
            np.ceil(np.clip(1.45 * ordinate + 0.008, 0.095, 0.30) / 0.025) * 0.025
        )
        height, alpha, beta, controls = legacy_functions(self.parameters)
        self.control_ylims = {
            "h": self._stable_limits(np.r_[height[1], controls["h"][1]], 0.28),
            "a": self._stable_limits(np.r_[alpha[1], controls["a"][1]], 24.0),
            "b": self._stable_limits(np.r_[beta[1], controls["b"][1]], 35.0, 0.0),
        }

    def reset_view(self) -> None:
        self._set_fixed_view_limits()
        self._redraw()

    def _ensure_geometry_visible(self, upper: np.ndarray, lower: np.ndarray) -> None:
        ordinate = float(np.max(np.abs(np.r_[upper, lower])))
        if ordinate <= 0.88 * self.geometry_ylim:
            return
        self.geometry_ylim = min(
            0.50, float(np.ceil((1.28 * ordinate + 0.008) / 0.025) * 0.025)
        )

    def _style_axis(self, axis, title: str) -> None:
        axis.set_facecolor("#202022")
        axis.set_title(title, color="#ECECEC", fontsize=10, fontweight="bold", pad=6)
        axis.tick_params(colors="#BBBBBB", labelsize=8)
        axis.grid(True, color="#393939", linewidth=0.5, alpha=0.65)
        for spine in axis.spines.values():
            spine.set_color("#505050")
        axis.xaxis.label.set_color("#CCCCCC")
        axis.yaxis.label.set_color("#CCCCCC")

    def _redraw(self) -> None:
        for axis in [self.geometry_axis, *self.control_axes]:
            axis.clear()
        _, upper, lower = self.current_geometry()
        camber = 0.5 * (upper + lower)
        valid, reason = validate_airfoil(upper, lower)
        if self.target is not None:
            tx, tu, tl = self.target
            target_label = (
                f"目标 {self.target_name}"
                if self.language == "zh"
                else f"Target {self.target_name}"
            )
            self.geometry_axis.plot(tx, tu, "--", color="#8B8B8B", lw=1.0, label=target_label)
            self.geometry_axis.plot(tx, tl, "--", color="#8B8B8B", lw=1.0)
        self.geometry_axis.plot(self.x, upper, color="#4DB8FF", lw=1.7, label="BCE 上表面" if self.language == "zh" else "BCE upper")
        self.geometry_axis.plot(self.x, lower, color="#168BD2", lw=1.7, label="BCE 下表面" if self.language == "zh" else "BCE lower")
        self.geometry_axis.plot(self.x, camber, "--", color="#D9822B", lw=1.0, label="弯度线" if self.language == "zh" else "Camber")
        self.geometry_axis.fill_between(self.x, lower, upper, color="#1672A3", alpha=0.12)
        self.geometry_axis.set_xlim(-0.02, 1.02)
        self.geometry_axis.set_ylim(-self.geometry_ylim, self.geometry_ylim)
        self.geometry_axis.set_aspect("equal", adjustable="box")
        self.geometry_axis.set_xlabel("x/c")
        self.geometry_axis.set_ylabel("y/c")
        state = ("有效" if valid else reason) if self.language == "zh" else ("valid" if valid else reason)
        self._style_axis(self.geometry_axis, f"{'当前翼型' if self.language == 'zh' else 'Current airfoil'}  •  {state}")
        legend = self.geometry_axis.legend(
            loc="center left", bbox_to_anchor=(1.005, 0.5), frameon=True, fontsize=8
        )
        legend.get_frame().set_facecolor("#252526")
        legend.get_frame().set_edgecolor("#505050")
        for text in legend.get_texts():
            text.set_color("#DDDDDD")

        _, _, _, controls = legacy_functions(self.parameters)
        curves = legacy_functions(self.parameters)[:3]
        titles = (("厚度 h(x)", "弯度 α(x)", "饱满度 β(x)") if self.language == "zh"
                  else ("Thickness h(x)", "Camber α(x)", "Fullness β(x)"))
        keys = ("h", "a", "b")
        colors = ("#4DB8FF", "#D9822B", "#A6D854")
        for index, (axis, curve, title, key, color) in enumerate(
            zip(self.control_axes, curves, titles, keys, colors)
        ):
            axis.plot(curve[0], curve[1], color=color, lw=1.4)
            cx, cy = controls[key]
            if index == 0:
                cx, cy = cx[:-1], cy[:-1]
            axis.plot(cx, cy, color="#D9534F", lw=0.8, alpha=0.45)
            axis.scatter(cx, cy, s=30, color="#D9534F", edgecolors="#E8E8E8", linewidths=0.5, zorder=5)
            if self.selected is not None and self.selected[0] == index:
                point = self.selected[1]
                axis.scatter(
                    [cx[point]], [cy[point]], s=72, color="#FFB000",
                    edgecolors="white", linewidths=1.0, zorder=7,
                )
            axis.set_xlim(-0.03, 1.03)
            axis.set_ylim(*self.control_ylims[key])
            axis.set_xlabel("x/c")
            self._style_axis(axis, title)
        self.figure.subplots_adjust(left=0.07, right=0.84, top=0.94, bottom=0.08)
        self.draw_idle()
        self.geometryChanged.emit(self.x.copy(), upper.copy(), lower.copy())

    def set_language(self, language: str) -> None:
        self.language = "zh" if language == "zh" else "en"
        self._redraw()

    def _nearest_control(self, event) -> tuple[int, int] | None:
        if event.inaxes not in self.control_axes or event.xdata is None or event.ydata is None:
            return None
        axis_index = self.control_axes.index(event.inaxes)
        _, _, _, controls = legacy_functions(self.parameters)
        key = ("h", "a", "b")[axis_index]
        x, y = controls[key]
        if axis_index == 0:
            x, y = x[:-1], y[:-1]
        x_range = max(float(np.ptp(event.inaxes.get_xlim())), 1.0e-9)
        y_range = max(float(np.ptp(event.inaxes.get_ylim())), 1.0e-9)
        distance = np.hypot((x - event.xdata) / x_range, (y - event.ydata) / y_range)
        point = int(np.argmin(distance))
        return (axis_index, point) if float(distance[point]) < 0.055 else None

    def _parameter_index(self, axis_index: int, point: int) -> int:
        return point if axis_index == 0 else 7 + point if axis_index == 1 else 14 + point

    def _press(self, event) -> None:
        if getattr(getattr(self, "toolbar", None), "mode", ""):
            return
        selected = self._nearest_control(event)
        if selected is None:
            return
        if self.constraint_mode == "lock_thickness" and selected[0] == 0:
            self.status.emit("厚度已锁定" if self.language == "zh" else "Thickness is locked")
            return
        if self.constraint_mode == "lock_camber" and selected[0] == 1:
            self.status.emit("弯度已锁定" if self.language == "zh" else "Camber is locked")
            return
        self.active = selected
        self.selected = selected
        parameter_index = self._parameter_index(*selected)
        self.drag_origin_y = float(event.ydata)
        self.drag_origin_value = float(self.parameters[parameter_index])
        self.drag_snapshot = self.parameters.copy()

    def _motion(self, event) -> None:
        if self.active is None or event.inaxes is not self.control_axes[self.active[0]] or event.ydata is None:
            return
        parameter_index = self._parameter_index(*self.active)
        value = self.drag_origin_value + (float(event.ydata) - self.drag_origin_y) * self.sensitivity
        previous = float(self.parameters[parameter_index])
        self.parameters[parameter_index] = np.clip(
            value, LOWER_BOUNDS[parameter_index], UPPER_BOUNDS[parameter_index]
        )
        _, upper, lower = self.current_geometry()
        valid, reason = validate_airfoil(upper, lower)
        if not valid:
            self.parameters[parameter_index] = previous
            self.status.emit(
                f"已阻止无效变形：{reason}"
                if self.language == "zh"
                else f"Invalid deformation blocked: {reason}"
            )
            return
        self._ensure_geometry_visible(upper, lower)
        self._redraw()

    def _release(self, _event) -> None:
        if self.active is not None and self.drag_snapshot is not None:
            if not np.array_equal(self.drag_snapshot, self.parameters):
                self.history.append(self.drag_snapshot)
                if len(self.history) > 40:
                    self.history.pop(0)
            self.status.emit(
                "旧 BCE 控制点已更新，可直接使用或转入 D-BCE。"
                if self.language == "zh"
                else "Legacy BCE updated; use directly or hand off to D-BCE."
            )
        self.active = None
        self.drag_snapshot = None


class AirfoilEditor(QWidget):
    status = Signal(str)
    geometryChanged = Signal(object, object, object)
    airfoilPathChanged = Signal(str)

    def __init__(self, workdir_provider, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workdir_provider = workdir_provider
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        control_rows = QVBoxLayout()
        control_rows.setSpacing(3)
        settings = QHBoxLayout()
        settings.setSpacing(3)
        self.title = QLabel("Legacy BCE manual design → compact D-BCE")
        self.title.setProperty("heading", True)
        settings.addWidget(self.title)
        settings.addStretch(1)
        self.constraint_label = QLabel("Constraint mode")
        settings.addWidget(self.constraint_label)
        self.constraint_mode = QComboBox()
        self.constraint_mode.addItem("Free deformation", "free")
        self.constraint_mode.addItem("Lock thickness", "lock_thickness")
        self.constraint_mode.addItem("Lock camber", "lock_camber")
        settings.addWidget(self.constraint_mode)
        self.sensitivity = QComboBox()
        self.sensitivity.addItem("Fine 0.35×", 0.35)
        self.sensitivity.addItem("Standard 0.8×", 0.8)
        self.sensitivity.addItem("Fast 1.5×", 1.5)
        self.sensitivity.setCurrentIndex(1)
        self.sensitivity_label = QLabel("Drag sensitivity")
        settings.addWidget(self.sensitivity_label)
        settings.addWidget(self.sensitivity)
        control_rows.addLayout(settings)

        actions = QHBoxLayout()
        actions.setSpacing(3)
        self.action_buttons: dict[str, QPushButton] = {}
        for key, text, callback in (
            ("import", "Import DAT", self._import),
            ("undo", "Undo last drag", self._undo),
            ("reset", "Restore initial fit", self._reset),
            ("view", "Reset view", self._reset_view),
            ("export", "Export manual DAT", self._export),
            ("direct", "Use edited shape directly", self._use_direct),
            ("handoff", "Refit with D-BCE & continue", self._handoff),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            if key == "handoff":
                button.setProperty("accent", True)
            self.action_buttons[key] = button
            actions.addWidget(button)
        actions.addStretch(1)
        control_rows.addLayout(actions)
        layout.addLayout(control_rows)
        self.canvas = BCECanvas(self)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        current_icon_size = self.toolbar.iconSize()
        self.toolbar.setIconSize(
            QSize(
                max(12, round(current_icon_size.width() * 0.8)),
                max(12, round(current_icon_size.height() * 0.8)),
            )
        )
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.toolbar)
        self.canvas.status.connect(self.status)
        self.canvas.geometryChanged.connect(self.geometryChanged)
        self.sensitivity.currentIndexChanged.connect(self._gain_changed)
        self.constraint_mode.currentIndexChanged.connect(self._constraint_changed)

    def ensure_exported(self) -> str:
        directory = Path(self.workdir_provider()) / "airfoil_designs"
        path = directory / "qt_current_airfoil.dat"
        self.canvas.export(path, "Qt_current_airfoil")
        self.airfoilPathChanged.emit(str(path))
        return str(path)

    def set_language(self, language: str) -> None:
        language = "zh" if language == "zh" else "en"
        self.canvas.set_language(language)
        current_constraint = self.constraint_mode.currentData()
        current_gain = self.sensitivity.currentData()
        self.title.setText(
            "旧 BCE 三贝塞尔手调 → 紧支撑 D-BCE"
            if language == "zh" else "Legacy BCE manual design → compact D-BCE"
        )
        self.constraint_label.setText("约束模式" if language == "zh" else "Constraint mode")
        constraint_text = {
            "free": ("自由变形", "Free deformation"),
            "lock_thickness": ("锁定厚度", "Lock thickness"),
            "lock_camber": ("锁定弯度", "Lock camber"),
        }
        self.constraint_mode.blockSignals(True)
        for index in range(self.constraint_mode.count()):
            data = self.constraint_mode.itemData(index)
            self.constraint_mode.setItemText(
                index, constraint_text[data][0 if language == "zh" else 1]
            )
        self.constraint_mode.setCurrentIndex(self.constraint_mode.findData(current_constraint))
        self.constraint_mode.blockSignals(False)
        gain_text = {
            0.35: ("精细 0.35×", "Fine 0.35×"),
            0.8: ("标准 0.8×", "Standard 0.8×"),
            1.5: ("快速 1.5×", "Fast 1.5×"),
        }
        self.sensitivity_label.setText("拖动灵敏度" if language == "zh" else "Drag sensitivity")
        self.sensitivity.blockSignals(True)
        for index in range(self.sensitivity.count()):
            gain = float(self.sensitivity.itemData(index))
            self.sensitivity.setItemText(index, gain_text[gain][0 if language == "zh" else 1])
        self.sensitivity.setCurrentIndex(self.sensitivity.findData(current_gain))
        self.sensitivity.blockSignals(False)
        button_text = {
            "import": ("导入并拟合 DAT", "Import & fit DAT"),
            "undo": ("撤销上次拖动", "Undo last drag"),
            "reset": ("恢复初始拟合", "Restore initial fit"),
            "view": ("重置预览范围", "Reset view"),
            "export": ("导出手调 DAT", "Export manual DAT"),
            "direct": ("直接使用手调翼型", "Use edited shape directly"),
            "handoff": ("D-BCE 重拟合并继续", "Refit with D-BCE & continue"),
        }
        for key, button in self.action_buttons.items():
            button.setText(button_text[key][0 if language == "zh" else 1])

    def _gain_changed(self) -> None:
        self.canvas.sensitivity = float(self.sensitivity.currentData())

    def _constraint_changed(self) -> None:
        self.canvas.set_constraint_mode(str(self.constraint_mode.currentData()))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import airfoil", "", "Airfoil DAT (*.dat);;All files (*)")
        if not path:
            return
        try:
            self.canvas.load_airfoil(path)
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    def _undo(self) -> None:
        self.canvas.undo()

    def _reset(self) -> None:
        self.canvas.reset()

    def _reset_view(self) -> None:
        self.canvas.reset_view()

    def _use_direct(self) -> None:
        path = self.ensure_exported()
        self.status.emit(
            f"手调翼型已直接送入后续流程：{path}"
            if self.canvas.language == "zh"
            else f"Edited airfoil sent directly to the downstream workflow: {path}"
        )

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export airfoil", "BCE_Qt_airfoil.dat", "Airfoil DAT (*.dat)")
        if path:
            self.canvas.export(Path(path))
            self.airfoilPathChanged.emit(path)

    def _handoff(self) -> None:
        directory = Path(self.workdir_provider()) / "airfoil_designs"
        path = directory / "qt_dbce_handoff.dat"
        try:
            rmse, variables = self.canvas.dbce_handoff(path)
        except Exception as exc:
            QMessageBox.critical(self, "D-BCE handoff failed", str(exc))
            return
        self.airfoilPathChanged.emit(str(path))
        QMessageBox.information(self, "D-BCE handoff", f"Saved: {path}\nRMSE: {rmse:.3e}\nVariables: {variables}")
