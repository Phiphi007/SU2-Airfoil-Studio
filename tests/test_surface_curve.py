import unittest

import numpy as np

from core_modules.airfoil_processor import process_airfoil
from core_modules.mesh_architect import (
    _clean_sharp_boundary, _open_boundary_normals, _quality_metrics,
    _resample_sharp_airfoil, _rotate_to_chord_axis, _wall_spacing_statistics,
)
from core_modules.surface_curve import reconstruct_perimeter


class SurfaceCurveTests(unittest.TestCase):
    def test_faceted_nose_is_repaired_with_reported_bound_and_graded_mesh(self):
        p = process_airfoil("builtin://naca0012", surface_point_count=100)
        # Mimic the old envelope's linearly sampled nose: a finite-angle V.
        mask = p.x < .004
        y = p.y.copy()
        y[mask] = np.sign(y[mask]) * 2.8 * p.x[mask]
        points, center, chord = _rotate_to_chord_axis(p.x, y)
        points = _clean_sharp_boundary(points, chord)
        curve, leading, quality = reconstruct_perimeter(points, chord)
        self.assertEqual(quality["leading_edge_repair_applied"], 1)
        self.assertGreater(quality["leading_edge_source_turn_deg"], 30)
        self.assertLessEqual(quality["wall_reconstruction_max_curve_deviation_pct"], .001)
        np.testing.assert_allclose(curve[[0, -1]], points[[0, -1]], atol=1e-14)
        np.testing.assert_allclose(curve[leading], points[np.argmin(points[:, 0])], atol=1e-14)
        for refinement in (.05, .35, 1.):
            wall, control = _resample_sharp_airfoil(points, chord, .0015, .0015, .0015, refinement)
            stats = _wall_spacing_statistics(wall, control["leading"], chord)
            self.assertLess(stats["wall_spacing_max_adjacent_ratio"], 1.2)
            self.assertGreaterEqual(stats["leading_edge_nodes_upper_5pct"], 12)
            normals = _open_boundary_normals(wall, center)
            turn = np.degrees(np.arccos(np.clip(np.sum(normals[:-1]*normals[1:], axis=1), -1, 1)))
            front = wall[:, 0] < wall[control["leading"], 0] + .05 * chord
            self.assertLess(np.max(turn[front[:-1] & front[1:]]), 8.)

    def test_concave_cell_has_negative_corner_jacobian(self):
        nodes = np.array([[0., 0.], [1., 0.], [.2, .2], [0., 1.]])
        quality = _quality_metrics(nodes, np.array([[1, 2, 3, 4]]))
        self.assertGreater(quality["minimum_signed_area"], 0.)
        self.assertLess(quality["minimum_scaled_jacobian"], 0.)
        self.assertGreater(quality["maximum_angle_deg"], 180.)

    def test_sparse_and_cambered_airfoils_have_bounded_reconstruction(self):
        for name, count in (("0012", 50), ("2412", 100), ("4415", 100), ("0006", 100)):
            p = process_airfoil("builtin://naca" + name, surface_point_count=count)
            points, _, chord = _rotate_to_chord_axis(p.x, p.y)
            _, _, quality = reconstruct_perimeter(_clean_sharp_boundary(points, chord), chord)
            self.assertLessEqual(quality["wall_reconstruction_max_curve_deviation_pct"], .001)
            for refinement in (.05, .35):
                wall, control = _resample_sharp_airfoil(
                    _clean_sharp_boundary(points, chord), chord, .0015, .0015, .0015, refinement)
                stats = _wall_spacing_statistics(wall, control["leading"], chord)
                self.assertLess(stats["wall_spacing_max_adjacent_ratio"], 1.2)


if __name__ == "__main__":
    unittest.main()
