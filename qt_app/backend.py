from __future__ import annotations

import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, Signal

from core_modules.runtime_paths import application_root, resource_root


class ApiProcess(QObject):
    """Run the existing JSON API without a console window."""

    log = Signal(str)
    started = Signal()
    finished = Signal(dict)
    failed = Signal(str)
    runningChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.started.connect(self._started)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.readyReadStandardOutput.connect(self._stdout)
        self.process.finished.connect(self._finished)
        self._stdout_buffer = bytearray()

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start_request(self, request: dict) -> None:
        if self.running:
            raise RuntimeError("A backend task is already running.")
        self._stdout_buffer.clear()
        if getattr(sys, "frozen", False):
            program = application_root() / "AutoFoilCLI.exe"
            arguments = ["run", "--request", "-"]
        else:
            program = Path(sys.executable)
            arguments = [str(resource_root() / "portable_entry.py"), "run", "--request", "-"]
        self.process.setProgram(str(program))
        self.process.setArguments(arguments)
        self.process.setWorkingDirectory(str(resource_root()))
        self.process.start()
        if not self.process.waitForStarted(5000):
            raise RuntimeError(self.process.errorString())
        payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
        self.process.write(payload)
        self.process.closeWriteChannel()

    def terminate(self) -> None:
        if self.running:
            self.process.terminate()
            if not self.process.waitForFinished(2500):
                self.process.kill()

    def _started(self) -> None:
        self.runningChanged.emit(True)
        self.started.emit()

    def _stderr(self) -> None:
        text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if text:
            self.log.emit(text.rstrip())

    def _stdout(self) -> None:
        self._stdout_buffer.extend(bytes(self.process.readAllStandardOutput()))

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.runningChanged.emit(False)
        raw = bytes(self._stdout_buffer).decode("utf-8", errors="replace").strip()
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self.failed.emit(f"Backend returned invalid JSON (exit {exit_code}):\n{raw[-2000:]}")
            return
        if exit_code or not result.get("ok", False):
            error = result.get("error", {})
            self.failed.emit(error.get("message") or f"Backend failed with exit {exit_code}.")
        else:
            self.finished.emit(result)


class OptimizerProcess(QObject):
    """Stream the existing adjoint optimizer through Qt's event loop."""

    log = Signal(str)
    finished = Signal(int)
    runningChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.started.connect(lambda: self.runningChanged.emit(True))
        self.process.readyReadStandardOutput.connect(self._output)
        self.process.finished.connect(self._finished)

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start(self, config_path: Path) -> None:
        if self.running:
            raise RuntimeError("An optimization task is already running.")
        if getattr(sys, "frozen", False):
            program = Path(sys.executable)
            arguments = ["--worker", "optimize", str(config_path)]
        else:
            program = Path(sys.executable)
            arguments = [
                str(resource_root() / "portable_entry.py"),
                "--worker",
                "optimize",
                str(config_path),
            ]
        self.process.setProgram(str(program))
        self.process.setArguments(arguments)
        self.process.setWorkingDirectory(str(resource_root()))
        self.process.start()
        if not self.process.waitForStarted(5000):
            raise RuntimeError(self.process.errorString())

    def terminate(self) -> None:
        if self.running:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()

    def _output(self) -> None:
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if text:
            self.log.emit(text.rstrip())

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.runningChanged.emit(False)
        self.finished.emit(exit_code)
