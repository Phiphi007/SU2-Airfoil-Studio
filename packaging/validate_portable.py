"""Exercise the actual EXEs after relocation with no Python/SU2 paths available."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    import pefile
    source = ROOT / 'portable_release' / 'SU2_AutoFoil_Studio'
    target = ROOT / 'build' / 'portable' / 'validation' / (uuid.uuid4().hex[:8] + ' 中文路径 with spaces')
    app = target / 'Copied App'
    app.mkdir(parents=True)
    for name in ('AutoFoilCLI.exe', 'AutoFoilStudio.exe'):
        shutil.copy2(source / name, app / name)
    for name in ('_internal', 'solvers'):
        shutil.copytree(source / name, app / name)
    windir = os.environ.get('SystemRoot', r'C:\Windows')
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE') if key in os.environ}
    env['PATH'] = str(Path(windir) / 'System32') + os.pathsep + windir
    env['LOCALAPPDATA'] = str(target / 'LocalAppData')
    env['SU2AUTOFOIL_DATA_DIR'] = str(target / 'Data')
    env['SU2AUTOFOIL_SMOKE_OUTPUT'] = str(target / 'GUI Cases')
    results = {'relocated_app': str(app), 'clean_path': env['PATH'], 'checks': []}

    def invoke(args, payload=None, executable='AutoFoilCLI.exe'):
        print('Checking:', executable, ' '.join(args), flush=True)
        run = subprocess.run([str(app / executable), *args],
                             input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                             capture_output=True, text=True, encoding='utf-8', errors='replace',
                             env=env, cwd=target, timeout=360)
        if run.returncode:
            raise RuntimeError(f'{args}: exit={run.returncode}\n{run.stdout}\n{run.stderr[-6000:]}')
        return run

    info = json.loads(invoke(['info']).stdout)
    assert info['frozen'] and str(app) in info['su2_executable']
    results['checks'].append('frozen info resolves the relocated bundled solver')
    doctor = json.loads(invoke(['doctor']).stdout)
    assert doctor['ok'] and doctor['gui'] == 'passed'
    results['doctor'] = doctor
    results['checks'].append('GUI/Tk/font/airfoil preview, Gmsh DLL and SU2 startup')
    parsed_schema = json.loads(invoke(['schema']).stdout)
    assert 'global_refinement' in parsed_schema['parameters']
    invalid = subprocess.run([str(app / 'AutoFoilCLI.exe'), 'run'], input='{"parameters":{"mach":-1}}',
                             capture_output=True, text=True, encoding='utf-8', env=env, cwd=target, timeout=30)
    assert invalid.returncode == 2 and not json.loads(invalid.stdout)['ok']
    results['checks'].append('schema and structured invalid-request response')
    gui_start = invoke(['--smoke-test'], executable='AutoFoilStudio.exe')
    desktop_log = target / 'Data' / 'desktop.log'
    gui_output = gui_start.stdout + (desktop_log.read_text(encoding='utf-8') if desktop_log.is_file() else '')
    assert 'GUI smoke test: PASS' in gui_output, (gui_start.stdout, gui_start.stderr)
    results['checks'].append('windowed EXE successfully initializes the real GUI')
    case = target / 'API 算例'
    solved = json.loads(invoke(['run'], {'mode': 'solve', 'output_dir': str(case),
                                       'parameters': {'global_refinement': 0.5, 'iterations': 2,
                                                      'threads': 2, 'language': 'en'}}).stdout)
    assert solved['ok'] and solved['last_values'] and (case / 'flow.vtu').is_file()
    assert len(list((case / 'Aerodynamic_Report').glob('*.png'))) == 4
    assert solved['residual_target_met'] is False
    results['api_last_values'] = solved['last_values']
    results['checks'].append('JSON API: real C-H mesh, 2-iteration OpenMP SU2 solve, CSV/VTU, four report PNGs')
    report = json.loads(invoke(['run'], {'mode': 'report', 'output_dir': str(case),
                                       'parameters': {'language': 'zh'}}).stdout)
    assert report['ok'] and report['residual_target_met'] is None
    results['checks'].append('report-only mode regenerates Chinese report without solving')
    # The GUI workflow must exercise the bundled mesh subprocess dispatch as well.
    gui_run = invoke(['--gui', '--workflow-smoke-test'])
    assert 'GUI workflow smoke test: PASS' in gui_run.stdout
    results['checks'].append('GUI workflow: frozen mesh subprocess, SU2, history, report, live plot')
    solver = app / 'solvers' / 'SU2' / 'bin' / 'SU2_CFD.exe'
    pe = pefile.PE(str(solver))
    imports = [item.dll.decode() for item in pe.DIRECTORY_ENTRY_IMPORT]
    assert not any('mpi' in name.lower() for name in imports)
    assert pe.FILE_HEADER.Machine == 0x8664
    assert pefile.PE(str(app / 'AutoFoilStudio.exe')).OPTIONAL_HEADER.Subsystem == 2
    assert pefile.PE(str(app / 'AutoFoilCLI.exe')).OPTIONAL_HEADER.Subsystem == 3
    results['solver_dll_imports'] = imports
    results['checks'].append('x64 solver has no MPI imports; GUI and console PE subsystems correct')
    sys.path.insert(0, str(ROOT / 'python_api'))
    from autofoil_client import AutoFoilClient
    client = AutoFoilClient(app / 'AutoFoilCLI.exe')
    assert client.info()['frozen']
    # Client test uses a real existing-result request; no numerical dependency on host Python.
    assert client.run(mode='report', output_dir=case, parameters={'language': 'en'})['ok']
    results['checks'].append('standard-library Python client reads EXE info and executes report request')
    results['status'] = 'passed'
    summary = ROOT / 'build' / 'portable' / 'validation_summary.json'
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS:', summary, flush=True)


if __name__ == '__main__':
    main()
