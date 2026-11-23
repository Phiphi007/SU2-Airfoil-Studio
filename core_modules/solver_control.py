"""File-based control channel between the Qt shell and the SU2 worker."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import threading
import time

from core_modules.process_control import ProcessController


CONTROL_FILENAME = ".solver_control.json"
STATUS_FILENAME = "solver_control_status.json"
SAVE_PRODUCTS = ("restart_flow.dat", "restart_flow.csv", "flow.vtu", "surface_flow.csv")


def _last_iteration(path: Path) -> int | None:
    if not path.is_file():
        return None
    last: int | None = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream, skipinitialspace=True):
                for key in ("Inner_Iter", "Iteration", "Iter"):
                    raw = row.get(key) or row.get(f'"{key}"')
                    if raw is None:
                        continue
                    value = float(raw)
                    if math.isfinite(value):
                        last = int(value)
                        break
    except (OSError, ValueError, csv.Error):
        return last
    return last


def _product_signature(output: Path) -> tuple[tuple[str, int, int], ...]:
    values = []
    for name in SAVE_PRODUCTS:
        path = output / name
        if path.is_file():
            stat = path.stat()
            values.append((name, stat.st_size, stat.st_mtime_ns))
    return tuple(values)


class SolverControlMonitor:
    """Poll commands and apply them to the actual SU2 child process."""

    def __init__(
        self,
        output: Path,
        controller: ProcessController,
        *,
        save_frequency: int = 100,
        poll_seconds: float = 0.2,
    ) -> None:
        self.output = output
        self.controller = controller
        self.save_frequency = max(1, int(save_frequency))
        self.poll_seconds = max(0.05, float(poll_seconds))
        self.control_path = output / CONTROL_FILENAME
        self.status_path = output / STATUS_FILENAME
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_serial: object = None
        self._pending_signature: tuple[tuple[str, int, int], ...] | None = None
        self._stable_polls = 0
        self._target_iteration: int | None = None
        self._write_status("starting")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="solver-control", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _write_status(self, state: str, **extra: object) -> None:
        payload = {"state": state, "updated_at": time.time(), **extra}
        temporary = self.status_path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.status_path)
        except OSError:
            pass

    def _command(self) -> str | None:
        try:
            payload = json.loads(self.control_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        serial = payload.get("serial")
        if serial == self._last_serial:
            return None
        self._last_serial = serial
        return str(payload.get("command", ""))

    def _handle(self, command: str) -> None:
        if command == "pause":
            self.controller.pause()
            self._write_status("paused")
        elif command == "resume":
            self.controller.resume()
            self._write_status("running")
        elif command == "stop_now":
            self._write_status("stopping", mode="immediate")
            self.controller.terminate("immediate")
        elif command == "stop_after_save":
            current = _last_iteration(self.output / "history.csv") or 0
            self._target_iteration = ((current // self.save_frequency) + 1) * self.save_frequency
            self._pending_signature = _product_signature(self.output)
            self._stable_polls = 0
            self.controller.resume()
            self._write_status(
                "stop_pending", mode="after_save", target_iteration=self._target_iteration
            )

    def _check_save_cycle(self) -> None:
        if self._target_iteration is None:
            return
        iteration = _last_iteration(self.output / "history.csv")
        if iteration is None or iteration < self._target_iteration:
            return
        signature = _product_signature(self.output)
        if not signature or signature == self._pending_signature:
            return
        if signature == getattr(self, "_last_observed_signature", None):
            self._stable_polls += 1
        else:
            self._last_observed_signature = signature
            self._stable_polls = 0
        if self._stable_polls >= 2:
            self._write_status(
                "stopping", mode="after_save", completed_iteration=iteration
            )
            self.controller.terminate("after_save")
            self._target_iteration = None

    def _run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            command = self._command()
            if command:
                self._handle(command)
            self._check_save_cycle()
