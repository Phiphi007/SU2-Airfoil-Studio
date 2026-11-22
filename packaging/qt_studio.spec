# Build with: python -m PyInstaller --noconfirm packaging/qt_studio.spec
from pathlib import Path
import importlib.util

root = Path(SPECPATH).parent
gmsh_module = Path(importlib.util.find_spec("gmsh").origin)
gmsh_dll = next(
    path
    for base in (gmsh_module.parent, gmsh_module.parent.parent)
    for path in base.glob("gmsh-*.dll")
)
a = Analysis(
    [str(root / "portable_entry.py")],
    pathex=[str(root)],
    binaries=[(str(gmsh_dll), ".")],
    datas=[
        (str(root / "config_template.cfg"), "."),
        (str(root / "assets"), "assets"),
        (str(root / "input_data"), "input_data"),
    ],
    hiddenimports=[
        "gmsh",
        "core_modules.mesh_worker",
        "parametric_adjoint.cli",
        "qt_app.main",
        "vtkmodules.qt.QVTKRenderWindowInteractor",
    ],
    excludes=["scipy", "IPython", "pytest"],
    hooksconfig={"matplotlib": {"backends": ["Agg", "QtAgg"]}},
    noarchive=False,
    optimize=1,
)
# A third-party ICU 78 binary can be discovered from the build machine's PATH
# under the unversioned name ``icuuc.dll``.  Qt 6 on Windows intentionally
# links to the operating-system ICU shim with that name; bundling the unrelated
# ICU 78 DLL shadows the system shim and makes QtCore fail with WinError 127.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() != "icuuc.dll"]
pyz = PYZ(a.pure)
gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SU2_Airfoil_Studio_Qt",
    icon=str(root / "assets" / "branding" / "su2_airfoil_studio_v3.ico"),
    console=False,
    debug=False,
    strip=False,
    upx=False,
)
cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoFoilCLI",
    icon=str(root / "assets" / "branding" / "su2_airfoil_studio_v3.ico"),
    console=True,
    debug=False,
    strip=False,
    upx=False,
)
bundle = COLLECT(
    gui,
    cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SU2_Airfoil_Studio_Qt",
)
