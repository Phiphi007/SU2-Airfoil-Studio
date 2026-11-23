"""Separate read-only bundled resources from per-user calculation output."""
from __future__ import annotations

import os
from pathlib import Path
import sys

APP_VERSION = "1.0.1"


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def application_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else resource_root()


def data_root() -> Path:
    override = os.environ.get("SU2AUTOFOIL_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SU2AutoFoilStudio"
    return resource_root() / "output_results"


def mesh_worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        worker = application_root() / "AutoFoilCLI.exe"
        if not worker.is_file():
            raise FileNotFoundError(f"Missing {worker}; copy the entire portable folder, not only one EXE.")
        return [str(worker), "--mesh-worker"]
    return [sys.executable, "-m", "core_modules.mesh_worker"]
