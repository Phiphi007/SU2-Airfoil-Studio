from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDockWidget  # noqa: E402

from qt_app.main_window import MainWindow  # noqa: E402
from qt_app.theme import apply_industrial_theme  # noqa: E402
from qt_app.vtk_viewer import _case_metadata  # noqa: E402


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    apply_industrial_theme(app)
    return app


def test_qt_workspace_and_bce_handoff(application, tmp_path: Path) -> None:
    assert application.font().family() == "Noto Sans CJK SC"
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    assert window.tabs.count() == 5
    assert window.mesh_viewer is not window.result_viewer
    assert window.mesh_viewer.allow_rotation is False
    assert window.result_display_tabs.indexOf(window.result_viewer) == 0
    assert not window.solver_pause_button.isEnabled()
    assert not window.solver_stop_now_button.isEnabled()
    assert not window.solver_stop_saved_button.isEnabled()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Airfoil Adjustment", "Mesh Generation", "Solver", "Results", "Adjoint Optimization"
    ]
    assert {dock.objectName() for dock in window.findChildren(QDockWidget)} == {
        "PipelineDock",
        "PropertiesDock",
        "OutputDock",
    }

    legacy = Path(window.editor.ensure_exported())
    handoff = tmp_path / "handoff.dat"
    rmse, variables = window.editor.canvas.dbce_handoff(handoff)
    assert legacy.is_file()
    assert handoff.is_file()
    assert rmse <= 1.0e-10
    assert variables > 0
    window.close()
    application.processEvents()


def test_qt_adjoint_controls_are_connected(application) -> None:
    window = MainWindow()
    assert window.optimize_start.isEnabled()
    assert window.parameterization.count() == 4
    assert window.deformation_mode.count() == 3
    assert window.optimization_steps.minimum() == 1
    assert window.bce_min_half_width.value() == pytest.approx(0.05)
    assert window.bce_min_support_points.value() == 12
    assert window.action_open_mesh.isEnabled()
    assert window.action_open_vtu.isEnabled()
    assert window.show_axis.isChecked()
    assert window.overlay_mach.isChecked()
    assert not window.overlay_reynolds.isChecked()
    assert window.overlay_position.count() == 3
    assert window.overlay_position.currentData() == "top_right"
    window.overlay_position.setCurrentIndex(0)
    assert window.result_viewer.annotation_position == "top_center"
    assert window.overlay_text_color.count() == 7
    window.overlay_text_color.setCurrentIndex(window.overlay_text_color.findData("black"))
    assert window.result_viewer.annotation_text_color == "black"
    assert window.axis_color.count() == 7
    window.axis_color.setCurrentIndex(window.axis_color.findData("cyan"))
    assert window.result_viewer.axis_color == "cyan"
    assert window.theme_combo.count() == 8
    window.theme_combo.setCurrentIndex(window.theme_combo.findData("deep_blue"))
    assert window.theme_combo.currentData() == "deep_blue"
    assert window.theme_combo.findData("rose") >= 0
    assert window.mesh_annotation_color.count() == 8
    assert window.mesh_annotation_color.currentData() == "auto"
    window.mesh_annotation_color.setCurrentIndex(
        window.mesh_annotation_color.findData("black")
    )
    assert window.mesh_viewer.annotation_text_color == "black"
    assert not window.show_result_mesh_edges.isChecked()
    assert window.result_mesh_edge_color.count() == 7
    window.show_result_mesh_edges.setChecked(True)
    window.result_mesh_edge_color.setCurrentIndex(
        window.result_mesh_edge_color.findData("red")
    )
    assert window.result_viewer.mesh_edges_visible
    assert window.result_viewer.mesh_edge_color == "red"
    assert window.show_airfoil_outline.isChecked()
    assert window.airfoil_outline_color.count() == 7
    window.show_airfoil_outline.setChecked(False)
    window.airfoil_outline_color.setCurrentIndex(
        window.airfoil_outline_color.findData("cyan")
    )
    assert not window.result_viewer.airfoil_outline_visible
    assert window.result_viewer.airfoil_outline_color == "cyan"
    assert window.thread_mode.count() == 2
    window.thread_mode.setCurrentIndex(window.thread_mode.findData("auto"))
    assert window._effective_threads() == window.auto_threads
    window.thread_mode.setCurrentIndex(window.thread_mode.findData("manual"))
    window.threads.setValue(3)
    assert window._effective_threads() == 3
    assert window.live_contour.isChecked()
    window.live_contour_interval.setValue(20)
    assert window.live_flow_timer.interval() == 20_000
    assert window.colormap.count() == 6
    window.colormap.setCurrentIndex(window.colormap.findData("viridis"))
    assert window.result_viewer.colormap_name == "viridis"
    window.close()
    application.processEvents()


def test_live_contour_refreshes_only_stable_new_field(application, tmp_path: Path) -> None:
    import time

    window = MainWindow()
    case = tmp_path / "case"
    case.mkdir()
    flow = case / "flow.vtu"
    flow.write_bytes(b"x" * 2048)
    old = time.time() - 3.0
    os.utime(flow, (old, old))
    loaded: list[tuple[Path, bool]] = []
    window.result_viewer.load_vtu = lambda path, preserve_view=False: loaded.append(
        (Path(path), preserve_view)
    )
    window._active_backend_mode = "solve"
    window._active_backend_output = case
    window._refresh_live_flow()
    assert loaded == [(flow, False)]
    window._refresh_live_flow()
    assert len(loaded) == 1
    window.close()
    application.processEvents()


