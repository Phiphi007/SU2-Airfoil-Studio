"""Bridge an existing SU2WorkFlow case directory into an optimization study."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


def _restart(case_dir: Path) -> Path:
    preferred = (
        "restart_flow.dat",
        "restart_flow.csv",
        "restart.dat",
        "solution_flow.dat",
    )
    for name in preferred:
        candidate = case_dir / name
        if candidate.is_file():
            return candidate
    candidates = sorted(
        (path for path in case_dir.glob("restart*.dat") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise FileNotFoundError(
        f"No SU2 flow restart found in {case_dir}. Run the direct case with OUTPUT_FILES=(RESTART)."
    )


def _last_result(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "last_result.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    metrics = raw.get("metrics", {}) if isinstance(raw, dict) else {}
    result: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    aliases = {
        "cl": ("升力系数 CL", "CL"),
        "cd": ("阻力系数 CD", "CD"),
    }
    for target, names in aliases.items():
        for name in names:
            if name in metrics:
                try:
                    result[target] = float(metrics[name])
                except (TypeError, ValueError):
                    pass
                break
    return result


def _cfg_number(path: Path, key: str, fallback: float) -> float:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*([^%#]+)", re.IGNORECASE)
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(line)
        if match:
            try:
                return float(match.group(1).strip().split()[0])
            except ValueError:
                break
    return fallback


def prepare_case_config(
    *,
    case_dir: Path,
    su2_bin: Path,
    output_config: Path,
    runtime_bin: Path | None,
    mode: str,
    objective_mode: str,
    target_cl: float | None,
    dcl_dalpha: float | None,
    dcd_dcl: float | None,
) -> Path:
    case_dir = case_dir.expanduser().resolve()
    mesh = case_dir / "mesh.su2"
    template = case_dir / "run.cfg"
    if not mesh.is_file() or not template.is_file():
        raise FileNotFoundError(f"Expected mesh.su2 and run.cfg in {case_dir}")
    restart = _restart(case_dir)
    last = _last_result(case_dir)
    payload: dict[str, Any] = {
        "output": str((case_dir / "parametric_optimization" / mode).resolve()),
        "steps": 6,
        "executables": {
            "cfd": str((su2_bin / "SU2_CFD.exe").resolve()),
            "cfd_ad": str((su2_bin / "SU2_CFD_AD.exe").resolve()),
            "dot_ad": str((su2_bin / "SU2_DOT_AD.exe").resolve()),
            "deform": str((su2_bin / "SU2_DEF.exe").resolve()),
            "runtime_bin": str(runtime_bin.resolve()) if runtime_bin else None,
        },
        "case": {
            "mesh": str(mesh.resolve()),
            "restart": str(restart.resolve()),
            "direct_template": str(template.resolve()),
            "adjoint_template": str(template.resolve()),
            "marker": "airfoil",
            "aoa_deg": float(last.get("aoa", last.get("angle_of_attack", _cfg_number(template, "AOA", 2.0)))),
            "mach": _cfg_number(template, "MACH_NUMBER", 0.15),
            "reynolds": _cfg_number(template, "REYNOLDS_NUMBER", 3_000_000.0),
            "initial_cl": last.get("cl", last.get("lift_coefficient")),
            "initial_cd": last.get("cd", last.get("drag_coefficient")),
        },
        "objective": {
            "mode": objective_mode,
            "target_cl": target_cl,
            "dcl_dalpha": dcl_dalpha,
            "dcd_dcl": dcd_dcl,
        },
        "parameterization": {
            "mode": mode,
            "cst_variables": 12,
            "bce_variables": 6,
            "bce_candidates": 1200,
            "bce_min_half_width": 0.05,
            "bce_min_support_points": 12,
            "endpoint_margin": 0.02,
            "endpoint_taper": True,
            "shape_mode": "camber",
            "relay_cst_steps": 3,
            "hybrid_cst_weight": 0.65,
            "hybrid_bce_weight": 0.35,
        },
        "trust_region": {
            "initial_radius": 0.0002,
            "minimum_radius": 0.000001,
            "maximum_radius": 0.0005,
            "accept_ratio": 0.10,
            "shrink_ratio": 0.25,
            "expand_ratio": 0.75,
            "shrink_factor": 0.5,
            "expand_factor": 1.25,
        },
        "constraints": {
            "max_displacement": 0.004,
            "min_thickness": 0.002,
            "thickness_x_min": 0.02,
            "thickness_x_max": 0.98,
            "aoa_min_deg": -10.0,
            "aoa_max_deg": 15.0,
        },
        "solver": {
            "direct_iterations": 2400,
            "correction_iterations": 1200,
            "adjoint_iterations": 800,
            "adjoint_cfl": 50.0,
            "threads": 1,
            "max_cl_corrections": 2,
            "cl_tolerance": 0.00002,
        },
    }
    if objective_mode == "fixed_aoa":
        payload["objective"] = {"mode": "fixed_aoa"}
    output_config.parent.mkdir(parents=True, exist_ok=True)
    output_config.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_config
