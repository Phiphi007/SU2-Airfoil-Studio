from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from core_modules.airfoil_processor import BUILTIN_NACA0012, process_airfoil
from core_modules.mesh_architect import (
    _clean_sharp_boundary,
    estimate_mesh_counts,
    _resample_sharp_airfoil,
    _rotate_to_chord_axis,
    _write_su2_file,
    generate_mesh,
)
from tests.tmp_workspace import workspace_temp_dir


def _read_su2_mesh(
    mesh_path: Path,
) -> tuple[list[str], np.ndarray, dict[str, list[tuple[int, int]]]]:
    """读取 SU2 网格：单元行、节点坐标与各标记的边界边（保持文件内 0 基索引）。"""
    lines = mesh_path.read_text(encoding="utf-8").splitlines()
    element_count = int(lines[1].split("=", 1)[1])
    elements = lines[2 : 2 + element_count]
    point_header = 2 + element_count
    point_count = int(lines[point_header].split("=", 1)[1])
    nodes = np.array(
        [
            [float(value) for value in line.split()[:2]]
            for line in lines[point_header + 1 : point_header + 1 + point_count]
        ]
    )
    markers: dict[str, list[tuple[int, int]]] = {}
    index = point_header + 1 + point_count
    n_mark = int(lines[index].split("=", 1)[1])
    index += 1
    for _ in range(n_mark):
        name = lines[index].split("=", 1)[1].strip()
        index += 1
        count = int(lines[index].split("=", 1)[1])
        index += 1
        edges = []
        for line in lines[index : index + count]:
            fields = line.split()
            edges.append((int(fields[1]), int(fields[2])))
        markers[name] = edges
        index += count
    return elements, nodes, markers


def _signed_area(vertices: np.ndarray) -> float:
    return 0.5 * float(
        np.sum(
            vertices[:, 0] * np.roll(vertices[:, 1], -1)
            - np.roll(vertices[:, 0], -1) * vertices[:, 1]
        )
    )


def _nearest_distances(reference: np.ndarray, query: np.ndarray) -> np.ndarray:
    return np.sqrt(
        np.min(np.sum((query[:, None, :2] - reference[None, :, :2]) ** 2, axis=2), axis=1)
    )