def test_mesh_staleness_and_live_solver_monitor(application, tmp_path: Path) -> None:
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    assert window.mesh_update_button.isEnabled()
    assert window.mesh_update_button.text() == "Generate mesh"
    window._mark_mesh_current()
    assert not window.mesh_update_button.isEnabled()
    assert window.mesh_update_button.text() == "Mesh up to date"

    window.editor.canvas.parameters[0] += 0.002
    window.editor.canvas._redraw()
    application.processEvents()
    assert window.mesh_update_button.isEnabled()
    assert window.mesh_update_button.text() == "Airfoil changed — update mesh"

    history = tmp_path / "history.csv"
    history.write_text(
        '"Inner_Iter","rms[Rho]","CL","CD"\n0,-3.0,0.20,0.030\n1,-4.0,0.21,0.025\n',
        encoding="utf-8",
    )
    window.solver_monitor.start(history)
    assert window.solver_monitor.refresh() == 2
    assert window.solver_monitor.iteration_count == 2
    assert list(window.solver_monitor.lines[0].get_ydata()) == [-3.0, -4.0]
    assert list(window.solver_monitor.lines[1].get_ydata()) == [0.030, 0.025]
    assert list(window.solver_monitor.lines[2].get_ydata()) == [0.20, 0.21]

    window._solver_is_active = lambda: True
    window.backend.send_control = lambda _command: True
    window._update_solver_controls()
    assert window.solver_pause_button.isEnabled()
    assert window.solver_stop_now_button.isEnabled()
    assert window.solver_stop_saved_button.isEnabled()
    window._toggle_solver_pause()
    assert window._solver_paused
    assert window.solver_pause_button.text() == "Resume"
    window._stop_solver_after_save()
    assert window._solver_stop_pending
    assert not window.solver_pause_button.isEnabled()
    assert window.solver_stop_now_button.isEnabled()

    window._set_language("zh")
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "翼型调整", "网格生成", "求解器", "结果", "伴随优化"
    ]
    window.close()
    application.processEvents()


def test_latest_manual_bce_constraints_and_actions_are_available(application, tmp_path: Path) -> None:
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    editor = window.editor
    assert [editor.constraint_mode.itemData(i) for i in range(editor.constraint_mode.count())] == [
        "free", "lock_thickness", "lock_camber"
    ]
    assert set(editor.action_buttons) == {
        "import", "undo", "reset", "view", "export", "direct", "handoff"
    }
    x_initial, upper_initial, lower_initial = editor.canvas.current_geometry()
    assert editor.canvas.target_name == "NACA0012"
    assert np.allclose(upper_initial, editor.canvas.target[1], atol=1.0e-12)
    assert np.allclose(lower_initial, editor.canvas.target[2], atol=1.0e-12)
    assert np.max(np.abs(0.5 * (upper_initial + lower_initial))) < 1.0e-12
    assert np.max(upper_initial - lower_initial) == pytest.approx(0.12, abs=3.0e-4)
    assert x_initial[0] == pytest.approx(0.0)
    assert x_initial[-1] == pytest.approx(1.0)

    lock_thickness = editor.constraint_mode.findData("lock_thickness")
    editor.constraint_mode.setCurrentIndex(lock_thickness)
    _, upper_0, lower_0 = editor.canvas.current_geometry()
    editor.canvas.parameters[9] += 4.0
    _, upper_1, lower_1 = editor.canvas.current_geometry()
    assert np.allclose(upper_1 - lower_1, upper_0 - lower_0)

    lock_camber = editor.constraint_mode.findData("lock_camber")
    editor.constraint_mode.setCurrentIndex(lock_camber)
    _, upper_2, lower_2 = editor.canvas.current_geometry()
    editor.canvas.parameters[2] *= 1.15
    _, upper_3, lower_3 = editor.canvas.current_geometry()
    assert np.allclose(upper_3 + lower_3, upper_2 + lower_2)

    editor.set_language("zh")
    assert editor.constraint_label.text() == "约束模式"
    assert editor.action_buttons["direct"].text() == "直接使用手调翼型"
    window.close()
    application.processEvents()


def test_case_metadata_drives_optional_vtk_overlay(tmp_path: Path) -> None:
    (tmp_path / "case_settings.json").write_text(
        '{"case_name":"NACA2412","mach":0.22,"aoa":4.5,"reynolds":3000000}',
        encoding="utf-8",
    )
    assert _case_metadata(tmp_path) == {
        "airfoil": "NACA2412",
        "mach": 0.22,
        "aoa": 4.5,
        "reynolds": 3_000_000,
    }


def test_case_metadata_falls_back_to_su2_config(tmp_path: Path) -> None:
    (tmp_path / "run.cfg").write_text(
        "MACH_NUMBER= 0.15\nAOA= 2.0\nREYNOLDS_NUMBER= 3000000\n",
        encoding="utf-8",
    )
    assert _case_metadata(tmp_path) == {
        "airfoil": tmp_path.name,
        "mach": 0.15,
        "aoa": 2.0,
        "reynolds": 3_000_000.0,
    }
