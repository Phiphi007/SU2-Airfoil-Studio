from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from core_modules.runtime_paths import resource_root


THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "window": "#1E1E1E", "panel": "#252526", "field": "#1B1B1C",
        "raised": "#2D2D30", "hover": "#3A3A3D", "pressed": "#202022",
        "border": "#3C3C3C", "divider": "#333333", "text": "#E6E6E6",
        "muted": "#A8A8A8", "accent": "#007ACC", "accent_hover": "#1684C7",
        "selection": "#094771", "disabled": "#777777", "danger_bg": "#3A2929",
        "danger_border": "#6E3B3B", "danger_text": "#F2B7B7", "status_text": "#FFFFFF",
    },
    "light": {
        "window": "#F1F1F1", "panel": "#FFFFFF", "field": "#FAFAFA",
        "raised": "#E5E5E5", "hover": "#D8D8D8", "pressed": "#CFCFCF",
        "border": "#B7B7B7", "divider": "#CDCDCD", "text": "#202020",
        "muted": "#606060", "accent": "#0078D4", "accent_hover": "#106EBE",
        "selection": "#B8DDFC", "disabled": "#8A8A8A", "danger_bg": "#F8E6E6",
        "danger_border": "#C97878", "danger_text": "#8B1E1E", "status_text": "#FFFFFF",
    },
    "deep_blue": {
        "window": "#101820", "panel": "#16232E", "field": "#0C141B",
        "raised": "#203241", "hover": "#294459", "pressed": "#111E28",
        "border": "#365268", "divider": "#273C4D", "text": "#E5EDF3",
        "muted": "#9DB0BE", "accent": "#2D9CDB", "accent_hover": "#48B2EC",
        "selection": "#174F70", "disabled": "#71818C", "danger_bg": "#3B2428",
        "danger_border": "#7B4048", "danger_text": "#F2B9BE", "status_text": "#FFFFFF",
    },
    "graphite": {
        "window": "#202225", "panel": "#292C30", "field": "#191B1E",
        "raised": "#34383D", "hover": "#41464C", "pressed": "#24272A",
        "border": "#4A4F55", "divider": "#393D42", "text": "#ECECEC",
        "muted": "#B0B3B6", "accent": "#D9822B", "accent_hover": "#E79A4D",
        "selection": "#6D451F", "disabled": "#7E8286", "danger_bg": "#40292B",
        "danger_border": "#7A4448", "danger_text": "#F0B9BD", "status_text": "#FFFFFF",
    },
    "rose": {
        "window": "#241A21", "panel": "#30232C", "field": "#1E161C",
        "raised": "#3B2B36", "hover": "#503A49", "pressed": "#281D25",
        "border": "#604657", "divider": "#46333F", "text": "#F4EAF0",
        "muted": "#C6AEBB", "accent": "#D95D91", "accent_hover": "#EB79A9",
        "selection": "#71334E", "disabled": "#8C7883", "danger_bg": "#47262E",
        "danger_border": "#8A4657", "danger_text": "#FFC4D2", "status_text": "#FFFFFF",
    },
    "forest": {
        "window": "#17201D", "panel": "#202C28", "field": "#121A17",
        "raised": "#2A3934", "hover": "#385047", "pressed": "#1A2521",
        "border": "#415E54", "divider": "#30453E", "text": "#E8F0ED",
        "muted": "#A7BBB4", "accent": "#2E9D78", "accent_hover": "#42B98F",
        "selection": "#245B49", "disabled": "#74857F", "danger_bg": "#40292B",
        "danger_border": "#7A4448", "danger_text": "#F0B9BD", "status_text": "#FFFFFF",
    },
    "violet": {
        "window": "#1D1926", "panel": "#282234", "field": "#17131F",
        "raised": "#342C43", "hover": "#473B5B", "pressed": "#211B2B",
        "border": "#584A70", "divider": "#3E3450", "text": "#F0ECF6",
        "muted": "#B8ADC8", "accent": "#8B6FD6", "accent_hover": "#A489E8",
        "selection": "#4F3D79", "disabled": "#80778D", "danger_bg": "#43272F",
        "danger_border": "#7D4452", "danger_text": "#F4BCC9", "status_text": "#FFFFFF",
    },
    "sand": {
        "window": "#E8E2D6", "panel": "#F4F0E8", "field": "#FCFAF5",
        "raised": "#DDD5C7", "hover": "#CEC3B2", "pressed": "#C4B9A8",
        "border": "#A99D8B", "divider": "#C3B9AA", "text": "#29251F",
        "muted": "#655E54", "accent": "#A66024", "accent_hover": "#BD7433",
        "selection": "#E4BF95", "disabled": "#877F73", "danger_bg": "#F1DADA",
        "danger_border": "#B76D6D", "danger_text": "#7F2323", "status_text": "#FFFFFF",
    },
}

COLORS = THEMES["dark"]


