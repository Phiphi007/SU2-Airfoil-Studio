import json
import unittest
from unittest.mock import patch

import numpy as np

from tests.tmp_workspace import workspace_temp_dir


class EmbeddedMeshTests(unittest.TestCase):
    def test_completion_stays_embedded_and_reloading_replaces_artists(self):
        from gui_app import AutoFoilStudio

        with workspace_temp_dir() as directory:
            nodes = np.array([[0., 0.], [1., 0.], [2., 0.], [0., 1.], [1., 1.], [2., 1.]])
            np.savez_compressed(directory / "mesh_preview.npz", nodes=nodes,
                                quads=np.array([[0, 1, 4, 3], [1, 2, 5, 4]]),
                                wall_edges=np.array([[0, 1], [1, 4], [4, 3], [3, 0]]),
                                source_boundary=nodes[[0, 1, 4, 3, 0]])
            quality = {
                "quadrilateral_cells": 2, "total_nodes": 6,
                "wake_length_chords": 5, "effective_farfield_chords": 5,
                "minimum_angle_deg": 90., "minimum_scaled_jacobian": 1.,
                "leading_edge_nodes_upper_5pct": 2, "leading_edge_nodes_lower_5pct": 2,
                "wall_spacing_max_adjacent_ratio": 1.,
                "leading_edge_radial_direction_max_step_deg": 0.,
            }
            (directory / "mesh_quality.json").write_text(json.dumps(quality), encoding="utf-8")
            mesh = directory / "mesh.su2"
            app = AutoFoilStudio(smoke_test=True)
            try:
                app.withdraw()
                app.update_idletasks()
                with patch("gui_app.messagebox.showinfo") as popup:
                    app._finish_mesh_preview(mesh)
                popup.assert_not_called()
                self.assertEqual(app.geometry_preview_notebook.select(), str(app.mesh_viewer))
                self.assertEqual(app.mesh_stage_value.get(), 100.)
                viewer = app.mesh_viewer
                self.assertEqual(len(viewer.quads), 2)
                np.testing.assert_allclose(viewer.jacobian, 1.)
                for view in ("leading", "trailing", "domain", "body"):
                    viewer.set_view(view)
                    self.assertTrue(np.all(np.isfinite(viewer.axis.get_xlim())))
                viewer.mode_var.set("缩放 Jacobian")
                viewer._render()
                first = viewer._collection
                viewer.load(mesh)
                self.assertNotIn(first, viewer.axis.collections)
                self.assertEqual(len(viewer.axis.collections), 1)
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
