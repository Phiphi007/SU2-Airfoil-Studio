"""Low-level SU2 process adapter for direct, AD, DOT and deformation runs."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import time
from typing import Mapping

from .config import StudyConfig


def config_with_overrides(
    source: Path, target: Path, overrides: Mapping[str, str | int | float | None]
) -> None:
    keys = {key.upper() for key, value in overrides.items() if value is not None}
    kept: list[str] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line)
        if not (match and match.group(1).upper() in keys):
            kept.append(line)
    kept.extend(("", "% --- ParametricAdjoint overrides ---"))
    kept.extend(f"{key}= {value}" for key, value in overrides.items() if value is not None)
    target.write_text("\n".join(kept) + "\n", encoding="utf-8")


class SU2Runner:
    def __init__(self, config: StudyConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        runtime = self.config.executables.runtime_bin
        if runtime:
            env["PATH"] = str(runtime) + os.pathsep + env.get("PATH", "")
        return env

    def validate_executables(self) -> None:
        for name in ("cfd", "cfd_ad", "dot_ad", "deform"):
            path = getattr(self.config.executables, name)
            if not path.is_file():
                raise FileNotFoundError(f"SU2 executable '{name}' not found: {path}")

    def run(self, executable: Path, cfg: Path, work: Path, log_name: str) -> float:
        if self.dry_run:
            (work / log_name).write_text(
                f"DRY RUN: {executable} {cfg.name}\n", encoding="utf-8"
            )
            return 0.0
        started = time.perf_counter()
        command = [str(executable)]
        if self.config.solver.threads > 1 and executable.name.startswith("SU2_CFD"):
            command.extend(("-t", str(self.config.solver.threads)))
        command.append(cfg.name)
        completed = subprocess.run(
            command,
            cwd=work,
            env=self.environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        elapsed = time.perf_counter() - started
        (work / log_name).write_text(completed.stdout, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(
                f"{executable.name} failed in {work} (exit {completed.returncode}).\n"
                f"Last output:\n{completed.stdout[-5000:]}"
            )
        return elapsed

    def direct_config(
        self,
        work: Path,
        *,
        name: str,
        mesh: str,
        solution: str,
        restart: str,
        history: str,
        aoa: float,
        iterations: int,
    ) -> Path:
        cfg = work / name
        config_with_overrides(self.config.case.direct_template, cfg, {
            "AOA": f"{aoa:.16g}",
            "MACH_NUMBER": self.config.case.mach,
            "REYNOLDS_NUMBER": self.config.case.reynolds,
            "MESH_FILENAME": mesh,
            "RESTART_SOL": "YES",
            "SOLUTION_FILENAME": solution,
            "RESTART_FILENAME": restart,
            "CONV_FILENAME": history,
            "ITER": iterations,
            "CONV_RESIDUAL_MINVAL": -10,
            "CONV_CAUCHY_EPS": "1e-10",
            "OUTPUT_WRT_FREQ": iterations,
            "SCREEN_WRT_FREQ_INNER": min(400, iterations),
        })
        return cfg

    def adjoint_config(
        self, work: Path, *, objective: str, mesh: str, solution: str, aoa: float
    ) -> Path:
        lower = objective.lower()
        cfg = work / f"adjoint_{lower}.cfg"
        config_with_overrides(self.config.case.adjoint_template, cfg, {
            "MATH_PROBLEM": "DISCRETE_ADJOINT",
            "OBJECTIVE_FUNCTION": objective,
            "AOA": f"{aoa:.16g}",
            "MACH_NUMBER": self.config.case.mach,
            "REYNOLDS_NUMBER": self.config.case.reynolds,
            "MESH_FILENAME": mesh,
            "SOLUTION_FILENAME": solution,
            "SOLUTION_ADJ_FILENAME": f"restart_adj_{lower}",
            "RESTART_ADJ_FILENAME": f"restart_adj_{lower}",
            "CONV_FILENAME": f"history_adj_{lower}",
            "SURFACE_ADJ_FILENAME": f"surface_adjoint_{lower}",
            "GRAD_OBJFUNC_FILENAME": f"gradient_{lower}",
            "RESTART_SOL": "NO",
            "ITER": self.config.solver.adjoint_iterations,
            "CFL_NUMBER": self.config.solver.adjoint_cfl,
            "QUASI_NEWTON_NUM_SAMPLES": 0,
            "RELAXATION_FACTOR_ADJOINT": 1,
            "DV_KIND": "HICKS_HENNE",
            "DV_MARKER": f"( {self.config.case.marker} )",
            "DV_PARAM": "( 1, 0.5 )",
            "DV_VALUE": "0.001",
            "OUTPUT_FILES": "( RESTART, SURFACE_CSV )",
            "TABULAR_FORMAT": "CSV",
        })
        return cfg

    def deform_config(self, work: Path, *, mesh_in: str, mesh_out: str) -> Path:
        cfg = work / "deform.cfg"
        config_with_overrides(self.config.case.direct_template, cfg, {
            "MESH_FILENAME": mesh_in,
            "MESH_OUT_FILENAME": mesh_out,
            "DV_KIND": "SURFACE_FILE",
            "DV_PARAM": "( 1, 0.5 )",
            "DV_VALUE": "0.1",
            "DV_MARKER": f"( {self.config.case.marker} )",
            "DV_FILENAME": "surface_positions.dat",
            "DEFORM_CONSOLE_OUTPUT": "NO",
        })
        return cfg
