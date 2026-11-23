from __future__ import annotations

from datetime import datetime
import csv
import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core_modules.runtime_paths import APP_VERSION, data_root
from core_modules.runtime_paths import resource_root
from parametric_adjoint.bridge import prepare_case_config
from qt_app import QT_FRONTEND_VERSION
from qt_app.airfoil_editor import AirfoilEditor
from qt_app.backend import ApiProcess, OptimizerProcess
from qt_app.solver_monitor import SolverConvergenceMonitor
from qt_app.vtk_viewer import VTKView


ZH_TEXT = {
    "File": "文件", "Run": "运行", "View": "视图", "Help": "帮助", "About": "关于",
    "Open airfoil…": "打开翼型…", "Export airfoil…": "导出翼型…", "Open SU2 mesh…": "打开 SU2 网格…",
    "Open VTU result…": "打开 VTU 结果…", "Generate mesh": "生成网格", "Run CFD": "运行 CFD", "Stop": "停止",
    "Capture workspace": "截取工作区",
    "Reset layout": "重置布局", " Work directory ": " 工作目录 ", "Browse…": "浏览…",
    "Airfoil Adjustment": "翼型调整", "Mesh Generation": "网格生成", "Solver": "求解器",
    "Results": "结果", "Adjoint Optimization": "伴随优化",
    "Legacy BCE manual design → compact D-BCE": "旧 BCE 手动设计 → 紧支撑 D-BCE",
    "Drag gain": "拖动灵敏度", "Fine 0.35×": "精细 0.35×", "Standard 0.8×": "标准 0.8×",
    "Fast 1.5×": "快速 1.5×", "Import DAT": "导入 DAT", "Undo": "撤销", "Reset": "重置",
    "Export DAT": "导出 DAT", "Apply D-BCE": "应用 D-BCE",
    "Pipeline Browser": "流程浏览器", "Properties": "属性", "Output / Convergence Log": "输出 / 收敛日志",
    "SU2 Airfoil Project": "SU2 翼型工程",
    "BCE editor": "BCE 编辑器", "C-H structured mesh": "C-H 结构网格", "SU2 direct solver": "SU2 直接求解",
    "Display": "显示", "Adjoint optimization": "伴随优化", "State": "状态", "Geometry valid": "几何有效",
    "Surface points / side": "每侧表面点数", "Global refinement": "全局加密系数", "Leading-edge size": "前缘尺寸",
    "Upper TE size": "上表面后缘尺寸", "Lower TE size": "下表面后缘尺寸", "Wake refinement": "尾迹加密",
    "Target Y+": "目标 Y+", "Farfield / chord": "远场 / 弦长", "Domain scale": "流场域缩放",
    "BL growth ratio": "附面层增长率", "BL thickness / chord": "附面层厚度 / 弦长", "Farfield cell size": "远场单元尺寸",
    "Solver": "求解器", "Turbulence": "湍流模型", "Angle of attack": "攻角", "Reynolds": "雷诺数",
    "Temperature [K]": "温度 [K]", "Residual target": "残差目标", "Iterations": "迭代次数", "OpenMP threads": "OpenMP 线程数",
    "Field": "场变量", "Automatic color range": "自动色阶", "Minimum": "最小值", "Maximum": "最大值",
    "Apply field / color range": "应用场变量 / 色阶", "Chord axis + AoA angle": "弦线 + 迎角标注",
    "Colormap": "云图配色", "Overlay text color": "标注文字颜色", "White": "白色", "Black": "黑色",
    "Overlay position": "信息框位置", "Overlay: airfoil name": "显示：翼型名称", "Overlay: Mach": "显示：马赫数",
    "Overlay: angle of attack": "显示：攻角", "Overlay: Reynolds": "显示：雷诺数", "Overlay: field name": "显示：场变量",
    "Top center": "正上方居中", "Top left": "左上角", "Top right": "右上角",
    "Fit full domain": "完整流场", "Fit airfoil": "翼型近场",
    "Parameterization": "参数化方法", "Objective": "优化目标", "Shape variables": "形状变量",
    "Minimum thickness": "最小厚度", "Maximum displacement": "最大位移", "Initial trust radius": "初始信赖域半径",
    "Optimization attempts": "优化尝试次数", "Adjoint iterations": "伴随迭代次数", "Adjoint CFL": "伴随 CFL",
    "CST variables": "CST 变量数", "D-BCE variables": "D-BCE 变量数", "Target CL": "目标 CL",
    "Direct-flow case": "直接流场算例", "SU2 AD bin": "SU2 AD 目录", "Select case…": "选择算例…",
    "Select SU2 bin…": "选择 SU2 目录…", "Start adjoint optimization": "开始伴随优化",
    "Minimum D-BCE half-width": "D-BCE 最小半宽", "Minimum brush support nodes": "笔刷最少支撑点",
    "2D mesh inspection": "二维网格检查", "Solver monitor": "求解监视器", "Discrete-adjoint workflow": "离散伴随工作流",
    "Generate mesh": "生成网格", "Airfoil changed — update mesh": "翼型已修改 — 更新网格",
    "Mesh settings changed — update mesh": "网格参数已修改 — 更新网格", "Mesh up to date": "网格已是最新",
    "Wheel: zoom  ·  Middle drag: pan": "滚轮：缩放  ·  中键拖动：平移",
    "No saved result image. Flow fields open in Results.": "尚无结果图像；流场云图在“结果”页显示。",
    "Run SU2 to display convergence and result files.": "运行 SU2 后显示收敛过程与结果文件。",
    "Result file": "结果文件", "Size": "大小", "Attempt": "尝试", "Stage": "阶段", "Accepted": "接受",
    "Objective": "目标值", "Trust radius": "信赖域半径", "Time (s)": "时间 (s)",
    "Flow field": "流场云图", "Reports / files": "报告 / 文件",
}


def _double(value: float, minimum: float, maximum: float, decimals: int = 5, step: float = 0.1) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setSingleStep(step)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


