from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from core_modules.runtime_paths import resource_root


COLORS = {
    "window": "#1E1E1E",
    "panel": "#252526",
    "field": "#1B1B1C",
    "raised": "#2D2D30",
    "border": "#3C3C3C",
    "divider": "#333333",
    "text": "#E6E6E6",
    "muted": "#A8A8A8",
    "blue": "#007ACC",
    "blue_hover": "#1684C7",
    "orange": "#D9822B",
    "danger": "#C94F4F",
}


STYLE_SHEET = """
* {
    font-family: "Noto Sans CJK SC", "Microsoft YaHei UI", "Segoe UI";
    font-size: 11px;
    color: #E6E6E6;
}
QMainWindow, QDialog, QWidget { background: #1E1E1E; }
QMenuBar { background: #252526; border-bottom: 1px solid #333333; padding: 1px; }
QMenuBar::item { padding: 3px 8px; background: transparent; }
QMenuBar::item:selected, QMenu::item:selected { background: #094771; }
QMenu { background: #252526; border: 1px solid #3C3C3C; padding: 2px; }
QMenu::item { padding: 4px 24px 4px 8px; }
QToolBar { background: #252526; border: 0; border-bottom: 1px solid #333333; spacing: 2px; padding: 2px; }
QToolButton, QPushButton {
    background: #2D2D30; border: 1px solid #3C3C3C; border-radius: 1px;
    padding: 3px 7px; min-height: 19px;
}
QToolButton:hover, QPushButton:hover { background: #3A3A3D; border-color: #555555; }
QToolButton:pressed, QPushButton:pressed { background: #202022; }
QPushButton[accent="true"] { background: #007ACC; border-color: #1684C7; font-weight: 600; }
QPushButton[accent="true"]:hover { background: #1684C7; }
QPushButton[danger="true"] { color: #F2B7B7; background: #3A2929; border-color: #6E3B3B; }
QPushButton:disabled, QToolButton:disabled { color: #777777; background: #292929; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #1B1B1C; border: 1px solid #3C3C3C; border-radius: 1px;
    padding: 2px 4px; min-height: 19px; selection-background-color: #094771;
}
QLineEdit, QSpinBox, QDoubleSpinBox { font-family: Consolas, "JetBrains Mono", monospace; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #007ACC; }
QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView { background: #252526; border: 1px solid #3C3C3C; selection-background-color: #094771; }
QGroupBox { background: #252526; border: 1px solid #333333; margin-top: 13px; padding: 5px 4px 4px 4px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 5px; padding: 0 3px; color: #ECECEC; }
QTabWidget::pane { border: 1px solid #333333; top: -1px; }
QTabBar::tab { background: #2D2D30; color: #B8B8B8; border: 1px solid #3C3C3C; padding: 4px 10px; }
QTabBar::tab:selected { background: #252526; color: white; border-top: 2px solid #007ACC; }
QTabBar::tab:hover:!selected { background: #343437; }
QDockWidget { titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { background: #252526; border: 1px solid #333333; padding: 4px; font-weight: 600; }
QTreeWidget, QTreeView, QListWidget, QTableWidget, QPlainTextEdit, QTextEdit {
    background: #1B1B1C; alternate-background-color: #202022; border: 1px solid #333333;
    selection-background-color: #094771; selection-color: white;
}
QTreeWidget, QPlainTextEdit { font-family: Consolas, "JetBrains Mono", monospace; }
QHeaderView::section { background: #2D2D30; border: 0; border-right: 1px solid #3C3C3C; border-bottom: 1px solid #3C3C3C; padding: 3px; font-weight: 600; }
QScrollBar:vertical { background: #1E1E1E; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #424242; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: #1B1B1C; border: 1px solid #3C3C3C; text-align: center; min-height: 13px; }
QProgressBar::chunk { background: #007ACC; }
QStatusBar { background: #007ACC; border: 0; }
QStatusBar QLabel { color: white; background: transparent; }
QSplitter::handle { background: #333333; width: 2px; height: 2px; }
QLabel[heading="true"] { font-size: 12px; font-weight: 700; color: #F0F0F0; }
QLabel[muted="true"] { color: #A8A8A8; }
"""


def apply_industrial_theme(app: QApplication) -> None:
    # Qt maintains its own application-font database.  Merely naming the
    # bundled Noto face in QSS is not enough on machines where it is not
    # installed system-wide (and produced tofu boxes in the packaged build).
    font_dir = resource_root() / "assets" / "fonts"
    registered_families: list[str] = []
    for filename in ("NotoSansCJKsc-Regular.otf", "NotoSansCJKsc-Bold.otf"):
        font_id = QFontDatabase.addApplicationFont(str(font_dir / filename))
        if font_id >= 0:
            registered_families.extend(QFontDatabase.applicationFontFamilies(font_id))
    if registered_families:
        app.setFont(QFont(registered_families[0], 11))

    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["field"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["panel"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["raised"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["blue"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE_SHEET)
