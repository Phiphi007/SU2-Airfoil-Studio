from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from core_modules.solver_control import SolverControlMonitor


class FakeController:
    def __init__(self) -> None:
        self.paused = False
        self.terminated: list[str] = []

    def pause(self) -> bool:
        self.paused = True
        return True

    def resume(self) -> bool:
        was_paused = self.paused
        self.paused = False
        return was_paused

    def terminate(self, mode: str = "immediate") -> bool:
        self.terminated.append(mode)
        return True


def _history(path: Path, iteration: int) -> None:
    path.write_text(
        f'"Inner_Iter","rms[Rho]","CL","CD"\n{iteration},-5,0.2,0.02\n',
        encoding="utf-8",
    )


class SolverControlTests(unittest.TestCase):
    def test_pause_resume_and_immediate_stop(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            controller = FakeController()
            monitor = SolverControlMonitor(Path(folder), controller)  # type: ignore[arg-type]
            monitor._handle("pause")
            self.assertTrue(controller.paused)
            monitor._handle("resume")
            self.assertFalse(controller.paused)
            monitor._handle("stop_now")
            self.assertEqual(controller.terminated, ["immediate"])

    def test_stop_after_next_stable_save_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            controller = FakeController()
            _history(output / "history.csv", 42)
            monitor = SolverControlMonitor(output, controller, save_frequency=100)  # type: ignore[arg-type]
            monitor._handle("stop_after_save")
            self.assertEqual(monitor._target_iteration, 100)

            _history(output / "history.csv", 100)
            (output / "flow.vtu").write_text("saved field", encoding="utf-8")
            for _ in range(4):
                monitor._check_save_cycle()
            self.assertEqual(controller.terminated, ["after_save"])
            status = json.loads(
                (output / "solver_control_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status["state"], "stopping")
            self.assertEqual(status["completed_iteration"], 100)
