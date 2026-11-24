from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
from matplotlib import colormaps
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core_modules.field_visualizer import read_airfoil_boundary
from core_modules.su2_mesh_import import read_mesh

try:
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    from vtkmodules.vtkCommonCore import vtkLookupTable, vtkPoints
    from vtkmodules.vtkCommonDataModel import (
        vtkCellArray,
        vtkPolyData,
        vtkPolyLine,
        vtkQuad,
        vtkTriangle,
        vtkUnstructuredGrid,
    )
    from vtkmodules.vtkIOImage import vtkPNGWriter
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader
    from vtkmodules.vtkInteractionStyle import (
        vtkInteractorStyleImage,
        vtkInteractorStyleTrackballCamera,
    )
    from vtkmodules.vtkRenderingCore import (
        vtkActor,
        vtkBillboardTextActor3D,
        vtkDataSetMapper,
        vtkRenderer,
        vtkTextActor,
        vtkWindowToImageFilter,
    )
    from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
    import vtkmodules.vtkInteractionStyle  # noqa: F401
    import vtkmodules.vtkRenderingOpenGL2  # noqa: F401

    VTK_AVAILABLE = True
except ImportError:
    VTK_AVAILABLE = False

VTK_ENABLED = VTK_AVAILABLE and os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen"

DISPLAY_COLORS = {
    "white": "#F5F5F5",
    "black": "#101010",
    "orange": "#F59E42",
    "blue": "#39A9F4",
    "green": "#4DD17A",
    "red": "#EF5B5B",
    "cyan": "#32D5D2",
}

LIGHT_VIEW_THEMES = {"light", "sand"}


def _display_color(value: str, default: str = "white") -> tuple[float, float, float]:
    text = DISPLAY_COLORS.get(str(value).lower(), str(value))
    if not text.startswith("#") or len(text) != 7:
        text = DISPLAY_COLORS[default]
    try:
        return tuple(int(text[index:index + 2], 16) / 255.0 for index in (1, 3, 5))
    except ValueError:
        return _display_color(default, "white")


def _lookup_table(name: str = "jet") -> "vtkLookupTable":
    """Build a VTK lookup table from the same perceptual maps used in reports."""
    aliases = {
        "grayscale": "gray",
        "grey": "gray",
        "coolwarm": "coolwarm",
    }
    cmap = colormaps.get_cmap(aliases.get(name.lower(), name.lower()))
    table = vtkLookupTable()
    table.SetNumberOfTableValues(256)
    for index in range(256):
        red, green, blue, alpha = cmap(index / 255.0)
        table.SetTableValue(index, red, green, blue, alpha)
    table.SetNanColor(0.45, 0.45, 0.45, 1.0)
    table.Build()
    return table


