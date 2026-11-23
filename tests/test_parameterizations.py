from __future__ import annotations

import unittest

import numpy as np

from parametric_adjoint.config import Constraints, Parameterization
from parametric_adjoint.constraints import check_geometry, minimum_thickness
from parametric_adjoint.parameterizations import build_direction
from parametric_adjoint.parameterizations.bce import dictionary
from parametric_adjoint.parameterizations.common import surface_sides
from parametric_adjoint.parameterizations.cst import matrix as cst_matrix


def surface(count: int = 161) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    theta = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    x = 0.5 * (1.0 + np.cos(theta))
    y = 0.06 * np.sin(theta)
    gradient = np.sin(2.3 * theta) + 0.25 * np.cos(5.0 * theta)
    return x, y, gradient


class ParameterizationTests(unittest.TestCase):
    def test_cst_and_bce_are_endpoint_safe(self) -> None:
        x, y, _ = surface()
        side = surface_sides(x, y)
        cst = cst_matrix(x, side, 8, "camber")
        bce, _ = dictionary(
            x, side, candidates=300, endpoint_margin=0.02,
            endpoint_taper=True, mode="camber",
        )
        endpoints = np.where((x < 1.0e-12) | (x > 1.0 - 1.0e-12))[0]
        self.assertTrue(np.allclose(cst[endpoints], 0.0, atol=1.0e-12))
        self.assertTrue(np.allclose(bce[endpoints], 0.0, atol=1.0e-12))

    def test_all_modes_produce_rms_normalized_descent(self) -> None:
        x, y, gradient = surface()
        for mode in ("cst", "bce", "hybrid"):
            cfg = Parameterization(
                mode=mode, cst_variables=8, bce_variables=4,
                bce_candidates=300, endpoint_margin=0.02,
            )
            result = build_direction(x, y, gradient, cfg, 1)
            self.assertAlmostEqual(float(np.sqrt(np.mean(result.values ** 2))), 1.0, places=12)
            self.assertLess(float(gradient @ result.values), 0.0)

    def test_bce_dictionary_rejects_under_resolved_brushes(self) -> None:
        x, y, _ = surface(81)
        side = surface_sides(x, y)
        matrix, metadata = dictionary(
            x, side, candidates=300, endpoint_margin=0.02,
            endpoint_taper=True, mode="camber",
            min_half_width=0.06, min_support_points=12,
        )
        self.assertTrue(metadata)
        self.assertTrue(all(item["half_width"] >= 0.06 for item in metadata))
        self.assertTrue(all(np.count_nonzero(matrix[:, index]) >= 12 for index in range(matrix.shape[1])))

    def test_relay_switches_after_global_stage(self) -> None:
        x, y, gradient = surface()
        cfg = Parameterization(
            mode="relay", relay_cst_steps=2, cst_variables=8,
            bce_variables=4, bce_candidates=300,
        )
        self.assertEqual(build_direction(x, y, gradient, cfg, 2).stage, "cst")
        self.assertEqual(build_direction(x, y, gradient, cfg, 3).stage, "bce")

    def test_thickness_constraint_rejects_crossing(self) -> None:
        x, y, _ = surface()
        side = surface_sides(x, y)
        self.assertGreater(minimum_thickness(x, y, 0.02, 0.98), 0.0)
        feasible, result = check_geometry(
            x, y, -0.07 * side,
            Constraints(max_displacement=0.1, min_thickness=0.002),
        )
        self.assertFalse(feasible)
        self.assertEqual(result["reason"], "minimum_thickness")


if __name__ == "__main__":
    unittest.main()
