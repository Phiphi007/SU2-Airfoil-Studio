from __future__ import annotations

import unittest

from parametric_adjoint.optimizer import AdjointOptimizer


class FixedLiftTrimSlopeTests(unittest.TestCase):
    def test_first_correction_uses_configured_slope(self) -> None:
        self.assertEqual(
            AdjointOptimizer._trim_slope(0.1, 2.0, 0.2, None),
            0.1,
        )

    def test_later_correction_uses_local_secant(self) -> None:
        slope = AdjointOptimizer._trim_slope(
            0.1,
            2.1,
            0.208,
            (2.0, 0.2),
        )
        self.assertAlmostEqual(slope, 0.08)

    def test_secant_is_bounded_and_sign_flip_is_rejected(self) -> None:
        self.assertAlmostEqual(
            AdjointOptimizer._trim_slope(0.1, 2.1, 0.3, (2.0, 0.2)),
            0.4,
        )
        self.assertAlmostEqual(
            AdjointOptimizer._trim_slope(0.1, 2.1, 0.19, (2.0, 0.2)),
            0.1,
        )


if __name__ == "__main__":
    unittest.main()
