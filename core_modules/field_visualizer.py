"""读取 SU2 的 ``flow.vtu`` 并渲染二维翼型流场云图。

VTU 解析
--------
SU2 写出的是 VTK XML UnstructuredGrid。这里用标准库 ``xml.etree`` 实现
轻量解析，支持两种数据存储方式：

- ``format="appended"``：数据块以原始二进制或 base64 形式附加在
  ``<AppendedData>`` 段，各数组用字节偏移量定位（``header_type`` 可为
  ``UInt32`` 或 ``UInt64``）。
- ``format="ascii"``：数据直接写在 ``<DataArray>`` 文本节点中。

云图渲染
--------
二维网格在显示阶段把每个四边形围绕中心拆成四个三角形，消除固定对角线
造成的方向性分片；主要体场再进行自适应弱双边平滑。两步都只作用于绘图
副本，原始 VTU 数据不会被改写。附面层单元长宽比很大，Matplotlib 的三角
等值线推进算法（``tricontourf``）在极扁单元上可能停滞，因此仍使用 Gouraud
着色的 ``tripcolor``。矢量场自动取模长。
"""

from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

_NUMPY_DTYPES = {
    "Float32": np.dtype("<f4"),
    "Float64": np.dtype("<f8"),
    "Int32": np.dtype("<i4"),
    "Int64": np.dtype("<i8"),
    "UInt8": np.dtype("u1"),
    "Int8": np.dtype("i1"),
    "UInt32": np.dtype("<u4"),
}

_VTK_NODES_PER_CELL = {5: 3, 9: 4, 3: 2, 10: 4, 12: 8}


def _dtype_for(data_type: str) -> np.dtype:
    if data_type not in _NUMPY_DTYPES:
        raise ValueError(f"不支持的 VTK 数据类型: {data_type}")
    return _NUMPY_DTYPES[data_type]


@dataclass
class VtuData:
    """解析后的 VTU 非结构网格数据。"""

    points: FloatArray
    cells: list[tuple[int, IntArray]]
    point_data: dict[str, FloatArray] = dataclass_field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return int(len(self.points))


def _parse_ascii_array(element: ET.Element) -> FloatArray:
    text = "".join(element.itertext())
    values = np.fromstring(text, sep=" ", dtype=float)
    components = int(float(element.get("NumberOfComponents", "1")))
    return values.reshape(-1, components) if components > 1 else values


def _load_appended_blob(
    raw_bytes: bytes,
    header_type: str,
    data_type: str,
    offset: int,
    count: int,
    components: int,
) -> FloatArray:
    dtype = _dtype_for(data_type)
    byte_count = count * components * dtype.itemsize
    # SU2 遵循 VTK 规范：appended 段每个数组前都有一个 header_type 字节的
    # 块长度头，且 offset 指向该头的起点。这里用“头值 == 数据字节数”自动
    # 探测：满足则跳过头，不满足则视为无头格式（例如自写测试文件）。
    start = offset
    if header_type.upper() == "UINT32":
        header_size = 4
        if len(raw_bytes) >= offset + 4:
            header_value = int(np.frombuffer(raw_bytes[offset : offset + 4], dtype="<u4")[0])
            if header_value == byte_count:
                start = offset + header_size
    else:
        header_size = 8
        if len(raw_bytes) >= offset + 8:
            header_value = int(np.frombuffer(raw_bytes[offset : offset + 8], dtype="<u8")[0])
            if header_value == byte_count:
                start = offset + header_size
    blob = raw_bytes[start : start + byte_count]
    if len(blob) < byte_count:
        raise ValueError(
            f"VTU 附加数据不足：偏移 {offset} 处需要 {byte_count} 字节，实际 {len(blob)}。"
        )
    values = np.frombuffer(blob, dtype=dtype, count=count * components).astype(float)
    return values.reshape(-1, components) if components > 1 else values