def _case_metadata(case_dir: str | Path) -> dict[str, object]:
    """Read optional display metadata from a generated case directory."""
    directory = Path(case_dir)
    data: dict[str, object] = {}
    settings = directory / "case_settings.json"
    if settings.is_file():
        try:
            loaded = json.loads(settings.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
    # Imported and solver-generated cases do not always contain
    # ``case_settings.json``.  SU2's run.cfg is authoritative for the flow
    # conditions, so use it as a fallback instead of silently displaying a
    # misleading zero-degree AoA overlay.
    config = directory / "run.cfg"
    if config.is_file():
        try:
            for raw_line in config.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                line = raw_line.split("%", 1)[0].strip()
                if "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                numeric = value.split(",", 1)[0].strip()
                if key == "MACH_NUMBER" and data.get("mach") is None:
                    data["mach"] = float(numeric)
                elif key == "AOA" and data.get("aoa") is None:
                    data["aoa"] = float(numeric)
                elif key == "REYNOLDS_NUMBER" and data.get("reynolds") is None:
                    data["reynolds"] = float(numeric)
        except (OSError, UnicodeError, ValueError):
            pass
    airfoil_path = str(data.get("airfoil_path", ""))
    inferred_name = (
        Path(airfoil_path).stem
        if airfoil_path and not airfoil_path.startswith("builtin://")
        else airfoil_path.removeprefix("builtin://")
    )
    return {
        "airfoil": str(data.get("case_name") or inferred_name or directory.name),
        "mach": data.get("mach"),
        "aoa": data.get("aoa"),
        "reynolds": data.get("reynolds"),
    }


class VTKView(QWidget):
    """Native Qt/VTK viewport for SU2 meshes and flow fields."""

    status = Signal(str)
    fieldsChanged = Signal(list)
    rangeChanged = Signal(float, float)

    def __init__(
        self, parent: QWidget | None = None, *, allow_rotation: bool = True
    ) -> None:
        super().__init__(parent)
        self.allow_rotation = bool(allow_rotation)
        self.source_path: Path | None = None
        self.dataset = None
        self.mapper = None
        self.actor = None
        self.scalar_bar = None
        self.current_field = ""
        self.airfoil_points: np.ndarray | None = None
        self.case_metadata: dict[str, object] = {}
        self.annotation_items = {
            "airfoil": True,
            "mach": True,
            "aoa": True,
            "reynolds": False,
            "field": True,
        }
        self.annotation_position = "top_right"
        self.annotation_text_color = "white"
        self.axis_color = "orange"
        self.mesh_edges_visible = False
        self.mesh_edge_color = "black"
        self.airfoil_outline_visible = True
        self.airfoil_outline_color = "white"
        self.airfoil_actor = None
        self.colormap_name = "jet"
        self.current_theme = "dark"
        self.show_axis = True
        self.axis_actor = None
        self.angle_actor = None
        self.info_actor = None
        self.auto_range = True
        self.custom_range: tuple[float, float] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        tools = QHBoxLayout()
        tools.setContentsMargins(2, 2, 2, 0)
        self.fit_button = QPushButton("Fit full domain")
        self.fit_button.clicked.connect(self.reset_camera)
        self.xy_button = QPushButton("Fit airfoil")
        self.xy_button.clicked.connect(self.fit_airfoil)
        tools.addWidget(self.fit_button)
        tools.addWidget(self.xy_button)
        hint = QLabel(
            "Wheel: zoom  ·  Middle drag: pan  ·  Left drag: rotate"
            if self.allow_rotation
            else "Wheel: zoom  ·  Middle drag: pan"
        )
        hint.setProperty("muted", True)
        tools.addWidget(hint)
        tools.addStretch(1)
        layout.addLayout(tools)
        if not VTK_ENABLED:
            message = QLabel(
                "Native VTK rendering is unavailable in this session. "
                "Install VTK or run without QT_QPA_PLATFORM=offscreen."
            )
            message.setWordWrap(True)
            layout.addWidget(message, 1)
            self.vtk_widget = None
            self.renderer = None
            return
        self.vtk_widget = QVTKRenderWindowInteractor(self)
        self.renderer = vtkRenderer()
        self.renderer.SetBackground(0.075, 0.075, 0.08)
        self.renderer.SetBackground2(0.12, 0.12, 0.125)
        self.renderer.GradientBackgroundOn()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.vtk_widget.GetRenderWindow().SetMultiSamples(8)
        self.interactor_style = (
            vtkInteractorStyleTrackballCamera()
            if self.allow_rotation
            else vtkInteractorStyleImage()
        )
        self.vtk_widget.GetRenderWindow().GetInteractor().SetInteractorStyle(self.interactor_style)
        layout.addWidget(self.vtk_widget, 1)
        self.vtk_widget.Initialize()
        self.vtk_widget.Start()

    def _render(self) -> None:
        if VTK_ENABLED and self.vtk_widget is not None and self.isVisible():
            self.vtk_widget.GetRenderWindow().Render()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._render()

    def clear(self) -> None:
        if not VTK_ENABLED or self.renderer is None:
            return
        self.renderer.RemoveAllViewProps()
        self.dataset = self.mapper = self.actor = self.scalar_bar = None
        self.airfoil_actor = None
        self.current_field = ""
        self.airfoil_points = None
        self.case_metadata = {}
        self.source_path = None
        self._render()

    def _install_dataset(self, dataset, *, wireframe: bool) -> None:
        self.renderer.RemoveAllViewProps()
        mapper = vtkDataSetMapper()
        mapper.SetInputData(dataset)
        mapper.SetLookupTable(_lookup_table(self.colormap_name))
        mapper.ScalarVisibilityOff()
        actor = vtkActor()
        actor.SetMapper(mapper)
        if wireframe:
            actor.GetProperty().SetRepresentationToWireframe()
            actor.GetProperty().SetColor(0.15, 0.86, 0.62)
            actor.GetProperty().SetLineWidth(1.0)
            actor.GetProperty().LightingOff()
        else:
            actor.GetProperty().SetRepresentationToSurface()
            actor.GetProperty().LightingOff()
            actor.GetProperty().SetEdgeVisibility(self.mesh_edges_visible)
            actor.GetProperty().SetEdgeColor(
                *_display_color(self.mesh_edge_color, "black")
            )
        self.renderer.AddActor(actor)
        self.dataset, self.mapper, self.actor = dataset, mapper, actor
        self.scalar_bar = None
        self.airfoil_actor = None
        self.axis_actor = self.angle_actor = self.info_actor = None
        self.reset_camera()

    def load_su2(self, path: str | Path) -> None:
        if not VTK_ENABLED:
            raise RuntimeError("VTK is not installed.")
        path = Path(path).expanduser().resolve()
        imported = read_mesh(path)
        points = vtkPoints()
        xyz = np.column_stack((imported.nodes, np.zeros(len(imported.nodes))))
        points.SetData(numpy_to_vtk(xyz, deep=True))
        grid = vtkUnstructuredGrid()
        grid.SetPoints(points)
        for kind, connectivity in imported.cells:
            cell = vtkTriangle() if kind == 5 else vtkQuad()
            for local, node in enumerate(connectivity):
                cell.GetPointIds().SetId(local, int(node))
            grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
        self.source_path = path
        self.case_metadata = _case_metadata(path.parent)
        wall_name = next(
            (name for name in imported.markers if name.lower() in {"airfoil", "wall"}),
            next((name for name in imported.markers if "airfoil" in name.lower()), None),
        )
        if wall_name:
            try:
                self.airfoil_points = imported.wall(wall_name)[0]
            except ValueError:
                self.airfoil_points = None
        self._install_dataset(grid, wireframe=True)
        self._refresh_annotations()
        self.fieldsChanged.emit([])
        self.status.emit(
            f"VTK mesh: {len(imported.nodes):,} nodes, {len(imported.cells):,} cells, "
            f"{len(imported.markers)} markers"
        )

    def load_vtu(self, path: str | Path, *, preserve_view: bool = False) -> list[str]:
        if not VTK_ENABLED:
            raise RuntimeError("VTK is not installed.")
        path = Path(path).expanduser().resolve()
        previous_field = self.current_field
        previous_auto = self.auto_range
        previous_range = self.custom_range
        camera_state = None
        if preserve_view and self.renderer is not None and self.dataset is not None:
            camera = self.renderer.GetActiveCamera()
            camera_state = (
                camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp(),
                camera.GetParallelScale(),
            )
        reader = vtkXMLUnstructuredGridReader()
        reader.SetFileName(str(path))
        reader.Update()
        grid = reader.GetOutput()
        if grid is None or grid.GetNumberOfPoints() == 0:
            raise ValueError(f"VTU contains no points: {path}")
        # Detach the data from the reader so the viewport owns a stable snapshot.
        detached = vtkUnstructuredGrid()
        detached.DeepCopy(grid)
        self.source_path = path
        self.case_metadata = _case_metadata(path.parent)
        self.airfoil_points = read_airfoil_boundary(path.parent)
        self._install_dataset(detached, wireframe=False)
        self._add_airfoil_outline()
        data = detached.GetPointData()
        fields = [
            data.GetArrayName(index)
            for index in range(data.GetNumberOfArrays())
            if data.GetArrayName(index)
        ]
        preferred = previous_field if preserve_view and previous_field in fields else None
        preferred = preferred or next((name for name in fields if name.lower() in {"mach", "mach_number"}), None)
        if preferred is None and fields:
            preferred = fields[0]
        if preferred:
            limits = previous_range if preserve_view and not previous_auto else None
            self.set_field(preferred, auto=previous_auto if preserve_view else True, limits=limits)
        self.fieldsChanged.emit(fields)
        self._refresh_annotations()
        if camera_state is None:
            self.reset_camera()
        else:
            camera = self.renderer.GetActiveCamera()
            camera.SetPosition(*camera_state[0])
            camera.SetFocalPoint(*camera_state[1])
            camera.SetViewUp(*camera_state[2])
            camera.SetParallelScale(camera_state[3])
            self._render()
        self.status.emit(
            f"VTK field: {detached.GetNumberOfPoints():,} points, "
            f"{detached.GetNumberOfCells():,} cells, {len(fields)} arrays"
        )
        return fields

    def _add_airfoil_outline(self) -> None:
        if self.airfoil_points is None or len(self.airfoil_points) < 3:
            return
        coordinates = np.asarray(self.airfoil_points, dtype=float)
        points = vtkPoints()
        points.SetData(
            numpy_to_vtk(
                np.column_stack((coordinates[:, :2], np.full(len(coordinates), 1.0e-8))),
                deep=True,
            )
        )
        line = vtkPolyLine()
        line.GetPointIds().SetNumberOfIds(len(coordinates) + 1)
        for index in range(len(coordinates)):
            line.GetPointIds().SetId(index, index)
        line.GetPointIds().SetId(len(coordinates), 0)
        cells = vtkCellArray()
        cells.InsertNextCell(line)
        poly = vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(cells)
        mapper = vtkDataSetMapper()
        mapper.SetInputData(poly)
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(
            *_display_color(self.airfoil_outline_color, "white")
        )
        actor.GetProperty().SetLineWidth(2.0)
        actor.GetProperty().LightingOff()
        actor.SetVisibility(self.airfoil_outline_visible)
        self.renderer.AddActor(actor)
        self.airfoil_actor = actor

    def _remove_annotation_actors(self) -> None:
        for actor in (self.axis_actor, self.angle_actor, self.info_actor):
            if actor is not None:
                self.renderer.RemoveViewProp(actor)
        self.axis_actor = self.angle_actor = self.info_actor = None

    def _polyline_actor(self, coordinates: np.ndarray, color, width: float):
        """Create one actor from NaN-separated two-dimensional polylines."""
        finite = np.all(np.isfinite(coordinates), axis=1)
        points = vtkPoints()
        cells = vtkCellArray()
        cursor = 0
        start = 0
        while start < len(coordinates):
            while start < len(coordinates) and not finite[start]:
                start += 1
            stop = start
            while stop < len(coordinates) and finite[stop]:
                stop += 1
            if stop - start >= 2:
                line = vtkPolyLine()
                line.GetPointIds().SetNumberOfIds(stop - start)
                for local, point in enumerate(coordinates[start:stop]):
                    points.InsertNextPoint(float(point[0]), float(point[1]), 1.0e-8)
                    line.GetPointIds().SetId(local, cursor)
                    cursor += 1
                cells.InsertNextCell(line)
            start = stop + 1
        poly = vtkPolyData()
        poly.SetPoints(points)
        poly.SetLines(cells)
        mapper = vtkDataSetMapper()
        mapper.SetInputData(poly)
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetLineWidth(width)
        actor.GetProperty().LightingOff()
        return actor

    def _refresh_annotations(self) -> None:
        if not VTK_ENABLED or self.renderer is None:
            return
        self._remove_annotation_actors()
        if self.show_axis and self.airfoil_points is not None and len(self.airfoil_points) >= 3:
            coordinates = np.asarray(self.airfoil_points, dtype=float)[:, :2]
            leading = coordinates[int(np.argmin(coordinates[:, 0]))]
            trailing = coordinates[int(np.argmax(coordinates[:, 0]))]
            chord_vector = trailing - leading
            chord = float(np.linalg.norm(chord_vector))
            if chord > 1.0e-12:
                direction = chord_vector / chord
                normal = np.array([-direction[1], direction[0]])
                pivot = leading - 0.12 * chord * direction
                aoa = float(self.case_metadata.get("aoa") or 0.0)
                base_angle = math.atan2(direction[1], direction[0])
                flow_angle = base_angle + math.radians(aoa)
                flow_direction = np.array([math.cos(flow_angle), math.sin(flow_angle)])
                radius = 0.14 * chord
                angles = np.linspace(base_angle, flow_angle, max(8, int(abs(aoa)) + 8))
                separated = np.full((1, 2), np.nan)
                chord_line = np.vstack(
                    (
                        pivot,
                        trailing + 0.08 * chord * direction,
                        separated,
                        pivot,
                        pivot + 0.42 * chord * flow_direction,
                        separated,
                        pivot + radius * np.column_stack((np.cos(angles), np.sin(angles))),
                    )
                )
                axis_color = _display_color(self.axis_color, "orange")
                self.axis_actor = self._polyline_actor(chord_line, axis_color, 2.0)
                self.renderer.AddActor(self.axis_actor)
                mid_angle = base_angle + 0.5 * math.radians(aoa)
                label_position = (
                    pivot
                    + 1.25 * radius * np.array([math.cos(mid_angle), math.sin(mid_angle)])
                    + 0.025 * chord * normal
                )
                self.angle_actor = vtkBillboardTextActor3D()
                self.angle_actor.SetInput(f"AoA = {aoa:.2f}°")
                self.angle_actor.SetPosition(
                    float(label_position[0]), float(label_position[1]), 2.0e-8
                )
                text = self.angle_actor.GetTextProperty()
                text.SetColor(*axis_color)
                text.SetFontSize(16)
                text.BoldOn()
                self.renderer.AddActor(self.angle_actor)

        lines: list[str] = []
        labels = (
            ("airfoil", "Airfoil", self.case_metadata.get("airfoil")),
            ("mach", "Mach", self.case_metadata.get("mach")),
            ("aoa", "AoA", self.case_metadata.get("aoa")),
            ("reynolds", "Re", self.case_metadata.get("reynolds")),
            ("field", "Field", self.current_field or None),
        )
        for key, label, value in labels:
            if not self.annotation_items.get(key, False) or value in (None, ""):
                continue
            if key == "aoa":
                rendered = f"{float(value):.2f} deg"
            elif key in {"mach", "reynolds"}:
                rendered = f"{float(value):.4g}"
            else:
                rendered = str(value)
            lines.append(f"{label}: {rendered}")
        if lines:
            self.info_actor = vtkTextActor()
            self.info_actor.SetInput("\n".join(lines))
            self.info_actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
            prop = self.info_actor.GetTextProperty()
            positions = {
                "top_center": (0.50, 0.965, "center"),
                "top_left": (0.025, 0.965, "left"),
                "top_right": (0.875, 0.965, "right"),
            }
            x_value, y_value, justification = positions.get(
                self.annotation_position, positions["top_right"]
            )
            self.info_actor.SetPosition(x_value, y_value)
            if justification == "left":
                prop.SetJustificationToLeft()
            elif justification == "center":
                prop.SetJustificationToCentered()
            else:
                prop.SetJustificationToRight()
            prop.SetVerticalJustificationToTop()
            text_color = self.annotation_text_color
            if text_color == "auto":
                text_color = "black" if self.current_theme in LIGHT_VIEW_THEMES else "white"
            prop.SetColor(*_display_color(text_color, "white"))
            prop.SetFontSize(15)
            prop.SetFontFamilyToArial()
            prop.BoldOn()
            self.renderer.AddViewProp(self.info_actor)
        self._render()

    def set_annotations(
        self,
        *,
        show_axis: bool | None = None,
        position: str | None = None,
        text_color: str | None = None,
        axis_color: str | None = None,
        **items: bool,
    ) -> None:
        if show_axis is not None:
            self.show_axis = bool(show_axis)
        if position in {"top_center", "top_left", "top_right"}:
            self.annotation_position = position
        if text_color == "auto" or text_color in DISPLAY_COLORS or (
            isinstance(text_color, str) and text_color.startswith("#")
        ):
            self.annotation_text_color = text_color
        if axis_color in DISPLAY_COLORS or (isinstance(axis_color, str) and axis_color.startswith("#")):
            self.axis_color = axis_color
        for key, value in items.items():
            if key in self.annotation_items:
                self.annotation_items[key] = bool(value)
        self._refresh_annotations()

    def set_background(self, theme: str) -> None:
        if not VTK_ENABLED or self.renderer is None:
            return
        backgrounds = {
            "dark": ((0.075, 0.075, 0.08), (0.12, 0.12, 0.125)),
            "light": ((0.86, 0.87, 0.88), (0.98, 0.98, 0.99)),
            "deep_blue": ((0.035, 0.075, 0.105), (0.075, 0.15, 0.20)),
            "graphite": ((0.09, 0.095, 0.10), (0.17, 0.18, 0.19)),
            "rose": ((0.105, 0.06, 0.09), (0.20, 0.12, 0.17)),
            "forest": ((0.045, 0.085, 0.07), (0.10, 0.17, 0.14)),
            "violet": ((0.065, 0.05, 0.10), (0.14, 0.11, 0.20)),
            "sand": ((0.82, 0.79, 0.72), (0.96, 0.94, 0.89)),
        }
        self.current_theme = theme if theme in backgrounds else "dark"
        first, second = backgrounds[self.current_theme]
        self.renderer.SetBackground(*first)
        self.renderer.SetBackground2(*second)
        if self.scalar_bar is not None:
            color = (
                (0.08, 0.08, 0.08)
                if self.current_theme in LIGHT_VIEW_THEMES
                else (0.9, 0.9, 0.9)
            )
            self.scalar_bar.GetTitleTextProperty().SetColor(*color)
            self.scalar_bar.GetLabelTextProperty().SetColor(*color)
        self._refresh_annotations()

    def set_colormap(self, name: str) -> None:
        normalized = str(name).lower()
        if normalized not in {"jet", "turbo", "viridis", "plasma", "coolwarm", "grayscale"}:
            raise ValueError(f"Unsupported colormap: {name}")
        self.colormap_name = normalized
        if self.mapper is not None:
            table = _lookup_table(normalized)
            self.mapper.SetLookupTable(table)
            if self.scalar_bar is not None:
                self.scalar_bar.SetLookupTable(table)
            self._render()

    def set_mesh_edges(self, visible: bool, color: str | None = None) -> None:
        """Overlay result-cell edges without rebuilding or copying the dataset."""
        self.mesh_edges_visible = bool(visible)
        if color in DISPLAY_COLORS or (
            isinstance(color, str) and color.startswith("#")
        ):
            self.mesh_edge_color = color
        if self.actor is not None:
            prop = self.actor.GetProperty()
            prop.SetEdgeVisibility(self.mesh_edges_visible)
            prop.SetEdgeColor(*_display_color(self.mesh_edge_color, "black"))
            self._render()

    def set_airfoil_outline(self, visible: bool, color: str | None = None) -> None:
        self.airfoil_outline_visible = bool(visible)
        if color in DISPLAY_COLORS or (
            isinstance(color, str) and color.startswith("#")
        ):
            self.airfoil_outline_color = color
        if self.airfoil_actor is not None:
            self.airfoil_actor.SetVisibility(self.airfoil_outline_visible)
            self.airfoil_actor.GetProperty().SetColor(
                *_display_color(self.airfoil_outline_color, "white")
            )
            self._render()

    def _field_values(self, name: str) -> np.ndarray:
        array = self.dataset.GetPointData().GetArray(name) if self.dataset is not None else None
        if array is None:
            raise KeyError(f"Point field not found: {name}")
        values = np.asarray(vtk_to_numpy(array), dtype=float)
        if values.ndim > 1:
            values = np.linalg.norm(values, axis=1)
        return values

    def set_field(
        self,
        name: str,
        *,
        auto: bool = True,
        limits: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        if self.dataset is None or self.mapper is None:
            raise RuntimeError("Load a VTU result before selecting a field.")
        values = self._field_values(name)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            raise ValueError(f"Field contains no finite values: {name}")
        if auto or limits is None:
            lower, upper = np.percentile(finite, (0.5, 99.5))
            if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
                lower, upper = float(np.min(finite)), float(np.max(finite))
            if upper <= lower:
                upper = lower + max(abs(lower), 1.0) * 1.0e-9
        else:
            lower, upper = map(float, limits)
            if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
                raise ValueError("Color maximum must be greater than color minimum.")
        array = self.dataset.GetPointData().GetArray(name)
        if array.GetNumberOfComponents() > 1:
            magnitude = numpy_to_vtk(values, deep=True)
            magnitude.SetName(f"{name} |magnitude|")
            self.dataset.GetPointData().AddArray(magnitude)
            selected = magnitude.GetName()
        else:
            selected = name
        self.dataset.GetPointData().SetActiveScalars(selected)
        self.mapper.SetScalarModeToUsePointFieldData()
        self.mapper.SelectColorArray(selected)
        self.mapper.SetScalarRange(float(lower), float(upper))
        self.mapper.InterpolateScalarsBeforeMappingOn()
        self.mapper.ScalarVisibilityOn()
        if self.scalar_bar is not None:
            self.renderer.RemoveViewProp(self.scalar_bar)
        self.scalar_bar = vtkScalarBarActor()
        self.scalar_bar.SetLookupTable(self.mapper.GetLookupTable())
        self.scalar_bar.SetTitle(name)
        self.scalar_bar.SetNumberOfLabels(5)
        self.scalar_bar.SetPosition(0.91, 0.10)
        self.scalar_bar.SetWidth(0.075)
        self.scalar_bar.SetHeight(0.80)
        self.scalar_bar.SetMaximumWidthInPixels(90)
        self.scalar_bar.SetTextPositionToPrecedeScalarBar()
        scalar_text = (0.08, 0.08, 0.08) if self.current_theme == "light" else (0.9, 0.9, 0.9)
        for prop in (self.scalar_bar.GetTitleTextProperty(), self.scalar_bar.GetLabelTextProperty()):
            prop.SetColor(*scalar_text)
            prop.SetFontFamilyToArial()
        self.renderer.AddViewProp(self.scalar_bar)
        self.current_field = name
        self.auto_range = auto
        self.custom_range = None if auto else (float(lower), float(upper))
        self.rangeChanged.emit(float(lower), float(upper))
        self._refresh_annotations()
        self._render()
        return float(lower), float(upper)

    def reset_camera(self) -> None:
        if not VTK_ENABLED or self.renderer is None or self.dataset is None:
            return
        self.renderer.ResetCamera()
        camera = self.renderer.GetActiveCamera()
        camera.SetPosition(0.0, 0.0, 1.0)
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetViewUp(0.0, 1.0, 0.0)
        camera.ParallelProjectionOn()
        self.renderer.ResetCameraClippingRange()
        self._render()

    def fit_airfoil(self) -> None:
        if not VTK_ENABLED or self.renderer is None or self.airfoil_points is None:
            return
        points = np.asarray(self.airfoil_points, dtype=float)
        chord = max(float(np.ptp(points[:, 0])), 1.0e-9)
        # Shift the geometry left to reserve a dedicated legend strip on the right.
        center_x = 0.5 * float(np.min(points[:, 0]) + np.max(points[:, 0])) + 0.10 * chord
        center_y = 0.5 * float(np.min(points[:, 1]) + np.max(points[:, 1]))
        camera = self.renderer.GetActiveCamera()
        camera.SetPosition(center_x, center_y, 1.0)
        camera.SetFocalPoint(center_x, center_y, 0.0)
        camera.SetViewUp(0.0, 1.0, 0.0)
        camera.ParallelProjectionOn()
        camera.SetParallelScale(0.42 * chord)
        self.renderer.ResetCameraClippingRange()
        self._render()

    def save_screenshot(self, path: str | Path, scale: int = 1) -> Path:
        if not VTK_ENABLED or self.vtk_widget is None:
            raise RuntimeError("Native VTK rendering is unavailable.")
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        self.vtk_widget.GetRenderWindow().Render()
        capture = vtkWindowToImageFilter()
        capture.SetInput(self.vtk_widget.GetRenderWindow())
        capture.SetScale(max(1, int(scale)))
        capture.ReadFrontBufferOff()
        capture.Update()
        writer = vtkPNGWriter()
        writer.SetFileName(str(target))
        writer.SetInputConnection(capture.GetOutputPort())
        writer.Write()
        return target

