"""Shared frozen entry point for the desktop and console executables."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import traceback


def main() -> int:
    if "--worker-log" in sys.argv:
        index = sys.argv.index("--worker-log")
        try:
            worker_log = Path(sys.argv[index + 1]).expanduser().resolve()
        except IndexError as exc:
            raise SystemExit("--worker-log requires a path") from exc
        del sys.argv[index:index + 2]
        worker_log.parent.mkdir(parents=True, exist_ok=True)
        worker_stream = worker_log.open("a", encoding="utf-8", buffering=1)
        sys.stdout = worker_stream
        sys.stderr = worker_stream
    # Windowed PyInstaller applications have no standard streams. Some numerical
    # libraries still write to them; keep those diagnostics in the user data folder.
    from core_modules.runtime_paths import data_root
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            data_root().mkdir(parents=True, exist_ok=True)
            setattr(sys, name, (data_root() / "desktop.log").open("a", encoding="utf-8"))
        elif hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if sys.stdin is not None and hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if sys.argv[1:2] == ["--mesh-worker"]:
        del sys.argv[1]
        from core_modules.mesh_worker import main as worker_main
        return worker_main()
    if sys.argv[1:2] == ["--worker"]:
        del sys.argv[1]
        from parametric_adjoint.cli import main as optimizer_main
        return optimizer_main(sys.argv[1:])
    gui_names = {"AutoFoilStudio", "SU2_AutoFoil_Optimizer_Studio"}
    if Path(sys.executable).stem in gui_names or sys.argv[1:2] == ["--gui"]:
        if sys.argv[1:2] == ["--gui"]:
            del sys.argv[1]
        try:
            from gui_app import main as gui_main
            return gui_main()
        except Exception:
            data_root().mkdir(parents=True, exist_ok=True)
            log = data_root() / "gui_error.log"
            log.write_text(traceback.format_exc(), encoding="utf-8")
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, f"启动失败 / Startup failed\n{log}", "SU2 AutoFoil Studio", 0x10)
            return 1
    from portable_api import main as api_main
    return api_main()


if __name__ == "__main__":
    raise SystemExit(main())