def _integer(value: int, minimum: int, maximum: int, step: int = 1) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setSingleStep(step)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SU2AirfoilStudioQt")
        self.setWindowTitle(f"SU2 Airfoil Studio · Qt Preview {QT_FRONTEND_VERSION}")
        self.resize(1500, 930)
        self.setMinimumSize(1050, 650)
        self.setDockNestingEnabled(True)
        self.settings = QSettings("Phiphi007", "SU2AirfoilStudioQt")
        self.backend = ApiProcess(self)
        self.optimizer = OptimizerProcess(self)
        self.current_airfoil = "builtin://naca0012"
        self.current_case: Path | None = None
        self.optimization_output: Path | None = None
        self._geometry_signature: str | None = None
        self._meshed_geometry_signature: str | None = None
        self._meshed_settings_signature: tuple | None = None
        self._mesh_exists = False
        self._active_backend_mode: str | None = None
        self._active_backend_output: Path | None = None
        self._build_actions()
        self._build_menu_and_toolbar()
        self._build_central()
        self._build_pipeline_dock()
        self._build_properties_dock()
        self._build_output_dock()
        self._build_status_bar()
        self._connect_backend()
        self.convergence_timer = QTimer(self)
        self.convergence_timer.setInterval(750)
        self.convergence_timer.timeout.connect(self.solver_monitor.refresh)
        self._combo_sources: dict[int, list[str]] = {}
        self._tab_sources = [self.tabs.tabText(index) for index in range(self.tabs.count())]
        self._set_language("en")
        self._restore_state()
        self._log(f"Qt frontend {QT_FRONTEND_VERSION} | backend {APP_VERSION}")
        self._log("The validated Python geometry/mesh/SU2 backend is reused without numerical changes.")

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.backend.running:
            answer = QMessageBox.question(self, "Task running", "Terminate the active task and exit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.backend.terminate()
        if self.optimizer.running:
            answer = QMessageBox.question(self, "Optimization running", "Terminate the active optimization and exit?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.optimizer.terminate()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        self.settings.setValue("workdir", self.workdir_edit.text())
        super().closeEvent(event)

    def _build_actions(self) -> None:
        self.action_open_airfoil = QAction("Open airfoil…", self)
        self.action_open_airfoil.setShortcut("Ctrl+O")
        self.action_open_airfoil.triggered.connect(lambda: self.editor._import())
        self.action_export_airfoil = QAction("Export airfoil…", self)
        self.action_export_airfoil.setShortcut("Ctrl+S")
        self.action_export_airfoil.triggered.connect(lambda: self.editor._export())
        self.action_open_mesh = QAction("Open SU2 mesh…", self)
        self.action_open_mesh.triggered.connect(self._open_mesh_file)
        self.action_open_vtu = QAction("Open VTU result…", self)
        self.action_open_vtu.triggered.connect(self._open_vtu_file)
        self.action_mesh = QAction("Generate mesh", self)
        self.action_mesh.setShortcut("F5")
        self.action_mesh.triggered.connect(lambda: self._start_backend("mesh"))
        self.action_solve = QAction("Run CFD", self)
        self.action_solve.setShortcut("F6")
        self.action_solve.triggered.connect(lambda: self._start_backend("solve"))
        self.action_stop = QAction("Stop", self)
        self.action_stop.setEnabled(False)
        self.action_stop.triggered.connect(self._stop_tasks)
        self.action_reset_layout = QAction("Reset layout", self)
        self.action_reset_layout.triggered.connect(self._reset_layout)
        self.action_capture = QAction("Capture workspace", self)
        self.action_capture.setShortcut("Ctrl+Shift+P")
        self.action_capture.triggered.connect(self._capture_workspace)
        self.action_about = QAction("About", self)
        self.action_about.triggered.connect(self._about)

    def _build_menu_and_toolbar(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.action_open_airfoil)
        file_menu.addAction(self.action_export_airfoil)
        file_menu.addAction(self.action_open_mesh)
        file_menu.addAction(self.action_open_vtu)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        run_menu = self.menuBar().addMenu("Run")
        run_menu.addAction(self.action_mesh)
        run_menu.addAction(self.action_solve)
        run_menu.addAction(self.action_stop)
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.action_reset_layout)
        view_menu.addAction(self.action_capture)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.action_about)

        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self.action_open_airfoil)
        toolbar.addAction(self.action_export_airfoil)
        toolbar.addSeparator()
        toolbar.addAction(self.action_mesh)
        toolbar.addAction(self.action_solve)
        toolbar.addAction(self.action_stop)
        toolbar.addAction(self.action_capture)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Work directory "))
        self.workdir_edit = QLineEdit(str(data_root() / "qt_cases"))
        self.workdir_edit.setMinimumWidth(340)
        toolbar.addWidget(self.workdir_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_workdir)
        toolbar.addWidget(browse)
        toolbar.addSeparator()
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("中文", "zh")
        self.language_combo.setMinimumWidth(92)
        self.language_combo.currentIndexChanged.connect(
            lambda: self._set_language(str(self.language_combo.currentData()))
        )
        toolbar.addWidget(self.language_combo)

    def _set_language(self, language: str) -> None:
        language = "zh" if language == "zh" else "en"
        self.ui_language = language

        def translated(source: str) -> str:
            return ZH_TEXT.get(source, source) if language == "zh" else source

        for widget in self.findChildren(QLabel):
            source = widget.property("i18n_source")
            if source is None:
                source = widget.text()
                widget.setProperty("i18n_source", source)
            widget.setText(translated(str(source)))
        for widget in self.findChildren(QAbstractButton):
            source = widget.property("i18n_source")
            if source is None:
                source = widget.text()
                widget.setProperty("i18n_source", source)
            widget.setText(translated(str(source)))
        for widget in self.findChildren(QGroupBox):
            source = widget.property("i18n_source")
            if source is None:
                source = widget.title()
                widget.setProperty("i18n_source", source)
            widget.setTitle(translated(str(source)))
        for widget in self.findChildren(QDockWidget):
            source = widget.property("i18n_source")
            if source is None:
                source = widget.windowTitle()
                widget.setProperty("i18n_source", source)
            widget.setWindowTitle(translated(str(source)))
        for action in self.findChildren(QAction):
            if action.isSeparator() or not action.text():
                continue
            source = action.property("i18n_source")
            if source is None:
                source = action.text()
                action.setProperty("i18n_source", source)
            action.setText(translated(str(source)))
        for combo in self.findChildren(QComboBox):
            if combo is self.language_combo:
                continue
            sources = self._combo_sources.setdefault(
                id(combo), [combo.itemText(index) for index in range(combo.count())]
            )
            combo.blockSignals(True)
            for index, source in enumerate(sources):
                if index < combo.count():
                    combo.setItemText(index, translated(source))
            combo.blockSignals(False)
        for index, source in enumerate(self._tab_sources):
            self.tabs.setTabText(index, translated(source))
        if hasattr(self, "result_display_tabs"):
            self.result_display_tabs.setTabText(0, translated("Flow field"))
            self.result_display_tabs.setTabText(1, translated("Reports / files"))

        def translate_item(item: QTreeWidgetItem) -> None:
            source = item.data(0, Qt.ItemDataRole.UserRole + 10)
            if source is None:
                source = item.text(0)
                item.setData(0, Qt.ItemDataRole.UserRole + 10, source)
            item.setText(0, translated(str(source)))
            for child_index in range(item.childCount()):
                translate_item(item.child(child_index))

        for tree in self.findChildren(QTreeWidget):
            for index in range(tree.topLevelItemCount()):
                translate_item(tree.topLevelItem(index))
        if hasattr(self, "editor"):
            self.editor.set_language(language)
        if hasattr(self, "mesh_update_button") and hasattr(self, "mesh_generate_button"):
            self._update_mesh_button_state()

    def _build_central(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.setCentralWidget(self.tabs)
        self.editor = AirfoilEditor(lambda: self.workdir_edit.text(), self)
        self.tabs.addTab(self.editor, "Airfoil Adjustment")
        self.mesh_viewer = VTKView(self, allow_rotation=False)
        self.mesh_viewer.status.connect(self._set_status)
        self.mesh_page = self._make_mesh_page(self.mesh_viewer)
        self.tabs.addTab(self.mesh_page, "Mesh Generation")
        self.solver_monitor = SolverConvergenceMonitor(self)
        self.solver_page = self._make_solver_page()
        self.tabs.addTab(self.solver_page, "Solver")
        self.results_page = self._build_results_page()
        self.tabs.addTab(self.results_page, "Results")
        self.optimization_page = self._build_optimization_page()
        self.tabs.addTab(self.optimization_page, "Adjoint Optimization")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.editor.status.connect(self._set_status)
        self.editor.geometryChanged.connect(self._geometry_changed)
        self.editor.airfoilPathChanged.connect(self._airfoil_path_changed)

    def _make_solver_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        heading = QLabel("Solver monitor")
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        layout.addWidget(self.solver_monitor, 1)
        return page

    def _make_mesh_page(self, viewer: VTKView) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        heading = QLabel("2D mesh inspection")
        heading.setProperty("heading", True)
        top.addWidget(heading)
        top.addStretch(1)
        self.mesh_update_button = QPushButton("Generate mesh")
        self.mesh_update_button.setProperty("accent", True)
        self.mesh_update_button.clicked.connect(lambda: self._start_backend("mesh"))
        top.addWidget(self.mesh_update_button)
        layout.addLayout(top)
        layout.addWidget(viewer, 1)
        return page

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.result_viewer = VTKView(self, allow_rotation=False)
        self.result_viewer.status.connect(self._set_status)
        self.result_viewer.fieldsChanged.connect(self._set_result_fields)
        self.result_viewer.rangeChanged.connect(self._result_range_changed)
        self.result_display_tabs = QTabWidget()
        self.result_display_tabs.addTab(self.result_viewer, "Flow field")
        report_page = QWidget()
        report_layout = QVBoxLayout(report_page)
        report_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.result_image = QLabel(
            "No saved report image. Flow fields open in this Results page."
        )
        self.result_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_image.setFrameShape(QFrame.Shape.StyledPanel)
        self.result_image.setMinimumSize(600, 400)
        self.result_image.setScaledContents(False)
        self.result_files = QTreeWidget()
        self.result_files.setHeaderLabels(["Result file", "Size"])
        self.result_files.itemDoubleClicked.connect(self._open_result_item)
        splitter.addWidget(self.result_image)
        splitter.addWidget(self.result_files)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        report_layout.addWidget(splitter, 1)
        self.result_display_tabs.addTab(report_page, "Reports / files")
        layout.addWidget(self.result_display_tabs, 1)
        return page

    def _build_optimization_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel("Discrete-adjoint workflow")
        heading.setProperty("heading", True)
        layout.addWidget(heading)
        message = QLabel(
            "The direct-flow case is handed to the existing SU2 discrete-adjoint backend. "
            "CST, compact D-BCE, hybrid and CST → D-BCE relay modes share the same task monitor."
        )
        message.setWordWrap(True)
        message.setProperty("muted", True)
        layout.addWidget(message)
        self.optimization_history = QTreeWidget()
        self.optimization_history.setHeaderLabels(
            ["Attempt", "Stage", "Accepted", "Objective", "Trust radius", "Time (s)"]
        )
        layout.addWidget(self.optimization_history, 1)
        action_row = QHBoxLayout()
        self.optimize_start = QPushButton("Start adjoint optimization")
        self.optimize_start.setProperty("accent", True)
        self.optimize_start.clicked.connect(self._start_optimization)
        self.optimize_stop = QPushButton("Stop")
        self.optimize_stop.setProperty("danger", True)
        self.optimize_stop.setEnabled(False)
        self.optimize_stop.clicked.connect(self.optimizer.terminate)
        action_row.addWidget(self.optimize_start)
        action_row.addWidget(self.optimize_stop)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return page

    def _build_pipeline_dock(self) -> None:
        dock = QDockWidget("Pipeline Browser", self)
        dock.setObjectName("PipelineDock")
        self.pipeline = QTreeWidget()
        self.pipeline.setHeaderHidden(True)
        root = QTreeWidgetItem(["SU2 Airfoil Project"])
        root.setExpanded(True)
        for text in (
            "Airfoil Adjustment",
            "Mesh Generation",
            "Solver",
            "Results",
            "Adjoint Optimization",
        ):
            root.addChild(QTreeWidgetItem([text]))
        self.pipeline.addTopLevelItem(root)
        self.pipeline.itemClicked.connect(self._pipeline_clicked)
        dock.setWidget(self.pipeline)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.pipeline_dock = dock

    def _build_properties_dock(self) -> None:
        dock = QDockWidget("Properties", self)
        dock.setObjectName("PropertiesDock")
        self.properties = QStackedWidget()
        self.properties.addWidget(self._bce_properties())
        self.properties.addWidget(self._mesh_properties())
        self.properties.addWidget(self._solver_properties())
        self.properties.addWidget(self._results_properties())
        self.properties.addWidget(self._optimization_properties())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.properties)
        dock.setWidget(scroll)
        dock.setMinimumWidth(310)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.properties_dock = dock

    def _panel(self, title: str) -> tuple[QWidget, QFormLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(4, 4, 4, 4)
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setContentsMargins(5, 7, 5, 5)
        form.setHorizontalSpacing(7)
        form.setVerticalSpacing(4)
        outer.addWidget(group)
        outer.addStretch(1)
        return page, form

    def _bce_properties(self) -> QWidget:
        page, form = self._panel("BCE editor")
        label = QLabel("Drag orange control points. Chordwise range stays fixed; vertical range expands in 0.025c steps.")
        label.setWordWrap(True)
        label.setProperty("muted", True)
        form.addRow(label)
        self.geometry_valid_label = QLabel("Geometry valid")
        form.addRow("State", self.geometry_valid_label)
        return page

    def _mesh_properties(self) -> QWidget:
        page, form = self._panel("C-H structured mesh")
        self.surface_points = _integer(100, 50, 800, 10)
        self.global_refinement = _double(1.0, 0.05, 10.0, 2, 0.05)
        self.leading_edge_size = _double(0.0015, 0.0001, 0.05, 5, 0.0001)
        self.trailing_upper_size = _double(0.0015, 0.0001, 0.05, 5, 0.0001)
        self.trailing_lower_size = _double(0.0015, 0.0001, 0.05, 5, 0.0001)
        self.wake_refinement = _double(2.0, 1.0, 12.0, 2, 0.25)
        self.y_plus = _double(1.0, 0.01, 500.0, 2, 0.1)
        self.farfield = _double(20.0, 2.0, 200.0, 1, 1.0)
        self.domain_scale = _double(1.0, 0.25, 10.0, 2, 0.25)
        self.growth_ratio = _double(1.15, 1.01, 2.0, 3, 0.01)
        self.bl_thickness = _double(0.08, 0.005, 1.0, 3, 0.01)
        self.farfield_size = _double(0.4, 0.01, 5.0, 3, 0.05)
        for label, widget in (
            ("Surface points / side", self.surface_points),
            ("Global refinement", self.global_refinement),
            ("Leading-edge size", self.leading_edge_size),
            ("Upper TE size", self.trailing_upper_size),
            ("Lower TE size", self.trailing_lower_size),
            ("Wake refinement", self.wake_refinement),
            ("Target Y+", self.y_plus),
            ("Farfield / chord", self.farfield),
            ("Domain scale", self.domain_scale),
            ("BL growth ratio", self.growth_ratio),
            ("BL thickness / chord", self.bl_thickness),
            ("Farfield cell size", self.farfield_size),
        ):
            form.addRow(label, widget)
        self.mesh_generate_button = QPushButton("Generate mesh")
        self.mesh_generate_button.setProperty("accent", True)
        self.mesh_generate_button.clicked.connect(lambda: self._start_backend("mesh"))
        form.addRow(self.mesh_generate_button)
        for widget in (
            self.surface_points,
            self.global_refinement,
            self.leading_edge_size,
            self.trailing_upper_size,
            self.trailing_lower_size,
            self.wake_refinement,
            self.y_plus,
            self.farfield,
            self.domain_scale,
            self.growth_ratio,
            self.bl_thickness,
            self.farfield_size,
        ):
            widget.valueChanged.connect(self._update_mesh_button_state)
        return page

    def _solver_properties(self) -> QWidget:
        page, form = self._panel("SU2 direct solver")
        self.solver = QComboBox()
        self.solver.addItems(["RANS", "EULER"])
        self.turbulence = QComboBox()
        self.turbulence.addItems(["SA", "SST"])
        self.mach = _double(0.15, 0.001, 5.0, 4, 0.01)
        self.aoa = _double(2.0, -30.0, 30.0, 3, 0.25)
        self.reynolds = _double(3_000_000.0, 1_000.0, 1.0e9, 0, 100_000.0)
        self.temperature = _double(288.15, 50.0, 2000.0, 2, 1.0)
        self.cfl = _double(5.0, 0.1, 1000.0, 2, 1.0)
        self.residual_min = _double(-8.0, -14.0, -1.0, 2, 0.5)
        self.iterations = _integer(1000, 1, 100000, 100)
        self.threads = _integer(1, 1, 64, 1)
        for label, widget in (
            ("Solver", self.solver),
            ("Turbulence", self.turbulence),
            ("Mach", self.mach),
            ("Angle of attack", self.aoa),
            ("Reynolds", self.reynolds),
            ("Temperature [K]", self.temperature),
            ("CFL", self.cfl),
            ("Residual target", self.residual_min),
            ("Iterations", self.iterations),
            ("OpenMP threads", self.threads),
        ):
            form.addRow(label, widget)
        button = QPushButton("Run CFD")
        button.setProperty("accent", True)
        button.clicked.connect(lambda: self._start_backend("solve"))
        form.addRow(button)
        return page

    def _results_properties(self) -> QWidget:
        page, form = self._panel("Display")
        self.field_combo = QComboBox()
        self.field_combo.addItems(["Mach", "Pressure", "Pressure_Coefficient", "Temperature", "Y_Plus"])
        self.auto_range = QCheckBox("Automatic color range")
        self.auto_range.setChecked(True)
        self.range_min = _double(0.0, -1.0e9, 1.0e9, 5, 0.1)
        self.range_max = _double(1.0, -1.0e9, 1.0e9, 5, 0.1)
        form.addRow("Field", self.field_combo)
        form.addRow(self.auto_range)
        form.addRow("Minimum", self.range_min)
        form.addRow("Maximum", self.range_max)
        apply_button = QPushButton("Apply field / color range")
        apply_button.setProperty("accent", True)
        apply_button.clicked.connect(self._apply_result_field)
        form.addRow(apply_button)
        self.show_axis = QCheckBox("Chord axis + AoA angle")
        self.show_axis.setChecked(True)
        form.addRow(self.show_axis)
        self.overlay_airfoil = QCheckBox("Overlay: airfoil name")
        self.overlay_mach = QCheckBox("Overlay: Mach")
        self.overlay_aoa = QCheckBox("Overlay: angle of attack")
        self.overlay_reynolds = QCheckBox("Overlay: Reynolds")
        self.overlay_field = QCheckBox("Overlay: field name")
        self.overlay_position = QComboBox()
        self.overlay_position.addItem("Top center", "top_center")
        self.overlay_position.addItem("Top left", "top_left")
        self.overlay_position.addItem("Top right", "top_right")
        self.overlay_position.setCurrentIndex(2)
        form.addRow("Overlay position", self.overlay_position)
        self.overlay_text_color = QComboBox()
        self.overlay_text_color.addItem("White", "white")
        self.overlay_text_color.addItem("Black", "black")
        form.addRow("Overlay text color", self.overlay_text_color)
        self.overlay_text_color.currentIndexChanged.connect(self._update_result_annotations)
        self.colormap = QComboBox()
        for label, value in (
            ("Jet", "jet"),
            ("Turbo", "turbo"),
            ("Viridis", "viridis"),
            ("Plasma", "plasma"),
            ("Coolwarm", "coolwarm"),
            ("Grayscale", "grayscale"),
        ):
            self.colormap.addItem(label, value)
        form.addRow("Colormap", self.colormap)
        self.colormap.currentIndexChanged.connect(self._update_colormap)
        self.overlay_position.currentIndexChanged.connect(self._update_result_annotations)
        for widget, checked in (
            (self.overlay_airfoil, True),
            (self.overlay_mach, True),
            (self.overlay_aoa, True),
            (self.overlay_reynolds, False),
            (self.overlay_field, True),
        ):
            widget.setChecked(checked)
            form.addRow(widget)
            widget.toggled.connect(self._update_result_annotations)
        self.show_axis.toggled.connect(self._update_result_annotations)
        self.field_combo.currentTextChanged.connect(self._field_selection_changed)
        self.auto_range.toggled.connect(self._range_mode_changed)
        self._range_mode_changed(True)
        return page

    def _update_result_annotations(self, *_args) -> None:
        self.result_viewer.set_annotations(
            show_axis=self.show_axis.isChecked(),
            position=self.overlay_position.currentData(),
            text_color=self.overlay_text_color.currentData(),
            airfoil=self.overlay_airfoil.isChecked(),
            mach=self.overlay_mach.isChecked(),
            aoa=self.overlay_aoa.isChecked(),
            reynolds=self.overlay_reynolds.isChecked(),
            field=self.overlay_field.isChecked(),
        )

    def _update_colormap(self, *_args) -> None:
        self.result_viewer.set_colormap(str(self.colormap.currentData()))

    def _optimization_properties(self) -> QWidget:
        page, form = self._panel("Adjoint optimization")
        self.opt_case = QLineEdit()
        self.opt_case.setPlaceholderText("Run a direct CFD case or select an existing case")
        case_browse = QPushButton("Select case…")
        case_browse.clicked.connect(self._browse_optimization_case)
        case_row = QWidget()
        case_layout = QHBoxLayout(case_row)
        case_layout.setContentsMargins(0, 0, 0, 0)
        case_layout.addWidget(self.opt_case, 1)
        case_layout.addWidget(case_browse)
        self.su2_bin = QLineEdit(str(self._discover_adjoint_bin() or ""))
        su2_browse = QPushButton("Select SU2 bin…")
        su2_browse.clicked.connect(self._browse_su2_bin)
        su2_row = QWidget()
        su2_layout = QHBoxLayout(su2_row)
        su2_layout.setContentsMargins(0, 0, 0, 0)
        su2_layout.addWidget(self.su2_bin, 1)
        su2_layout.addWidget(su2_browse)
        self.parameterization = QComboBox()
        self.parameterization.addItems(["CST → D-BCE relay", "D-BCE", "CST", "Hybrid"])
        self.objective = QComboBox()
        self.objective.addItems(["Fixed AoA: minimize CD", "Fixed CL: minimize CD"])
        self.deformation_mode = QComboBox()
        self.deformation_mode.addItems(["Camber + thickness", "Camber", "Thickness"])
        self.min_thickness = _double(0.005, 0.0001, 0.5, 5, 0.001)
        self.max_displacement = _double(0.01, 0.00001, 0.2, 5, 0.001)
        self.trust_radius = _double(0.0002, 0.000001, 0.01, 6, 0.00005)
        self.optimization_steps = _integer(6, 1, 100, 1)
        self.cst_variables = _integer(12, 2, 100, 1)
        self.bce_variables = _integer(6, 1, 100, 1)
        self.bce_min_half_width = _double(0.05, 0.01, 0.30, 3, 0.005)
        self.bce_min_support_points = _integer(12, 6, 200, 1)
        self.adjoint_iterations = _integer(800, 10, 100000, 100)
        self.adjoint_cfl = _double(50.0, 0.1, 1000.0, 2, 5.0)
        self.target_cl = _double(0.5, -5.0, 5.0, 5, 0.05)
        form.addRow("Direct-flow case", case_row)
        form.addRow("SU2 AD bin", su2_row)
        for label, widget in (
            ("Parameterization", self.parameterization),
            ("Objective", self.objective),
            ("Shape variables", self.deformation_mode),
            ("Minimum thickness", self.min_thickness),
            ("Maximum displacement", self.max_displacement),
            ("Initial trust radius", self.trust_radius),
            ("Optimization attempts", self.optimization_steps),
            ("CST variables", self.cst_variables),
            ("D-BCE variables", self.bce_variables),
            ("Minimum D-BCE half-width", self.bce_min_half_width),
            ("Minimum brush support nodes", self.bce_min_support_points),
            ("Adjoint iterations", self.adjoint_iterations),
            ("Adjoint CFL", self.adjoint_cfl),
            ("Target CL", self.target_cl),
        ):
            form.addRow(label, widget)
        button = QPushButton("Start adjoint optimization")
        button.setProperty("accent", True)
        button.clicked.connect(self._start_optimization)
        form.addRow(button)
        return page

    def _build_output_dock(self) -> None:
        dock = QDockWidget("Output / Convergence Log", self)
        dock.setObjectName("OutputDock")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(10000)
        dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.output_dock = dock
        self.resizeDocks([dock], [190], Qt.Orientation.Vertical)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.status_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(220)
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.progress)

    def _connect_backend(self) -> None:
        self.backend.log.connect(self._log)
        self.backend.started.connect(lambda: self._set_status("Backend task started"))
        self.backend.runningChanged.connect(self._running_changed)
        self.backend.finished.connect(self._backend_finished)
        self.backend.failed.connect(self._backend_failed)
        self.optimizer.log.connect(self._log)
        self.optimizer.runningChanged.connect(self._optimizer_running_changed)
        self.optimizer.finished.connect(self._optimizer_finished)

    def _restore_state(self) -> None:
        geometry = self.settings.value("geometry")
        state = self.settings.value("state")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)
        workdir = self.settings.value("workdir")
        if workdir:
            self.workdir_edit.setText(str(workdir))

    def _reset_layout(self) -> None:
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.pipeline_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.output_dock)
        for dock in (self.pipeline_dock, self.properties_dock, self.output_dock):
            dock.show()

    @staticmethod
    def _discover_adjoint_bin() -> Path | None:
        candidates: list[Path] = []
        if os.environ.get("SU2_PARAMETRIC_BIN"):
            candidates.append(Path(os.environ["SU2_PARAMETRIC_BIN"]))
        candidates.extend(
            (
                resource_root() / "solvers" / "SU2" / "bin",
                resource_root().parent / "solvers" / "SU2" / "bin",
                Path("E:/MyUniversity/BrainStorm/BrushAirfoil/third_party/SU2-8.5.0-ad/install_ad_mingw/bin"),
            )
        )
        required = ("SU2_CFD.exe", "SU2_CFD_AD.exe", "SU2_DOT_AD.exe", "SU2_DEF.exe")
        return next((path.resolve() for path in candidates if all((path / name).is_file() for name in required)), None)

    @staticmethod
    def _runtime_bin(su2_bin: Path) -> Path | None:
        dlls = ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")
        if all((su2_bin / name).is_file() for name in dlls):
            return su2_bin
        candidates = (
            resource_root() / "third_party" / "msys2-portable" / "msys64" / "ucrt64" / "bin",
            su2_bin.parent / "runtime",
        )
        return next((path.resolve() for path in candidates if all((path / name).is_file() for name in dlls)), None)

    def _browse_optimization_case(self) -> None:
        start = self.opt_case.text() or (str(self.current_case) if self.current_case else self.workdir_edit.text())
        path = QFileDialog.getExistingDirectory(self, "Select solved SU2 case", start)
        if path:
            self.opt_case.setText(path)

    def _browse_su2_bin(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select SU2 AD bin", self.su2_bin.text())
        if path:
            self.su2_bin.setText(path)

    def _prepare_optimization(self) -> tuple[Path, Path]:
        case_text = self.opt_case.text().strip()
        case = Path(case_text).expanduser().resolve() if case_text else self.current_case
        if case is None:
            raise ValueError("Run direct CFD first or select a solved case directory.")
        su2_bin_text = self.su2_bin.text().strip()
        su2_bin = Path(su2_bin_text).expanduser().resolve() if su2_bin_text else self._discover_adjoint_bin()
        if su2_bin is None:
            raise FileNotFoundError("Select a SU2 bin containing CFD, CFD_AD, DOT_AD and DEF executables.")
        methods = ("relay", "bce", "cst", "hybrid")
        shapes = ("both", "camber", "thickness")
        objective_mode = "fixed_aoa" if self.objective.currentIndex() == 0 else "fixed_lift"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        config_path = case / "parametric_optimization" / f"qt_study_{stamp}.json"
        target_cl = self.target_cl.value() if objective_mode == "fixed_lift" else None
        prepare_case_config(
            case_dir=case,
            su2_bin=su2_bin,
            output_config=config_path,
            runtime_bin=self._runtime_bin(su2_bin),
            mode=methods[self.parameterization.currentIndex()],
            objective_mode=objective_mode,
            target_cl=target_cl,
            dcl_dalpha=0.1 if target_cl is not None else None,
            dcd_dcl=0.01 if target_cl is not None else None,
        )
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        output = config_path.parent / stamp
        payload["output"] = str(output.resolve())
        payload["steps"] = self.optimization_steps.value()
        payload["parameterization"].update(
            {
                "shape_mode": shapes[self.deformation_mode.currentIndex()],
                "cst_variables": self.cst_variables.value(),
                "bce_variables": self.bce_variables.value(),
                "bce_min_half_width": self.bce_min_half_width.value(),
                "bce_min_support_points": self.bce_min_support_points.value(),
            }
        )
        payload["constraints"].update(
            {
                "min_thickness": self.min_thickness.value(),
                "max_displacement": self.max_displacement.value(),
            }
        )
        payload["trust_region"]["initial_radius"] = self.trust_radius.value()
        payload["solver"].update(
            {
                "adjoint_iterations": self.adjoint_iterations.value(),
                "adjoint_cfl": self.adjoint_cfl.value(),
                "threads": self.threads.value(),
            }
        )
        payload["case"].update(
            {"mach": self.mach.value(), "reynolds": self.reynolds.value(), "aoa_deg": self.aoa.value()}
        )
        config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return config_path, output

    def _start_optimization(self) -> None:
        if self.backend.running or self.optimizer.running:
            QMessageBox.warning(self, "Busy", "Wait for or stop the current task first.")
            return
        try:
            config_path, output = self._prepare_optimization()
            output.mkdir(parents=True, exist_ok=True)
            self.optimization_output = output
            self.optimizer.start(config_path)
        except Exception as exc:
            QMessageBox.critical(self, "Optimization start failed", str(exc))
            return
        self._log(f"OPTIMIZATION {config_path}")
        self.progress.setRange(0, 0)
        self.tabs.setCurrentIndex(4)

    def _optimizer_running_changed(self, running: bool) -> None:
        self.optimize_start.setEnabled(not running)
        self.optimize_stop.setEnabled(running)
        self.action_mesh.setEnabled(not running and not self.backend.running)
        self.action_solve.setEnabled(not running and not self.backend.running)
        self.action_stop.setEnabled(running or self.backend.running)
        self._update_mesh_button_state()
        if not running:
            self.progress.setRange(0, 100)

    def _optimizer_finished(self, exit_code: int) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if exit_code == 0 else 0)
        if exit_code:
            self._set_status(f"Optimization failed (exit {exit_code})")
            QMessageBox.critical(self, "Optimization failed", "See Output / Convergence Log for details.")
            return
        self._set_status("Adjoint optimization completed")
        self._load_optimization_history()

    def _load_optimization_history(self) -> None:
        output = getattr(self, "optimization_output", None)
        history = output / "optimization_history.csv" if output else None
        self.optimization_history.clear()
        if history is None or not history.is_file():
            self._log("Optimization completed without optimization_history.csv")
            return
        with history.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                values = [
                    row.get("attempt", row.get("step", "")),
                    row.get("stage", ""),
                    row.get("accepted", ""),
                    row.get("objective", row.get("cd", "")),
                    row.get("trust_radius", ""),
                    row.get("total_seconds", row.get("selection_seconds", "")),
                ]
                self.optimization_history.addTopLevelItem(QTreeWidgetItem(values))
        final_airfoil = output / "final_airfoil.dat"
        if final_airfoil.is_file():
            self._log(f"Optimized airfoil: {final_airfoil}")

    def _stop_tasks(self) -> None:
        if self.backend.running:
            self.backend.terminate()
        if self.optimizer.running:
            self.optimizer.terminate()

    def _browse_workdir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select work directory", self.workdir_edit.text())
        if path:
            self.workdir_edit.setText(path)

    def _open_mesh_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open SU2 mesh", self.workdir_edit.text(), "SU2 mesh (*.su2);;All files (*)"
        )
        if not path:
            return
        try:
            self.mesh_viewer.load_su2(path)
            self._mark_mesh_current()
            self.tabs.setCurrentIndex(1)
        except Exception as exc:
            QMessageBox.critical(self, "Mesh display failed", str(exc))

    def _open_vtu_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open VTU result", self.workdir_edit.text(), "VTK unstructured grid (*.vtu);;All files (*)"
        )
        if not path:
            return
        try:
            self.result_viewer.load_vtu(path)
            self.result_display_tabs.setCurrentIndex(0)
            self.tabs.setCurrentIndex(3)
        except Exception as exc:
            QMessageBox.critical(self, "VTU display failed", str(exc))

    def _tab_changed(self, index: int) -> None:
        self.properties.setCurrentIndex(index)

    def _pipeline_clicked(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        if parent is None:
            return
        index = parent.indexOfChild(item)
        self.tabs.setCurrentIndex(index)

    @staticmethod
    def _geometry_digest(x, upper, lower) -> str:
        digest = hashlib.sha256()
        for values in (x, upper, lower):
            digest.update(memoryview(values.astype("<f8", copy=False)))
        return digest.hexdigest()

    def _mesh_settings_signature(self) -> tuple | None:
        if not hasattr(self, "surface_points"):
            return None
        return tuple(self._parameters()[name] for name in (
            "surface_points",
            "global_refinement",
            "leading_edge_size",
            "trailing_upper_size",
            "trailing_lower_size",
            "wake_refinement",
            "y_plus",
            "farfield",
            "domain_scale",
            "growth_ratio",
            "boundary_layer_thickness",
            "farfield_size",
        ))

    def _update_mesh_button_state(self, *_args) -> None:
        if not hasattr(self, "mesh_update_button") or not hasattr(self, "mesh_generate_button"):
            return
        geometry_stale = (
            self._mesh_exists
            and self._meshed_geometry_signature != self._geometry_signature
        )
        settings_stale = (
            self._mesh_exists
            and self._meshed_settings_signature != self._mesh_settings_signature()
        )
        if not self._mesh_exists:
            source = "Generate mesh"
            enabled = True
            accent = True
        elif geometry_stale:
            source = "Airfoil changed — update mesh"
            enabled = True
            accent = True
        elif settings_stale:
            source = "Mesh settings changed — update mesh"
            enabled = True
            accent = True
        else:
            source = "Mesh up to date"
            enabled = False
            accent = False
        text = ZH_TEXT.get(source, source) if getattr(self, "ui_language", "en") == "zh" else source
        busy = self.backend.running or self.optimizer.running
        for button in (self.mesh_update_button, self.mesh_generate_button):
            button.setText(text)
            button.setProperty("accent", accent)
            button.setEnabled(enabled and not busy)
            button.style().unpolish(button)
            button.style().polish(button)

    def _mark_mesh_current(self) -> None:
        self._mesh_exists = True
        self._meshed_geometry_signature = self._geometry_signature
        self._meshed_settings_signature = self._mesh_settings_signature()
        self._update_mesh_button_state()

    def _geometry_changed(self, x, upper, lower) -> None:
        thickness = float((upper - lower).max())
        minimum = float((upper[2:-2] - lower[2:-2]).min())
        self.geometry_valid_label.setText(f"t/c max={thickness:.5f} | min={minimum:.5f}")
        signature = self._geometry_digest(x, upper, lower)
        if signature != self._geometry_signature:
            self._geometry_signature = signature
            self._update_mesh_button_state()

    def _airfoil_path_changed(self, path: str) -> None:
        self.current_airfoil = path
        self._log(f"Current airfoil: {path}")

    def _parameters(self) -> dict:
        return {
            "surface_points": self.surface_points.value(),
            "global_refinement": self.global_refinement.value(),
            "leading_edge_size": self.leading_edge_size.value(),
            "trailing_upper_size": self.trailing_upper_size.value(),
            "trailing_lower_size": self.trailing_lower_size.value(),
            "wake_refinement": self.wake_refinement.value(),
            "y_plus": self.y_plus.value(),
            "farfield": self.farfield.value(),
            "domain_scale": self.domain_scale.value(),
            "growth_ratio": self.growth_ratio.value(),
            "boundary_layer_thickness": self.bl_thickness.value(),
            "farfield_size": self.farfield_size.value(),
            "solver": self.solver.currentText(),
            "turbulence": self.turbulence.currentText(),
            "mach": self.mach.value(),
            "aoa": self.aoa.value(),
            "reynolds": self.reynolds.value(),
            "temperature": self.temperature.value(),
            "cfl": self.cfl.value(),
            "residual_min": self.residual_min.value(),
            "iterations": self.iterations.value(),
            "threads": self.threads.value(),
            "language": "zh",
        }

    def _start_backend(self, mode: str) -> None:
        if self.backend.running or self.optimizer.running:
            QMessageBox.warning(self, "Busy", "Wait for or stop the current task first.")
            return
        workdir = Path(self.workdir_edit.text()).expanduser()
        workdir.mkdir(parents=True, exist_ok=True)
        try:
            airfoil = self.editor.ensure_exported()
        except Exception as exc:
            QMessageBox.critical(self, "Airfoil export failed", str(exc))
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = workdir / f"Qt_{mode}_{stamp}"
        self._active_backend_mode = mode
        self._active_backend_output = output
        request = {
            "api_version": 1,
            "mode": mode,
            "airfoil": airfoil,
            "output_dir": str(output),
            "parameters": self._parameters(),
        }
        self._log("REQUEST " + json.dumps(request, ensure_ascii=False))
        self.progress.setRange(0, 0)
        if mode == "solve":
            self.solver_monitor.start(output / "history.csv")
            self.convergence_timer.start()
            self.tabs.setCurrentIndex(2)
        try:
            self.backend.start_request(request)
        except Exception as exc:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            QMessageBox.critical(self, "Backend start failed", str(exc))

    def _running_changed(self, running: bool) -> None:
        self.action_mesh.setEnabled(not running and not self.optimizer.running)
        self.action_solve.setEnabled(not running and not self.optimizer.running)
        self.action_stop.setEnabled(running or self.optimizer.running)
        self._update_mesh_button_state()
        if not running:
            self.progress.setRange(0, 100)

    def _backend_finished(self, result: dict) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.current_case = Path(result["output_dir"])
        self.opt_case.setText(str(self.current_case))
        self._set_status(f"Completed: {self.current_case.name}")
        self._log(json.dumps(result.get("last_values", {}), ensure_ascii=False, indent=2))
        self._populate_results(result)
        mode = result.get("mode")
        if mode in {"mesh", "solve"}:
            self._mark_mesh_current()
        if mode == "solve":
            self.convergence_timer.stop()
            self.solver_monitor.finish(result.get("last_values", {}))
            self.tabs.setCurrentIndex(3)
        else:
            self.tabs.setCurrentIndex(1)
        self._active_backend_mode = None

    def _backend_failed(self, message: str) -> None:
        self.convergence_timer.stop()
        self.solver_monitor.refresh()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._set_status("Task failed")
        self._log("ERROR: " + message)
        self._active_backend_mode = None
        QMessageBox.critical(self, "Task failed", message)

    def _populate_results(self, result: dict) -> None:
        self.result_files.clear()
        images: list[Path] = []
        mesh_path: Path | None = None
        flow_path: Path | None = None
        for relative, absolute in sorted(result.get("files", {}).items()):
            path = Path(absolute)
            size = path.stat().st_size if path.is_file() else 0
            item = QTreeWidgetItem([relative, f"{size / 1024:.1f} KiB"])
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            self.result_files.addTopLevelItem(item)
            if path.suffix.lower() == ".png":
                images.append(path)
            if path.name.lower() == "mesh.su2":
                mesh_path = path
            if path.name.lower() == "flow.vtu":
                flow_path = path
        if mesh_path is not None:
            try:
                self.mesh_viewer.load_su2(mesh_path)
            except Exception as exc:
                self._log(f"VTK mesh display failed: {exc}")
        if flow_path is not None:
            try:
                self.result_viewer.load_vtu(flow_path)
                self.result_display_tabs.setCurrentIndex(0)
            except Exception as exc:
                self._log(f"VTK field display failed: {exc}")
        preferred = next((p for p in images if "Contour" in p.name), None)
        preferred = preferred or next((p for p in images if "Convergence" in p.name), None)
        preferred = preferred or (images[0] if images else None)
        if preferred:
            self._show_image(preferred, switch=flow_path is None)

    def _show_image(self, path: Path, *, switch: bool = True) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        margins = self.result_image.contentsMargins()
        target = self.result_image.size()
        target.setWidth(max(1, target.width() - margins.left() - margins.right()))
        target.setHeight(max(1, target.height() - margins.top() - margins.bottom()))
        self.result_image.setPixmap(pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.result_image.setToolTip(str(path))
        if switch:
            self.result_display_tabs.setCurrentIndex(1)
            self.tabs.setCurrentIndex(3)

    def _open_result_item(self, item: QTreeWidgetItem) -> None:
        path = Path(item.data(0, Qt.ItemDataRole.UserRole))
        if path.suffix.lower() == ".png":
            self._show_image(path)
        elif path.suffix.lower() == ".vtu":
            try:
                self.result_viewer.load_vtu(path)
                self.result_display_tabs.setCurrentIndex(0)
                self.tabs.setCurrentIndex(3)
            except Exception as exc:
                QMessageBox.critical(self, "VTU display failed", str(exc))
        elif path.suffix.lower() == ".su2":
            try:
                self.mesh_viewer.load_su2(path)
                self._mark_mesh_current()
                self.tabs.setCurrentIndex(1)
            except Exception as exc:
                QMessageBox.critical(self, "Mesh display failed", str(exc))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _set_result_fields(self, fields: list[str]) -> None:
        selected = self.result_viewer.current_field
        self.field_combo.blockSignals(True)
        self.field_combo.clear()
        self.field_combo.addItems(fields)
        if selected in fields:
            self.field_combo.setCurrentText(selected)
        self.field_combo.blockSignals(False)

    def _result_range_changed(self, lower: float, upper: float) -> None:
        self.range_min.setValue(lower)
        self.range_max.setValue(upper)

    def _range_mode_changed(self, automatic: bool) -> None:
        self.range_min.setEnabled(not automatic)
        self.range_max.setEnabled(not automatic)

    def _field_selection_changed(self, name: str) -> None:
        if name and self.result_viewer.dataset is not None and self.auto_range.isChecked():
            try:
                self.result_viewer.set_field(name, auto=True)
            except Exception as exc:
                self._log(f"Field selection failed: {exc}")

    def _apply_result_field(self) -> None:
        name = self.field_combo.currentText()
        if not name:
            QMessageBox.information(self, "No field", "Load a flow.vtu result first.")
            return
        try:
            limits = None if self.auto_range.isChecked() else (self.range_min.value(), self.range_max.value())
            self.result_viewer.set_field(name, auto=self.auto_range.isChecked(), limits=limits)
            self.result_display_tabs.setCurrentIndex(0)
            self.tabs.setCurrentIndex(3)
        except Exception as exc:
            QMessageBox.critical(self, "Color range failed", str(exc))

    def _log(self, text: str) -> None:
        if text:
            self.log_view.appendPlainText(text)
            scrollbar = self.log_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.statusBar().showMessage(text, 5000)

    def _capture_workspace(self) -> None:
        """Save a lossless, full-window UI capture for reports and support."""
        labels = ("airfoil", "mesh", "solver", "results", "adjoint")
        page = labels[self.tabs.currentIndex()] if self.tabs.currentIndex() < len(labels) else "workspace"
        language = str(self.language_combo.currentData() or "en")
        directory = Path(self.workdir_edit.text()).expanduser() / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = directory / f"{page}_{language}_{stamp}.png"
        if not self.grab().save(str(path), "PNG"):
            QMessageBox.critical(self, "Capture failed", str(path))
            return
        self._log(f"Workspace capture: {path}")
        self._set_status(f"Saved: {path.name}")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About SU2 Airfoil Studio Qt",
            f"SU2 Airfoil Studio\nQt frontend {QT_FRONTEND_VERSION}\nValidated backend {APP_VERSION}\n\n"
            "Qt 6 dock-based migration inspired by ParaView's desktop interaction model.",
        )
