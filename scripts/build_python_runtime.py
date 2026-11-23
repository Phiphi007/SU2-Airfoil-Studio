"""Create and validate the private Python runtime next to the C++ executable."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def runtime_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--bootstrap-python", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.resolve()
    bootstrap = args.bootstrap_python.resolve()
    if not bootstrap.is_file():
        parser.error(f"Bootstrap Python does not exist: {bootstrap}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not runtime_python(destination).is_file():
        subprocess.run([str(bootstrap), "-m", "venv", "--copies", str(destination)], check=True)
    python = runtime_python(destination)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / "requirements-runtime-build.txt")], check=True)
    probe = "import numpy,pandas,matplotlib,gmsh,PIL,PySide6,vtk; print('runtime import check passed')"
    subprocess.run([str(python), "-c", probe], check=True)
    subprocess.run([str(python), str(ROOT / "portable_api.py"), "info"], check=True)
    (destination / "studio-runtime.json").write_text(json.dumps({
        "bootstrap_python": str(bootstrap), "requirements": "requirements.txt", "validated": True
    }, indent=2), encoding="utf-8")
    print(f"Private runtime ready: {python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