def read_vtu(path: str | Path) -> VtuData:
    """解析 SU2/VTK 非结构网格文件，返回节点、单元与节点场数据。"""
    vtu_path = Path(path).expanduser().resolve()
    if not vtu_path.is_file():
        raise FileNotFoundError(f"找不到体场文件: {vtu_path}")
    raw = vtu_path.read_bytes()
    # 二进制附加数据可能包含非法 UTF-8 字节，先手动切分 XML 部分。
    appended_index = raw.find(b"<AppendedData")
    xml_bytes = raw[:appended_index] if appended_index >= 0 else raw
    if appended_index >= 0:
        xml_bytes += b"</VTKFile>"
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"无法解析 VTU XML: {vtu_path}") from exc

    header_type = str(root.get("header_type", "UInt64"))
    piece = root.find(".//Piece")
    if piece is None:
        raise ValueError(f"VTU 文件缺少 Piece 段: {vtu_path}")
    n_points = int(piece.get("NumberOfPoints", "0"))
    n_cells = int(piece.get("NumberOfCells", "0"))

    appended_blob: bytes | None = None
    if appended_index >= 0:
        encoding = "raw"
        match = re.search(
            rb'<AppendedData[^>]*encoding="([^"]+)"', raw[appended_index:]
        )
        if match:
            encoding = match.group(1).decode("ascii")
        start = raw.find(b"_", appended_index) + 1
        if start <= 0:
            raise ValueError("VTU 附加数据段缺少下划线分隔符。")
        appended_blob = raw[start:]
        if encoding == "base64":
            appended_blob = base64.b64decode(appended_blob)

    points_element = piece.find("./Points/DataArray")
    if points_element is None:
        raise ValueError(f"VTU 文件缺少点坐标: {vtu_path}")
    points = _read_array(points_element, n_points, 3, appended_blob, header_type)

    cells: list[tuple[int, IntArray]] = []
    cell_arrays = {
        element.get("Name"): element for element in piece.findall("./Cells/DataArray")
    }
    connectivity = cell_arrays.get("connectivity")
    offsets = cell_arrays.get("offsets")
    types = cell_arrays.get("types")
    if connectivity is not None and offsets is not None and types is not None:
        offs = _read_array(offsets, n_cells, 1, appended_blob, header_type)
        typs = _read_array(types, n_cells, 1, appended_blob, header_type)
        conn = _read_array(
            connectivity, int(offs[-1]), 1, appended_blob, header_type
        )
        start = 0
        for end, vtk_type in zip(offs, typs):
            end = int(end)
            segment = conn[start:end].astype(np.int64)
            if segment.ndim > 1:
                segment = segment.reshape(-1)
            cells.append((int(vtk_type), segment))
            start = end
    elif connectivity is not None and offsets is None and types is None:
        # 单一单元类型的退化情况：由 Piece 属性推断。
        vtk_type = int(piece.get("vtk_type", "-1"))
        nodes_per_cell = _VTK_NODES_PER_CELL.get(vtk_type, 0)
        if vtk_type < 0 or nodes_per_cell == 0:
            raise ValueError("VTU 单元段缺少 types 数组且无法推断单元类型。")
        conn = _read_array(connectivity, None, 1, appended_blob, header_type)
        conn = conn.astype(np.int64).reshape(-1)
        cells = [
            (vtk_type, conn[i : i + nodes_per_cell])
            for i in range(0, len(conn), nodes_per_cell)
        ]
    else:
        raise ValueError(f"VTU 单元数据不完整: {vtu_path}")

    point_data: dict[str, FloatArray] = {}
    for element in piece.findall("./PointData/DataArray"):
        name = str(element.get("Name", "")).strip()
        if not name:
            continue
        components = int(float(element.get("NumberOfComponents", "1")))
        point_data[name] = _read_array(
            element, n_points, components, appended_blob, header_type
        )

    return VtuData(points=points, cells=cells, point_data=point_data)


def _read_array(
    element: ET.Element,
    expected_count: int | None,
    components: int,
    appended_blob: bytes | None,
    header_type: str,
) -> FloatArray:
    data_type = str(element.get("type", "Float32"))
    fmt = str(element.get("format", "ascii"))
    if fmt == "appended":
        if appended_blob is None:
            raise ValueError("VTU 使用 appended 格式但缺少附加数据段。")
        offset = int(element.get("offset", "0"))
        if expected_count is None:
            raise ValueError("appended 数组缺少元素数量信息。")
        return _load_appended_blob(
            appended_blob, header_type, data_type, offset, expected_count, components
        )
    return _parse_ascii_array(element)


