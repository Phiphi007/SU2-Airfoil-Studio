"""Command-line entry points."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

from .bridge import prepare_case_config
from .config import load_config
from .constraints import check_geometry
from .io import json_ready
from .optimizer import AdjointOptimizer
from .parameterizations import build_direction
from .su2 import SU2Runner


def _progress(message: str) -> None:
    print(f"[Progress] {message}", flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parametric-adjoint",
        description="CST/BCE/hybrid/relay optimization using SU2 discrete adjoints.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate files, executables and geometry bases")
    check.add_argument("config", type=Path)
    optimize = sub.add_parser("optimize", help="run one optimization study")
    optimize.add_argument("config", type=Path)
    optimize.add_argument("--steps", type=int, help="override the configured attempt count")
    optimize.add_argument("--output", type=Path, help="override the configured output directory")
    compare = sub.add_parser("compare", help="run fair studies in separate output folders")
    compare.add_argument("config", type=Path)
    compare.add_argument("--methods", default="cst,bce,relay")
    prepare = sub.add_parser("prepare-case", help="create JSON from an SU2WorkFlow case")
    prepare.add_argument("case_dir", type=Path)
    prepare.add_argument("--su2-bin", type=Path, required=True)
    prepare.add_argument("--runtime-bin", type=Path)
    prepare.add_argument("--output-config", type=Path, default=Path("optimization.json"))
    prepare.add_argument("--mode", choices=("cst", "bce", "hybrid", "relay"), default="relay")
    prepare.add_argument("--objective", choices=("fixed_aoa", "fixed_lift"), default="fixed_aoa")
    prepare.add_argument("--target-cl", type=float)
    prepare.add_argument("--dcl-dalpha", type=float)
    prepare.add_argument("--dcd-dcl", type=float)
    return parser


def _check(config_path: Path) -> dict[str, object]:
    cfg = load_config(config_path)
    SU2Runner(cfg).validate_executables()
    theta = np.linspace(0.0, 2.0 * np.pi, 161, endpoint=False)
    x = 0.5 * (1.0 + np.cos(theta))
    y = 0.06 * np.sin(theta)
    gradient = np.sin(2.3 * theta) + 0.25 * np.cos(5.0 * theta)
    result = build_direction(x, y, gradient, cfg.parameterization, 1)
    feasible, geometry = check_geometry(
        x, y, cfg.trust_region.initial_radius * result.values, cfg.constraints
    )
    return {
        "status": "ok" if feasible else "warning",
        "mode": cfg.parameterization.mode,
        "first_stage": result.stage,
        "basis_condition": result.condition,
        "capture_fraction_on_synthetic_gradient": result.capture_fraction,
        "initial_step_geometry": geometry,
        "files": "ok",
        "executables": "ok",
    }


def _compare(config_path: Path, methods: list[str]) -> list[dict[str, object]]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    base_cfg = load_config(config_path)
    base_output = base_cfg.output
    raw.setdefault("executables", {}).update({
        "cfd": str(base_cfg.executables.cfd),
        "cfd_ad": str(base_cfg.executables.cfd_ad),
        "dot_ad": str(base_cfg.executables.dot_ad),
        "deform": str(base_cfg.executables.deform),
        "runtime_bin": (
            str(base_cfg.executables.runtime_bin)
            if base_cfg.executables.runtime_bin else None
        ),
    })
    raw.setdefault("case", {}).update({
        "mesh": str(base_cfg.case.mesh),
        "restart": str(base_cfg.case.restart),
        "direct_template": str(base_cfg.case.direct_template),
        "adjoint_template": str(base_cfg.case.adjoint_template),
    })
    generated = base_output / "comparison_configs"
    generated.mkdir(parents=True, exist_ok=True)
    results = []
    for method in methods:
        if method not in {"cst", "bce", "hybrid", "relay"}:
            raise ValueError(f"Unknown comparison method: {method}")
        study = json.loads(json.dumps(raw))
        study.setdefault("parameterization", {})["mode"] = method
        study["output"] = str(base_output / method)
        path = generated / f"{method}.json"
        path.write_text(json.dumps(study, ensure_ascii=False, indent=2), encoding="utf-8")
        result = AdjointOptimizer(load_config(path), progress=_progress).run()
        results.append({"method": method, **result["final"], "total_seconds": result["total_seconds"]})
    summary = base_output / "comparison_summary.json"
    summary.write_text(json.dumps(json_ready(results), ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "prepare-case":
        if args.objective == "fixed_lift" and None in (
            args.target_cl, args.dcl_dalpha, args.dcd_dcl
        ):
            raise SystemExit("fixed_lift requires --target-cl, --dcl-dalpha and --dcd-dcl")
        path = prepare_case_config(
            case_dir=args.case_dir,
            su2_bin=args.su2_bin,
            output_config=args.output_config.resolve(),
            runtime_bin=args.runtime_bin,
            mode=args.mode,
            objective_mode=args.objective,
            target_cl=args.target_cl,
            dcl_dalpha=args.dcl_dalpha,
            dcd_dcl=args.dcd_dcl,
        )
        print(path)
        return 0
    if args.command == "check":
        result = _check(args.config)
    elif args.command == "optimize":
        cfg = load_config(args.config)
        if args.steps is not None:
            if args.steps < 1:
                raise SystemExit("--steps must be >= 1")
            cfg = replace(cfg, steps=args.steps)
        if args.output is not None:
            cfg = replace(cfg, output=args.output.expanduser().resolve())
        result = AdjointOptimizer(cfg, progress=_progress).run()
    else:
        methods = [item.strip().lower() for item in args.methods.split(",") if item.strip()]
        result = _compare(args.config, methods)
    print(json.dumps(json_ready(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
