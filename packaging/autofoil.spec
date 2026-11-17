# Build with: python packaging/build_windows.py
from pathlib import Path
import importlib.util
import os

root = Path(SPECPATH).parent
# The build Python uses a portable Tcl installation. Ensure analysis subprocesses
# can discover it; PyInstaller remaps these files into _tcl_data/_tk_data.
local_tcl = root / '.runtime' / 'tcl'
if local_tcl.is_dir():
    os.environ['TCL_LIBRARY'] = str(local_tcl / 'tcl8.6')
    os.environ['TK_LIBRARY'] = str(local_tcl / 'tk8.6')
gmsh_module = Path(importlib.util.find_spec('gmsh').origin)
gmsh_dll = next(p for base in (gmsh_module.parent, gmsh_module.parent.parent)
                for p in base.glob('gmsh-*.dll'))
a = Analysis(
    [str(root / 'portable_entry.py')], pathex=[str(root)],
    binaries=[(str(gmsh_dll), '.')],
    datas=[(str(root / 'config_template.cfg'), '.'),
           (str(root / 'assets'), 'assets'), (str(root / 'input_data'), 'input_data')],
    hiddenimports=['gmsh', 'PIL._tkinter_finder', 'core_modules.mesh_worker'],
    excludes=['scipy', 'IPython', 'pytest'],
    hooksconfig={'matplotlib': {'backends': ['Agg', 'TkAgg']}},
    noarchive=False,
)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AutoFoilStudio',
          console=False, debug=False, strip=False, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AutoFoilCLI',
          console=True, debug=False, strip=False, upx=False)
bundle = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name='SU2_AutoFoil_Studio')