# 云图可选字段：显示名 -> (VTU 数组名, 是否取模长)
CONTOUR_FIELDS: dict[str, tuple[str, bool]] = {
    "Mach": ("Mach", False),
    "Pressure": ("Pressure", False),
    "Pressure_Coefficient": ("Pressure_Coefficient", False),
    "Temperature": ("Temperature", False),
    "Density": ("Density", False),
    "Velocity": ("Velocity", True),
    "Momentum": ("Momentum", True),
    "Laminar_Viscosity": ("Laminar_Viscosity", False),
    "Eddy_Viscosity": ("Eddy_Viscosity", False),
    "Y_Plus": ("Y_Plus", False),
    "Skin_Friction_Coefficient": ("Skin_Friction_Coefficient", True),
    "Heat_Flux": ("Heat_Flux", False),
    "Nu_Tilde": ("Nu_Tilde", False),
}

# 这些是定义在体网格节点上的连续场，适合做保梯度的显示平滑。Y+、Cf、
# 热流等壁面诊断量不在这里处理，避免把壁面量扩散到外场。
_SMOOTHED_VOLUME_FIELDS = {
    "Mach",
    "Pressure",
    "Pressure_Coefficient",
    "Temperature",
    "Density",
    "Velocity",
    "Momentum",
    "Laminar_Viscosity",
    "Eddy_Viscosity",
    "Nu_Tilde",
}


def _find_field(data: VtuData, display_name: str) -> tuple[str, FloatArray]:
    if display_name not in CONTOUR_FIELDS:
        raise KeyError(
            f"未知云图字段: {display_name}，可选 {list(CONTOUR_FIELDS)}"
        )
    array_name, take_magnitude = CONTOUR_FIELDS[display_name]
    if array_name not in data.point_data:
        raise KeyError(
            f"flow.vtu 中没有字段 {array_name}；可用字段: {sorted(data.point_data)}"
        )
    values = np.asarray(data.point_data[array_name], dtype=float)
    if take_magnitude:
        if values.ndim == 1:
            values = np.abs(values)
        else:
            values = np.linalg.norm(values, axis=1)
    if values.ndim != 1:
        values = values[:, 0]
    return array_name, values


def triangulate(cells: list[tuple[int, IntArray]]) -> IntArray:
    """把三角形/四边形单元统一拆成三角形（节点索引保持 0 基）。"""
    triangles: list[IntArray] = []
    for vtk_type, connectivity in cells:
        if vtk_type == 5:
            triangles.append(connectivity[:3])
        elif vtk_type == 9:
            nodes = connectivity[:4]
            triangles.append(nodes[[0, 1, 2]])
            triangles.append(nodes[[0, 2, 3]])
        # 其他单元类型（如 3D 单元）直接忽略。
    if not triangles:
        raise ValueError("网格中没有可绘制的三角形或四边形单元。")
    return np.asarray(np.vstack(triangles), dtype=np.int64)


