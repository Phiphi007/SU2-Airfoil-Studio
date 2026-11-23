"""Stage a Windows folder whose EXE can be launched by double-clicking."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--translation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--windeployqt", type=Path, required=True)
    parser.add_argument("--su2-bin", type=Path, required=True, help="Directory with Windows SU2_CFD.exe, SU2_CFD_AD.exe, SU2_DOT_AD.exe and SU2_DEF.exe")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Build this folder on Windows with the Windows Qt SDK")
    for path in (args.exe, args.backend / "studio-backend.exe", args.translation, args.windeployqt):
        if not path.is_file():
            parser.error(f"Missing input: {path}")
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    executable = output / args.exe.name
    shutil.copy2(args.exe, executable)
    shutil.copy2(args.translation, output / args.translation.name)
    shutil.copytree(args.backend, output / "runtime/backend/studio-backend")
    solver_bin=args.su2_bin.resolve()
    target=output / "solvers/SU2/bin"
    target.mkdir(parents=True)
    for name in ("SU2_CFD.exe", "SU2_CFD_AD.exe", "SU2_DOT_AD.exe", "SU2_DEF.exe"):
        if not (solver_bin / name).is_file():
            parser.error(f"Missing built solver: {solver_bin / name}")
        shutil.copy2(solver_bin / name,target / name)
    licenses=output / "licenses"
    licenses.mkdir()
    root=Path(__file__).resolve().parents[1]
    shutil.copy2(root / "third_party/su2/COPYING", licenses / "SU2-COPYING")
    shutil.copy2(root / "third_party/gmsh/LICENSE.txt", licenses / "Gmsh-LICENSE.txt")
    shutil.copy2(root / "assets/fonts/OFL-JetBrainsMono.txt", licenses / "JetBrainsMono-OFL.txt")
    subprocess.run([str(args.windeployqt), "--release", "--no-translations", str(executable)], check=True)
    subprocess.run([str(output / "runtime/backend/studio-backend/studio-backend.exe"), "info"], check=True)
    print(f"Windows desktop folder ready: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
