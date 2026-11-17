from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from parametric_adjoint.deformation import Brush, DBCEDeformationModel
from parametric_adjoint.legacy_deformation import compact_dbce_refit
from parametric_adjoint.optimizer import AdjointOptimizer
from tests.tmp_workspace import workspace_temp_dir


class DBCEDeformationTests(unittest.TestCase):
    @staticmethod
    def surfaces() -> tuple[np.ndarray, np.ndarray]:
        x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, 121)))
        thickness = 0.12 * np.sqrt(np.clip(x, 0.0, 1.0)) * (1.0 - x)
        return np.column_stack((x, thickness)), np.column_stack((x, -thickness))

    def test_compact_brush_is_local_and_endpoint_safe(self) -> None:
        upper, lower = self.surfaces()
        model = DBCEDeformationModel()
        model.load_surfaces("test", upper, lower)
        model.brushes.append(Brush("camber", 0.45, 0.12, 0.01))
        x, moved_upper, moved_lower = model.geometry()
        outside = (x < 0.33) | (x > 0.57)
        np.testing.assert_allclose(moved_upper[outside], model.upper[outside], atol=1.0e-14)
        np.testing.assert_allclose(moved_lower[outside], model.lower[outside], atol=1.0e-14)
        self.assertAlmostEqual(moved_upper[0], model.upper[0])
        self.assertAlmostEqual(moved_upper[-1], model.upper[-1])
        np.testing.assert_allclose(
            moved_upper - model.upper, moved_lower - model.lower, atol=1.0e-14
        )

    def test_accepted_shape_can_be_exported_as_selig_dat(self) -> None:
        upper, lower = self.surfaces()
        x = np.concatenate((upper[::-1, 0], lower[1:, 0]))
        y = np.concatenate((upper[::-1, 1], lower[1:, 1]))
        dy = 0.002 * np.exp(-((x - 0.5) / 0.12) ** 2)
        with workspace_temp_dir() as directory:
            target = directory / "final_airfoil.dat"
            AdjointOptimizer._write_airfoil_dat(target, x, y, dy)
            rows = target.read_text(encoding="ascii").splitlines()
        self.assertEqual(rows[0], "SU2_adjoint_optimized")
        self.assertGreater(len(rows), 100)
        coordinates = np.loadtxt(rows[1:])
        self.assertAlmostEqual(float(coordinates[0, 0]), 1.0, places=8)
        self.assertAlmostEqual(float(np.min(coordinates[:, 0])), 0.0, places=8)

    def test_compact_handoff_is_exact_without_manual_change(self) -> None:
        upper, lower = self.surfaces()
        x = upper[:, 0]
        fitted_upper, fitted_lower, rmse, variables = compact_dbce_refit(
            x, upper[:, 1], lower[:, 1], upper[:, 1], lower[:, 1]
        )
        np.testing.assert_allclose(fitted_upper, upper[:, 1], atol=1.0e-14)
        np.testing.assert_allclose(fitted_lower, lower[:, 1], atol=1.0e-14)
        self.assertLess(rmse, 1.0e-14)
        self.assertEqual(variables, 20)

    def test_compact_handoff_regularizes_curvature_without_losing_shape(self) -> None:
        from parametric_adjoint.legacy_deformation import (
            INITIAL_PARAMETERS,
            legacy_airfoil,
        )

        x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, 141)))
        baseline = INITIAL_PARAMETERS.copy()
        baseline_upper, baseline_lower, _ = legacy_airfoil(baseline, x)
        edited = baseline.copy()
        edited[9] += 8.0
        edited[3] += 0.025
        target_upper, target_lower, _ = legacy_airfoil(edited, x)
        fitted_upper, fitted_lower, rmse, _ = compact_dbce_refit(
            x, baseline_upper, baseline_lower, target_upper, target_lower
        )

        self.assertLess(rmse, 3.0e-4)
        self.assertLess(
            float(np.max(np.abs(np.r_[fitted_upper - target_upper, fitted_lower - target_lower]))),
            7.0e-4,
        )
        np.testing.assert_allclose(
            [fitted_upper[0], fitted_upper[-1], fitted_lower[0], fitted_lower[-1]],
            [baseline_upper[0], baseline_upper[-1], baseline_lower[0], baseline_lower[-1]],
            atol=1.0e-14,
        )
        uniform_x = np.linspace(0.0, 1.0, 801)
        step = float(uniform_x[1] - uniform_x[0])

        def curvature(values: np.ndarray) -> np.ndarray:
            sampled = np.interp(uniform_x, x, values)
            return np.gradient(np.gradient(sampled, step), step)

        target_camber_delta = 0.5 * (
            target_upper - baseline_upper + target_lower - baseline_lower
        )
        fitted_camber_delta = 0.5 * (
            fitted_upper - baseline_upper + fitted_lower - baseline_lower
        )
        target_roughness = float(np.sqrt(np.mean(curvature(target_camber_delta) ** 2)))
        fitted_roughness = float(np.sqrt(np.mean(curvature(fitted_camber_delta) ** 2)))
        self.assertLess(fitted_roughness, 1.2 * target_roughness)

    def test_legacy_three_curve_controls_export_and_dbce_handoff(self) -> None:
        from gui_app import AutoFoilStudio

        with workspace_temp_dir() as directory:
            app = AutoFoilStudio(smoke_test=True)
            try:
                app.withdraw()
                app.update()
                app._initialize_airfoil_project()
                panel = app.project_panel
                self.assertTrue(panel.loaded)
                self.assertEqual(len(panel.control_artists), 3)

                original = float(panel.parameters[9])
                xlim_before = panel.geometry_axis.get_xlim()
                ylim_before = panel.geometry_axis.get_ylim()
                panel.active_index = 9
                panel.selected_index = 9
                panel.drag_origin_y = original
                panel.drag_origin_value = original
                panel.drag_snapshot = panel.parameters.copy()
                event = type("Event", (), {
                    "inaxes": panel.alpha_axis,
                    "xdata": 0.5,
                    "ydata": original + 2.0,
                })()
                panel._drag(event)
                panel._release(event)
                self.assertAlmostEqual(float(panel.parameters[9]), original + 1.6)
                self.assertEqual(panel.geometry_axis.get_xlim(), xlim_before)
                self.assertEqual(panel.geometry_axis.get_ylim(), ylim_before)
                initial_half_span = panel.geometry_ylim[1]
                panel._ensure_geometry_visible(
                    np.full_like(panel.x, 0.24), np.full_like(panel.x, -0.24)
                )
                self.assertGreater(panel.geometry_ylim[1], initial_half_span)
                self.assertEqual(panel.geometry_ylim[0], -panel.geometry_ylim[1])
                panel._undo()
                self.assertAlmostEqual(float(panel.parameters[9]), original)
                # Reapply a small edit for export / D-BCE handoff.
                panel.parameters[9] = original + 0.4

                exported = directory / "legacy_bce.dat"
                with patch(
                    "parametric_adjoint.legacy_deformation.filedialog.asksaveasfilename",
                    return_value=str(exported),
                ):
                    panel._export()
                self.assertTrue(exported.is_file())

                panel.workdir_var.set(str(directory))
                panel._apply_compact()
                applied = directory / "airfoil_designs" / "NACA0012_dbce_refit.dat"
                self.assertTrue(applied.is_file())
                current_upper, current_lower, _ = panel._current()
                exported = np.loadtxt(applied, skiprows=1)
                expected_y = np.r_[current_upper[::-1], current_lower[1:]]
                np.testing.assert_allclose(exported[:, 1], expected_y, atol=5.1e-10)
                self.assertIn("手调几何零改动", panel.status_var.get())
                self.assertEqual(app.airfoil_path_var.get(), str(applied))
                self.assertEqual(app.main_notebook.select(), str(app.geometry_tab))
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
