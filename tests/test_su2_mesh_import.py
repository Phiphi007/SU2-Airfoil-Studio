import unittest
import hashlib
import numpy as np
from core_modules.su2_mesh_import import read_mesh,stage_mesh,boundary_config
from tests.tmp_workspace import workspace_temp_dir


def ring(path):
    path.write_text('''% Pointwise-style mixed mesh
NDIME= 2
NELEM= 5
5 0 1 5 0
5 0 5 4 1
9 1 2 6 5 2
9 2 3 7 6 3
9 3 0 4 7 4
NPOIN= 8
0 0 0
3 0 1
3 3 2
0 3 3
1 1 4
2 1 5
2 2 6
1 2 7
NMARK= 2
MARKER_TAG= wing_pw
MARKER_ELEMS= 4
3 5 4
3 7 6
3 4 7
3 6 5
MARKER_TAG= outer_pw
MARKER_ELEMS= 4
3 0 1
3 1 2
3 2 3
3 3 0
''',encoding='utf-8')


class ImportTests(unittest.TestCase):
    def test_mixed_mesh_keeps_source_bytes_and_actual_wall(self):
        with workspace_temp_dir() as folder:
            source=folder/'pointwise.su2';ring(source)
            mesh=read_mesh(source)
            before=hashlib.sha256(source.read_bytes()).digest()
            quality=stage_mesh(mesh,folder/'case','wing_pw')
            self.assertEqual(before,hashlib.sha256((folder/'case/mesh.su2').read_bytes()).digest())
            self.assertEqual(quality['triangle_cells'],2)
            wall,edges=mesh.wall('wing_pw')
            self.assertEqual(len(wall),5)
            np.testing.assert_array_equal(wall[0],wall[-1])
            with np.load(folder/'case/mesh_preview.npz') as archive:
                self.assertTrue(np.all(archive['cell_quality']>0))

    def test_custom_boundary_names_and_sidecar(self):
        with workspace_temp_dir() as folder:
            source=folder/'mesh.su2';ring(source);mesh=read_mesh(source)
            config=boundary_config(mesh,'wing_pw','outer_pw')
            self.assertIn('MARKER_HEATFLUX= ( wing_pw, 0 )',config)
            cfg=folder/'boundary.cfg'
            cfg.write_text('AOA=99\nMARKER_HEATFLUX= (wing_pw,0)\nMARKER_FAR= (\nouter_pw\n)\n')
            result=boundary_config(mesh,'wing_pw','',cfg=cfg)
            self.assertNotIn('AOA',result)
            self.assertIn('MARKER_MONITORING= ( wing_pw )',result)
            cfg.write_text('MARKER_HEATFLUX= (wing_pw,0)\n')
            with self.assertRaisesRegex(ValueError,'未覆盖'):boundary_config(mesh,'wing_pw','',cfg=cfg)

    def test_reject_missing_boundary_bad_cell_and_3d(self):
        with workspace_temp_dir() as folder:
            path=folder/'mesh.su2';ring(path);text=path.read_text()
            for bad in (text.replace('NDIME= 2','NDIME= 3'),
                        text.replace('5 0 1 5 0','5 0 0 5 0'),
                        text.replace('3 3 0','3 3 4')):
                path.write_text(bad)
                with self.assertRaises(ValueError):read_mesh(path)

    def test_embedded_viewer_displays_mixed_mesh(self):
        from gui_app import AutoFoilStudio
        with workspace_temp_dir() as folder:
            path=folder/'mesh.su2';ring(path)
            stage_mesh(read_mesh(path),folder/'case','wing_pw')
            app=AutoFoilStudio(smoke_test=True)
            try:
                app.withdraw()
                app.mesh_viewer.load(folder/'case/mesh.su2')
                app.mesh_viewer.mode_var.set('缩放 Jacobian')
                app.mesh_viewer._render()
                self.assertIn('2 三角形',app.mesh_viewer.quality_var.get())
                self.assertGreater(float(app.mesh_viewer.jacobian.min()),0)
            finally:app.destroy()
