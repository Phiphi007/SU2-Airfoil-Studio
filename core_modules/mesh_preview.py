"""Embedded desktop mesh inspection; displays the actual generated cells."""
from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from .ui_layout import wrap_to_width


class EmbeddedMeshPreview(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.nodes = self.quads = self.polygons = None
        self.quality = {}
        self._pending = None
        self._drawing = False
        self._collection = None
        self.mode_var = tk.StringVar(value="网格线")
        self.status_var = tk.StringVar(value="生成网格后在此检查；滚轮缩放，工具栏可平移。")
        self.quality_var = tk.StringVar(value="尚无网格")
        actions = ttk.Frame(self)
        actions.grid(row=0, column=0, sticky="ew", pady=2)
        for text, view in (("翼型附近", "body"), ("前缘", "leading"),
                           ("后缘", "trailing"), ("整个流场域", "domain")):
            ttk.Button(actions, text=text, command=lambda v=view: self.set_view(v)).pack(side="left", padx=2)
        mode = ttk.Combobox(actions, textvariable=self.mode_var,
                            values=("网格线", "缩放 Jacobian"), width=18, state="readonly")
        mode.pack(side="right", padx=2)
        mode.bind("<<ComboboxSelected>>", lambda event: self._render())
        quality_label = ttk.Label(self, textvariable=self.quality_var, wraplength=680,
                                 foreground="#DCDCDC", font=("Microsoft YaHei UI", 9, "bold"))
        quality_label.grid(row=1, column=0, sticky="ew", pady=3)
        wrap_to_width(quality_label)
        self.figure = Figure(figsize=(8, 6), dpi=100, facecolor="#1E1E1E")
        self.axis = self.figure.add_subplot(111)
        self.figure.subplots_adjust(left=.09, right=.98, bottom=.11, top=.95)
        self.axis.set_facecolor("#202022")
        self.axis.tick_params(colors="#C8C8C8", labelsize=8)
        for spine in self.axis.spines.values():
            spine.set_color("#545454")
        self.axis.set_xlabel("x / c", color="#DCDCDC")
        self.axis.set_ylabel("y / c", color="#DCDCDC")
        self.axis.set_aspect("equal", adjustable="box")
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().configure(width=1, height=1)
        self.canvas.get_tk_widget().grid(row=2, column=0, sticky="nsew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.toolbar.grid(row=3, column=0, sticky="ew")
        status_label = ttk.Label(self, textvariable=self.status_var, foreground="#B8B8B8", wraplength=680)
        status_label.grid(row=4, column=0, sticky="ew", pady=2)
        wrap_to_width(status_label)
        self.axis.callbacks.connect("xlim_changed", lambda axis: self._schedule())
        self.axis.callbacks.connect("ylim_changed", lambda axis: self._schedule())
        self.canvas.mpl_connect("scroll_event", self._zoom)

    def destroy(self):
        if self._pending:
            self.after_cancel(self._pending)
            self._pending = None
        super().destroy()

    def load(self, mesh_path: Path) -> None:
        with np.load(mesh_path.parent / "mesh_preview.npz", allow_pickle=False) as archive:
            self.nodes = archive["nodes"].copy()
            self.quads = archive["quads"].copy()
            wall_edges = archive["wall_edges"]
            self.wall = self.nodes[np.r_[wall_edges[:, 0], wall_edges[-1, 1]]]
            self.source = archive["source_boundary"].copy()
            imported_quality = archive["cell_quality"].copy() if "cell_quality" in archive else None
        self.quality = json.loads((mesh_path.parent / "mesh_quality.json").read_text(encoding="utf-8"))
        self.origin = np.array([self.wall[:, 0].min(), self.wall[np.argmin(self.wall[:, 0]), 1]])
        self.chord = float(np.ptp(self.wall[:, 0]))
        self.normalized = (self.nodes - self.origin) / self.chord
        self.polygons = self.normalized[self.quads]
        self.low = self.polygons.min(axis=1)
        self.high = self.polygons.max(axis=1)
        self.jacobian = np.ones(len(self.quads))
        for corner in range(4):
            a = self.polygons[:, (corner-1)%4] - self.polygons[:, corner]
            b = self.polygons[:, (corner+1)%4] - self.polygons[:, corner]
            cross = a[:, 1]*b[:, 0] - a[:, 0]*b[:, 1]
            scaled = cross / np.maximum(np.linalg.norm(a, axis=1)*np.linalg.norm(b, axis=1), 1e-30)
            self.jacobian = np.minimum(self.jacobian, scaled)
        if imported_quality is not None:
            self.jacobian = imported_quality
        q = self.quality
        self.quality_var.set(
            f"{len(self.quads):,} 个四边形 | {len(self.nodes):,} 节点 | "
            f"最小角 {q['minimum_angle_deg']:.2f}° | Jacobian {q['minimum_scaled_jacobian']:.3f}\n"
            f"前缘上/下 {q.get('leading_edge_nodes_upper_5pct', 0)}/{q.get('leading_edge_nodes_lower_5pct', 0)} 点 | "
            f"壁面相邻边长比 {q.get('wall_spacing_max_adjacent_ratio', 0):.3f} | "
            f"前缘方向最大步变 {q.get('leading_edge_radial_direction_max_step_deg', 0):.2f}°\n"
            f"前缘修复 {'已应用' if q.get('leading_edge_repair_applied') else '无需'} | "
            f"曲线/原始折线最大偏差 {q.get('wall_reconstruction_max_curve_deviation_pct', 0):.3e}c"
        )
        if q.get("imported_mesh"):
            self.quality_var.set(
                f"导入网格：{q['quadrilateral_cells']:,} 四边形 / {q['triangle_cells']:,} 三角形 | {len(self.nodes):,} 节点\n"
                f"最小角 {q['minimum_angle_deg']:.2f}° | 最小角正弦 {q['minimum_scaled_jacobian']:.3f} | 壁面：{q['wall_marker']}\n"
                "保持原节点与单元；未重新划分网格"
            )
        # Replacing a mesh clears the old overlays and toolbar view history.
        for line in list(self.axis.lines):
            line.remove()
        for points, color, style, width in ((self.source, "#D99A47", "--", .8),
                                             (self.wall, "#E2E2E2", "-", 1.0)):
            values = (points - self.origin) / self.chord
            self.axis.plot(values[:, 0], values[:, 1], color=color,
                           linestyle=style, linewidth=width, zorder=3)
        self.toolbar.update()
        self.set_view("body")

    def set_view(self, view: str) -> None:
        if self.nodes is None:
            return
        if view == "domain":
            low, high = self.normalized.min(axis=0), self.normalized.max(axis=0)
            limits = (low[0], high[0], low[1], high[1])
        else:
            limits = {"body": (-.18, 1.25, -.35, .35),
                      "leading": (-.025, .10, -.075, .075),
                      "trailing": (.90, 1.08, -.075, .075)}[view]
        self.axis.set_xlim(*limits[:2])
        self.axis.set_ylim(*limits[2:])
        self._render()

    def _schedule(self):
        if self._drawing or self.nodes is None:
            return
        if self._pending:
            self.after_cancel(self._pending)
        # Limit-change callbacks fire for every mouse pixel while the toolbar
        # pans.  A slightly longer debounce avoids rebuilding a large
        # PolyCollection several times during one gesture.
        self._pending = self.after(180, self._render)

    def _render(self):
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = None
        if self.nodes is None:
            return
        self._drawing = True
        try:
            x0, x1 = sorted(self.axis.get_xlim())
            y0, y1 = sorted(self.axis.get_ylim())
            ids = np.flatnonzero((self.high[:, 0] >= x0) & (self.low[:, 0] <= x1)
                                 & (self.high[:, 1] >= y0) & (self.low[:, 1] <= y1))
            # A half-million antialiased polygons makes TkAgg redraw on every
            # pan event.  Keep an interactive line budget; zooming in naturally
            # restores the real cells because fewer cells intersect the view.
            line_budget = 75_000
            stride = max(1, int(np.ceil(len(ids) / line_budget)))
            visible = ids[::stride]
            if self._collection is not None:
                self._collection.remove()
            quality_mode = self.mode_var.get() == "缩放 Jacobian"
            self._collection = PolyCollection(
                self.polygons[visible], facecolors="none" if not quality_mode else None,
                edgecolors="#678BA0" if not quality_mode else "#36434A",
                linewidths=.28 if not quality_mode else .12, antialiaseds=False,
                cmap="viridis", zorder=1,
            )
            if quality_mode:
                self._collection.set_array(self.jacobian[visible])
                self._collection.set_clim(0, 1)
            self.axis.add_collection(self._collection, autolim=False)
            detail = "完整显示" if stride == 1 else f"交互抽样 1/{stride}；放大后恢复真实单元"
            self.status_var.set(
                f"视窗内 {len(ids):,} 个单元 · {detail} · 橙色虚线：输入折线；浅色实线：实际壁面"
                + (" · Jacobian 色阶：0 紫 → 1 黄" if quality_mode else "")
            )
            self.canvas.draw_idle()
        finally:
            self._drawing = False

    def _zoom(self, event):
        if event.inaxes is not self.axis or event.xdata is None or event.ydata is None:
            return
        factor = .8 if event.button == "up" else 1.25
        x0, x1 = self.axis.get_xlim()
        y0, y1 = self.axis.get_ylim()
        self.axis.set_xlim(event.xdata + (x0-event.xdata)*factor, event.xdata + (x1-event.xdata)*factor)
        self.axis.set_ylim(event.ydata + (y0-event.ydata)*factor, event.ydata + (y1-event.ydata)*factor)