def refine_quads_for_display(
    x_coord: FloatArray,
    y_coord: FloatArray,
    values: FloatArray,
    cells: list[tuple[int, IntArray]],
    max_quads: int = 150_000,
) -> tuple[FloatArray, FloatArray, IntArray, FloatArray, bool]:
    """在每个四边形中心插入显示节点并构造四个三角形。

    SU2 的 C-H 网格本质上是四边形。直接固定沿 0→2 对角线拆分会在高曲率
    前缘形成成排的三角扇面。中心扇形拆分对四个角点对称，中心值取角点
    凸组合，因此不会制造新极值。超大网格本身已经足够细，为控制交互内存
    会跳过额外细分。
    """
    triangles: list[IntArray] = []
    quadrilaterals: list[IntArray] = []
    for vtk_type, connectivity in cells:
        nodes = np.asarray(connectivity, dtype=np.int64)
        if vtk_type == 5 and len(nodes) >= 3:
            triangles.append(nodes[:3])
        elif vtk_type == 9 and len(nodes) >= 4:
            quadrilaterals.append(nodes[:4])

    if not quadrilaterals or len(quadrilaterals) > max_quads:
        return (
            np.asarray(x_coord, dtype=float),
            np.asarray(y_coord, dtype=float),
            triangulate(cells),
            np.asarray(values, dtype=float),
            False,
        )

    quads = np.asarray(np.vstack(quadrilaterals), dtype=np.int64)
    base_count = len(x_coord)
    center_ids = np.arange(base_count, base_count + len(quads), dtype=np.int64)
    center_x = np.mean(np.asarray(x_coord, dtype=float)[quads], axis=1)
    center_y = np.mean(np.asarray(y_coord, dtype=float)[quads], axis=1)
    center_values = np.mean(np.asarray(values, dtype=float)[quads], axis=1)
    refined_triangles = np.vstack(
        (
            np.asarray(np.vstack(triangles), dtype=np.int64)
            if triangles
            else np.empty((0, 3), dtype=np.int64),
            np.column_stack((quads[:, 0], quads[:, 1], center_ids)),
            np.column_stack((quads[:, 1], quads[:, 2], center_ids)),
            np.column_stack((quads[:, 2], quads[:, 3], center_ids)),
            np.column_stack((quads[:, 3], quads[:, 0], center_ids)),
        )
    )
    return (
        np.concatenate((np.asarray(x_coord, dtype=float), center_x)),
        np.concatenate((np.asarray(y_coord, dtype=float), center_y)),
        np.asarray(refined_triangles, dtype=np.int64),
        np.concatenate((np.asarray(values, dtype=float), center_values)),
        True,
    )


def smooth_scalar_for_display(
    values: FloatArray,
    triangles: IntArray,
    iterations: int = 8,
    strength: float = 0.35,
) -> FloatArray:
    """对非结构网格节点标量做弱双边平滑，仅供绘图。

    权重同时考虑网格相邻关系和数值差异：小幅的节点间振荡会被平均，
    激波、停滞点等真实大梯度因权重很小而基本保留。每步都是相邻值的
    凸组合，因此不会制造超过原始范围的新极值。
    """
    original = np.asarray(values, dtype=float)
    connectivity = np.asarray(triangles, dtype=np.int64)
    if (
        iterations <= 0
        or strength <= 0.0
        or len(original) < 4
        or len(connectivity) == 0
    ):
        return original.copy()
    if connectivity.ndim != 2 or connectivity.shape[1] != 3:
        raise ValueError("显示平滑需要形状为 (N, 3) 的三角形连接表。")

    finite = original[np.isfinite(original)]
    span = float(np.percentile(finite, 99.0) - np.percentile(finite, 1.0))
    sample = connectivity[: min(len(connectivity), 100_000)]
    edge_changes = np.concatenate(
        tuple(
            np.abs(original[sample[:, first]] - original[sample[:, second]])
            for first, second in ((0, 1), (1, 2), (2, 0))
        )
    )
    edge_changes = edge_changes[np.isfinite(edge_changes)]
    typical_change = float(np.median(edge_changes)) if len(edge_changes) else 0.0
    range_scale = max(
        0.15 * max(span, 0.0),
        1.5 * typical_change,
        np.finfo(float).eps * max(float(np.max(np.abs(finite))), 1.0),
    )

    smoothed = original.copy()
    blend = float(np.clip(strength, 0.0, 0.8))
    for _ in range(iterations):
        weighted_sum = np.zeros(len(smoothed), dtype=float)
        weight_sum = np.zeros(len(smoothed), dtype=float)
        for first, second in ((0, 1), (1, 2), (2, 0)):
            left = connectivity[:, first]
            right = connectivity[:, second]
            difference = (smoothed[left] - smoothed[right]) / range_scale
            # 给强梯度边保留很小的权重下限，避免粗 C-H 网格在前缘形成
            # 完全互不交流的扇形色带；97% 的双边权重仍会保护激波与峰值。
            weight = 0.03 + 0.97 * np.exp(-0.5 * np.square(difference))
            weighted_sum += np.bincount(
                left, weights=weight * smoothed[right], minlength=len(smoothed)
            )
            weighted_sum += np.bincount(
                right, weights=weight * smoothed[left], minlength=len(smoothed)
            )
            weight_sum += np.bincount(left, weights=weight, minlength=len(smoothed))
            weight_sum += np.bincount(right, weights=weight, minlength=len(smoothed))
        active = weight_sum > np.finfo(float).eps
        neighbor_mean = smoothed.copy()
        neighbor_mean[active] = weighted_sum[active] / weight_sum[active]
        smoothed[active] = (
            (1.0 - blend) * smoothed[active] + blend * neighbor_mean[active]
        )
    return smoothed


