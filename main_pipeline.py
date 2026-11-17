"""SU2_AutoFoil 顶层命令行入口：只负责参数解析和模块调度。"""

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
        raise argparse.ArgumentTypeError("该参数必须大于 0。")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从翼型 DAT 自动生成全结构化二维网格、运行 SU2 并输出气动报告。"
    )
    parser.add_argument(
        "airfoil",
        nargs="?",
        default=airfoil_processor.BUILTIN_NACA0012,
        help="Selig 顺序的翼型 .dat 文件；省略时使用内置解析 NACA0012。",
    )
    parser.add_argument(
        "--surface-points", type=int, default=100, help="上下表面共同点数（每侧）。"
    )
    parser.add_argument(
        "--global-refinement",
        type=_positive_float,
        default=1.0,
        help="全局网格加密系数，范围 0.05 到 10.0；小于 1 生成粗网格。",
    )
    parser.add_argument(
        "--leading-edge-size",
        type=_positive_float,
        default=0.0015,
        help="连续前缘控制点目标尺寸/弦长。",
    )
    parser.add_argument(
        "--trailing-upper-size",
        type=_positive_float,
        default=0.0015,
        help="后缘上控制点目标尺寸/弦长。",
    )
    parser.add_argument(
        "--trailing-lower-size",
        type=_positive_float,
        default=0.0015,
        help="后缘下控制点目标尺寸/弦长。",
    )
    parser.add_argument(
        "--wake-refinement",
        type=_positive_float,
        default=2.0,
        help="后缘尾迹块加密系数，范围 1 到 12。",
    )
    parser.add_argument("--mach", type=_positive_float, default=0.15)
    parser.add_argument("--aoa", type=float, default=2.0, help="攻角，单位为度。")
    parser.add_argument("--reynolds", type=_positive_float, default=3.0e6)
    parser.add_argument("--temperature", type=_positive_float, default=288.15, help="自由来流温度 K。")
    parser.add_argument(
        "--velocity",
        type=_positive_float,
        help="来流速度 m/s；省略时由 Mach 和温度计算。",
    )
    parser.add_argument(
        "--nu",
        type=_positive_float,
        help="运动黏度 m^2/s；省略时由 Re=VL/nu 反算。",
    )
    parser.add_argument("--y-plus", type=_positive_float, default=1.0, dest="y_plus")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--threads", type=int, default=1, help="SU2 OpenMP threads (no MPI required).")
    parser.add_argument("--solver", choices=("RANS", "EULER"), default="RANS")
    parser.add_argument("--turbulence", choices=("SA", "SST"), default="SA")
    parser.add_argument("--cfl", type=_positive_float, default=5.0)
    parser.add_argument("--residual-min", type=float, default=-8.0)
    parser.add_argument("--farfield", type=_positive_float, default=20.0, help="远场半径/弦长。")
    parser.add_argument(
        "--domain-scale",
        type=_positive_float,
        default=1.0,
        help="流场域缩放系数，范围 0.25 到 10.0；与远场半径相乘。",
    )
    parser.add_argument("--growth-ratio", type=_positive_float, default=1.15)
    parser.add_argument(
        "--boundary-layer-thickness",
        type=_positive_float,
        default=0.08,
        help="附面层结构块总厚度/弦长，默认 0.08。",
    )
    parser.add_argument(
        "--wall-size",
        type=_positive_float,
        default=0.008,
        help="兼容旧版参数；全结构网格中由全局加密系数接管。",
    )
    parser.add_argument(
        "--farfield-size",
        type=_positive_float,
        default=0.4,
        help="远场目标单元尺寸/弦长。",
    )
    parser.add_argument("--output-dir", default=str(data_root()))
    parser.add_argument("--show-gmsh", action="store_true", help="划分网格后打开 Gmsh GUI。")
    parser.add_argument("--mesh-only", action="store_true", help="生成网格和 run.cfg，但不启动 SU2。")
    parser.add_argument("--post-only", action="store_true", help="只读取已有 CSV 并重新生成报告。")
    parser.add_argument("--skip-report", action="store_true", help="求解后不生成 PNG 报告。")
    parser.add_argument(
        "--language", choices=("zh", "en"), default="zh", help="报告语言：zh 或 en。"
    )
    return parser


