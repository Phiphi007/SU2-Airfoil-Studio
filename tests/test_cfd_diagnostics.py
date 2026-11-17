import json
import unittest
import numpy as np
from core_modules.history_monitor import assess_convergence, read_history_points
from core_modules.field_visualizer import read_airfoil_boundary
from tests.tmp_workspace import workspace_temp_dir
from tests.test_field_visualizer import _build_appended_vtu


class CfdDiagnosticTests(unittest.TestCase):
    def test_convergence_uses_final_residual_and_force_window(self):
        with workspace_temp_dir() as folder:
            path = folder/'history.csv'
            rows = ['"Inner_Iter","rms[Rho]","rms[RhoU]","CL","CD"']
            for step in range(200):
                residual = -6.0 - 2.1*step/199
                rows.append(f'{step},{residual},-8.2,0.328486,0.021481')
            path.write_text('\n'.join(rows)+'\n', encoding='utf-8')
            result = assess_convergence(path, -8.0)
            self.assertTrue(result['passed'])
            self.assertGreater(result['residual_max']['rms[Rho]'], -8.0)
            self.assertLessEqual(result['residual_final']['rms[Rho]'], -8.0)

    def test_convergence_rejects_unstable_force_or_bad_final_residual(self):
        with workspace_temp_dir() as folder:
            path = folder/'history.csv'
            rows = ['"Inner_Iter","rms[Rho]","CL","CD"']
            for step in range(200):
                lift = 0.3 + (0.01 if step % 2 else 0.0)
                rows.append(f'{step},-8.2,{lift},0.02')
            path.write_text('\n'.join(rows)+'\n', encoding='utf-8')
            self.assertFalse(assess_convergence(path, -8.0)['passed'])
            rows[-1] = '199,-7.9,0.3,0.02'
            path.write_text('\n'.join(rows)+'\n', encoding='utf-8')
            self.assertFalse(assess_convergence(path, -8.0)['passed'])

    def test_history_ignores_incomplete_nonfinite_and_already_displayed_rows(self):
        with workspace_temp_dir() as folder:
            path = folder/'history.csv'
            path.write_text('"Inner_Iter", "rms[Rho]", "CL", "CD"\n'
                            '0,-3,0.2,0.04\n1,-4,nan,0.03\n2,-5,0.3,0.02\n3,-6,0.4,',encoding='utf-8')
            self.assertEqual(read_history_points(path, 0), [(2,-5.,.3,.02)])
            self.assertEqual(read_history_points(path, 2), [])

    def test_cfd_wall_takes_precedence_over_source_polygon(self):
        with workspace_temp_dir() as folder:
            actual = np.array([[1.,0.],[0.,0.],[.5,-.1]])
            np.savetxt(folder/'processed_airfoil.dat', actual+10,header='source',comments='')
            np.savez(folder/'mesh_preview.npz',nodes=actual,
                     wall_edges=np.array([[0,1],[1,2],[2,0]]))
            np.testing.assert_array_equal(read_airfoil_boundary(folder), actual[[0,1,2,0]])

    def test_gui_reads_history_without_stdout_and_rejects_delayed_duplicates(self):
        from gui_app import AutoFoilStudio
        with workspace_temp_dir() as folder:
            (folder/'history.csv').write_text('"Inner_Iter","rms[Rho]","CL","CD"\n0,-3,.2,.04\n1,-4,.3,.03\n')
            app=AutoFoilStudio(smoke_test=True)
            try:
                app.withdraw()
                app.active_case_dir=folder
                app.running=True
                app._drain_events()
                self.assertEqual(app.live_iterations,[0,1])
                app._handle_su2_output('| 0 | -3 | .2 | .04 |')
                app._handle_su2_output('| 1 | -4 | .3 | .03 |')
                app._drain_events()
                self.assertEqual(app.live_iterations,[0,1])
            finally:
                app.running=False
                app.destroy()

    def test_unconverged_warning_survives_contour_completion(self):
        from gui_app import AutoFoilStudio
        with workspace_temp_dir() as folder:
            _build_appended_vtu(folder/'flow.vtu')
            (folder/'last_result.json').write_text(json.dumps({'status':'unconverged'}))
            app=AutoFoilStudio(smoke_test=True)
            try:
                app.withdraw()
                app.active_case_dir=folder
                app._contour_worker('Mach',folder)
                app._drain_events()
                self.assertTrue(app.contour_data['unconverged'])
                self.assertIn('未收敛',app.status_var.get())
                self.assertTrue(any('UNCONVERGED' in text.get_text() or '未收敛' in text.get_text()
                                    for text in app.contour_ax.texts))
            finally:
                app.destroy()
