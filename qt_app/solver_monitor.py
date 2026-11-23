from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core_modules.history_monitor import read_history_points


class SolverConvergenceMonitor(QWidget):
    """Live residual/force monitor backed by SU2's flushed history.csv."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        self.summary = QLabel("Waiting for a solver run")
        self.summary.setProperty("heading", True)
        layout.addWidget(self.summary)
        self.figure = Figure(figsize=(10.0, 6.0), dpi=100, facecolor="#1E1E1E")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.subplots(3, 1, sharex=True)
        self.lines = []
        colors = ("#4DB8FF", "#D9822B", "#67C587")
        labels = ("log10 RMS density", "CD", "CL")
        for axis, color, label in zip(self.axes, colors, labels):
            (line,) = axis.plot([], [], color=color, linewidth=1.35)
            self.lines.append(line)
            axis.set_facecolor("#202022")
            axis.set_ylabel(label, color="#D8D8D8", fontsize=8)
            axis.grid(True, color="#3A3A3A", linewidth=0.5, alpha=0.75)
            axis.tick_params(colors="#BBBBBB", labelsize=8)
            for spine in axis.spines.values():
                spine.set_color("#505050")
        self.axes[-1].set_xlabel("Inner iteration", color="#D8D8D8", fontsize=8)
        self.figure.subplots_adjust(left=0.09, right=0.985, top=0.975, bottom=0.09, hspace=0.13)
        layout.addWidget(self.canvas, 1)
        self.history_path: Path | None = None
        self.iterations: list[int] = []
        self.residuals: list[float] = []
        self.cd: list[float] = []
        self.cl: list[float] = []

    @property
    def iteration_count(self) -> int:
        return len(self.iterations)

    def start(self, history_path: str | Path) -> None:
        self.history_path = Path(history_path)
        self.iterations.clear()
        self.residuals.clear()
        self.cd.clear()
        self.cl.clear()
        for line in self.lines:
            line.set_data([], [])
        self.summary.setText("Waiting for SU2 history.csv")
        self.canvas.draw_idle()

    def refresh(self) -> int:
        if self.history_path is None:
            return 0
        after = self.iterations[-1] if self.iterations else -1
        points = read_history_points(self.history_path, after)
        for iteration, residual, cl_value, cd_value in points:
            self.iterations.append(iteration)
            self.residuals.append(residual)
            self.cl.append(cl_value)
            self.cd.append(cd_value)
        if not points:
            return 0
        values = (self.residuals, self.cd, self.cl)
        for axis, line, ordinate in zip(self.axes, self.lines, values):
            line.set_data(self.iterations, ordinate)
            axis.relim()
            axis.autoscale_view()
        self.summary.setText(
            f"Iteration {self.iterations[-1]:,}  |  "
            f"RMS={self.residuals[-1]:.5f}  |  "
            f"CL={self.cl[-1]:.6f}  |  CD={self.cd[-1]:.6f}"
        )
        self.canvas.draw_idle()
        return len(points)

    def finish(self, last_values: dict | None = None, state: str = "Completed") -> None:
        self.refresh()
        if self.iterations:
            self.summary.setText(state + "  |  " + self.summary.text())
        elif last_values:
            rendered = "  |  ".join(f"{key}={value}" for key, value in last_values.items())
            self.summary.setText(state + "  |  " + rendered)
        else:
            self.summary.setText(state + " without readable convergence history")
