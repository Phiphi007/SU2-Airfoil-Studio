"""JSON configuration model with strict, actionable validation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


def _path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


@dataclass(frozen=True)
class Executables:
    cfd: Path
    cfd_ad: Path
    dot_ad: Path
    deform: Path
    runtime_bin: Path | None = None


@dataclass(frozen=True)
class Case:
    mesh: Path
    restart: Path
    direct_template: Path
    adjoint_template: Path
    marker: str = "airfoil"
    aoa_deg: float = 2.0
    mach: float | None = None
    reynolds: float | None = None
    initial_cl: float | None = None
    initial_cd: float | None = None


@dataclass(frozen=True)
class Objective:
    mode: str = "fixed_lift"
    target_cl: float | None = None
    dcl_dalpha: float | None = None
    dcd_dcl: float | None = None


@dataclass(frozen=True)
class Parameterization:
    mode: str = "relay"
    cst_variables: int = 12
    bce_variables: int = 6
    bce_candidates: int = 1200
    bce_min_half_width: float = 0.05
    bce_min_support_points: int = 12
    endpoint_margin: float = 0.02
    endpoint_taper: bool = True
    shape_mode: str = "camber"
    relay_cst_steps: int = 3
    hybrid_cst_weight: float = 0.65
    hybrid_bce_weight: float = 0.35


@dataclass(frozen=True)
class TrustRegion:
    initial_radius: float = 2.0e-4
    minimum_radius: float = 1.0e-6
    maximum_radius: float = 5.0e-4
    accept_ratio: float = 0.10
    shrink_ratio: float = 0.25
    expand_ratio: float = 0.75
    shrink_factor: float = 0.5
    expand_factor: float = 1.25


@dataclass(frozen=True)
class Constraints:
    max_displacement: float = 0.004
    min_thickness: float = 0.002
    thickness_x_min: float = 0.02
    thickness_x_max: float = 0.98
    aoa_min_deg: float = -10.0
    aoa_max_deg: float = 15.0


@dataclass(frozen=True)
class Solver:
    direct_iterations: int = 2400
    correction_iterations: int = 1200
    adjoint_iterations: int = 800
    adjoint_cfl: float = 50.0
    threads: int = 1
    max_cl_corrections: int = 2
    cl_tolerance: float = 2.0e-5


@dataclass(frozen=True)
class StudyConfig:
    source: Path
    output: Path
    steps: int
    executables: Executables
    case: Case
    objective: Objective = field(default_factory=Objective)
    parameterization: Parameterization = field(default_factory=Parameterization)
    trust_region: TrustRegion = field(default_factory=TrustRegion)
    constraints: Constraints = field(default_factory=Constraints)
    solver: Solver = field(default_factory=Solver)


def _section(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name, {})
    if not isinstance(value, dict):
        raise TypeError(f"'{name}' must be a JSON object")
    return value


def load_config(path: str | Path) -> StudyConfig:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    base = source.parent
    exe = _section(payload, "executables")
    case = _section(payload, "case")
    required_exe = ("cfd", "cfd_ad", "dot_ad", "deform")
    required_case = ("mesh", "restart", "direct_template", "adjoint_template")
    missing = [f"executables.{key}" for key in required_exe if key not in exe]
    missing += [f"case.{key}" for key in required_case if key not in case]
    if missing:
        raise KeyError("Missing configuration keys: " + ", ".join(missing))

    cfg = StudyConfig(
        source=source,
        output=_path(str(payload.get("output", "runs/default")), base),
        steps=int(payload.get("steps", 5)),
        executables=Executables(
            **{key: _path(str(exe[key]), base) for key in required_exe},
            runtime_bin=_path(str(exe["runtime_bin"]), base) if exe.get("runtime_bin") else None,
        ),
        case=Case(
            mesh=_path(str(case["mesh"]), base),
            restart=_path(str(case["restart"]), base),
            direct_template=_path(str(case["direct_template"]), base),
            adjoint_template=_path(str(case["adjoint_template"]), base),
            marker=str(case.get("marker", "airfoil")),
            aoa_deg=float(case.get("aoa_deg", 2.0)),
            mach=float(case["mach"]) if case.get("mach") is not None else None,
            reynolds=float(case["reynolds"]) if case.get("reynolds") is not None else None,
            initial_cl=float(case["initial_cl"]) if case.get("initial_cl") is not None else None,
            initial_cd=float(case["initial_cd"]) if case.get("initial_cd") is not None else None,
        ),
        objective=Objective(**_section(payload, "objective")),
        parameterization=Parameterization(**_section(payload, "parameterization")),
        trust_region=TrustRegion(**_section(payload, "trust_region")),
        constraints=Constraints(**_section(payload, "constraints")),
        solver=Solver(**_section(payload, "solver")),
    )
    _validate(cfg)
    return cfg


def _validate(cfg: StudyConfig) -> None:
    if cfg.steps < 1:
        raise ValueError("steps must be >= 1")
    if cfg.parameterization.mode not in {"cst", "bce", "hybrid", "relay"}:
        raise ValueError("parameterization.mode must be cst, bce, hybrid, or relay")
    if cfg.parameterization.shape_mode not in {"camber", "thickness", "both"}:
        raise ValueError("shape_mode must be camber, thickness, or both")
    if not 0.0 < cfg.parameterization.bce_min_half_width < 0.5:
        raise ValueError("bce_min_half_width must lie between 0 and 0.5")
    if cfg.parameterization.bce_min_support_points < 6:
        raise ValueError("bce_min_support_points must be >= 6")
    if cfg.objective.mode not in {"fixed_aoa", "fixed_lift"}:
        raise ValueError("objective.mode must be fixed_aoa or fixed_lift")
    if cfg.objective.mode == "fixed_lift":
        names = ("target_cl", "dcl_dalpha", "dcd_dcl")
        missing = [name for name in names if getattr(cfg.objective, name) is None]
        if missing:
            raise ValueError("fixed_lift requires objective." + ", objective.".join(missing))
    if cfg.constraints.aoa_min_deg > cfg.constraints.aoa_max_deg:
        raise ValueError("constraints.aoa_min_deg must not exceed aoa_max_deg")
    if not cfg.constraints.aoa_min_deg <= cfg.case.aoa_deg <= cfg.constraints.aoa_max_deg:
        raise ValueError("case.aoa_deg must lie inside the configured AoA bounds")
    if cfg.case.mach is not None and cfg.case.mach <= 0.0:
        raise ValueError("case.mach must be positive")
    if cfg.case.reynolds is not None and cfg.case.reynolds <= 0.0:
        raise ValueError("case.reynolds must be positive")
    for name, file in {
        "case.mesh": cfg.case.mesh,
        "case.restart": cfg.case.restart,
        "case.direct_template": cfg.case.direct_template,
        "case.adjoint_template": cfg.case.adjoint_template,
    }.items():
        if not file.is_file():
            raise FileNotFoundError(f"{name} does not exist: {file}")
