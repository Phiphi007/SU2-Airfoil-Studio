from __future__ import annotations

import json
from pathlib import Path

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


def test_pause_resume_and_immediate_stop(tmp_path: Path) -> None:
    controller = FakeController()
    monitor = SolverControlMonitor(tmp_path, controller)  # type: ignore[arg-type]
    monitor._handle("pause")
    assert controller.paused
    monitor._handle("resume")
    assert not controller.paused
    monitor._handle("stop_now")
    assert controller.terminated == ["immediate"]


def test_stop_after_next_stable_save_cycle(tmp_path: Path) -> None:
    controller = FakeController()
    _history(tmp_path / "history.csv", 42)
    monitor = SolverControlMonitor(tmp_path, controller, save_frequency=100)  # type: ignore[arg-type]
    monitor._handle("stop_after_save")
    assert monitor._target_iteration == 100

    _history(tmp_path / "history.csv", 100)
    (tmp_path / "flow.vtu").write_text("saved field", encoding="utf-8")
    for _ in range(4):
        monitor._check_save_cycle()
    assert controller.terminated == ["after_save"]
    status = json.loads((tmp_path / "solver_control_status.json").read_text(encoding="utf-8"))
    assert status["state"] == "stopping"
    assert status["completed_iteration"] == 100
