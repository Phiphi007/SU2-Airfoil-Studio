from __future__ import annotations

import unittest

import numpy as np

from core_modules.airfoil_processor import process_airfoil
from core_modules.mesh_architect import _rotate_to_chord_axis, generate_mesh
from tests.test_mesh_architect import _read_su2_mesh
from tests.test_mesh_architect import _nearest_distances
from tests.tmp_workspace import workspace_temp_dir


def _naca_source(designation: str) -> tuple[np.ndarray, np.ndarray]:
    """直接用 NACA 解析式生成 Selig 边界点（上后缘->前缘->下后缘）。"""
    from core_modules.airfoil_processor import generate_naca4_surfaces

    upper, lower = generate_naca4_surfaces(designation, 161)
    boundary = np.vstack((upper, lower[1:]))
    return boundary[:, 0], boundary[:, 1]


def _minimum_angle(nodes: np.ndarray, elements: list[str]) -> float:
    worst = 180.0
    for line in elements:
        fields = [int(v) for v in line.split()]
        poly = nodes[np.asarray(fields[1:-1], dtype=int)]
        n = len(poly)
        for i in range(n):
            a = poly[(i - 1) % n] - poly[i]
            b = poly[(i + 1) % n] - poly[i]
            cos = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-300)
            worst = min(worst, float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))))
    return worst


def _signed_area(vertices: np.ndarray) -> float:
    return 0.5 * float(
        np.sum(
            vertices[:, 0] * np.roll(vertices[:, 1], -1)
            - np.roll(vertices[:, 0], -1) * vertices[:, 1]
        )
    )


class MultiAirfoilTests(unittest.TestCase):
    """用多个 NACA 翼型验证尖后缘与全结构 C-H 网格质量。"""

    AIRFOILS = ("0012", "0015", "2412", "6409")

    def test_naca4_thickness_and_camber_formulas(self) -> None:
        # 0015 厚度应约为 0012 的 1.25 倍。
        _, y_0012 = _naca_source("0012")
        _, y_0015 = _naca_source("0015")
        self.assertAlmostEqual(
            float(np.ptp(y_0015)) / float(np.ptp(y_0012)), 1.25, delta=0.02
        )
        # 2412 应向上弯（有弯度），6409 弯度更大。
        x_2412, y_2412 = _naca_source("2412")
        x_6409, y_6409 = _naca_source("6409")
        mid_2412 = float(np.mean(y_2412[(x_2412 > 0.35) & (x_2412 < 0.45)]))
        mid_6409 = float(np.mean(y_6409[(x_6409 > 0.35) & (x_6409 < 0.45)]))
        self.assertGreater(mid_2412, 0.008)
        self.assertGreater(mid_6409, mid_2412)

    def test_structured_mesh_quality_for_multiple_naca_airfoils(self) -> None:
        for designation in self.AIRFOILS:
            with self.subTest(designation=designation):
                processed = process_airfoil(
                    f"builtin://naca{designation}",
                    surface_point_count=81,
                )
                with workspace_temp_dir() as temporary_dir:
                    mesh_path = generate_mesh(
                        processed.x,
                        processed.y,
                        delta_y=7.1e-6,
                        output_dir=temporary_dir,
                        wall_size_pct=0.008,
                        farfield_size_pct=0.4,
                        terminal_output=False,
                    )
                    elements, nodes, markers = _read_su2_mesh(mesh_path)

                element_types = [line.split()[0] for line in elements]
                self.assertEqual(set(element_types), {"9"}, "体单元必须全部为四边形")
                self.assertEqual(
                    set(markers), {"airfoil", "farfield_inlet", "farfield_outlet"}
                )

                # 全部体单元面积为正。
                minimum_area = float("inf")
                for line in elements:
                    fields = [int(v) for v in line.split()]
                    area = _signed_area(nodes[np.asarray(fields[1:-1], dtype=int)])
                    minimum_area = min(minimum_area, area)
                    self.assertGreater(area, 1.0e-14)
                self.assertGreater(minimum_area, 0.0)

                # 代数映射会自动搜索径向混合策略；强弯度翼型仍需超过 30°。
                worst_angle = _minimum_angle(nodes, elements)
                self.assertGreaterEqual(
                    worst_angle, 30.0, f"网格最小内角 {worst_angle:.2f}° 低于门限"
                )

                # 翼面边界贴合几何（前缘/后缘共线判断）。
                rotated, _, _ = _rotate_to_chord_axis(processed.x, processed.y)
                boundary_indices = sorted(
                    {index for edge in markers["airfoil"] for index in edge}
                )
                distances = _nearest_distances(
                    rotated, nodes[boundary_indices][:, :2]
                )
                self.assertLess(float(np.max(distances)), 0.02)

    def test_process_multiple_naca_airfoils_have_exact_sharp_te(self) -> None:
        for designation in self.AIRFOILS:
            with self.subTest(designation=designation):
                processed = process_airfoil(
                    f"builtin://naca{designation}", surface_point_count=81
                )
                self.assertEqual(len(processed.upper), len(processed.lower))
                self.assertEqual(processed.trailing_edge_radius, 0.0)
                np.testing.assert_allclose(
                    processed.upper[0], processed.lower[0], atol=1.0e-14
                )
                np.testing.assert_allclose(
                    processed.upper[-1], processed.lower[-1], atol=1.0e-14
                )
                self.assertTrue(np.all(np.isfinite(processed.x)))
                self.assertTrue(np.all(np.isfinite(processed.y)))

    def test_default_50_point_configuration_passes_quality_gates(self) -> None:
        """默认严格 C-H 配置在分块接口处仍需保持至少 35° 最小角。"""
        for designation in ("0012", "2412"):
            with self.subTest(designation=designation):
                processed = process_airfoil(
                    f"builtin://naca{designation}", surface_point_count=50
                )
                with workspace_temp_dir() as temporary_dir:
                    mesh_path = generate_mesh(
                        processed.x,
                        processed.y,
                        delta_y=7.1e-6,
                        output_dir=temporary_dir,
                        wall_size_pct=0.012,
                        farfield_size_pct=0.4,
                        terminal_output=False,
                    )
                    elements, nodes, _ = _read_su2_mesh(mesh_path)
                element_types = [line.split()[0] for line in elements]
                self.assertEqual(set(element_types), {"9"})
                worst_angle = _minimum_angle(nodes, elements)
                self.assertGreaterEqual(
                    worst_angle, 35.0, f"网格最小内角 {worst_angle:.2f}° 低于门限"
                )


if __name__ == "__main__":
    unittest.main()
