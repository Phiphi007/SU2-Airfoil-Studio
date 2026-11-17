# Build the integrated meshing, CFD, post-processing and adjoint application.
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
        "PIL._tkinter_finder",
        "core_modules.mesh_worker",
        "parametric_adjoint.cli",
        "parametric_adjoint.gui",
    ],
    excludes=["scipy", "IPython", "pytest"],
    hooksconfig={"matplotlib": {"backends": ["Agg", "TkAgg"]}},
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SU2_AutoFoil_Optimizer_Studio",
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
    # Keep the legacy helper name because mesh_worker_command resolves it.
    name="AutoFoilCLI",
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
    name="SU2_AutoFoil_Optimizer_Studio",
)
