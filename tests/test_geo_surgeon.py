from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from core_modules import geo_surgeon
from core_modules.airfoil_processor import BUILTIN_NACA0012, process_airfoil
from tests.tmp_workspace import workspace_temp_dir


def _make_selig_file(directory: Path, points: np.ndarray) -> Path:
    path = directory / "airfoil.dat"
    np.savetxt(path, points, fmt="%.8f")
    return path


class GeoSurgeonTests(unittest.TestCase):
    def test_load_and_split_surface_directions(self) -> None:
        from core_modules.airfoil_processor import generate_naca0012_surfaces

        upper_source, lower_source = generate_naca0012_surfaces(161)
        boundary = np.vstack((upper_source, lower_source[::-1][1:]))
        # 模拟有限厚度后缘的 Selig 文件：首末点接近但不重合。
        boundary = boundary.copy()
        boundary[-1] = boundary[-1] + np.array([0.0, 1.0e-4])
        with workspace_temp_dir() as directory:
            path = _make_selig_file(directory, boundary)
            loaded = geo_surgeon.load_airfoil(path)
        upper, lower = geo_surgeon.split_surfaces(loaded)
        self.assertEqual(len(upper), len(lower))
        # 拆分结果方向统一为尖后缘 -> 前缘。
        self.assertGreater(upper[0, 0], upper[-1, 0])
        self.assertGreater(lower[0, 0], lower[-1, 0])
        np.testing.assert_allclose(upper[0], lower[0], atol=1.0e-10)
        np.testing.assert_allclose(upper[-1], lower[-1], atol=1.0e-10)

    def test_default_mode_has_exact_sharp_trailing_edge(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=161)
        self.assertEqual(processed.trailing_edge_radius, 0.0)
        np.testing.assert_allclose(processed.upper[0], processed.lower[0], atol=1e-14)
        np.testing.assert_allclose(processed.x[0], processed.x[-1], atol=1e-14)
        np.testing.assert_allclose(processed.y[0], processed.y[-1], atol=1e-14)
        self.assertAlmostEqual(float(np.max(processed.x)), processed.chord + float(np.min(processed.x)), delta=1e-8)

    def test_sharp_surfaces_keep_cosine_spacing(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=161)
        upper_x = processed.upper[:, 0]
        # 尖点附近仍应保持 Cosine 加密，而不是出现异常长尾段。
        trailing_spacing = float(np.abs(upper_x[1] - upper_x[0]))
        mid = len(upper_x) // 2
        middle_spacing = float(np.abs(upper_x[mid + 1] - upper_x[mid]))
        self.assertLess(trailing_spacing, 0.5 * middle_spacing)

    def test_existing_sharp_deformation_is_not_tail_refitted(self) -> None:
        from core_modules.airfoil_processor import generate_naca0012_surfaces

        upper, lower = generate_naca0012_surfaces(141)
        x = upper[:, 0]
        # Strong but smooth camber, representative of a manual BCE edit.
        camber = 0.12 * np.sin(np.pi * x)
        upper[:, 1] += camber
        lower[:, 1] += camber
        upper[0] = lower[0] = 0.5 * (upper[0] + lower[0])
        rebuilt_upper, rebuilt_lower = geo_surgeon.sharpen_surfaces(upper, lower)
        np.testing.assert_allclose(rebuilt_upper, upper, atol=1e-14)
        np.testing.assert_allclose(rebuilt_lower, lower, atol=1e-14)

    def test_sharp_rebuild_returns_closed_finite_boundary(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=81)
        self.assertTrue(np.all(np.isfinite(processed.x)))
        self.assertTrue(np.all(np.isfinite(processed.y)))
        self.assertEqual(len(processed.upper), len(processed.lower))
        np.testing.assert_allclose(
            [processed.x[0], processed.y[0]],
            [processed.x[-1], processed.y[-1]],
            atol=1.0e-14,
        )
        # 拟合尖点位于原始坐标下游或原始位置（不允许回缩）。
        self.assertGreaterEqual(float(np.max(processed.x)), 1.0 - 1.0e-9)

    def test_rejects_non_selig_input(self) -> None:
        # 前缘在端点位置的输入无法拆分，必须报错。
        points = np.column_stack(
            (np.linspace(0.0, 1.0, 30), np.zeros(30))
        )
        with self.assertRaises(ValueError):
            geo_surgeon.split_surfaces(points)


if __name__ == "__main__":
    unittest.main()