def run_pipeline(args: argparse.Namespace) -> Path | None:
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.post_only:
        print("[1/1] 正在从已有 SU2 CSV 生成报告...")
        return post_analyzer.generate_report(output_dir, language=args.language)

    print("[1/5] 正在清洗翼型并统一为尖后缘...")
    processed = airfoil_processor.process_airfoil(
        args.airfoil,
        surface_point_count=args.surface_points,
    )
    x_coord, y_coord = processed.x, processed.y
    chord = float(x_coord.max() - x_coord.min())

    # 未显式给速度时，使用理想气体声速 a=sqrt(gamma*R*T) 从 Mach 换算。
    velocity = args.velocity or args.mach * math.sqrt(1.4 * 287.05 * args.temperature)
    kinematic_viscosity = args.nu or velocity * chord / args.reynolds

    print("[2/5] 正在计算目标 Y+ 对应的第一层高度...")
    wall = yplus_calc.estimate_wall_spacing(
        velocity, chord, kinematic_viscosity, args.y_plus
    )
    print(
        f"      Re={wall.reynolds_number:.6g}, Cf={wall.skin_friction_coefficient:.4e}, "
        f"delta_y={wall.first_layer_height:.4e} m"
    )

    print("[3/5] 正在生成 Pointwise 风格多块 C-H 四边形网格...")
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
    print(f"      网格: {mesh_path}")

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
    print(f"[4/5] SU2 配置已生成: {run_config}")
    if args.mesh_only:
        print("      --mesh-only 已启用，跳过求解与报告。")
        return None

    su2_driver.run_cfd_streaming(
        parameters,
        template_path=PROJECT_ROOT / "config_template.cfg",
        output_dir=output_dir,
        threads=args.threads,
        log_callback=print,
    )
    if args.skip_report:
        print("[5/5] --skip-report 已启用，流程结束。")
        return None

    print("[5/5] 正在生成 SU2 气动报告...")
    return post_analyzer.generate_report(output_dir, language=args.language)


def validate_args(args: argparse.Namespace) -> None:
    def error(message: str) -> None:
        raise ValueError(message)
    if args.threads < 1:
        error("--threads must be at least 1.")
    if not math.isfinite(args.aoa) or not math.isfinite(args.residual_min):
        error("aoa and residual_min must be finite.")
    if args.iterations <= 0:
        error("--iterations 必须大于 0。")
    if args.surface_points < 8:
        error("--surface-points 不能小于 8。")
    if not (
        mesh_architect.GLOBAL_REFINEMENT_MIN
        <= args.global_refinement
        <= mesh_architect.GLOBAL_REFINEMENT_MAX
    ):
        error(
            f"--global-refinement 必须处于 {mesh_architect.GLOBAL_REFINEMENT_MIN} "
            f"到 {mesh_architect.GLOBAL_REFINEMENT_MAX}。"
        )
    if not (
        mesh_architect.DOMAIN_SCALE_MIN
        <= args.domain_scale
        <= mesh_architect.DOMAIN_SCALE_MAX
    ):
        error(
            f"--domain-scale 必须处于 {mesh_architect.DOMAIN_SCALE_MIN} "
            f"到 {mesh_architect.DOMAIN_SCALE_MAX}。"
        )
    if args.farfield * args.domain_scale < 5.0:
        error("--farfield 与 --domain-scale 的乘积不能小于 5。")
    control_sizes = (
        args.leading_edge_size,
        args.trailing_upper_size,
        args.trailing_lower_size,
    )
    if any(size > 0.05 for size in control_sizes):
        error("前缘、后缘上和后缘下尺寸都必须处于 0 到 0.05。")
    if not (
        mesh_architect.WAKE_REFINEMENT_MIN
        <= args.wake_refinement
        <= mesh_architect.WAKE_REFINEMENT_MAX
    ):
        error("--wake-refinement 必须处于 1 到 12。")
    if args.mesh_only and args.post_only:
        error("--mesh-only 与 --post-only 不能同时使用。")
    if args.boundary_layer_thickness > 0.5:
        error("--boundary-layer-thickness 必须处于 (0, 0.5]。")


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
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    if report:
        print(f"流程完成，报告已保存: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
