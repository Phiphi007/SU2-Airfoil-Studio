"""全结构化网格独立进程入口；不要从 GUI 线程直接调用 main。"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .mesh_architect import generate_mesh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SU2 AutoFoil structured mesh worker")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--delta-y", required=True, type=float)
    parser.add_argument("--farfield", required=True, type=float)
    parser.add_argument("--domain-scale", required=True, type=float)
    parser.add_argument("--bl-thickness", required=True, type=float)
    parser.add_argument("--growth-ratio", required=True, type=float)
    parser.add_argument("--wall-size", required=True, type=float)
    parser.add_argument("--farfield-size", required=True, type=float)
    parser.add_argument("--global-refinement", required=True, type=float)
    parser.add_argument("--leading-edge-size", required=True, type=float)
    parser.add_argument("--trailing-upper-size", required=True, type=float)
    parser.add_argument("--trailing-lower-size", required=True, type=float)
    parser.add_argument("--wake-refinement", required=True, type=float)
    parser.add_argument("--show-gui", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input).resolve()
    with np.load(input_path) as coordinates:
        x_coord = np.asarray(coordinates["x"], dtype=float)
        y_coord = np.asarray(coordinates["y"], dtype=float)
    generate_mesh(
        x_coord,
        y_coord,
        args.delta_y,
        output_dir=args.output,
        farfield_chords=args.farfield,
        domain_scale=args.domain_scale,
        boundary_layer_thickness_pct=args.bl_thickness,
        growth_ratio=args.growth_ratio,
        wall_size_pct=args.wall_size,
        farfield_size_pct=args.farfield_size,
        global_refinement=args.global_refinement,
        leading_edge_size_pct=args.leading_edge_size,
        trailing_upper_size_pct=args.trailing_upper_size,
        trailing_lower_size_pct=args.trailing_lower_size,
        wake_refinement=args.wake_refinement,
        show_gui=args.show_gui,
        terminal_output=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
