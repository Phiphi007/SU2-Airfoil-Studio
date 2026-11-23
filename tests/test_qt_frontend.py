from __future__ import annotations

import os
from pathlib import Path

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
    window = MainWindow()
    window.workdir_edit.setText(str(tmp_path))
    assert window.tabs.count() == 5
    assert window.mesh_viewer is window.result_viewer
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
    assert window.scene_viewer.annotation_position == "top_center"
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
