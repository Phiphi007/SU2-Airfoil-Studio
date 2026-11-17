"""Register the bundled open-source font for Tk and Matplotlib."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_FONT = PROJECT_ROOT / "assets" / "fonts" / "NotoSansCJKsc-Regular.otf"
BUNDLED_BOLD_FONT = PROJECT_ROOT / "assets" / "fonts" / "NotoSansCJKsc-Bold.otf"
FALLBACK_FAMILY = "DejaVu Sans"
WINDOWS_UI_FAMILY = "Microsoft YaHei UI"
_registered_family: str | None = None


def register_bundled_font() -> str:
    """Prefer the native Windows UI face and retain bundled Noto as fallback."""
    global _registered_family
    if _registered_family is not None:
        return _registered_family
    if not BUNDLED_FONT.is_file():
        _registered_family = WINDOWS_UI_FAMILY if os.name == "nt" else FALLBACK_FAMILY
        return _registered_family

    # Tk uses the operating-system font collection. FR_PRIVATE makes the font
    # available only to this process and does not install anything system-wide.
    available_fonts = [
        path for path in (BUNDLED_FONT, BUNDLED_BOLD_FONT) if path.is_file()
    ]
    if os.name == "nt":
        try:
            for font_path in available_fonts:
                ctypes.windll.gdi32.AddFontResourceExW(str(font_path), 0x10, 0)
        except (AttributeError, OSError):
            pass

    try:
        from matplotlib import font_manager

        for font_path in available_fonts:
            font_manager.fontManager.addfont(str(font_path))
        _registered_family = (
            WINDOWS_UI_FAMILY
            if os.name == "nt"
            else font_manager.FontProperties(fname=str(BUNDLED_FONT)).get_name()
        )
    except (ImportError, OSError, RuntimeError):
        _registered_family = WINDOWS_UI_FAMILY if os.name == "nt" else FALLBACK_FAMILY
    return _registered_family


def configure_matplotlib_font() -> str:
    """Apply the bundled family without changing the selected UI language."""
    family = register_bundled_font()
    try:
        import matplotlib

        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [
            family,
            "Microsoft YaHei",
            "Noto Sans CJK SC",
            FALLBACK_FAMILY,
        ]
        matplotlib.rcParams["axes.unicode_minus"] = False
    except ImportError:
        pass
    return family
