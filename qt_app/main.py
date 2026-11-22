from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core_modules.runtime_paths import resource_root

from qt_app.main_window import MainWindow
from qt_app.theme import apply_industrial_theme


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("SU2 Airfoil Studio")
    app.setOrganizationName("Phiphi007")
    icon_path = resource_root() / "assets" / "branding" / "su2_airfoil_studio.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    apply_industrial_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
