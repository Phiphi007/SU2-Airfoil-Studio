from __future__ import annotations

import unittest

import numpy as np

from core_modules.airfoil_processor import BUILTIN_NACA0012, process_airfoil
from core_modules.cosine_resampler import (
    resample_surface_cosine,
    resample_surfaces_cosine,
)


class CosineResamplerTests(unittest.TestCase):
    def test_cosine_spacing_clusters_both_edges(self) -> None:
        theta = np.linspace(0.0, np.pi, 81)
        x = 0.5 * (1.0 - np.cos(theta))
        surface = np.column_stack((x, np.zeros_like(x)))
        resampled = resample_surface_cosine(surface, 81)
        # Cosine 分布两端的间距远小于中间。
        edge_spacing = float(np.min(np.abs(np.diff(resampled[:2, 0]))))
        middle = len(resampled) // 2
        middle_spacing = float(np.abs(resampled[middle + 1, 0] - resampled[middle, 0]))
        self.assertLess(edge_spacing, 0.3 * middle_spacing)
        # 首末点必须与输入一致。
        np.testing.assert_allclose(resampled[0], surface[0], atol=1.0e-12)
        np.testing.assert_allclose(resampled[-1], surface[-1], atol=1.0e-12)

    def test_resample_keeps_reversed_direction(self) -> None:
        surface = np.column_stack(
            (np.linspace(1.0, 0.0, 40), np.linspace(0.0, 0.06, 40))
        )  # 后缘 -> 前缘
        resampled = resample_surface_cosine(surface, 40)
        self.assertLess(resampled[1, 0], resampled[0, 0])
        np.testing.assert_allclose(resampled[0], surface[0], atol=1.0e-12)
        np.testing.assert_allclose(resampled[-1], surface[-1], atol=1.0e-12)

    def test_requested_surface_counts_and_directions(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=101)
        self.assertEqual(len(processed.upper), 101)
        self.assertEqual(len(processed.lower), 101)
        # 后缘上/下端点 -> 前缘方向：X 单调减小。
        self.assertTrue(np.all(np.diff(processed.upper[:, 0]) < 0.0))
        self.assertTrue(np.all(np.diff(processed.lower[:, 0]) < 0.0))

    def test_shared_endpoints_after_joint_resampling(self) -> None:
        upper = np.column_stack((np.linspace(1.0, 0.0, 60), np.linspace(0.0, 0.06, 60)))
        lower = np.column_stack((np.linspace(1.0, 0.0, 60), np.linspace(0.0, -0.06, 60)))
        new_upper, new_lower = resample_surfaces_cosine(upper, lower, 61)
        np.testing.assert_allclose(new_upper[0], new_lower[0], atol=1.0e-14)
        np.testing.assert_allclose(new_upper[-1], new_lower[-1], atol=1.0e-14)


if __name__ == "__main__":
    unittest.main()
