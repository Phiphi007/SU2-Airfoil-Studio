from __future__ import annotations

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

from core_modules.airfoil_processor import process_airfoil
from parametric_adjoint.deformation import write_selig
from parametric_adjoint.legacy_deformation import (
    INITIAL_PARAMETERS,
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
        self.parameters = INITIAL_PARAMETERS.copy()
        self.baseline_parameters = self.parameters.copy()
        self.target: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self.x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, 181)))
        self.history: list[np.ndarray] = []
        self.sensitivity = 0.8
        self.active: tuple[int, int] | None = None
        self.drag_origin_y = 0.0
        self.drag_origin_value = 0.0
        self.drag_snapshot: np.ndarray | None = None
        self.geometry_ylim = 0.18
        self.language = "en"
        self.mpl_connect("button_press_event", self._press)
        self.mpl_connect("motion_notify_event", self._motion)
        self.mpl_connect("button_release_event", self._release)
        self._redraw()

    def current_geometry(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        upper, lower, _ = legacy_airfoil(self.parameters, self.x)
        return self.x.copy(), upper, lower

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
        self.history.clear()
        self._redraw()
        self.status.emit(f"Imported and fitted: {Path(path).name} | RMSE={rmse:.3e}")

    def reset(self) -> None:
        self.history.append(self.parameters.copy())
        self.parameters = self.baseline_parameters.copy()
        self.geometry_ylim = 0.18
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
        baseline_upper, baseline_lower, _ = legacy_airfoil(self.baseline_parameters, self.x)
        target_upper, target_lower, _ = legacy_airfoil(self.parameters, self.x)
        upper, lower, rmse, variables = compact_dbce_refit(
            self.x, baseline_upper, baseline_lower, target_upper, target_lower
        )
        write_selig(path, "BCE_Qt_D_BCE_handoff", self.x, upper, lower)
        self.status.emit(f"D-BCE handoff: RMSE={rmse:.3e}, variables={variables}")
        return rmse, variables

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
        upper, lower, camber = legacy_airfoil(self.parameters, self.x)
        valid, reason = validate_airfoil(upper, lower)
        if self.target is not None:
            tx, tu, tl = self.target
            self.geometry_axis.plot(tx, tu, "--", color="#8B8B8B", lw=1.0, label="导入目标" if self.language == "zh" else "Imported target")
            self.geometry_axis.plot(tx, tl, "--", color="#8B8B8B", lw=1.0)
        self.geometry_axis.plot(self.x, upper, color="#4DB8FF", lw=1.7, label="BCE 上表面" if self.language == "zh" else "BCE upper")
        self.geometry_axis.plot(self.x, lower, color="#168BD2", lw=1.7, label="BCE 下表面" if self.language == "zh" else "BCE lower")
        self.geometry_axis.plot(self.x, camber, "--", color="#D9822B", lw=1.0, label="弯度线" if self.language == "zh" else "Camber")
        self.geometry_axis.fill_between(self.x, lower, upper, color="#1672A3", alpha=0.12)
        magnitude = float(np.max(np.abs(np.r_[upper, lower])))
        while magnitude > self.geometry_ylim * 0.88:
            self.geometry_ylim += 0.025
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
            axis.scatter(cx, cy, s=28, color="#F0A020", edgecolors="#1E1E1E", linewidths=0.7, zorder=5)
            axis.set_xlim(-0.03, 1.03)
            pad = max(0.02 if index == 0 else 2.0, float(np.ptp(cy)) * 0.28)
            axis.set_ylim(float(np.min(cy)) - pad, float(np.max(cy)) + pad)
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
        selected = self._nearest_control(event)
        if selected is None:
            return
        self.active = selected
        parameter_index = self._parameter_index(*selected)
        self.drag_origin_y = float(event.ydata)
        self.drag_origin_value = float(self.parameters[parameter_index])
        self.drag_snapshot = self.parameters.copy()

    def _motion(self, event) -> None:
        if self.active is None or event.inaxes is not self.control_axes[self.active[0]] or event.ydata is None:
            return
        parameter_index = self._parameter_index(*self.active)
        value = self.drag_origin_value + (float(event.ydata) - self.drag_origin_y) * self.sensitivity
        self.parameters[parameter_index] = np.clip(value, LOWER_BOUNDS[parameter_index], UPPER_BOUNDS[parameter_index])
        self._redraw()

    def _release(self, _event) -> None:
        if self.active is not None and self.drag_snapshot is not None:
            if not np.array_equal(self.drag_snapshot, self.parameters):
                self.history.append(self.drag_snapshot)
                if len(self.history) > 40:
                    self.history.pop(0)
            self.status.emit("BCE geometry updated")
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
        controls = QHBoxLayout()
        controls.setSpacing(3)
        title = QLabel("Legacy BCE manual design → compact D-BCE")
        title.setProperty("heading", True)
        controls.addWidget(title)
        controls.addStretch(1)
        self.sensitivity = QComboBox()
        self.sensitivity.addItem("Fine 0.35×", 0.35)
        self.sensitivity.addItem("Standard 0.8×", 0.8)
        self.sensitivity.addItem("Fast 1.5×", 1.5)
        self.sensitivity.setCurrentIndex(1)
        controls.addWidget(QLabel("Drag gain"))
        controls.addWidget(self.sensitivity)
        for text, callback in (
            ("Import DAT", self._import),
            ("Undo", self._undo),
            ("Reset", self._reset),
            ("Export DAT", self._export),
            ("Apply D-BCE", self._handoff),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            if text == "Apply D-BCE":
                button.setProperty("accent", True)
            controls.addWidget(button)
        layout.addLayout(controls)
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

    def ensure_exported(self) -> str:
        directory = Path(self.workdir_provider()) / "airfoil_designs"
        path = directory / "qt_current_airfoil.dat"
        self.canvas.export(path, "Qt_current_airfoil")
        self.airfoilPathChanged.emit(str(path))
        return str(path)

    def set_language(self, language: str) -> None:
        self.canvas.set_language(language)

    def _gain_changed(self) -> None:
        self.canvas.sensitivity = float(self.sensitivity.currentData())

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
