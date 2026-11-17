from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from core_modules.field_visualizer import (
    list_available_fields,
    read_vtu,
    render_contour,
    refine_quads_for_display,
    smooth_scalar_for_display,
    triangulate,
)
from tests.tmp_workspace import workspace_temp_dir


def _build_appended_vtu(path: Path) -> None:
    """手工构造一个含三角形 + 四边形混合单元的 appended 二进制 VTU。"""
    points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.5, 1.6, 0.0],
        ],
        dtype="<f4",
    )
    connectivity = np.array([0, 1, 4, 2, 3, 4, 0, 1, 3, 2], dtype="<i4")
    offsets = np.array([3, 6, 10], dtype="<i4")
    types = np.array([5, 5, 9], dtype="u1")
    mach = np.array([0.1, 0.2, 0.15, 0.25, 0.9], dtype="<f4")
    pressure = np.array([101000.0, 100500.0, 100800.0, 100200.0, 99900.0], dtype="<f4")

    parts = [
        points.tobytes(),
        connectivity.tobytes(),
        offsets.tobytes(),
        types.tobytes(),
        mach.tobytes(),
        pressure.tobytes(),
    ]
    offsets_bytes = []
    position = 0
    for part in parts:
        offsets_bytes.append(position)
        position += len(part)

    header = (
        '<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian" '
        'header_type="UInt64">\n<UnstructuredGrid>\n'
        f'<Piece NumberOfPoints="{len(points)}" NumberOfCells="{len(types)}">\n'
    )
    arrays = (
        '<Points><DataArray type="Float32" NumberOfComponents="3" '
        f'offset="{offsets_bytes[0]}" format="appended"/></Points>\n'
        "<Cells>\n"
        f'<DataArray type="Int32" Name="connectivity" offset="{offsets_bytes[1]}" format="appended"/>\n'
        f'<DataArray type="Int32" Name="offsets" offset="{offsets_bytes[2]}" format="appended"/>\n'
        f'<DataArray type="UInt8" Name="types" offset="{offsets_bytes[3]}" format="appended"/>\n'
        "</Cells>\n<PointData>\n"
        f'<DataArray type="Float32" Name="Mach" offset="{offsets_bytes[4]}" format="appended"/>\n'
        f'<DataArray type="Float32" Name="Pressure" offset="{offsets_bytes[5]}" format="appended"/>\n'
        "</PointData>\n</Piece>\n</UnstructuredGrid>\n<AppendedData encoding=\"raw\">\n_"
    )
    footer = "\n</AppendedData>\n</VTKFile>\n"
    path.write_bytes(
        (header + arrays).encode("ascii") + b"".join(parts) + footer.encode("ascii")
    )


def _build_su2_style_vtu(path: Path) -> None:
    """构造 SU2 风格的 VTU：appended 段每个数组前都有 8 字节块长度头。"""
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.5, 1.6, 0.0]],
        dtype="<f4",
    )
    connectivity = np.array([0, 1, 4, 2, 3, 4, 0, 1, 3, 2], dtype="<i4")
    offsets = np.array([3, 6, 10], dtype="<i4")
    types = np.array([5, 5, 9], dtype="u1")
    mach = np.array([0.1, 0.2, 0.15, 0.25, 0.9], dtype="<f4")

    blocks = [points, connectivity, offsets, types, mach]
    header_type = "UInt64"
    body = bytearray()
    array_offsets = []
    for block in blocks:
        array_offsets.append(len(body))
        data = block.astype(block.dtype).tobytes()
        body += np.uint64(len(data)).tobytes() + data
    header = (
        '<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian" '
        f'header_type="{header_type}">\n<UnstructuredGrid>\n'
        f'<Piece NumberOfPoints="{len(points)}" NumberOfCells="{len(types)}">\n'
    )
    arrays = (
        '<Points><DataArray type="Float32" NumberOfComponents="3" '
        f'offset="{array_offsets[0]}" format="appended"/></Points>\n'
        "<Cells>\n"
        f'<DataArray type="Int32" Name="connectivity" offset="{array_offsets[1]}" format="appended"/>\n'
        f'<DataArray type="Int32" Name="offsets" offset="{array_offsets[2]}" format="appended"/>\n'
        f'<DataArray type="UInt8" Name="types" offset="{array_offsets[3]}" format="appended"/>\n'
        "</Cells>\n<PointData>\n"
        f'<DataArray type="Float32" Name="Mach" offset="{array_offsets[4]}" format="appended"/>\n'
        "</PointData>\n</Piece>\n</UnstructuredGrid>\n<AppendedData encoding=\"raw\">\n_"
    )
    footer = "\n</AppendedData>\n</VTKFile>\n"
    path.write_bytes(
        (header + arrays).encode("ascii") + bytes(body) + footer.encode("ascii")
    )


class FieldVisualizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = workspace_temp_dir()
        self.directory: Path = self._temporary.__enter__()
        self.vtu_path = self.directory / "flow.vtu"
        _build_appended_vtu(self.vtu_path)

    def tearDown(self) -> None:
        self._temporary.__exit__(None, None, None)

    def test_read_appended_vtu_geometry_and_fields(self) -> None:
        data = read_vtu(self.vtu_path)
        self.assertEqual(data.n_points, 5)
        self.assertEqual(len(data.cells), 3)
        self.assertEqual(data.cells[0][0], 5)  # 三角形
        self.assertEqual(data.cells[2][0], 9)  # 四边形
        np.testing.assert_array_equal(data.cells[2][1], [0, 1, 3, 2])
        np.testing.assert_allclose(data.points[0], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(
            np.asarray(data.point_data["Mach"]), [0.1, 0.2, 0.15, 0.25, 0.9]
        )

    def test_read_su2_style_vtu_with_block_headers(self) -> None:
        """SU2 的 VTU 每个数组前有 8 字节块长度头，必须正确跳过。"""
        su2_path = self.directory / "flow_su2_style.vtu"
        _build_su2_style_vtu(su2_path)
        data = read_vtu(su2_path)
        self.assertEqual(data.n_points, 5)
        self.assertEqual(len(data.cells), 3)
        self.assertEqual(sorted({cell_type for cell_type, _ in data.cells}), [5, 9])
        np.testing.assert_array_equal(data.cells[2][1], [0, 1, 3, 2])
        np.testing.assert_allclose(data.points[0], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(
            np.asarray(data.point_data["Mach"]), [0.1, 0.2, 0.15, 0.25, 0.9]
        )

    def test_triangulate_splits_quads(self) -> None:
        data = read_vtu(self.vtu_path)
        triangles = triangulate(data.cells)
        self.assertEqual(len(triangles), 4)  # 2 个三角形 + 1 个四边形拆成 2 个

    def test_display_refinement_splits_quad_symmetrically_without_new_extrema(self) -> None:
        x_coord = np.asarray([0.0, 1.0, 1.0, 0.0])
        y_coord = np.asarray([0.0, 0.0, 1.0, 1.0])
        values = np.asarray([0.0, 2.0, 4.0, 6.0])
        cells = [(9, np.asarray([0, 1, 2, 3], dtype=np.int64))]
        x_new, y_new, triangles, values_new, refined = refine_quads_for_display(
            x_coord, y_coord, values, cells
        )
        self.assertTrue(refined)
        self.assertEqual(len(x_new), 5)
        self.assertEqual(len(y_new), 5)
        self.assertEqual(triangles.shape, (4, 3))
        self.assertAlmostEqual(values_new[-1], 3.0)
        self.assertGreaterEqual(float(np.min(values_new)), float(np.min(values)))
        self.assertLessEqual(float(np.max(values_new)), float(np.max(values)))

    def test_display_smoothing_reduces_scalar_zigzag_without_new_extrema(self) -> None:
        count = 40
        baseline = np.linspace(-0.8, 0.3, count)
        values = baseline + 0.08 * np.where(np.arange(count) % 2, 1.0, -1.0)
        triangles = np.column_stack(
            (
                np.arange(count - 2),
                np.arange(1, count - 1),
                np.arange(2, count),
            )
        )
        smoothed = smooth_scalar_for_display(values, triangles)
        raw_roughness = float(np.mean(np.abs(np.diff(values, n=2))))
        smooth_roughness = float(np.mean(np.abs(np.diff(smoothed, n=2))))
        self.assertLess(smooth_roughness, raw_roughness)
        self.assertGreaterEqual(float(np.min(smoothed)), float(np.min(values)))
        self.assertLessEqual(float(np.max(smoothed)), float(np.max(values)))

    def test_render_contour_writes_png(self) -> None:
        output = render_contour(
            self.vtu_path, "Mach", self.directory / "Contour_Mach.png"
        )
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 10_000)

    def test_list_available_fields(self) -> None:
        available = list_available_fields(self.vtu_path)
        self.assertIn("Mach", available)
        self.assertIn("Pressure", available)
        self.assertNotIn("Temperature", available)

    def test_render_contour_ascii_format(self) -> None:
        ascii_path = self.directory / "flow_ascii.vtu"
        data = read_vtu(self.vtu_path)
        lines = [
            '<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian">',
            "<UnstructuredGrid>",
            f'<Piece NumberOfPoints="{data.n_points}" NumberOfCells="{len(data.cells)}">',
            "<Points>",
            '<DataArray type="Float32" NumberOfComponents="3" format="ascii">',
            " ".join(f"{v:.6g}" for point in data.points for v in point),
            "</DataArray>",
            "</Points>",
            "<Cells>",
            '<DataArray type="Int32" Name="connectivity" format="ascii">',
            " ".join(str(node) for _, cell in data.cells for node in cell),
            "</DataArray>",
            '<DataArray type="Int32" Name="offsets" format="ascii">',
            " ".join(
                str(offset)
                for offset in np.cumsum([len(cell) for _, cell in data.cells])
            ),
            "</DataArray>",
            '<DataArray type="UInt8" Name="types" format="ascii">',
            " ".join(str(cell_type) for cell_type, _ in data.cells),
            "</DataArray>",
            "</Cells>",
            "<PointData>",
            '<DataArray type="Float32" Name="Mach" format="ascii">',
            " ".join(f"{v:.6g}" for v in np.asarray(data.point_data["Mach"])),
            "</DataArray>",
            "</PointData>",
            "</Piece>",
            "</UnstructuredGrid>",
            "</VTKFile>",
        ]
        ascii_path.write_text("\n".join(lines), encoding="utf-8")
        parsed = read_vtu(ascii_path)
        np.testing.assert_allclose(parsed.points, data.points, rtol=1.0e-6)
        output = render_contour(
            ascii_path, "Mach", self.directory / "Contour_ascii.png"
        )
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
