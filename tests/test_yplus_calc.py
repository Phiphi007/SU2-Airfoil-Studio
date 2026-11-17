from __future__ import annotations

import unittest

from core_modules.yplus_calc import (
    calculate_first_layer_height,
    estimate_wall_spacing,
)


class YPlusCalculatorTests(unittest.TestCase):
    def test_matches_documented_schlichting_formula(self) -> None:
        # Re = 1e6 时 Schlichting 关联式参考值。
        velocity, chord, nu = 15.0, 1.0, 1.5e-5
        wall = estimate_wall_spacing(velocity, chord, nu, Y_target=1.0)
        self.assertAlmostEqual(wall.reynolds_number, 1.0e6, delta=1.0)
        expected_cf = (2.0 * __import__("math").log10(1.0e6) - 0.65) ** -2.3
        self.assertAlmostEqual(wall.skin_friction_coefficient, expected_cf, places=12)
        self.assertAlmostEqual(
            wall.first_layer_height, nu / (velocity * (expected_cf / 2.0) ** 0.5), places=12
        )

    def test_target_yplus_scales_height_linearly(self) -> None:
        first = calculate_first_layer_height(50.0, 1.0, 1.5e-5, Y_target=1.0)
        double = calculate_first_layer_height(50.0, 1.0, 1.5e-5, Y_target=2.0)
        self.assertAlmostEqual(double, 2.0 * first, places=12)

    def test_rejects_nonphysical_inputs(self) -> None:
        for args in ((0.0, 1.0, 1.5e-5), (50.0, 0.0, 1.5e-5), (50.0, 1.0, 0.0)):
            with self.assertRaises(ValueError):
                estimate_wall_spacing(*args, Y_target=1.0)


if __name__ == "__main__":
    unittest.main()
