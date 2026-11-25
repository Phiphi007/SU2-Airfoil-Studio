from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class WorkflowStepper(QWidget):
    """Compact clickable vertical workflow indicator for the five main pages."""

    stepClicked = Signal(int)

    def __init__(self, labels: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels = list(labels)
        self._current = 0
        self._completed: set[int] = set()
        self._hovered = -1
        self._margin_top = 28.0
        self._spacing = 58.0
        self._node_x = 24.0
        self._radius = 10.0
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(176)
        self.setMinimumHeight(int(self._margin_top * 2 + self._spacing * max(1, len(labels) - 1)))
        self.setAccessibleName("Workflow steps")

    @property
    def current_step(self) -> int:
        return self._current

    @property
    def completed_steps(self) -> set[int]:
        return set(self._completed)

    def setLabels(self, labels: list[str]) -> None:  # noqa: N802
        if len(labels) != len(self._labels):
            raise ValueError("Workflow label count cannot change.")
        self._labels = list(labels)
        self.update()

    def setCurrentStep(self, index: int) -> None:  # noqa: N802
        index = max(0, min(len(self._labels) - 1, int(index)))
        if index != self._current:
            self._current = index
            self.update()

    def setCompletedSteps(self, steps: set[int]) -> None:  # noqa: N802
        normalized = {int(step) for step in steps if 0 <= int(step) < len(self._labels)}
        if normalized != self._completed:
            self._completed = normalized
            self.update()

    def _center(self, index: int) -> QPointF:
        return QPointF(self._node_x, self._margin_top + index * self._spacing)

    def _row_at(self, y: float) -> int:
        for index in range(len(self._labels)):
            if abs(y - self._center(index).y()) <= self._spacing * 0.43:
                return index
        return -1

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        hovered = self._row_at(event.position().y())
        if hovered != self._hovered:
            self._hovered = hovered
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if hovered >= 0 else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._row_at(event.position().y())
            if index >= 0:
                self.setCurrentStep(index)
                self.stepClicked.emit(index)
                self.setFocus()
                return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            self.setCurrentStep(self._current - 1)
            self.stepClicked.emit(self._current)
            return
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            self.setCurrentStep(self._current + 1)
            self.stepClicked.emit(self._current)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.stepClicked.emit(self._current)
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = self.palette()
        accent = palette.highlight().color()
        text = palette.windowText().color()
        muted = palette.placeholderText().color()
        surface = palette.base().color()
        hover = QColor(accent)
        hover.setAlpha(34)

        # Row hover is deliberately restrained so the diagram still reads as
        # an engineering workflow instead of a large web-style menu.
        if self._hovered >= 0:
            center = self._center(self._hovered)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover)
            painter.drawRect(QRectF(2, center.y() - 22, self.width() - 4, 44))

        for index in range(len(self._labels) - 1):
            start = self._center(index)
            stop = self._center(index + 1)
            completed_segment = index in self._completed
            painter.setPen(QPen(accent if completed_segment else muted, 3.0 if completed_segment else 1.5))
            painter.drawLine(start, stop)

        label_font = QFont(self.font())
        label_font.setPointSize(10)
        number_font = QFont(self.font())
        number_font.setPointSize(8)
        number_font.setBold(True)

        for index, label in enumerate(self._labels):
            center = self._center(index)
            complete = index in self._completed
            current = index == self._current
            painter.setPen(QPen(accent if complete or current else muted, 2.5 if current else 1.5))
            painter.setBrush(accent if complete else surface)
            painter.drawEllipse(center, self._radius, self._radius)

            painter.setFont(number_font)
            if complete:
                painter.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
                path = QPainterPath()
                path.moveTo(center.x() - 4.5, center.y())
                path.lineTo(center.x() - 1.0, center.y() + 3.5)
                path.lineTo(center.x() + 5.0, center.y() - 4.0)
                painter.drawPath(path)
            elif current:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(accent)
                painter.drawEllipse(center, 3.0, 3.0)
            else:
                painter.setPen(muted)
                painter.drawText(
                    QRectF(center.x() - 8, center.y() - 8, 16, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    str(index + 1),
                )

            painter.setFont(label_font)
            painter.setPen(text if complete or current else muted)
            if current:
                label_font.setBold(True)
                painter.setFont(label_font)
            painter.drawText(
                QRectF(45, center.y() - 17, max(20, self.width() - 49), 34),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label,
            )
            label_font.setBold(False)