def _gauge_pressure(data: VtuData) -> tuple[FloatArray, float]:
    """返回表压（p - p_inf）与远场静压 p_inf。

    p_inf 取离形心最远的 2% 节点（远场圆周）的平均压力；绝对压力云图的
    变化量远小于其绝对值，直接绘制几乎整场同色，改成表压后才能看出
    流场结构。
    """
    pressure = np.asarray(data.point_data["Pressure"], dtype=float)
    centroid = np.mean(data.points[:, :2], axis=0)
    radius = np.linalg.norm(data.points[:, :2] - centroid, axis=1)
    farfield = radius >= 0.98 * float(np.max(radius))
    p_inf = float(np.mean(pressure[farfield]))
    return pressure - p_inf, p_inf


def read_airfoil_boundary(case_dir: str | Path) -> FloatArray | None:
    """Use the actual meshed wall, including any bounded nose reconstruction."""
    case_dir = Path(case_dir)
    preview = case_dir / "mesh_preview.npz"
    if preview.is_file():
        with np.load(preview, allow_pickle=False) as archive:
            nodes, edges = archive["nodes"], archive["wall_edges"]
            return np.asarray(nodes[np.r_[edges[:, 0], edges[-1, 1]], :2], dtype=float)
    source = case_dir / "processed_airfoil.dat"
    if source.is_file():
        return np.loadtxt(source, skiprows=1)[:, :2]
    return None


def prepare_contour_data(
    vtu_path: str | Path,
    field_name: str,
    airfoil_points: FloatArray | None = None,
) -> dict[str, Any]:
    """解析 VTU 并整理出绘图所需的全部数据，供界面交互式绘图使用。

    返回字典：``x``、``y``、``triangles``、``values``、``label``、
    ``vmin``、``vmax``、``airfoil_points``（可能为 None）。
    压力场自动转为表压（扣除远场静压）。
    """
    data = read_vtu(vtu_path)
    array_name, values = _find_field(data, display_name=field_name)
    label = field_name
    if field_name == "Pressure":
        values, _ = _gauge_pressure(data)
        label = "p - p_inf [Pa]"
    cells = data.cells
    x_coord = data.points[:, 0]
    y_coord = data.points[:, 1]

    node_valid = np.isfinite(x_coord) & np.isfinite(y_coord) & np.isfinite(values)
    if not np.all(node_valid):
        renumber = np.full(len(x_coord), -1, dtype=np.int64)
        renumber[node_valid] = np.arange(int(np.count_nonzero(node_valid)))
        x_coord = x_coord[node_valid]
        y_coord = y_coord[node_valid]
        values = values[node_valid]
        cells = [
            (vtk_type, renumber[np.asarray(connectivity, dtype=np.int64)])
            for vtk_type, connectivity in cells
            if len(connectivity) > 0 and np.all(node_valid[connectivity])
        ]

    triangles = triangulate(cells)
    if len(x_coord) < 3 or len(triangles) == 0:
        raise ValueError("有效场数据不足以绘制云图。")
    # 极小的诊断/测试网格没有足够邻域，不做图形平滑，避免边界值占比过高。
    display_smoothed = field_name in _SMOOTHED_VOLUME_FIELDS and len(values) >= 20
    if display_smoothed:
        # 粗网格更容易显示出扇形分片，因此自动多做一次弱迭代；细网格减少
        # 处理次数，兼顾交互速度和真实梯度保留。
        # The final high-resolution raster performs the visible anti-aliasing;
        # one or two graph passes are enough to suppress isolated node noise.
        iterations = 2 if len(values) < 50_000 else 1
        values = smooth_scalar_for_display(values, triangles, iterations=iterations)
    x_coord, y_coord, triangles, values, display_refined = refine_quads_for_display(
        x_coord, y_coord, values, cells
    )
    finite_values = values[np.isfinite(values)]
    if len(finite_values) == 0:
        raise ValueError("云图字段全部为无效值。")
    # 色标范围取 0.5%～99.5% 分位，避免个别数值异常单元把整张图色域拉爆；
    # 超出范围的取值在图上饱和显示。
    vmin = float(np.percentile(finite_values, 0.5))
    vmax = float(np.percentile(finite_values, 99.5))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax - vmin < 1.0e-300:
        raise ValueError(
            f"{field_name} 在当前算例中全为常值，没有可显示的分布"
            "（例如层流算例的 Y_Plus、绝热壁面的 Heat_Flux 恒为 0）。"
        )
    return {
        "x": x_coord,
        "y": y_coord,
        "triangles": triangles,
        "values": values,
        "label": label,
        "vmin": vmin,
        "vmax": vmax,
        "airfoil_points": airfoil_points,
        "display_smoothed": display_smoothed,
        "display_refined": display_refined,
    }


