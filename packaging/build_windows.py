"""Reproducible portable folder build; downloads must be supplied explicitly."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-freeze', action='store_true', help='Repackage an already built executable.')
    args = parser.parse_args()
    downloads = ROOT / 'build' / 'portable' / 'downloads'
    required = ['SU2-v8.5.0-win64-omp.zip', 'SU2-v8.5.0-source.zip', 'gmsh-4.15.2-source.tgz',
                'Tcl-8.6.12-license.terms']
    if metadata.version('gmsh') != '4.15.2':
        raise RuntimeError('Install gmsh==4.15.2 to match the distributed source archive.')
    for name in required:
        if not (downloads / name).is_file():
            raise FileNotFoundError(f'Download the upstream archive first: {downloads / name}')
    release_parent = ROOT / 'portable_release'
    app = release_parent / 'SU2_AutoFoil_Studio'
    if app.exists() and not (app / 'BUILD_MANIFEST.json').is_file():
        raise RuntimeError(f'Refusing to overwrite an unrecognized directory: {app}')
    env = os.environ.copy()
    env['PYINSTALLER_CONFIG_DIR'] = str(ROOT / 'build' / 'portable' / 'cache')
    if not args.skip_freeze:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                        '--distpath', str(ROOT / 'build' / 'portable' / 'frozen'),
                        '--workpath', str(ROOT / 'build' / 'portable' / 'work'),
                        str(ROOT / 'packaging' / 'autofoil.spec')], env=env, cwd=ROOT, check=True)
    frozen = ROOT / 'build' / 'portable' / 'frozen' / 'SU2_AutoFoil_Studio'
    app.mkdir(parents=True, exist_ok=True)
    (app / 'BUILD_MANIFEST.json').write_text('{"status": "build in progress"}', encoding='utf-8')
    shutil.copytree(frozen, app, dirs_exist_ok=True)
    solver_dir = app / 'solvers' / 'SU2' / 'bin'
    solver_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(downloads / required[0]) as outer:
        nested = [n for n in outer.namelist() if n.lower().endswith('.zip')]
        binary_zip = io.BytesIO(outer.read(nested[0])) if len(nested) == 1 else downloads / required[0]
    with zipfile.ZipFile(binary_zip) as archive:
        executable = next(n for n in archive.namelist() if n.endswith('/SU2_CFD.exe') or n == 'SU2_CFD.exe')
        (solver_dir / 'SU2_CFD.exe').write_bytes(archive.read(executable))
        # Official OpenMP package should be standalone apart from Windows DLLs.
        for item in archive.namelist():
            if item.lower().endswith('.dll'):
                (solver_dir / Path(item).name).write_bytes(archive.read(item))
    licenses = app / 'licenses'
    sources = app / 'sources'
    licenses.mkdir(exist_ok=True)
    sources.mkdir(exist_ok=True)
    with zipfile.ZipFile(downloads / required[1]) as archive:
        name = next(n for n in archive.namelist() if n.endswith('/LICENSE.md') and n.count('/') == 1)
        (licenses / 'SU2-LICENSE.md').write_bytes(archive.read(name))
    with tarfile.open(downloads / required[2]) as archive:
        name = next(m for m in archive.getmembers() if m.name.endswith('/LICENSE.txt') and m.name.count('/') == 1)
        (licenses / 'Gmsh-LICENSE.txt').write_bytes(archive.extractfile(name).read())
    for name in required[1:3]:
        shutil.copy2(downloads / name, sources / name)
    shutil.copy2(downloads / required[3], licenses / required[3])
    for dist in metadata.distributions():
        for item in dist.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice', 'authors')) for part in item.parts):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = licenses / 'python_packages' / dist.metadata['Name'] / Path(*item.parts[-2:])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    for base in [Path(sys.base_prefix), Path(sys.base_prefix) / 'tcl' / 'tcl8.6',
                 Path(sys.base_prefix) / 'tcl' / 'tk8.6']:
        for source in base.glob('*license*'):
            if source.is_file():
                shutil.copy2(source, licenses / f'{base.name}-{source.name}')
        for source in base.glob('LICENSE*'):
            if source.is_file():
                shutil.copy2(source, licenses / f'{base.name}-{source.name}')
    for folder in ['python_api', 'airfoils', 'input_data']:
        shutil.copytree(ROOT / folder, app / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ['API.md', 'README_便携版.md', 'THIRD_PARTY.md', 'BUILD.md', 'VALIDATION.md']:
        shutil.copy2(ROOT / 'packaging' / name, app / name)
    shutil.copy2(ROOT / 'assets' / 'fonts' / 'OFL.txt', licenses / 'Noto-OFL.txt')
    # Include the application's editable source and build recipe, not local cases,
    # caches, environments or downloaded binary archives.
    with zipfile.ZipFile(sources / 'AutoFoil-application-source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for folder in ['core_modules', 'packaging', 'python_api', 'tests', 'assets', 'input_data', 'airfoils', 'docs']:
            for source in (ROOT / folder).rglob('*'):
                if source.is_file() and not any(p in ('__pycache__', '.tmp') for p in source.parts) and source.suffix != '.pyc':
                    archive.write(source, source.relative_to(ROOT).as_posix())
        for name in ['gui_app.py', 'main_pipeline.py', 'portable_api.py', 'portable_entry.py',
                     'requirements.txt', 'config_template.cfg', 'README.md', 'THIRD_PARTY_NOTICES.md']:
            archive.write(ROOT / name, name)
    manifest = {'version': '1.0.0-portable', 'build_date': '2026-10-06', 'python': sys.version,
                'packages': {d.metadata['Name']: d.version for d in metadata.distributions()},
                'upstream_archives': {name: digest(downloads / name) for name in required},
                'files': {p.relative_to(app).as_posix(): digest(p) for p in sorted(app.rglob('*'))
                          if p.is_file() and p.name != 'BUILD_MANIFEST.json'}}
    (app / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    package = release_parent / 'SU2_AutoFoil_Studio_Windows_x64.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(app.rglob('*')):
            if source.is_file():
                archive.write(source, source.relative_to(release_parent).as_posix())
    (release_parent / (package.name + '.sha256')).write_text(f'{digest(package)}  {package.name}\n', encoding='ascii')
    print(f'Portable folder: {app}\nZIP: {package}\nBytes: {package.stat().st_size}')


if __name__ == '__main__':
    main()
