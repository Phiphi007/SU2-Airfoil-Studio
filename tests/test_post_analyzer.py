from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from core_modules.post_analyzer import (
    REPORT_PANELS,
    _split_surface_indices,
    generate_report,
    smooth_surface_for_display,
)
from tests.tmp_workspace import workspace_temp_dir


class PostAnalyzerTests(unittest.TestCase):
    def test_surface_display_smoothing_reduces_zigzag_and_keeps_endpoints(self) -> None:
        x = np.linspace(0.0, 1.0, 101)
        baseline = -0.8 + 0.7 * x + 0.08 * np.sin(np.pi * x)
        raw = baseline + 0.045 * np.where(np.arange(len(x)) % 2, 1.0, -1.0)
        smoothed = smooth_surface_for_display(raw)
        self.assertLess(
            float(np.sqrt(np.mean(np.square(smoothed - baseline)))),
            float(np.sqrt(np.mean(np.square(raw - baseline)))),
        )
        np.testing.assert_allclose(smoothed[:2], raw[:2])
        np.testing.assert_allclose(smoothed[-2:], raw[-2:])
        self.assertGreaterEqual(float(np.min(smoothed)), float(np.min(raw)))
        self.assertLessEqual(float(np.max(smoothed)), float(np.max(raw)))

    def test_generate_report_writes_four_separate_panel_images(self) -> None:
        with workspace_temp_dir() as directory:
            iterations = np.arange(30)
            pd.DataFrame(
                {
                    "Inner_Iter": iterations,
                    "rms[Rho]": -2.0 - 0.12 * iterations,
                    "CL": 0.5 + 0.1 * (1.0 - np.exp(-iterations / 5.0)),
                    "CD": 0.02 + 0.01 * np.exp(-iterations / 5.0),
                }
            ).to_csv(directory / "history.csv", index=False)
            branch_x = np.linspace(0.0, 1.0, 61)
            upper_y = 0.06 * np.sin(np.pi * branch_x)
            lower_y = -0.06 * np.sin(np.pi * branch_x)
            x = np.r_[branch_x, branch_x[1:-1]]
            y = np.r_[upper_y, lower_y[1:-1]]
            cp = np.r_[
                -0.9 + 0.9 * branch_x,
                0.25 - 0.2 * branch_x[1:-1],
            ]
            cf = np.r_[
                0.006 + 0.001 * branch_x,
                0.0065 + 0.001 * branch_x[1:-1],
            ]
            pd.DataFrame(
                {
                    "x": x,
                    "y": y,
                    "Pressure_Coefficient": cp,
                    "Skin_Friction_Coefficient_x": cf,
                }
            ).to_csv(directory / "surface_flow.csv", index=False)
            first_panel = generate_report(directory)
            self.assertEqual(first_panel.parent.name, "Aerodynamic_Report")
            for _, _, filename in REPORT_PANELS:
                path = first_panel.parent / filename
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 10_000)

    def test_split_is_independent_of_csv_point_order(self) -> None:
        # 构造 SU2 表面 CSV 式的点集：前缘/后缘节点唯一，上下表面各自采样，
        # 然后打乱 CSV 行顺序，验证拆分结果与行顺序无关。
        upper_x = np.linspace(0.0, 1.0, 40)
        lower_x = np.linspace(0.0, 1.0, 40)
        upper_points = np.column_stack(
            (upper_x[1:-1], 0.06 * np.sin(np.pi * upper_x[1:-1]))
        )
        lower_points = np.column_stack(
            (lower_x[1:-1], -0.06 * np.sin(np.pi * lower_x[1:-1]))
        )
        shared = np.array(
            [[0.0, 0.0], [1.0, 0.0]]
        )  # 前缘与后缘各一个共享节点
        x = np.r_[shared[:, 0], upper_points[:, 0], lower_points[:, 0]]
        y = np.r_[shared[:, 1], upper_points[:, 1], lower_points[:, 1]]
        rng = np.random.default_rng(42)
        permutation = rng.permutation(len(x))
        upper_idx, lower_idx = _split_surface_indices(x[permutation], y[permutation])

        def sorted_x(indices: np.ndarray) -> np.ndarray:
            return np.sort(x[permutation][indices])

        np.testing.assert_allclose(sorted_x(upper_idx), upper_x, atol=1.0e-8)
        np.testing.assert_allclose(sorted_x(lower_idx), lower_x, atol=1.0e-8)

    def test_split_uses_contour_topology_for_strong_camber(self) -> None:
        # 两个表面都位于直弦上方。旧的弦线符号法会把下表面的一大段错分到
        # 上表面，按 x 连线后形成振幅接近翼型厚度的高频震荡。
        branch_x = np.linspace(0.0, 1.0, 121)
        camber = 0.12 * np.sin(np.pi * branch_x)
        thickness = 0.035 * np.sin(np.pi * branch_x)
        upper_y = camber + thickness
        lower_y = camber - thickness
        # 模拟 SU2 表面输出的 TE upper -> LE -> TE lower 顺序。
        x = np.r_[branch_x[::-1], branch_x[1:]]
        y = np.r_[upper_y[::-1], lower_y[1:]]

        upper_idx, lower_idx = _split_surface_indices(x, y)
        self.assertEqual(len(upper_idx), len(branch_x))
        self.assertEqual(len(lower_idx), len(branch_x))
        np.testing.assert_allclose(x[upper_idx], branch_x, atol=1.0e-12)
        np.testing.assert_allclose(x[lower_idx], branch_x, atol=1.0e-12)
        np.testing.assert_allclose(y[upper_idx], upper_y, atol=1.0e-12)
        np.testing.assert_allclose(y[lower_idx], lower_y, atol=1.0e-12)

    def test_split_rejects_flat_geometry(self) -> None:
        with self.assertRaises(ValueError):
            _split_surface_indices(np.linspace(0.0, 1.0, 10), np.zeros(10))


if __name__ == "__main__":
    unittest.main()