def rasterize_contour_for_display(
    prepared: dict[str, Any],
    horizontal_pixels: int = 1100,
    smoothing_passes: int = 2,
) -> dict[str, Any]:
    """Interpolate the unstructured field to a display raster.

    This is a rendering-only transform: SU2 values and optimization data are not
    changed.  A normalized binomial filter removes visible triangle/fan seams
    without requiring SciPy and without bleeding values into the airfoil hole.
    """
    import matplotlib.tri as mtri

    x = np.asarray(prepared["x"], dtype=float)
    y = np.asarray(prepared["y"], dtype=float)
    airfoil = prepared.get("airfoil_points")
    if airfoil is not None and len(airfoil) >= 3:
        airfoil = np.asarray(airfoil, dtype=float)
        chord = max(float(np.ptp(airfoil[:, 0])), 1.0e-9)
        center_y = 0.5 * float(np.min(airfoil[:, 1]) + np.max(airfoil[:, 1]))
        xmin = float(np.min(airfoil[:, 0])) - 0.55 * chord
        xmax = float(np.max(airfoil[:, 0])) + 0.25 * chord
        ymin = center_y - 0.38 * chord
        ymax = center_y + 0.38 * chord
    else:
        xmin, xmax = np.percentile(x, (1.0, 99.0))
        ymin, ymax = np.percentile(y, (1.0, 99.0))
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("云图显示范围无效。")
    nx = max(320, int(horizontal_pixels))
    ny = int(np.clip(nx * (ymax - ymin) / (xmax - xmin), 300, 760))
    gx = np.linspace(xmin, xmax, nx)
    gy = np.linspace(ymin, ymax, ny)
    grid_x, grid_y = np.meshgrid(gx, gy)
    triangles = np.asarray(prepared["triangles"], dtype=int)
    # Build the expensive point-location map only for cells intersecting the
    # visible near-field window.  A typical C-grid has hundreds of thousands
    # of far-field cells which cannot contribute a single display pixel here.
    tx = x[triangles]
    ty = y[triangles]
    visible = (
        (np.min(tx, axis=1) <= xmax)
        & (np.max(tx, axis=1) >= xmin)
        & (np.min(ty, axis=1) <= ymax)
        & (np.max(ty, axis=1) >= ymin)
    )
    local_triangles = triangles[visible]
    if len(local_triangles) == 0:
        prepared["display_rasterized"] = False
        return prepared
    used = np.unique(local_triangles)
    renumber = np.full(len(x), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used), dtype=np.int64)
    local_triangles = renumber[local_triangles]
    triangulation = mtri.Triangulation(x[used], y[used], local_triangles)
    try:
        interpolator = mtri.LinearTriInterpolator(
            triangulation, np.asarray(prepared["values"], dtype=float)[used]
        )
    except RuntimeError:
        # Some diagnostic files contain overlapping cells.  Gouraud rendering
        # can still display those, while a point-location map is undefined.
        prepared["display_rasterized"] = False
        return prepared
    raster = np.ma.asarray(interpolator(grid_x, grid_y), dtype=float)
    mask = np.ma.getmaskarray(raster) | ~np.isfinite(raster.filled(np.nan))
    values = raster.filled(0.0)
    weights = (~mask).astype(float)

    kernel = np.asarray([1.0, 4.0, 6.0, 4.0, 1.0], dtype=float) / 16.0

    def blur_axis(array: np.ndarray, axis: int) -> np.ndarray:
        pad = [(0, 0)] * array.ndim
        pad[axis] = (2, 2)
        padded = np.pad(array, pad, mode="constant")
        result = np.zeros_like(array)
        for offset, coefficient in enumerate(kernel):
            slices = [slice(None)] * array.ndim
            slices[axis] = slice(offset, offset + array.shape[axis])
            result += coefficient * padded[tuple(slices)]
        return result

    for _ in range(max(0, int(smoothing_passes))):
        numerator = blur_axis(blur_axis(values * weights, 1), 0)
        denominator = blur_axis(blur_axis(weights, 1), 0)
        active = denominator > 1.0e-10
        values[active] = numerator[active] / denominator[active]
        weights = np.where(mask, 0.0, 1.0)

    prepared["raster_values"] = np.ma.array(values, mask=mask)
    prepared["raster_extent"] = (xmin, xmax, ymin, ymax)
    prepared["display_rasterized"] = True
    return prepared


