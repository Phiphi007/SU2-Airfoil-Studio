"""Freeze the versioned JSON backend for an isolated release folder."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
               "--name", "studio-backend", "--distpath", str(output),
               "--workpath", str(output / "_work"), "--specpath", str(output / "_spec"),
               "--paths", str(ROOT), "--collect-all", "gmsh",
               "--add-data", f"{ROOT / 'config_template.cfg'}{';' if sys.platform == 'win32' else ':'}.",
               "--add-data", f"{ROOT / 'airfoils'}{';' if sys.platform == 'win32' else ':'}airfoils",
               str(ROOT / "portable_api.py")]
    subprocess.run(command, cwd=ROOT, check=True)
    executable = output / "studio-backend" / ("studio-backend.exe" if sys.platform == "win32" else "studio-backend")
    subprocess.run([str(executable), "info"], check=True)
    print(f"Embedded backend ready: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