STYLE_TEMPLATE = """
* { font-family: "Noto Sans CJK SC", "Microsoft YaHei UI", "Segoe UI"; font-size: 11px; color: @TEXT@; }
QMainWindow, QDialog, QWidget { background: @WINDOW@; }
QMenuBar { background: @PANEL@; border-bottom: 1px solid @DIVIDER@; padding: 1px; }
QMenuBar::item { padding: 3px 8px; background: transparent; }
QMenuBar::item:selected, QMenu::item:selected { background: @SELECTION@; }
QMenu { background: @PANEL@; border: 1px solid @BORDER@; padding: 2px; }
QMenu::item { padding: 4px 24px 4px 8px; }
QToolBar { background: @PANEL@; border: 0; border-bottom: 1px solid @DIVIDER@; spacing: 2px; padding: 2px; }
QToolButton, QPushButton { background: @RAISED@; border: 1px solid @BORDER@; border-radius: 1px; padding: 3px 7px; min-height: 19px; }
QToolButton:hover, QPushButton:hover { background: @HOVER@; border-color: @MUTED@; }
QToolButton:pressed, QPushButton:pressed { background: @PRESSED@; }
QPushButton[accent="true"] { background: @ACCENT@; border-color: @ACCENT_HOVER@; color: @STATUS_TEXT@; font-weight: 600; }
QPushButton[accent="true"]:hover { background: @ACCENT_HOVER@; }
QPushButton[danger="true"] { color: @DANGER_TEXT@; background: @DANGER_BG@; border-color: @DANGER_BORDER@; }
QPushButton:disabled, QToolButton:disabled { color: @DISABLED@; background: @RAISED@; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: @FIELD@; border: 1px solid @BORDER@; border-radius: 1px; padding: 2px 4px; min-height: 19px; selection-background-color: @SELECTION@; }
QLineEdit, QSpinBox, QDoubleSpinBox { font-family: Consolas, "JetBrains Mono", monospace; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: @ACCENT@; }
QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView { background: @PANEL@; border: 1px solid @BORDER@; selection-background-color: @SELECTION@; }
QCheckBox { spacing: 5px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid @BORDER@; border-radius: 1px; background: @FIELD@; }
QCheckBox::indicator:hover { border-color: @ACCENT_HOVER@; }
QCheckBox::indicator:checked { background: @ACCENT@; border-color: @ACCENT_HOVER@; image: url("@CHECK_ICON@"); }
QCheckBox::indicator:disabled { background: @RAISED@; border-color: @DIVIDER@; }
QGroupBox { background: @PANEL@; border: 1px solid @DIVIDER@; margin-top: 13px; padding: 5px 4px 4px 4px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 5px; padding: 0 3px; color: @TEXT@; }
QTabWidget::pane { border: 1px solid @DIVIDER@; top: -1px; }
QTabBar::tab { background: @RAISED@; color: @MUTED@; border: 1px solid @BORDER@; padding: 4px 10px; }
QTabBar::tab:selected { background: @PANEL@; color: @TEXT@; border-top: 2px solid @ACCENT@; }
QTabBar::tab:hover:!selected { background: @HOVER@; }
QDockWidget { titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { background: @PANEL@; border: 1px solid @DIVIDER@; padding: 4px; font-weight: 600; }
QTreeWidget, QTreeView, QListWidget, QTableWidget, QPlainTextEdit, QTextEdit { background: @FIELD@; alternate-background-color: @PANEL@; border: 1px solid @DIVIDER@; selection-background-color: @SELECTION@; selection-color: @TEXT@; }
QTreeWidget, QPlainTextEdit { font-family: Consolas, "JetBrains Mono", monospace; }
QHeaderView::section { background: @RAISED@; border: 0; border-right: 1px solid @BORDER@; border-bottom: 1px solid @BORDER@; padding: 3px; font-weight: 600; }
QScrollBar:vertical { background: @WINDOW@; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: @BORDER@; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: @FIELD@; border: 1px solid @BORDER@; text-align: center; min-height: 13px; }
QProgressBar::chunk { background: @ACCENT@; }
QStatusBar { background: @ACCENT@; border: 0; }
QStatusBar QLabel { color: @STATUS_TEXT@; background: transparent; }
QSplitter::handle { background: @DIVIDER@; width: 2px; height: 2px; }
QLabel[heading="true"] { font-size: 12px; font-weight: 700; color: @TEXT@; }
QLabel[muted="true"] { color: @MUTED@; }
"""


def _style_sheet(colors: dict[str, str]) -> str:
    result = STYLE_TEMPLATE
    for key, value in colors.items():
        result = result.replace(f"@{key.upper()}@", value)
    check_icon = (resource_root() / "assets" / "icons" / "checkmark.svg").as_posix()
    result = result.replace("@CHECK_ICON@", check_icon)
    return result


def apply_industrial_theme(app: QApplication, theme: str = "dark") -> str:
    """Apply a compact industrial palette and return the normalized theme name."""
    normalized = theme if theme in THEMES else "dark"
    colors = THEMES[normalized]
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
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["field"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["panel"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["raised"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["status_text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["muted"]))
    app.setPalette(palette)
    app.setStyleSheet(_style_sheet(colors))
    return normalized
