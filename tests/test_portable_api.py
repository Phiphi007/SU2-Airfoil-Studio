from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import portable_api as api
from tests.tmp_workspace import workspace_temp_dir


class PortableAPITests(unittest.TestCase):
    def test_defaults_and_parameter_conversion(self):
        with workspace_temp_dir() as root:
            args, mode, output = api.parse_request({'output_dir': str(root / 'case'),
                                                   'parameters': {'aoa': -2, 'threads': 2, 'solver': 'EULER'}})
            self.assertEqual(mode, 'mesh')
            self.assertTrue(args.mesh_only)
            self.assertEqual(args.aoa, -2.0)
            self.assertEqual(args.threads, 2)
            self.assertEqual(args.solver, 'EULER')
            self.assertFalse(output.exists())

    def test_rejects_invalid_requests_before_creating_output(self):
        for request in [[], {'api_version': True}, {'unexpected': 1}, {'mode': 'unknown'},
                        {'parameters': {'mach': float('nan')}}, {'parameters': {'mach': -1}},
                        {'parameters': {'threads': True}}, {'parameters': {'iterations': 0}},
                        {'parameters': {'global_refinement': 11}}, {'parameters': {'global_refinement': 0.049}},
                        {'parameters': {'domain_scale': 10.1}}, {'parameters': {'domain_scale': 0.2}},
                        {'parameters': {'wake_refinement': 13}},
                        {'parameters': {'show_gmsh': True}}, {'parameters': {'solver': 'LBM'}},
                        {'parameters': {'skip_report': 'false'}}, {'parameters': {'misspelled': 1}},
                        {'airfoil': 'no-such-airfoil.dat'}, {'mode': 'report'}, {'output_dir': ''}]:
            with self.subTest(request=request), self.assertRaises(api.RequestError):
                api.parse_request(request)

    def test_existing_directory_is_never_overwritten(self):
        with workspace_temp_dir() as root:
            with self.assertRaises(api.RequestError):
                api.parse_request({'output_dir': str(root)})

    def test_json_stdout_excludes_progress_and_marks_nonconvergence(self):
        with workspace_temp_dir() as root:
            out = root / 'case'
            def pipeline(args, **_kwargs):
                print('progress not JSON')
                (out / 'history.csv').write_text('"Inner_Iter","rms[Rho]","CL","CD"\n1,-3,0.2,0.04\n')
                return None
            stdout, stderr = io.StringIO(), io.StringIO()
            payload = json.dumps({'mode': 'solve', 'output_dir': str(out)})
            with patch('main_pipeline.run_pipeline', pipeline), patch('sys.stdin', io.StringIO(payload)), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                code = api.main(['run'])
            result = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(result['ok'])
            self.assertFalse(result['residual_target_met'])
            self.assertEqual(result['last_values']['CL'], 0.2)
            self.assertIn('progress not JSON', stderr.getvalue())
            self.assertTrue((out / 'api_result.json').is_file())
            saved = json.loads((out / 'case_request.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['mode'], 'solve')
            self.assertEqual(saved['output_dir'], str(out))

    def test_pipeline_failure_returns_partial_files(self):
        with workspace_temp_dir() as root:
            out = root / 'case'
            def pipeline(args, **_kwargs):
                (out / 'run.cfg').write_text('partial')
                raise RuntimeError('solver failed')
            with patch('main_pipeline.run_pipeline', pipeline):
                result, code = api.execute({'output_dir': str(out), 'mode': 'solve'})
            self.assertEqual(code, 1)
            self.assertFalse(result['ok'])
            self.assertIn('run.cfg', result['files'])
            self.assertIn('solver failed', result['error']['message'])

    def test_optimization_requires_converged_direct_case(self):
        with workspace_temp_dir() as root:
            case = root / 'direct'
            case.mkdir()
            (case / 'api_result.json').write_text(json.dumps({
                'mode': 'solve', 'ok': True, 'residual_target_met': False
            }), encoding='utf-8')
            output = root / 'optimization'
            with self.assertRaisesRegex(api.RequestError, 'residual target'):
                api.execute({'mode': 'optimize', 'case_dir': str(case),
                             'output_dir': str(output), 'method': 'cst', 'steps': 1})
            self.assertFalse(output.exists())

    def test_bad_json_returns_structured_error(self):
        stdout = io.StringIO()
        with patch('sys.stdin', io.StringIO('{broken')), redirect_stdout(stdout):
            code = api.main(['run'])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(stdout.getvalue())['ok'])

    def test_frozen_worker_uses_cli_instead_of_python_module_flag(self):
        from core_modules.runtime_paths import mesh_worker_command
        with workspace_temp_dir() as root:
            worker = root / 'AutoFoilCLI.exe'
            worker.touch()
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(root / 'SU2_Airfoil_Studio_Qt.exe')):
                self.assertEqual(mesh_worker_command(), [str(worker), '--mesh-worker'])

    def test_bundled_solver_wins_over_system_path(self):
        from core_modules.su2_driver import _resolve_executable
        with workspace_temp_dir() as root:
            solver = root / 'solvers' / 'SU2' / 'bin' / 'SU2_CFD.exe'
            solver.parent.mkdir(parents=True)
            solver.touch()
            with patch('core_modules.runtime_paths.application_root', return_value=root), \
                    patch.dict('os.environ', {'SU2AUTOFOIL_SU2_EXECUTABLE': ''}), \
                    patch('shutil.which', side_effect=AssertionError('PATH must not be consulted')):
                self.assertEqual(_resolve_executable('SU2_CFD'), str(solver))

    def test_frozen_backend_finds_desktop_solver(self):
        from core_modules.su2_driver import _resolve_executable
        with workspace_temp_dir() as root:
            backend = root / 'runtime' / 'backend' / 'studio-backend'
            backend.mkdir(parents=True)
            solver = root / 'solvers' / 'SU2' / 'bin' / 'SU2_CFD'
            solver.parent.mkdir(parents=True)
            solver.touch()
            with patch.object(sys, 'frozen', True, create=True), \
                    patch('core_modules.runtime_paths.application_root', return_value=backend), \
                    patch.dict('os.environ', {'SU2AUTOFOIL_SU2_EXECUTABLE': ''}), \
                    patch('shutil.which', side_effect=AssertionError('PATH must not be consulted')):
                self.assertEqual(_resolve_executable('SU2_CFD'), str(solver))


if __name__ == '__main__':
    unittest.main()
