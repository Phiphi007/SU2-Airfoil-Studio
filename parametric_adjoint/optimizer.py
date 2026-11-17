"""Trust-region SU2 discrete-adjoint optimizer."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import time
from typing import Any, Callable

import numpy as np

from .config import StudyConfig
from .constraints import check_geometry
from .io import (
    json_ready,
    read_adjoint_history,
    read_history,
    read_sensitivity,
    write_surface_positions,
)
from .parameterizations import build_direction
from .parameterizations.common import surface_sides
from .su2 import SU2Runner


@dataclass
class DesignState:
    mesh: Path
    restart: Path
    aoa_deg: float
    cl: float
    cd: float
    objective: float
    accepted_steps: int = 0


class AdjointOptimizer:
    def __init__(
        self,
        config: StudyConfig,
        *,
        dry_run: bool = False,
        progress: Callable[[str], None] | None = None,
    ):
        self.cfg = config
        self.runner = SU2Runner(config, dry_run=dry_run)
        self.progress = progress

    def _emit(self, message: str) -> None:
        if self.progress:
            self.progress(message)

    def _direct(
        self,
        work: Path,
        *,
        mesh: str,
        solution: str,
        restart: str,
        history: str,
        aoa: float,
        iterations: int,
        label: str,
    ) -> tuple[dict[str, float | int], float]:
        cfg = self.runner.direct_config(
            work,
            name=f"{label}.cfg",
            mesh=mesh,
            solution=solution,
            restart=restart,
            history=history,
            aoa=aoa,
            iterations=iterations,
        )
        self._emit(f"正问题开始：{label}，AoA={aoa:.7f}°，ITER={iterations}")
        seconds = self.runner.run(self.cfg.executables.cfd, cfg, work, f"{label}.log")
        self._emit(f"正问题完成：{label}，耗时 {seconds:.2f} s")
        return read_history(work / f"{history}.csv"), seconds

    def _initial_state(self) -> DesignState:
        if self.cfg.case.initial_cl is not None and self.cfg.case.initial_cd is not None:
            cd = self.cfg.case.initial_cd
            cl = self.cfg.case.initial_cl
            objective = self._objective(cd, cl)
            return DesignState(
                self.cfg.case.mesh,
                self.cfg.case.restart,
                self.cfg.case.aoa_deg,
                cl,
                cd,
                objective,
            )
        work = self.cfg.output / "baseline"
        work.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.cfg.case.mesh, work / "mesh.su2")
        shutil.copy2(self.cfg.case.restart, work / "restart_input.dat")
        history, _ = self._direct(
            work,
            mesh="mesh.su2",
            solution="restart_input",
            restart="restart_baseline",
            history="history_baseline",
            aoa=self.cfg.case.aoa_deg,
            iterations=self.cfg.solver.direct_iterations,
            label="direct_baseline",
        )
        cd, cl = float(history["cd"]), float(history["cl"])
        return DesignState(
            work / "mesh.su2",
            work / "restart_baseline.dat",
            self.cfg.case.aoa_deg,
            cl,
            cd,
            self._objective(cd, cl),
        )

    def _objective(self, cd: float, cl: float) -> float:
        if self.cfg.objective.mode == "fixed_aoa":
            return cd
        assert self.cfg.objective.target_cl is not None
        assert self.cfg.objective.dcd_dcl is not None
        return cd - self.cfg.objective.dcd_dcl * (cl - self.cfg.objective.target_cl)

    @staticmethod
    def _surface_curves(
        x: np.ndarray, y: np.ndarray, reference_y: np.ndarray | None = None
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        reference = np.asarray(y if reference_y is None else reference_y, dtype=float)
        side = surface_sides(np.asarray(x, dtype=float), reference)

        def curve(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            xs = np.asarray(x, dtype=float)[mask]
            ys = np.asarray(y, dtype=float)[mask]
            order = np.argsort(xs)
            xs, ys = xs[order], ys[order]
            unique, inverse = np.unique(xs, return_inverse=True)
            sums = np.zeros_like(unique)
            counts = np.zeros_like(unique)
            np.add.at(sums, inverse, ys)
            np.add.at(counts, inverse, 1.0)
            return unique, sums / counts

        return curve(side >= 0.0), curve(side <= 0.0)

    @staticmethod
    def _write_airfoil_dat(
        path: Path,
        x: np.ndarray,
        y: np.ndarray,
        displacement: np.ndarray,
        title: str = "SU2_adjoint_optimized",
    ) -> None:
        """Write the accepted wall shape as a reusable Selig DAT file."""
        moved_y = np.asarray(y, dtype=float) + np.asarray(displacement, dtype=float)
        (upper_x, upper_y), (lower_x, lower_y) = AdjointOptimizer._surface_curves(
            np.asarray(x, dtype=float), moved_y, np.asarray(y, dtype=float)
        )
        lines = [title]
        lines.extend(
            f" {xi:.10f}  {yi:.10f}" for xi, yi in zip(upper_x[::-1], upper_y[::-1])
        )
        lines.extend(
            f" {xi:.10f}  {yi:.10f}" for xi, yi in zip(lower_x[1:], lower_y[1:])
        )
        path.write_text("\n".join(lines) + "\n", encoding="ascii")

    @staticmethod
    def _write_airfoil_comparison(
        path: Path,
        initial_x: np.ndarray,
        initial_y: np.ndarray,
        final_x: np.ndarray,
        final_y: np.ndarray,
        initial: dict[str, Any],
        final: DesignState,
    ) -> None:
        """Create an actual-scale overlay plus upper/lower displacement plot."""
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        (ixu, iyu), (ixl, iyl) = AdjointOptimizer._surface_curves(initial_x, initial_y)
        (fxu, fyu), (fxl, fyl) = AdjointOptimizer._surface_curves(
            final_x, final_y, initial_y
        )
        low = max(float(ixu.min()), float(ixl.min()), float(fxu.min()), float(fxl.min()))
        high = min(float(ixu.max()), float(ixl.max()), float(fxu.max()), float(fxl.max()))
        grid = np.linspace(low, high, 501)
        chord = max(high - low, 1.0e-12)
        upper_delta = (
            np.interp(grid, fxu, fyu) - np.interp(grid, ixu, iyu)
        ) / chord
        lower_delta = (
            np.interp(grid, fxl, fyl) - np.interp(grid, ixl, iyl)
        ) / chord

        figure = Figure(figsize=(10.4, 7.0), dpi=140, facecolor="white")
        FigureCanvasAgg(figure)
        shape_axis = figure.add_subplot(211)
        delta_axis = figure.add_subplot(212)
        shape_axis.plot(ixu, iyu, "--", color="#7b8794", linewidth=1.5, label="Initial")
        shape_axis.plot(ixl, iyl, "--", color="#7b8794", linewidth=1.5)
        shape_axis.plot(fxu, fyu, color="#087f6d", linewidth=2.0, label="Optimized")
        shape_axis.plot(fxl, fyl, color="#087f6d", linewidth=2.0)
        shape_axis.fill_between(
            grid,
            np.interp(grid, fxl, fyl),
            np.interp(grid, fxu, fyu),
            color="#087f6d",
            alpha=0.07,
        )
        shape_axis.set_aspect("equal", adjustable="datalim")
        shape_axis.set_ylabel("y / c")
        shape_axis.grid(True, linestyle=":", linewidth=0.6, alpha=0.65)
        shape_axis.legend(frameon=False, loc="best")
        shape_axis.set_title(
            "Airfoil geometry before / after adjoint optimization\n"
            f"CD {float(initial['cd']):.7f} → {final.cd:.7f}   |   "
            f"CL {float(initial['cl']):.7f} → {final.cl:.7f}   |   "
            f"AoA {float(initial['aoa_deg']):.4f}° → {final.aoa_deg:.4f}°"
        )
        delta_axis.axhline(0.0, color="#8796a3", linewidth=0.8)
        delta_axis.plot((grid - low) / chord, upper_delta, color="#0f6fba", label="Upper Δy/c")
        delta_axis.plot((grid - low) / chord, lower_delta, color="#d9822b", label="Lower Δy/c")
        delta_axis.set_xlabel("x / c")
        delta_axis.set_ylabel("Δy / c")
        delta_axis.grid(True, linestyle=":", linewidth=0.6, alpha=0.65)
        delta_axis.legend(frameon=False, loc="best")
        figure.tight_layout(pad=1.4)
        figure.savefig(path, dpi=140, bbox_inches="tight")

    def _adjoint(
        self, objective: str, state: DesignState, step_dir: Path
    ) -> tuple[dict[str, np.ndarray], float, dict[str, float | int]]:
        work = step_dir / f"adjoint_{objective.lower()}"
        work.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state.mesh, work / "mesh.su2")
        shutil.copy2(state.restart, work / "restart_flow_current.dat")
        cfg = self.runner.adjoint_config(
            work,
            objective=objective,
            mesh="mesh.su2",
            solution="restart_flow_current",
            aoa=state.aoa_deg,
        )
        self._emit(f"{objective} 离散伴随开始")
        cfd_seconds = self.runner.run(
            self.cfg.executables.cfd_ad, cfg, work, f"cfd_ad_{objective.lower()}.log"
        )
        dot_seconds = self.runner.run(
            self.cfg.executables.dot_ad, cfg, work, f"dot_ad_{objective.lower()}.log"
        )
        self._emit(
            f"{objective} 伴随完成：AD {cfd_seconds:.2f} s，DOT {dot_seconds:.2f} s"
        )
        convergence = read_adjoint_history(work / f"history_adj_{objective.lower()}.csv")
        convergence.update({
            "cfd_ad_seconds": cfd_seconds,
            "dot_ad_seconds": dot_seconds,
            "total_seconds": cfd_seconds + dot_seconds,
        })
        return (
            read_sensitivity(work / "surface_sens.csv"),
            cfd_seconds + dot_seconds,
            convergence,
        )

    @staticmethod
    def _same_surface(first: dict[str, np.ndarray], second: dict[str, np.ndarray]) -> None:
        if not np.array_equal(first["id"], second["id"]):
            raise RuntimeError("DRAG and LIFT adjoints returned different surface ordering")

    def _gradient(
        self, state: DesignState, step_dir: Path
    ) -> tuple[
        dict[str, np.ndarray], np.ndarray, np.ndarray | None, float,
        dict[str, dict[str, float | int]],
    ]:
        drag, seconds, drag_convergence = self._adjoint("DRAG", state, step_dir)
        convergence = {"drag": drag_convergence}
        lift_gradient: np.ndarray | None = None
        gradient = drag["gy"].copy()
        if self.cfg.objective.mode == "fixed_lift":
            lift, lift_seconds, lift_convergence = self._adjoint("LIFT", state, step_dir)
            self._same_surface(drag, lift)
            lift_gradient = lift["gy"].copy()
            assert self.cfg.objective.dcd_dcl is not None
            gradient -= self.cfg.objective.dcd_dcl * lift_gradient
            seconds += lift_seconds
            convergence["lift"] = lift_convergence
        return drag, gradient, lift_gradient, seconds, convergence

    def _trial(
        self,
        state: DesignState,
        step_dir: Path,
        surface: dict[str, np.ndarray],
        displacement: np.ndarray,
        predicted_delta: float,
        lift_slope: float,
    ) -> tuple[DesignState, dict[str, Any]]:
        work = step_dir / "trial"
        work.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state.mesh, work / "mesh_current.su2")
        shutil.copy2(state.restart, work / "restart_flow_current.dat")
        write_surface_positions(
            work / "surface_positions.dat",
            work / "mesh_current.su2",
            surface,
            displacement,
        )
        deform_cfg = self.runner.deform_config(
            work, mesh_in="mesh_current.su2", mesh_out="mesh_trial.su2"
        )
        self._emit("SU2_DEF 网格形变开始")
        deform_seconds = self.runner.run(
            self.cfg.executables.deform, deform_cfg, work, "deform.log"
        )
        self._emit(f"SU2_DEF 完成，耗时 {deform_seconds:.2f} s")
        aoa = state.aoa_deg
        aoa_limited = False
        if self.cfg.objective.mode == "fixed_lift":
            assert self.cfg.objective.dcl_dalpha is not None
            aoa -= lift_slope / self.cfg.objective.dcl_dalpha
            bounded = float(np.clip(
                aoa, self.cfg.constraints.aoa_min_deg, self.cfg.constraints.aoa_max_deg
            ))
            aoa_limited = aoa_limited or bounded != aoa
            aoa = bounded
        history, direct_seconds = self._direct(
            work,
            mesh="mesh_trial.su2",
            solution="restart_flow_current",
            restart="restart_trial",
            history="history_trial",
            aoa=aoa,
            iterations=self.cfg.solver.direct_iterations,
            label="direct_trial",
        )
        solution = "restart_trial"
        corrections: list[dict[str, float | int]] = []
        total_direct = direct_seconds
        if self.cfg.objective.mode == "fixed_lift":
            assert self.cfg.objective.target_cl is not None
            assert self.cfg.objective.dcl_dalpha is not None
            for index in range(1, self.cfg.solver.max_cl_corrections + 1):
                error = float(history["cl"]) - self.cfg.objective.target_cl
                if abs(error) <= self.cfg.solver.cl_tolerance:
                    break
                aoa -= error / self.cfg.objective.dcl_dalpha
                bounded = float(np.clip(
                    aoa, self.cfg.constraints.aoa_min_deg, self.cfg.constraints.aoa_max_deg
                ))
                aoa_limited = aoa_limited or bounded != aoa
                aoa = bounded
                next_solution = f"restart_correct_{index}"
                history, seconds = self._direct(
                    work,
                    mesh="mesh_trial.su2",
                    solution=solution,
                    restart=next_solution,
                    history=f"history_correct_{index}",
                    aoa=aoa,
                    iterations=self.cfg.solver.correction_iterations,
                    label=f"direct_correct_{index}",
                )
                total_direct += seconds
                solution = next_solution
                corrections.append({"index": index, "aoa_deg": aoa, "seconds": seconds})
        cd, cl = float(history["cd"]), float(history["cl"])
        objective = self._objective(cd, cl)
        actual_delta = objective - state.objective
        ratio = actual_delta / predicted_delta if predicted_delta < 0.0 else -math.inf
        cl_error = (
            abs(cl - float(self.cfg.objective.target_cl))
            if self.cfg.objective.mode == "fixed_lift"
            else 0.0
        )
        constraint_ok = cl_error <= self.cfg.solver.cl_tolerance
        accepted = bool(
            actual_delta < 0.0
            and ratio >= self.cfg.trust_region.accept_ratio
            and constraint_ok
        )
        trial = DesignState(
            work / "mesh_trial.su2",
            work / f"{solution}.dat",
            aoa,
            cl,
            cd,
            objective,
            state.accepted_steps + (1 if accepted else 0),
        )
        return trial, {
            "accepted": accepted,
            "predicted_delta": predicted_delta,
            "actual_delta": actual_delta,
            "acceptance_ratio": ratio,
            "deform_seconds": deform_seconds,
            "direct_seconds": total_direct,
            "corrections": corrections,
            "density_residual": history.get("density_residual"),
            "cl_error": cl_error,
            "aoa_constraint_active": aoa_limited,
            "constraint_ok": constraint_ok,
        }

    def _next_radius(self, radius: float, ratio: float, accepted: bool) -> float:
        trust = self.cfg.trust_region
        if not accepted or ratio < trust.shrink_ratio:
            return max(trust.minimum_radius, radius * trust.shrink_factor)
        if ratio >= trust.expand_ratio:
            return min(trust.maximum_radius, radius * trust.expand_factor)
        return radius

    def run(self) -> dict[str, Any]:
        self.runner.validate_executables()
        self.cfg.output.mkdir(parents=True, exist_ok=True)
        self._emit(f"输出目录：{self.cfg.output}")
        self._emit(
            f"参数化={self.cfg.parameterization.mode}，目标={self.cfg.objective.mode}，"
            f"计划尝试={self.cfg.steps}"
        )
        state = self._initial_state()
        radius = self.cfg.trust_region.initial_radius
        started = time.perf_counter()
        rows: list[dict[str, Any]] = []
        initial_wall: tuple[np.ndarray, np.ndarray] | None = None
        initial = {
            "mesh": state.mesh,
            "restart": state.restart,
            "aoa_deg": state.aoa_deg,
            "cl": state.cl,
            "cd": state.cd,
            "objective": state.objective,
        }
        for attempt in range(1, self.cfg.steps + 1):
            self._emit(
                f"===== 尝试 {attempt}/{self.cfg.steps}，当前信赖域 {radius:.3e} ====="
            )
            step_started = time.perf_counter()
            step_dir = self.cfg.output / f"step_{attempt:03d}"
            step_dir.mkdir(parents=True, exist_ok=True)
            surface, gradient, lift_gradient, adjoint_seconds, adjoint_convergence = self._gradient(
                state, step_dir
            )
            if initial_wall is None:
                initial_wall = (surface["x"].copy(), surface["y"].copy())
                self._write_airfoil_dat(
                    self.cfg.output / "initial_airfoil.dat",
                    initial_wall[0], initial_wall[1], np.zeros_like(initial_wall[1]),
                    title="SU2_adjoint_initial",
                )
            selection_started = time.perf_counter()
            direction = build_direction(
                surface["x"],
                surface["y"],
                gradient,
                self.cfg.parameterization,
                state.accepted_steps + 1,
            )
            self._emit(
                f"几何方向：{direction.stage}，捕获率={direction.capture_fraction:.4f}，"
                f"条件数={direction.condition:.3e}"
            )
            feasible = False
            geometry: dict[str, float | str] = {}
            trial_radius = radius
            while trial_radius >= self.cfg.trust_region.minimum_radius:
                displacement = trial_radius * direction.values
                feasible, geometry = check_geometry(
                    surface["x"], surface["y"], displacement, self.cfg.constraints
                )
                if feasible:
                    break
                trial_radius *= self.cfg.trust_region.shrink_factor
            selection_seconds = time.perf_counter() - selection_started
            if not feasible:
                raise RuntimeError(
                    "No feasible geometry step above minimum trust radius: "
                    + str(geometry)
                )
            fixed_slope = float(gradient @ direction.values)
            lift_slope = (
                float(lift_gradient @ direction.values) * trial_radius
                if lift_gradient is not None else 0.0
            )
            predicted_delta = fixed_slope * trial_radius
            if predicted_delta >= 0.0:
                raise RuntimeError("Selected direction is not a descent direction")
            trial, result = self._trial(
                state,
                step_dir,
                surface,
                displacement,
                predicted_delta,
                lift_slope,
            )
            accepted = bool(result["accepted"])
            if accepted:
                state = trial
                self._write_airfoil_dat(
                    self.cfg.output / "final_airfoil.dat",
                    surface["x"],
                    surface["y"],
                    displacement,
                )
                assert initial_wall is not None
                self._write_airfoil_comparison(
                    self.cfg.output / "airfoil_comparison.png",
                    initial_wall[0], initial_wall[1],
                    surface["x"], surface["y"] + displacement,
                    initial, trial,
                )
            ratio = float(result["acceptance_ratio"])
            radius = self._next_radius(trial_radius, ratio, accepted)
            row: dict[str, Any] = {
                "attempt": attempt,
                "accepted_step": state.accepted_steps,
                "accepted": accepted,
                "stage": direction.stage,
                "trust_radius": trial_radius,
                "next_radius": radius,
                "cl": trial.cl,
                "cd": trial.cd,
                "objective": trial.objective,
                "predicted_delta": result["predicted_delta"],
                "actual_delta": result["actual_delta"],
                "acceptance_ratio": ratio,
                "capture_fraction": direction.capture_fraction,
                "geometry_condition": direction.condition,
                "adjoint_seconds": adjoint_seconds,
                "adjoint_convergence": adjoint_convergence,
                "selection_seconds": selection_seconds,
                "deform_seconds": result["deform_seconds"],
                "direct_seconds": result["direct_seconds"],
                "attempt_seconds": time.perf_counter() - step_started,
                "geometry": geometry,
                "parameterization": direction.details,
                "corrections": result["corrections"],
                "cl_error": result["cl_error"],
                "aoa_constraint_active": result["aoa_constraint_active"],
                "constraint_ok": result["constraint_ok"],
            }
            rows.append(row)
            self._emit(
                f"{'接受' if accepted else '拒绝'}：CD={trial.cd:.9f}，CL={trial.cl:.9f}，"
                f"实际变化={float(result['actual_delta']):+.6e}，rho={ratio:.3f}"
            )
            (step_dir / "result.json").write_text(
                json.dumps(json_ready(row), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._write_summary(initial, state, rows, time.perf_counter() - started)
        summary = self._write_summary(initial, state, rows, time.perf_counter() - started)
        self._emit(
            f"优化结束：接受 {state.accepted_steps} 步，总耗时 {summary['total_seconds']:.2f} s"
        )
        return summary

    def _write_summary(
        self,
        initial: dict[str, Any],
        state: DesignState,
        rows: list[dict[str, Any]],
        seconds: float,
    ) -> dict[str, Any]:
        payload = {
            "configuration": str(self.cfg.source),
            "parameterization": self.cfg.parameterization.mode,
            "objective_mode": self.cfg.objective.mode,
            "initial": initial,
            "final": {
                "mesh": state.mesh,
                "restart": state.restart,
                "aoa_deg": state.aoa_deg,
                "cl": state.cl,
                "cd": state.cd,
                "objective": state.objective,
                "accepted_steps": state.accepted_steps,
                "airfoil_dat": (
                    self.cfg.output / "final_airfoil.dat"
                    if (self.cfg.output / "final_airfoil.dat").is_file()
                    else None
                ),
                "comparison_plot": (
                    self.cfg.output / "airfoil_comparison.png"
                    if (self.cfg.output / "airfoil_comparison.png").is_file()
                    else None
                ),
            },
            "total_seconds": seconds,
            "attempts": rows,
        }
        ready = json_ready(payload)
        (self.cfg.output / "optimization_summary.json").write_text(
            json.dumps(ready, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        flat_keys = [
            "attempt", "accepted_step", "accepted", "stage", "trust_radius",
            "next_radius", "cl", "cd", "objective", "predicted_delta",
            "actual_delta", "acceptance_ratio", "capture_fraction",
            "geometry_condition", "adjoint_seconds", "selection_seconds",
            "deform_seconds", "direct_seconds", "attempt_seconds",
        ]
        with (self.cfg.output / "optimization_history.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=flat_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return ready
