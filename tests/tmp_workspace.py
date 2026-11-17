"""测试共用的临时目录助手：沙箱环境可能限制进程写入某些目录。"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_CANDIDATES = (
    PROJECT_ROOT / ".tests_tmp",
    PROJECT_ROOT / "tests" / ".tmp",
    Path(tempfile.gettempdir()),
)

_temp_base: Path | None = None


def _writable_base() -> Path:
    global _temp_base
    if _temp_base is not None:
        return _temp_base
    for candidate in _CANDIDATES:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            _temp_base = candidate
            return candidate
        except (PermissionError, OSError):
            continue
    raise PermissionError("找不到可写的临时目录；测试无法运行。")


@contextmanager
def workspace_temp_dir() -> Iterator[Path]:
    """在可写根目录下创建临时子目录，结束后尽力清理。"""
    base = _writable_base()
    path = base / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
