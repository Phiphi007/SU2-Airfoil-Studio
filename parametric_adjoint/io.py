"""SU2 mesh, history and sensitivity readers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np


def read_mesh_points(path: Path) -> np.ndarray:
    lines = path.read_text(encoding="utf-8").splitlines()
    row = next(i for i, line in enumerate(lines) if line.lstrip().startswith("NPOIN="))
    count = int(lines[row].split("=", 1)[1].split()[0])
    return np.asarray([
        [float(field) for field in line.split()[:2]]
        for line in lines[row + 1:row + 1 + count]
    ])


def read_sensitivity(path: Path) -> dict[str, np.ndarray]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError(f"Empty surface sensitivity: {path}")
    return {
        "id": np.asarray([int(row["PointID"]) for row in rows], dtype=int),
        "x": np.asarray([float(row["x"]) for row in rows]),
        "y": np.asarray([float(row["y"]) for row in rows]),
        "gx": np.asarray([float(row["Sensitivity_x"]) for row in rows]),
        "gy": np.asarray([float(row["Sensitivity_y"]) for row in rows]),
    }


def read_history(path: Path, tail_count: int = 50) -> dict[str, float | int]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError(f"Empty SU2 history: {path}")
    names = {name.strip().strip('"'): name for name in rows[0]}
    try:
        cd_name, cl_name = names["CD"], names["CL"]
    except KeyError as exc:
        raise RuntimeError(f"History lacks CD/CL columns: {path}") from exc
    residual_key = next((name for clean, name in names.items() if clean == "rms[Rho]"), None)
    cd = np.asarray([float(row[cd_name]) for row in rows])
    cl = np.asarray([float(row[cl_name]) for row in rows])
    tail = min(tail_count, len(rows))
    result: dict[str, float | int] = {
        "iterations": len(rows),
        "cd": float(np.mean(cd[-tail:])),
        "cl": float(np.mean(cl[-tail:])),
        "cd_range": float(np.ptp(cd[-tail:])),
        "cl_range": float(np.ptp(cl[-tail:])),
    }
    if residual_key:
        result["density_residual"] = float(rows[-1][residual_key])
    return result


def read_adjoint_history(path: Path) -> dict[str, float | int]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError(f"Empty adjoint history: {path}")
    names = {name.strip().strip('"'): name for name in rows[0]}
    residual_name = names.get("rms[A_Rho]")
    iteration_name = names.get("Inner_Iter") or names.get("Iteration")
    result: dict[str, float | int] = {"rows": len(rows)}
    if residual_name:
        result["final_density_residual"] = float(rows[-1][residual_name])
    if iteration_name:
        result["final_iteration"] = int(float(rows[-1][iteration_name]))
    return result


def write_surface_positions(
    path: Path, mesh: Path, surface: dict[str, np.ndarray], dy: np.ndarray
) -> None:
    points = read_mesh_points(mesh)
    if len(dy) != len(surface["id"]):
        raise ValueError("Direction and sensitivity surface have different sizes")
    lines = []
    for point_id, delta in zip(surface["id"], dy):
        x, y = points[int(point_id)]
        lines.append(f"{int(point_id)}\t{x:.16e}\t{y + float(delta):.16e}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value