def render_contour(
    vtu_path: str | Path,
    field_name: str,
    output_path: str | Path,
    cmap: str = "jet",
    levels: int = 64,
    dpi: int = 150,
    airfoil_points: FloatArray | None = None,
    title: str | None = None,
    figsize: tuple[float, float] = (9.6, 8.2),
) -> Path:
    """读取体场数据并渲染指定标量场云图，返回 PNG 路径。

    ``airfoil_points`` 为 (N, 2) 的翼型轮廓点，用于叠加壁面轮廓线。
    渲染使用 Gouraud ``tripcolor``（见模块说明）。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    prepared = rasterize_contour_for_display(
        prepare_contour_data(vtu_path, field_name, airfoil_points)
    )

    figure, axis = plt.subplots(figsize=figsize)
    if prepared.get("display_rasterized"):
        filled = axis.imshow(
            prepared["raster_values"],
            origin="lower",
            extent=prepared["raster_extent"],
            interpolation="bicubic",
            cmap=cmap,
            vmin=prepared["vmin"],
            vmax=prepared["vmax"],
        )
    else:
        filled = axis.tripcolor(
            prepared["x"], prepared["y"], prepared["triangles"], prepared["values"],
            shading="gouraud", edgecolors="none", linewidth=0.0,
            cmap=cmap, vmin=prepared["vmin"], vmax=prepared["vmax"],
        )
    if prepared["airfoil_points"] is not None and len(prepared["airfoil_points"]) >= 3:
        axis.fill(
            prepared["airfoil_points"][:, 0],
            prepared["airfoil_points"][:, 1],
            color="white",
            zorder=4,
        )
        axis.plot(
            prepared["airfoil_points"][:, 0],
            prepared["airfoil_points"][:, 1],
            color="black",
            linewidth=1.1,
            zorder=5,
        )
    axis.set_aspect("equal", adjustable="box")
    if prepared.get("display_rasterized"):
        xmin, xmax, ymin, ymax = prepared["raster_extent"]
        axis.set_xlim(xmin, xmax)
        axis.set_ylim(ymin, ymax)
    axis.set_xlabel("x")
    axis.set_ylabel("y")
    smoothing_note = (
        " - high-quality anti-aliased display"
        if prepared.get("display_rasterized")
        else " - lightly smoothed for display" if prepared["display_smoothed"] else ""
    )
    axis.set_title(
        title or f"{field_name} ({prepared['label']}){smoothing_note}",
        fontweight="bold",
    )
    colorbar = figure.colorbar(filled, ax=axis, shrink=0.82, pad=0.02)
    colorbar.set_label(prepared["label"])
    figure.tight_layout()

    png_path = Path(output_path).expanduser().resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png_path, dpi=dpi, bbox_inches="tight")
    plt.close(figure)
    return png_path


def list_available_fields(vtu_path: str | Path) -> list[str]:
    """返回该 flow.vtu 中可以绘制的字段显示名。"""
    data = read_vtu(vtu_path)
    return [
        name
        for name, (array, _) in CONTOUR_FIELDS.items()
        if array in data.point_data
    ]
