"""Build the pinned SU2 direct and adjoint executables for local packaging."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "third_party/su2"
TARGETS = (
    "SU2_CFD/src/SU2_CFD",
    "SU2_CFD/src/SU2_CFD_AD",
    "SU2_DOT/src/SU2_DOT_AD",
    "SU2_DEF/src/SU2_DEF",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/su2-native")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--eigen-include", type=Path, help="System Eigen3 include directory; otherwise use SU2's pinned submodule")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    source = SOURCE.resolve()
    build = args.build_dir.resolve()
    if not (source / "meson.build").is_file():
        parser.error("Initialize third_party/su2 with git submodule update --init --recursive")
    patch_file = ROOT / "patches/su2/0001-fix-fsi-interpolator-include.patch"
    patch_check = subprocess.run(["patch", "--dry-run", "--reverse", "-p1", "-d", str(source),
                                  "-i", str(patch_file)], capture_output=True)
    if patch_check.returncode:
        subprocess.run(["patch", "-p1", "-d", str(source), "-i", str(patch_file)], check=True)
    if not (source / "su2preconfig.timestamp").is_file():
        preconfigure = [sys.executable, "preconfigure.py", "--no-mpp", "--no-coolprop", "--no-fado", "--no-mlpcpp"]
        if args.eigen_include:
            preconfigure.append("--no-eigen")
        subprocess.run(preconfigure, cwd=source, check=True)
    meson = source / "externals/meson/meson.py"
    if not meson.is_file():
        parser.error("Meson not found in SU2 externals; initialize its submodule")
    if not (build / "build.ninja").is_file():
        command = [sys.executable, str(meson), "setup", str(build), str(source),
                   f"--prefix={build / 'install'}", "--buildtype=release",
                   "-Dwith-mpi=disabled", "-Denable-autodiff=true", "-Denable-cgns=false",
                   "-Denable-tecio=false", "-Dcpu-arch="]
        if args.eigen_include:
            include = args.eigen_include.resolve()
            if not (include / "Eigen/Core").is_file():
                parser.error(f"Eigen/Core not found under {include}")
            command.append(f"-Dcpp_args=-I{include}")
        subprocess.run(command, cwd=ROOT, check=True)
    environment = os.environ.copy()
    environment.setdefault("CCACHE_DIR", str(build / "ccache"))
    environment.setdefault("CCACHE_TEMPDIR", str(build / "ccache-tmp"))
    suffix = ".exe" if os.name == "nt" else ""
    subprocess.run(["ninja", "-C", str(build), f"-j{args.jobs}", *(target + suffix for target in TARGETS)],
                   cwd=ROOT, env=environment, check=True)
    for target in TARGETS:
        executable = build / (target + suffix)
        if not executable.is_file():
            raise RuntimeError(f"Missing built SU2 executable: {executable}")
    print(f"SU2 executables ready in {build}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
