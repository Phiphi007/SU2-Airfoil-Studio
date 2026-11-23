"""Write compact little-endian geometry for the native Qt mesh and field views."""
from __future__ import annotations

from pathlib import Path
import struct

import numpy as np

from core_modules.field_visualizer import read_vtu

MAGIC = b"SAFV1\0\0\0"


def _write(path: str | Path, nodes: np.ndarray, cells: np.ndarray,
           boundary: np.ndarray, values: np.ndarray | None) -> Path:
    points = np.asarray(nodes[:, :2], dtype="<f4")
    faces = np.asarray(cells, dtype="<u4")
    wall = np.asarray(boundary[:, :2], dtype="<f4")
    if points.ndim != 2 or points.shape[1] != 2 or faces.ndim != 2 or faces.shape[1] != 4:
        raise ValueError("Expected 2-D nodes and quadrilateral cell indices.")
    chord = float(np.ptp(wall[:, 0]))
    if chord <= 0 or len(wall) < 3 or np.max(faces) >= len(points):
        raise ValueError("Invalid airfoil boundary or cell indices.")
    xmid = float((np.min(wall[:, 0]) + np.max(wall[:, 0])) / 2)
    ymid = float((np.min(wall[:, 1]) + np.max(wall[:, 1])) / 2)
    bounds = (xmid - 0.9 * chord, xmid + 0.9 * chord,
              ymid - 0.45 * chord, ymid + 0.45 * chord)
    has_values = values is not None
    if has_values:
        scalar = np.asarray(values, dtype="<f4")
        if scalar.shape != (len(points),):
            raise ValueError("Scalar field does not match the node count.")
        local = ((points[:, 0] >= bounds[0]) & (points[:, 0] <= bounds[1])
                 & (points[:, 1] >= bounds[2]) & (points[:, 1] <= bounds[3])
                 & np.isfinite(scalar))
        sample = scalar[local]
        if len(sample) < 2:
            raise ValueError("Not enough finite near-field scalar values.")
        vmin, vmax = (float(v) for v in np.percentile(sample, (1, 99)))
    else:
        scalar = None
        vmin, vmax = 0.0, 1.0
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        stream.write(struct.pack("<8sIIII6f", MAGIC, len(points), len(faces), len(wall),
                                 int(has_values), *bounds, vmin, vmax))
        stream.write(points.tobytes())
        stream.write(faces.tobytes())
        stream.write(wall.tobytes())
        if scalar is not None:
            stream.write(scalar.tobytes())
    return target


def write_mesh_view(mesh_data: str | Path, output: str | Path) -> Path:
    with np.load(mesh_data) as data:
        return _write(output, data["nodes"], data["quads"], data["source_boundary"], None)


def write_flow_view(vtu: str | Path, boundary: np.ndarray, output: str | Path,
                    field: str = "Mach") -> Path:
    data = read_vtu(vtu)
    if field not in data.point_data:
        raise ValueError(f"Field not present in VTU: {field}")
    faces = []
    for kind, indices in data.cells:
        if kind == 9 and len(indices) == 4:
            faces.append(indices)
        elif kind == 5 and len(indices) == 3:
            faces.append([indices[0], indices[1], indices[2], indices[2]])
    if not faces:
        raise ValueError("VTU has no 2-D surface cells.")
    return _write(output, data.points, np.asarray(faces), boundary,
                  np.asarray(data.point_data[field]).reshape(-1))