class MeshArchitectTests(unittest.TestCase):
    def test_structured_mesh_contains_only_quadrilaterals(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=121)
        with workspace_temp_dir() as temporary_dir:
            mesh_path = generate_mesh(
                processed.x,
                processed.y,
                delta_y=7.1e-6,
                output_dir=temporary_dir,
                wall_size_pct=0.008,
                farfield_size_pct=0.4,
                terminal_output=False,
            )
            elements, nodes, markers = _read_su2_mesh(mesh_path)
            quality = json.loads(
                (Path(temporary_dir) / "mesh_quality.json").read_text(
                    encoding="utf-8"
                )
            )

        element_types = [line.split()[0] for line in elements]
        self.assertEqual(set(element_types), {"9"})

        # 全部体单元有向面积为正（逆时针）。
        minimum_area = float("inf")
        for line in elements:
            fields = [int(value) for value in line.split()]
            connectivity = np.asarray(fields[1:-1], dtype=int)  # 文件内为 0 基
            vertices = nodes[connectivity]
            area = _signed_area(vertices)
            minimum_area = min(minimum_area, area)
            self.assertGreater(area, 1.0e-14)
        self.assertGreater(minimum_area, 0.0)

        # 三个物理标记都存在。C-H 多块外边界比翼面包含更多节点，不能再用
        # 旧的单环 C 网格假设要求两者边数相等。
        self.assertEqual(
            set(markers), {"airfoil", "farfield_inlet", "farfield_outlet"}
        )
        self.assertTrue(all(len(edges) > 0 for edges in markers.values()))
        self.assertEqual(
            quality["topology"], "strict_sharp_te_multiblock_c_h_grid"
        )
        self.assertEqual(quality["trailing_edge_gap"], 0.0)
        self.assertEqual(quality["wake_boundary_spreading_angle_deg"], 0.0)
        self.assertGreater(quality["wake_streamwise_nodes"], 500)
        self.assertLess(
            quality["te_upper_control_index"], quality["leading_control_index"]
        )
        self.assertLess(
            quality["leading_control_index"], quality["te_lower_control_index"]
        )
        self.assertGreaterEqual(
            quality["median_bl_to_external_height_ratio"], 0.85
        )
        self.assertLessEqual(
            quality["median_bl_to_external_height_ratio"], 1.15
        )
        self.assertGreaterEqual(quality["p05_bl_to_external_height_ratio"], 0.65)
        self.assertLessEqual(quality["p95_bl_to_external_height_ratio"], 1.50)
        self.assertGreaterEqual(quality["minimum_angle_deg"], 30.0)
        self.assertGreaterEqual(quality["minimum_scaled_jacobian"], 0.40)
        self.assertGreaterEqual(quality["leading_edge_nodes_upper_5pct"], 30)
        self.assertGreaterEqual(quality["leading_edge_nodes_lower_5pct"], 30)
        self.assertLessEqual(quality["wall_spacing_max_adjacent_ratio"], 1.10)
        self.assertLessEqual(
            quality["leading_edge_radial_direction_p95_step_deg"], 8.0
        )

    def test_single_leading_edge_and_trailing_sizes_are_local(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=81)
        rotated, _, chord = _rotate_to_chord_axis(processed.x, processed.y)
        boundary = _clean_sharp_boundary(rotated, chord)
        coarse, coarse_controls = _resample_sharp_airfoil(
            boundary,
            chord,
            0.006,
            0.003,
            0.003,
            1.0,
        )
        fine, fine_controls = _resample_sharp_airfoil(
            boundary,
            chord,
            0.003,
            0.0015,
            0.0015,
            1.0,
        )
        self.assertGreater(len(fine), len(coarse))
        self.assertEqual(fine_controls["te_upper"], 0)
        self.assertEqual(fine_controls["te_lower"], len(fine) - 1)
        self.assertGreater(fine_controls["leading"], coarse_controls["leading"])
        np.testing.assert_allclose(fine[0], fine[-1], atol=1.0e-14)

    def test_default_leading_edge_distribution_is_dense_and_smooth(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=100)
        rotated, _, chord = _rotate_to_chord_axis(processed.x, processed.y)
        boundary = _clean_sharp_boundary(rotated, chord)
        sampled, controls = _resample_sharp_airfoil(
            boundary, chord, 0.0015, 0.0015, 0.0015, 1.0
        )
        leading = controls["leading"]
        front_limit = sampled[leading, 0] + 0.05 * chord
        self.assertGreaterEqual(
            int(np.count_nonzero(sampled[: leading + 1, 0] <= front_limit)), 30
        )
        self.assertGreaterEqual(
            int(np.count_nonzero(sampled[leading:, 0] <= front_limit)), 30
        )
        edge = np.linalg.norm(np.diff(sampled, axis=0), axis=1)
        ratio = np.maximum(edge[1:] / edge[:-1], edge[:-1] / edge[1:])
        self.assertLessEqual(float(np.max(ratio)), 1.10)

    def test_wake_refinement_increases_only_wake_stream_density(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=50)
        reports = []
        for refinement in (1.0, 3.0):
            with workspace_temp_dir() as temporary_dir:
                generate_mesh(
                    processed.x,
                    processed.y,
                    delta_y=7.1e-6,
                    output_dir=temporary_dir,
                    global_refinement=0.5,
                    wake_refinement=refinement,
                    terminal_output=False,
                )
                reports.append(
                    json.loads(
                        (Path(temporary_dir) / "mesh_quality.json").read_text(
                            encoding="utf-8"
                        )
                    )
                )
        self.assertEqual(reports[0]["surface_nodes"], reports[1]["surface_nodes"])
        self.assertLess(
            reports[0]["wake_streamwise_nodes"],
            reports[1]["wake_streamwise_nodes"],
        )
        self.assertGreater(
            reports[0]["wake_streamwise_first_cell_pct"],
            reports[1]["wake_streamwise_first_cell_pct"],
        )

    def test_airfoil_boundary_follows_airfoil_geometry(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=121)
        with workspace_temp_dir() as temporary_dir:
            mesh_path = generate_mesh(
                processed.x,
                processed.y,
                delta_y=7.1e-6,
                output_dir=temporary_dir,
                wall_size_pct=0.008,
                farfield_size_pct=0.4,
                terminal_output=False,
            )
            _, nodes, markers = _read_su2_mesh(mesh_path)

        rotated, _, _ = _rotate_to_chord_axis(processed.x, processed.y)
        airfoil_edges = markers["airfoil"]
        boundary_indices = sorted(
            {index for edge in airfoil_edges for index in edge}
        )
        boundary_nodes = nodes[boundary_indices]
        distances = _nearest_distances(rotated, boundary_nodes[:, :2])
        self.assertLess(float(np.max(distances)), 0.02)

    def test_first_boundary_layer_height_matches_target_delta_y(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=121)
        delta_y = 7.1e-6
        with workspace_temp_dir() as temporary_dir:
            mesh_path = generate_mesh(
                processed.x,
                processed.y,
                delta_y=delta_y,
                output_dir=temporary_dir,
                wall_size_pct=0.008,
                farfield_size_pct=0.4,
                terminal_output=False,
            )
            elements, nodes, markers = _read_su2_mesh(mesh_path)

        # 每个翼面边界节点都存在一个相邻体单元，其法向第一层高度接近 delta_y。
        element_nodes = [
            [int(value) for value in line.split()[1:-1]] for line in elements
        ]
        adjacency: dict[int, set[int]] = {}
        for element in element_nodes:
            for node in element:
                adjacency.setdefault(node, set()).update(element)
        heights: list[float] = []
        for edge in markers["airfoil"]:
            for wall_node in edge:
                neighbors = adjacency.get(wall_node, set())
                if len(neighbors) < 2:
                    continue
                others = np.asarray(sorted(neighbors - {wall_node}), dtype=int)
                heights.append(
                    float(
                        np.min(
                            np.linalg.norm(nodes[others] - nodes[wall_node], axis=1)
                        )
                    )
                )
        heights.sort()
        median_height = float(np.median(heights))
        self.assertLessEqual(median_height, delta_y * 2.5)
        self.assertGreaterEqual(median_height, delta_y * 0.4)

    def test_sharp_airfoil_boundary_follows_processed_geometry(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=50)
        with workspace_temp_dir() as temporary_dir:
            mesh_path = generate_mesh(
                processed.x,
                processed.y,
                delta_y=7.1e-6,
                output_dir=temporary_dir,
                wall_size_pct=0.012,
                farfield_size_pct=0.4,
                terminal_output=False,
            )
            _, nodes, markers = _read_su2_mesh(mesh_path)

        rotated, _, chord = _rotate_to_chord_axis(processed.x, processed.y)
        tip_x = float(np.max(rotated[:, 0]))
        boundary_indices = sorted(
            {index for edge in markers["airfoil"] for index in edge}
        )
        wall_nodes = nodes[boundary_indices][:, :2]
        distances = _nearest_distances(rotated, wall_nodes)
        self.assertLess(float(np.max(distances)), 0.025 * chord)
        # 物理上重合的尖后缘逻辑端必须保留在翼面边界上。
        te_point = rotated[np.argmax(rotated[:, 0])]
        te_distance = _nearest_distances(wall_nodes, np.asarray([te_point]))
        self.assertLess(float(np.max(te_distance)), 1.0e-10)

    def test_global_refinement_controls_entire_mesh_density(self) -> None:
        """全局系数必须同时增加翼面节点和总四边形数。"""
        counts: dict[float, tuple[int, int]] = {}
        for refinement in (0.5, 1.0, 1.5):
            processed = process_airfoil(
                BUILTIN_NACA0012, surface_point_count=50
            )
            with workspace_temp_dir() as temporary_dir:
                mesh_path = generate_mesh(
                    processed.x,
                    processed.y,
                    delta_y=7.1e-6,
                    output_dir=temporary_dir,
                    wall_size_pct=0.012,
                    farfield_size_pct=0.4,
                    global_refinement=refinement,
                    terminal_output=False,
                )
                elements, _, markers = _read_su2_mesh(mesh_path)
            counts[refinement] = (len(markers["airfoil"]), len(elements))
        self.assertLess(counts[0.5][0], counts[1.0][0])
        self.assertLess(counts[1.0][0], counts[1.5][0])
        self.assertLess(counts[0.5][1], counts[1.0][1])
        self.assertLess(counts[1.0][1], counts[1.5][1])

    def test_extra_coarse_refinement_and_domain_scale(self) -> None:
        processed = process_airfoil(BUILTIN_NACA0012, surface_point_count=100)
        results = []
        for refinement in (0.05, 0.10, 0.25):
            with workspace_temp_dir() as temporary_dir:
                generate_mesh(
                    processed.x,
                    processed.y,
                    delta_y=8.45e-6,
                    output_dir=temporary_dir,
                    global_refinement=refinement,
                    terminal_output=False,
                )
                report = json.loads(
                    (Path(temporary_dir) / "mesh_quality.json").read_text(
                        encoding="utf-8"
                    )
                )
            self.assertGreaterEqual(report["minimum_angle_deg"], 30.0)
            self.assertGreaterEqual(report["minimum_scaled_jacobian"], 0.40)
            self.assertLessEqual(report["actual_boundary_layer_growth_ratio"], 2.0)
            results.append(report["quadrilateral_cells"])
        self.assertLess(results[0], results[1])
        self.assertLess(results[1], results[2])

        estimate = estimate_mesh_counts(
            processed.x,
            processed.y,
            8.45e-6,
            global_refinement=0.10,
            domain_scale=2.0,
        )
        with workspace_temp_dir() as temporary_dir:
            generate_mesh(
                processed.x,
                processed.y,
                delta_y=8.45e-6,
                output_dir=temporary_dir,
                global_refinement=0.10,
                domain_scale=2.0,
                terminal_output=False,
            )
            actual = json.loads(
                (Path(temporary_dir) / "mesh_quality.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(actual["effective_farfield_chords"], 40.0)
        relative_error = abs(
            estimate["quadrilateral_cells"] - actual["quadrilateral_cells"]
        ) / actual["quadrilateral_cells"]
        self.assertLess(relative_error, 0.10)

    def test_mixed_mesh_runs_through_su2_writer_roundtrip(self) -> None:
        # 直接用自写器写一个 2 三角形 + 1 四边形的小混合网格，检查文件结构。
        nodes = np.array(
            [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 1.8]]
        )
        triangles = np.array([[1, 2, 5], [2, 4, 5]])
        quads = np.array([[1, 2, 4, 3]])
        markers = {
            "airfoil": np.array([[1, 2], [2, 4]]),
            "farfield_inlet": np.array([[3, 1], [5, 3]]),
            "farfield_outlet": np.array([[4, 5]]),
        }
        with workspace_temp_dir() as temporary_dir:
            mesh_path = Path(temporary_dir) / "mesh.su2"
            _write_su2_file(mesh_path, nodes, triangles, quads, markers)
            elements, written_nodes, written_markers = _read_su2_mesh(mesh_path)
        self.assertEqual(len(elements), 3)
        self.assertEqual(len(written_nodes), 5)
        # 0 基索引还原后连通性必须与输入一致。
        first_triangle = [int(v) for v in elements[0].split()[1:-1]]
        self.assertEqual(first_triangle, [0, 1, 4])
        self.assertEqual(written_markers["farfield_outlet"], [(3, 4)])


if __name__ == "__main__":
    unittest.main()
