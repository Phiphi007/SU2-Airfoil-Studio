"""Top-level command line entry for SU2 airfoil meshing and analysis."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from core_modules.runtime_paths import resource_root, data_root

from core_modules import (
    airfoil_processor,
    mesh_architect,
    post_analyzer,
    su2_driver,
    yplus_calc,
)

PROJECT_ROOT = resource_root()


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("This parameter must be greater than zero.")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a structured 2-D airfoil mesh, run SU2, and write an aerodynamic report."
    )
    parser.add_argument(
        "airfoil",
        nargs="?",
        default=airfoil_processor.BUILTIN_NACA0012,
        help="Airfoil DAT in Selig order; defaults to analytic NACA0012.",
    )
    parser.add_argument(
        "--surface-points", type=int, default=100, help="Number of points on each airfoil surface."
    )
    parser.add_argument(
        "--global-refinement",
        type=_positive_float,
        default=1.0,
        help="Global mesh refinement factor, 0.05 to 10.0; below 1 makes a coarser mesh.",
    )
    parser.add_argument(
        "--leading-edge-size",
        type=_positive_float,
        default=0.0015,
        help="Leading-edge control-point target size divided by chord.",
    )
    parser.add_argument(
        "--trailing-upper-size",
        type=_positive_float,
        default=0.0015,
        help="Upper trailing-edge control-point target size divided by chord.",
    )
    parser.add_argument(
        "--trailing-lower-size",
        type=_positive_float,
        default=0.0015,
        help="Lower trailing-edge control-point target size divided by chord.",
    )
    parser.add_argument(
        "--wake-refinement",
        type=_positive_float,
        default=2.0,
        help="Wake-block refinement factor, 1 to 12.",
    )
    parser.add_argument("--mach", type=_positive_float, default=0.15)
    parser.add_argument("--aoa", type=float, default=2.0, help="Angle of attack in degrees.")
    parser.add_argument("--reynolds", type=_positive_float, default=3.0e6)
    parser.add_argument("--temperature", type=_positive_float, default=288.15, help="Freestream temperature in K.")
    parser.add_argument(
        "--velocity",
        type=_positive_float,
        help="Freestream velocity in m/s; computed from Mach and temperature by default.",
    )
    parser.add_argument(
        "--nu",
        type=_positive_float,
        help="Kinematic viscosity in m^2/s; computed from Reynolds number by default.",
    )
    parser.add_argument("--y-plus", type=_positive_float, default=1.0, dest="y_plus")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--threads", type=int, default=1, help="SU2 OpenMP threads (no MPI required).")
    parser.add_argument("--solver", choices=("RANS", "EULER"), default="RANS")
    parser.add_argument("--turbulence", choices=("SA", "SST"), default="SA")
    parser.add_argument("--cfl", type=_positive_float, default=5.0)
    parser.add_argument("--residual-min", type=float, default=-8.0)
    parser.add_argument("--farfield", type=_positive_float, default=20.0, help="Farfield radius divided by chord.")
    parser.add_argument(
        "--domain-scale",
        type=_positive_float,
        default=1.0,
        help="Domain scale factor, 0.25 to 10.0; multiplies the farfield radius.",
    )
    parser.add_argument("--growth-ratio", type=_positive_float, default=1.15)
    parser.add_argument(
        "--boundary-layer-thickness",
        type=_positive_float,
        default=0.08,
        help="Boundary-layer block thickness divided by chord; default 0.08.",
    )
    parser.add_argument(
        "--wall-size",
        type=_positive_float,
        default=0.008,
        help="Legacy option; the global refinement factor controls the structured mesh.",
    )
    parser.add_argument(
        "--farfield-size",
        type=_positive_float,
        default=0.4,
        help="Farfield target cell size divided by chord.",
    )
    parser.add_argument("--output-dir", default=str(data_root()))
    parser.add_argument("--show-gmsh", action="store_true", help="Open Gmsh after mesh generation.")
    parser.add_argument("--mesh-only", action="store_true", help="Write the mesh and run.cfg without starting SU2.")
    parser.add_argument("--post-only", action="store_true", help="Regenerate a report from existing CSV results.")
    parser.add_argument("--skip-report", action="store_true", help="Skip PNG report generation after solving.")
    parser.add_argument(
        "--language", choices=("zh", "en"), default="en", help="Report language: en or zh."
    )
    return parser


def run_pipeline(args: argparse.Namespace, process_control=None) -> Path | None:
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.post_only:
        print("[1/1] Generating a report from existing SU2 CSV files...")
        return post_analyzer.generate_report(output_dir, language=args.language)

    print("[1/5] Preparing the airfoil and sharp trailing edge...")
    processed = airfoil_processor.process_airfoil(
        args.airfoil,
        surface_point_count=args.surface_points,
    )
    x_coord, y_coord = processed.x, processed.y
    chord = float(x_coord.max() - x_coord.min())

    # 未显式给速度时，使用理想气体声速 a=sqrt(gamma*R*T) 从 Mach 换算。
    velocity = args.velocity or args.mach * math.sqrt(1.4 * 287.05 * args.temperature)
    kinematic_viscosity = args.nu or velocity * chord / args.reynolds

    print("[2/5] Computing first-layer spacing for the target Y+...")
    wall = yplus_calc.estimate_wall_spacing(
        velocity, chord, kinematic_viscosity, args.y_plus
    )
    print(
        f"      Re={wall.reynolds_number:.6g}, Cf={wall.skin_friction_coefficient:.4e}, "
        f"delta_y={wall.first_layer_height:.4e} m"
    )

    print("[3/5] Generating the multiblock C-H quadrilateral mesh...")
    mesh_path = mesh_architect.generate_mesh(
        x_coord,
        y_coord,
        wall.first_layer_height,
        output_dir=output_dir,
        farfield_chords=args.farfield,
        domain_scale=args.domain_scale,
        boundary_layer_thickness_pct=args.boundary_layer_thickness,
        growth_ratio=args.growth_ratio,
        wall_size_pct=args.wall_size,
        farfield_size_pct=args.farfield_size,
        global_refinement=args.global_refinement,
        leading_edge_size_pct=args.leading_edge_size,
        trailing_upper_size_pct=args.trailing_upper_size,
        trailing_lower_size_pct=args.trailing_lower_size,
        wake_refinement=args.wake_refinement,
        show_gui=args.show_gmsh,
    )
    print(f"      Mesh: {mesh_path}")

    parameters = {
        "SOLVER": args.solver,
        "TURBULENCE_MODEL": args.turbulence if args.solver == "RANS" else "NONE",
        "TURBULENCE_OPTIONS": (
            "SA_OPTIONS= NEGATIVE, EXPERIMENTAL"
            if args.solver == "RANS" and args.turbulence == "SA"
            else ""
        ),
        "AIRFOIL_BOUNDARY": ("MARKER_HEATFLUX= ( airfoil, 0.0 )" if args.solver == "RANS"
                             else "MARKER_EULER= ( airfoil )"),
        "CFL_NUMBER": args.cfl,
        "RESIDUAL_MIN": args.residual_min,
        "MACH": args.mach,
        "AOA": args.aoa,
        "REYNOLDS": args.reynolds,
        "REYNOLDS_LENGTH": chord,
        "TEMPERATURE": args.temperature,
        "ITERATIONS": args.iterations,
        "MUSCL_TURB": "YES" if args.solver == "RANS" else "NO",
    }
    run_config = su2_driver.generate_config(
        parameters,
        template_path=PROJECT_ROOT / "config_template.cfg",
        output_dir=output_dir,
    )
    print(f"[4/5] SU2 configuration: {run_config}")
    if args.mesh_only:
        print("      Mesh-only mode: skipping the solver and report.")
        return None

    su2_driver.run_cfd_streaming(
        parameters,
        template_path=PROJECT_ROOT / "config_template.cfg",
        output_dir=output_dir,
        threads=args.threads,
        log_callback=print,
        process_control=process_control,
    )
    if args.skip_report:
        print("[5/5] Report generation skipped.")
        return None

    print("[5/5] Generating the SU2 aerodynamic report...")
    return post_analyzer.generate_report(output_dir, language=args.language)


def validate_args(args: argparse.Namespace) -> None:
    def error(message: str) -> None:
        raise ValueError(message)
    if args.threads < 1:
        error("--threads must be at least 1.")
    if not math.isfinite(args.aoa) or not math.isfinite(args.residual_min):
        error("aoa and residual_min must be finite.")
    if args.iterations <= 0:
        error("--iterations must be greater than zero.")
    if args.surface_points < 8:
        error("--surface-points must be at least 8.")
    if not (
        mesh_architect.GLOBAL_REFINEMENT_MIN
        <= args.global_refinement
        <= mesh_architect.GLOBAL_REFINEMENT_MAX
    ):
        error(
            f"--global-refinement must be between {mesh_architect.GLOBAL_REFINEMENT_MIN} "
            f"and {mesh_architect.GLOBAL_REFINEMENT_MAX}."
        )
    if not (
        mesh_architect.DOMAIN_SCALE_MIN
        <= args.domain_scale
        <= mesh_architect.DOMAIN_SCALE_MAX
    ):
        error(
            f"--domain-scale must be between {mesh_architect.DOMAIN_SCALE_MIN} "
            f"and {mesh_architect.DOMAIN_SCALE_MAX}."
        )
    if args.farfield * args.domain_scale < 5.0:
        error("The product of --farfield and --domain-scale must be at least 5.")
    control_sizes = (
        args.leading_edge_size,
        args.trailing_upper_size,
        args.trailing_lower_size,
    )
    if any(size > 0.05 for size in control_sizes):
        error("Leading- and trailing-edge target sizes must be between 0 and 0.05.")
    if not (
        mesh_architect.WAKE_REFINEMENT_MIN
        <= args.wake_refinement
        <= mesh_architect.WAKE_REFINEMENT_MAX
    ):
        error("--wake-refinement must be between 1 and 12.")
    if args.mesh_only and args.post_only:
        error("--mesh-only and --post-only cannot be used together.")
    if args.boundary_layer_thickness > 0.5:
        error("--boundary-layer-thickness must be in (0, 0.5].")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        report = run_pipeline(args)
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if report:
        print(f"Completed. Report saved: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
