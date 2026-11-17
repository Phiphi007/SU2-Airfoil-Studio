"""Fast endpoint-safe D-BCE manual deformation workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .parameterizations.bce import compact_bump


@dataclass(frozen=True)
class Brush:
    mode: str
    center: float
    half_width: float
    amplitude: float


MODE_LABELS = {
    "弯度（上下同向）": "camber",
    "厚度（上下反向）": "thickness",
    "仅上表面": "upper",
    "仅下表面": "lower",
}


def _surface_on_common_x(surface: np.ndarray, target_x: np.ndarray) -> np.ndarray:
    order = np.argsort(surface[:, 0])
    x, y = surface[order, 0], surface[order, 1]
    unique, indices = np.unique(x, return_index=True)
    return np.interp(target_x, unique, y[indices])


def write_selig(path: Path, name: str, x: np.ndarray, upper: np.ndarray, lower: np.ndarray) -> None:
    lines = [name]
    lines.extend(f" {xi:.9f}  {yi:.9f}" for xi, yi in zip(x[::-1], upper[::-1]))
    lines.extend(f" {xi:.9f}  {yi:.9f}" for xi, yi in zip(x[1:], lower[1:]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


class DBCEDeformationModel:
    def __init__(self) -> None:
        self.name = ""
        self.x = np.asarray([], dtype=float)
        self.upper = np.asarray([], dtype=float)
        self.lower = np.asarray([], dtype=float)
        self.brushes: list[Brush] = []

    @property
    def loaded(self) -> bool:
        return len(self.x) >= 4

    def load_surfaces(self, name: str, upper: np.ndarray, lower: np.ndarray) -> None:
        upper = np.asarray(upper, dtype=float)
        lower = np.asarray(lower, dtype=float)
        if upper.ndim != 2 or lower.ndim != 2 or upper.shape[1] < 2 or lower.shape[1] < 2:
            raise ValueError("翼型表面必须是 N×2 坐标数组。")
        x_min = max(float(np.min(upper[:, 0])), float(np.min(lower[:, 0])))
        x_max = min(float(np.max(upper[:, 0])), float(np.max(lower[:, 0])))
        if x_max - x_min <= 1.0e-8:
            raise ValueError("上下表面没有有效的共同弦向范围。")
        count = max(len(upper), len(lower), 181)
        theta = np.linspace(0.0, np.pi, count)
        x = x_min + (x_max - x_min) * 0.5 * (1.0 - np.cos(theta))
        upper_y = _surface_on_common_x(upper[:, :2], x)
        lower_y = _surface_on_common_x(lower[:, :2], x)
        if np.any(upper_y[1:-1] <= lower_y[1:-1]):
            raise ValueError("导入翼型存在表面交叉或负厚度。")
        self.name = name
        self.x = x
        self.upper = upper_y
        self.lower = lower_y
        self.brushes.clear()

    def profile(self, brush: Brush) -> np.ndarray:
        """Return the normalized endpoint-safe compact influence of one brush."""
        chord = max(float(np.ptp(self.x)), 1.0e-12)
        xn = (self.x - float(np.min(self.x))) / chord
        phi = compact_bump(xn, brush.center, brush.half_width)
        phi *= np.sqrt(np.clip(xn, 0.0, 1.0)) * (1.0 - np.clip(xn, 0.0, 1.0))
        maximum = float(np.max(phi))
        return phi / maximum if maximum > 1.0e-14 else phi

    def geometry(self, exclude_index: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if not self.loaded:
            raise RuntimeError("尚未载入翼型。")
        upper = self.upper.copy()
        lower = self.lower.copy()
        chord = max(float(np.ptp(self.x)), 1.0e-12)
        for index, brush in enumerate(self.brushes):
            if index == exclude_index:
                continue
            phi = self.profile(brush)
            delta = brush.amplitude * chord * phi
            if brush.mode == "camber":
                upper += delta
                lower += delta
            elif brush.mode == "thickness":
                upper += delta
                lower -= delta
            elif brush.mode == "upper":
                upper += delta
            elif brush.mode == "lower":
                lower += delta
            else:
                raise ValueError(f"未知笔刷模式: {brush.mode}")
        return self.x.copy(), upper, lower

    def validate(self) -> tuple[bool, str, dict[str, float]]:
        x, upper, lower = self.geometry()
        chord = max(float(np.ptp(x)), 1.0e-12)
        thickness = (upper - lower) / chord
        interior = (x > float(np.min(x)) + 0.02 * chord) & (
            x < float(np.max(x)) - 0.02 * chord
        )
        minimum = float(np.min(thickness[interior])) if np.any(interior) else float(np.min(thickness))
        maximum = float(np.max(thickness))
        if minimum <= 2.0e-4:
            return False, f"局部厚度过小或表面交叉：min(t/c)={minimum:.6f}", {
                "minimum_thickness": minimum,
                "maximum_thickness": maximum,
            }
        if maximum > 0.45:
            return False, f"最大厚度超过安全范围：max(t/c)={maximum:.4f}", {
                "minimum_thickness": minimum,
                "maximum_thickness": maximum,
            }
        return True, "几何有效", {
            "minimum_thickness": minimum,
            "maximum_thickness": maximum,
        }


class DBCEDeformationPanel(ttk.Frame):
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
        self.model = DBCEDeformationModel()
        self.mode_var = tk.StringVar(value="弯度（上下同向）")
        self.center_var = tk.StringVar(value="0.40")
        self.width_var = tk.StringVar(value="0.18")
        self.amplitude_var = tk.StringVar(value="0.002")
        self.status_var = tk.StringVar(value="载入当前翼型或导入 DAT 后，可添加 D-BCE 笔刷。")
        self.active_drag: tuple[int, str] | None = None
        self.drag_artists: list[tuple[object, int, str]] = []
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_controls()
        self._build_plot()

    def _build_controls(self) -> None:
        project = ttk.LabelFrame(self, text="项目工作目录与翼型来源", padding=10)
        project.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        project.columnconfigure(1, weight=1)
        ttk.Label(project, text="工作目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(project, textvariable=self.workdir_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(project, text="选择…", command=self._choose_workdir).grid(row=0, column=2)
        ttk.Button(project, text="使用主程序当前翼型", command=self.load_current_airfoil).grid(
            row=1, column=0, sticky="ew", pady=(8, 0)
        )
        ttk.Button(project, text="导入翼型 DAT", command=self._import_dat).grid(
            row=1, column=1, sticky="w", padx=6, pady=(8, 0)
        )
        ttk.Label(
            project,
            text="可直接采用原翼型，也可叠加紧支撑 D-BCE 笔刷后再进入网格与计算。",
            foreground="#9A9A9A",
        ).grid(row=1, column=2, sticky="e", pady=(8, 0))

        controls = ttk.LabelFrame(self, text="端点安全 D-BCE 手动变形", padding=10)
        controls.grid(row=1, column=0, sticky="nsw", padx=(0, 8))
        ttk.Label(controls, text="变形类型").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(
            controls, textvariable=self.mode_var, values=tuple(MODE_LABELS),
            state="readonly", width=19,
        ).grid(row=0, column=1, sticky="ew", pady=3)
        for row, (label, variable) in enumerate((
            ("中心 x/c", self.center_var),
            ("半宽 w/c", self.width_var),
            ("幅值 Δy/c", self.amplitude_var),
        ), start=1):
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(controls, textvariable=variable, width=12).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Button(controls, text="添加可视化笔刷", command=self._add_brush).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 3)
        )
        ttk.Button(controls, text="生成一组可拖动控制点", command=self._seed_drag_handles).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=3
        )
        ttk.Button(controls, text="删除选中", command=self._delete_selected).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=3
        )
        ttk.Button(controls, text="清除全部变形", command=self._clear).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=3
        )
        self.brush_tree = ttk.Treeview(
            controls, columns=("mode", "center", "width", "amp"), show="headings", height=8
        )
        for key, title, width in (
            ("mode", "类型", 72), ("center", "中心", 55),
            ("width", "半宽", 55), ("amp", "幅值", 62),
        ):
            self.brush_tree.heading(key, text=title)
            self.brush_tree.column(key, width=width, anchor="center")
        self.brush_tree.grid(row=8, column=0, columnspan=2, pady=(8, 3))
        self.brush_tree.bind("<<TreeviewSelect>>", self._tree_selected)
        ttk.Separator(controls).grid(row=9, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Button(
            controls, text="导出当前翼型 DAT…", command=self._export_current
        ).grid(row=10, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(
            controls, text="直接使用原翼型", command=lambda: self._apply(use_deformed=False)
        ).grid(row=11, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(
            controls, text="使用变形翼型进入网格与计算", style="Accent.TButton",
            command=lambda: self._apply(use_deformed=True),
        ).grid(row=12, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Label(controls, textvariable=self.status_var, wraplength=260).grid(
            row=13, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

    def _build_plot(self) -> None:
        plot_frame = ttk.Frame(self)
        plot_frame.grid(row=1, column=1, sticky="nsew")
        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)
        self.figure = Figure(figsize=(9, 5.8), dpi=100, facecolor="#1E1E1E")
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
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
        self.canvas.mpl_connect("button_press_event", self._press_handle)
        self.canvas.mpl_connect("motion_notify_event", self._drag_handle)
        self.canvas.mpl_connect("button_release_event", self._release_handle)
        self._draw()

    def _choose_workdir(self) -> None:
        selected = filedialog.askdirectory(parent=self, title="选择项目工作目录")
        if selected:
            self.workdir_var.set(selected)

    def load_current_airfoil(self, silent: bool = False) -> None:
        payload = self.current_airfoil_provider()
        if payload is None:
            if not silent:
                messagebox.showinfo("当前翼型尚未准备", "请等待主程序完成翼型预览。", parent=self)
            return
        name, upper, lower = payload
        try:
            self.model.load_surfaces(name, upper, lower)
        except Exception as exc:
            if not silent:
                messagebox.showerror("无法载入翼型", str(exc), parent=self)
            return
        self.status_var.set(f"已载入 {name}；D-BCE 无需逆向拟合。")
        self._seed_drag_handles(redraw=False)
        self._refresh_tree()
        self._draw()

    def _import_dat(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="导入 Selig 翼型", filetypes=[("Airfoil DAT", "*.dat *.txt")]
        )
        if not path:
            return
        try:
            points = []
            for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
                fields = line.replace(",", " ").split()
                try:
                    points.append((float(fields[0]), float(fields[1])))
                except (ValueError, IndexError):
                    continue
            coordinates = np.asarray(points, dtype=float)
            leading = int(np.argmin(coordinates[:, 0]))
            upper = coordinates[: leading + 1]
            lower = coordinates[leading:][::-1]
            self.model.load_surfaces(Path(path).stem, upper, lower)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        self.status_var.set(f"已导入 {Path(path).name}；D-BCE 无需逆向拟合。")
        self._seed_drag_handles(redraw=False)
        self._refresh_tree()
        self._draw()

    def _seed_drag_handles(self, redraw: bool = True) -> None:
        if not self.model.loaded:
            if redraw:
                messagebox.showinfo("尚无翼型", "请先载入翼型。", parent=self)
            return
        mode = MODE_LABELS[self.mode_var.get()]
        centers = (0.12, 0.28, 0.48, 0.68, 0.86)
        widths = (0.09, 0.13, 0.16, 0.14, 0.10)
        self.model.brushes = [
            Brush(mode, center, width, 0.0) for center, width in zip(centers, widths)
        ]
        self.status_var.set("已生成 5 个可拖动控制点：红点改位置/幅值，橙色三角改笔刷宽度。")
        self._refresh_tree()
        if redraw:
            self._draw()

    def _tree_selected(self, _event=None) -> None:
        selected = self.brush_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        if not 0 <= index < len(self.model.brushes):
            return
        brush = self.model.brushes[index]
        label = next(key for key, value in MODE_LABELS.items() if value == brush.mode)
        self.mode_var.set(label)
        self.center_var.set(f"{brush.center:.4f}")
        self.width_var.set(f"{brush.half_width:.4f}")
        self.amplitude_var.set(f"{brush.amplitude:+.5f}")

    def _add_brush(self) -> None:
        if not self.model.loaded:
            messagebox.showinfo("尚无翼型", "请先载入主程序当前翼型或导入 DAT。", parent=self)
            return
        try:
            center = float(self.center_var.get())
            width = float(self.width_var.get())
            amplitude = float(self.amplitude_var.get())
            if not 0.02 <= center <= 0.98:
                raise ValueError("中心必须位于 0.02～0.98。")
            if not 0.02 <= width <= 0.35:
                raise ValueError("半宽必须位于 0.02～0.35。")
            if center - width < 0.01 or center + width > 0.99:
                raise ValueError("笔刷支撑不能跨越前缘或后缘。")
            if abs(amplitude) > 0.05:
                raise ValueError("单笔幅值绝对值不能超过 0.05c。")
            brush = Brush(MODE_LABELS[self.mode_var.get()], center, width, amplitude)
            self.model.brushes.append(brush)
            valid, reason, _ = self.model.validate()
            if not valid:
                self.model.brushes.pop()
                raise ValueError(reason)
        except Exception as exc:
            messagebox.showerror("无法添加笔刷", str(exc), parent=self)
            return
        self.status_var.set("已添加端点安全 D-BCE 笔刷。")
        self._refresh_tree()
        self._draw()

    def _delete_selected(self) -> None:
        selected = self.brush_tree.selection()
        if not selected:
            return
        indices = sorted((int(item) for item in selected), reverse=True)
        for index in indices:
            if 0 <= index < len(self.model.brushes):
                self.model.brushes.pop(index)
        self._refresh_tree()
        self._draw()

    def _clear(self) -> None:
        self.model.brushes.clear()
        self._refresh_tree()
        self._draw()
        self.status_var.set("已恢复原始导入翼型。")

    def _refresh_tree(self) -> None:
        selected = self.brush_tree.selection()
        self.brush_tree.delete(*self.brush_tree.get_children())
        reverse = {value: key.split("（", 1)[0] for key, value in MODE_LABELS.items()}
        for index, brush in enumerate(self.model.brushes):
            self.brush_tree.insert(
                "", "end", iid=str(index),
                values=(reverse[brush.mode], f"{brush.center:.3f}", f"{brush.half_width:.3f}", f"{brush.amplitude:+.4f}"),
            )
        if selected and self.brush_tree.exists(selected[0]):
            self.brush_tree.selection_set(selected[0])

    def _draw(self) -> None:
        self.axis.clear()
        self.axis.set_facecolor("#252526")
        self.axis.grid(True, color="#3A3A3A", linewidth=0.55, linestyle=":")
        self.axis.tick_params(colors="#B8B8B8", labelsize=8)
        self.axis.xaxis.label.set_color("#D4D4D4")
        self.axis.yaxis.label.set_color("#D4D4D4")
        self.axis.title.set_color("#E8E8E8")
        for spine in self.axis.spines.values():
            spine.set_color("#555555")
        self.axis.set_xlabel("x/c")
        self.axis.set_ylabel("y/c")
        if not self.model.loaded:
            self.axis.text(0.5, 0.5, "载入翼型后在这里预览 D-BCE 变形", ha="center", va="center", color="#D4D4D4", transform=self.axis.transAxes)
        else:
            x, upper, lower = self.model.geometry()
            self.axis.plot(self.model.x, self.model.upper, "--", color="#8796a3", linewidth=1.2, label="原始翼型")
            self.axis.plot(self.model.x, self.model.lower, "--", color="#8796a3", linewidth=1.2)
            self.axis.plot(x, upper, color="#4FC1FF", linewidth=1.7, label="当前 D-BCE 翼型")
            self.axis.plot(x, lower, color="#4FC1FF", linewidth=1.7)
            self.axis.plot(x, 0.5 * (upper + lower), color="#d9822b", linewidth=1.0, label="中弧线")
            self.axis.fill_between(x, lower, upper, color="#007ACC", alpha=0.12)
            self.drag_artists = []
            selected = self.brush_tree.selection()
            selected_index = int(selected[0]) if selected else -1
            chord = max(float(np.ptp(x)), 1.0e-12)
            x_min = float(np.min(x))
            for index, brush in enumerate(self.model.brushes):
                center_x = x_min + brush.center * chord
                left_x = x_min + (brush.center - brush.half_width) * chord
                right_x = x_min + (brush.center + brush.half_width) * chord
                if brush.mode == "camber":
                    handle_curve = 0.5 * (upper + lower)
                elif brush.mode in {"thickness", "upper"}:
                    handle_curve = upper
                else:
                    handle_curve = lower
                handle_y = float(np.interp(center_x, x, handle_curve))
                left_y = float(np.interp(left_x, x, handle_curve))
                right_y = float(np.interp(right_x, x, handle_curve))
                active = index == selected_index or (
                    self.active_drag is not None and self.active_drag[0] == index
                )
                if active:
                    self.axis.axvspan(
                        left_x, right_x, color="#ef8a24", alpha=0.10, zorder=0
                    )
                    profile = self.model.profile(brush)
                    scale = max(abs(brush.amplitude) * chord, 0.006 * chord)
                    guide = handle_curve + np.sign(brush.amplitude or 1.0) * scale * profile
                    self.axis.plot(x, guide, ":", color="#ef8a24", linewidth=1.0, alpha=0.8)
                center_artist, = self.axis.plot(
                    [center_x], [handle_y], "o", color="#d83b3b", markeredgecolor="white",
                    markeredgewidth=0.9, markersize=9 if active else 7, picker=10, zorder=9,
                )
                width_artist, = self.axis.plot(
                    [left_x, right_x], [left_y, right_y], "<", color="#ef8a24",
                    linestyle="None", markersize=7 if active else 5, picker=9, zorder=8,
                )
                # Use a right-facing marker for the right support edge.
                self.axis.plot([right_x], [right_y], ">", color="#ef8a24", markersize=7 if active else 5, zorder=8)
                self.drag_artists.append((center_artist, index, "center"))
                self.drag_artists.append((width_artist, index, "width"))
            self.axis.legend(loc="best", frameon=False, labelcolor="#D4D4D4", fontsize=8)
            valid, reason, metrics = self.model.validate()
            self.axis.set_title(
                f"{self.model.name} · {len(self.model.brushes)} 个笔刷 · "
                f"min t/c={metrics['minimum_thickness']:.4f} · {'有效' if valid else reason}",
                color="#E8E8E8", fontweight="bold",
            )
            self.axis.text(
                0.01, 0.02,
                "拖动红点：位置 + 变形幅值   ·   拖动橙色三角：作用范围",
                transform=self.axis.transAxes, color="#D4D4D4", fontsize=9,
                bbox={"facecolor": "#252526", "edgecolor": "#3C3C3C", "alpha": 0.90},
            )
        self.axis.set_aspect("equal", adjustable="datalim")
        self.figure.tight_layout(pad=1.2)
        self.canvas.draw_idle()

    def _press_handle(self, event) -> None:
        if event.inaxes is not self.axis or getattr(
            getattr(self.canvas, "toolbar", None), "mode", ""
        ):
            return
        for artist, index, kind in reversed(self.drag_artists):
            contains, details = artist.contains(event)
            if contains:
                if kind == "width" and details.get("ind") is not None:
                    point = int(details["ind"][0])
                    kind = "width_left" if point == 0 else "width_right"
                self.active_drag = (index, kind)
                self.brush_tree.selection_set(str(index))
                self._tree_selected()
                self._draw()
                return

    def _drag_handle(self, event) -> None:
        if self.active_drag is None or event.inaxes is not self.axis or event.xdata is None:
            return
        index, kind = self.active_drag
        if not 0 <= index < len(self.model.brushes):
            return
        old = self.model.brushes[index]
        chord = max(float(np.ptp(self.model.x)), 1.0e-12)
        x_min = float(np.min(self.model.x))
        xn = float(np.clip((float(event.xdata) - x_min) / chord, 0.01, 0.99))
        if kind.startswith("width"):
            maximum = min(0.35, old.center - 0.01, 0.99 - old.center)
            width = float(np.clip(abs(xn - old.center), 0.02, maximum))
            candidate = Brush(old.mode, old.center, width, old.amplitude)
        else:
            if event.ydata is None:
                return
            center = float(np.clip(xn, old.half_width + 0.01, 0.99 - old.half_width))
            base_x, base_upper, base_lower = self.model.geometry(exclude_index=index)
            provisional = Brush(old.mode, center, old.half_width, old.amplitude)
            influence = float(np.interp(x_min + center * chord, base_x, self.model.profile(provisional)))
            if old.mode == "camber":
                anchor_curve = 0.5 * (base_upper + base_lower)
            elif old.mode in {"thickness", "upper"}:
                anchor_curve = base_upper
            else:
                anchor_curve = base_lower
            anchor = float(np.interp(x_min + center * chord, base_x, anchor_curve))
            amplitude = (float(event.ydata) - anchor) / max(chord * influence, 1.0e-12)
            candidate = Brush(old.mode, center, old.half_width, float(np.clip(amplitude, -0.05, 0.05)))
        self.model.brushes[index] = candidate
        valid, reason, _ = self.model.validate()
        if not valid:
            self.model.brushes[index] = old
            self.status_var.set(f"已阻止无效拖动：{reason}")
            return
        self.status_var.set("正在拖动 D-BCE 控制点；翼型已实时更新。")
        self._refresh_tree()
        self._tree_selected()
        self._draw()

    def _release_handle(self, _event) -> None:
        if self.active_drag is not None:
            self.active_drag = None
            self.status_var.set("变形已更新；可继续拖动、导出 DAT 或进入网格生成。")
            self._draw()

    def _export_current(self) -> None:
        if not self.model.loaded:
            messagebox.showinfo("尚无翼型", "请先载入翼型。", parent=self)
            return
        valid, reason, _ = self.model.validate()
        if not valid:
            messagebox.showerror("几何无效", reason, parent=self)
            return
        target = filedialog.asksaveasfilename(
            parent=self, title="导出当前 D-BCE 翼型", defaultextension=".dat",
            initialfile=f"{self.model.name}_dbce.dat",
            filetypes=[("Airfoil DAT", "*.dat")],
        )
        if not target:
            return
        x, upper, lower = self.model.geometry()
        write_selig(Path(target), f"{self.model.name}_dbce", x, upper, lower)
        self.status_var.set(f"已导出：{target}")

    def _apply(self, *, use_deformed: bool) -> None:
        if not self.model.loaded:
            messagebox.showinfo("尚无翼型", "请先载入翼型。", parent=self)
            return
        workdir = Path(self.workdir_var.get()).expanduser().resolve()
        if not str(self.workdir_var.get()).strip():
            messagebox.showerror("缺少工作目录", "请先选择项目工作目录。", parent=self)
            return
        x = self.model.x.copy()
        upper, lower = (
            self.model.geometry()[1:] if use_deformed else (self.model.upper.copy(), self.model.lower.copy())
        )
        if use_deformed:
            valid, reason, _ = self.model.validate()
            if not valid:
                messagebox.showerror("几何无效", reason, parent=self)
                return
        suffix = "dbce" if use_deformed else "original"
        target = workdir / "airfoil_designs" / f"{self.model.name}_{suffix}.dat"
        try:
            write_selig(target, f"{self.model.name}_{suffix}", x, upper, lower)
        except OSError as exc:
            messagebox.showerror("无法写入翼型", str(exc), parent=self)
            return
        self.apply_callback(target)
        self.status_var.set(f"已应用到主程序：{target}")
