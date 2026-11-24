"""生成 SU2 配置并以子进程运行 SU2_CFD。"""

from __future__ import annotations

import re
import os
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Event
from typing import Callable, Mapping

from core_modules.process_control import ProcessController


DEFAULT_PARAMETERS: dict[str, float | int | str] = {
    "SOLVER": "RANS",
    "TURBULENCE_MODEL": "SA",
    "TURBULENCE_OPTIONS": "SA_OPTIONS= NEGATIVE, EXPERIMENTAL",
    "INIT_OPTION": "REYNOLDS",
    "MACH": 0.15,
    "AOA": 2.0,
    "PRESSURE": 101325.0,
    "REYNOLDS": 3.0e6,
    "REYNOLDS_LENGTH": 1.0,
    "REFERENCE_AREA": 1.0,
    "REFERENCE_ORIGIN_X": 0.25,
    "REFERENCE_SCALING": "DIMENSIONAL",
    "ADDITIONAL_NUMERICS": "",
    "CONVERGENCE_FIELDS": "( RMS_DENSITY, LIFT, DRAG )",
    "CAUCHY_EPS": 1e-6,
    "TEMPERATURE": 288.15,
    "DENSITY": 1.225,
    "ITERATIONS": 1000,
    "AIRFOIL_BOUNDARY": "MARKER_HEATFLUX= ( airfoil, 0.0 )",
    "FARFIELD_BOUNDARY": "MARKER_FAR= ( farfield_inlet, farfield_outlet )",
    "CFL_NUMBER": 20.0,
    "CFL_ADAPT": "NO",
    "CFL_ADAPT_PARAM": "( 0.1, 2.0, 1.0, 100.0 )",
    "LINEAR_SOLVER": "FGMRES",
    "LINEAR_SOLVER_ERROR": 1.0e-8,
    "LINEAR_SOLVER_ITER": 20,
    "FLOW_SCHEME": "ROE",
    "RECONSTRUCTION_GRADIENT": "LEAST_SQUARES",
    "MUSCL_FLOW": "YES",
    "MUSCL_TURB": "YES",
    "SLOPE_LIMITER": "VENKATAKRISHNAN",
    "LIMITER_COEFF": 0.05,
    "LIMITER_ITER": 999999,
    "RESIDUAL_MIN": -8.0,
    "SCREEN_OUTPUT": "( INNER_ITER, RMS_DENSITY, LIFT, DRAG )",
}


class CalculationCancelled(RuntimeError):
    """用户从界面主动取消 SU2 计算。"""


def _format_value(value: float | int | str) -> str:
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def generate_config(
    parameters: Mapping[str, float | int | str] | None = None,
    template_path: str | Path = "config_template.cfg",
    output_dir: str | Path = "output_results",
) -> Path:
    """用字符串替换模板占位符并生成 ``output_dir/run.cfg``。

    模板中的 ``{{KEY}}`` 占位符全部被参数替换；任何未赋值的占位符都会
    触发 ``KeyError``，避免把残缺配置交给 SU2。
    """
    template = Path(template_path).expanduser().resolve()
    if not template.is_file():
        raise FileNotFoundError(f"找不到 SU2 配置模板: {template}")

    merged = DEFAULT_PARAMETERS.copy()
    if parameters:
        merged.update({str(key).upper(): value for key, value in parameters.items()})
    # Centered schemes do not use MUSCL reconstruction and SU2 rejects a
    # separately allocated reconstruction gradient for them.
    if str(merged["FLOW_SCHEME"]).upper() in {"JST", "JST_KE", "JST_MAT", "LAX-FRIEDRICH"}:
        merged["RECONSTRUCTION_GRADIENT"] = "NONE"

    config_text = template.read_text(encoding="utf-8")
    for key, value in merged.items():
        config_text = config_text.replace("{{" + key + "}}", _format_value(value))

    unresolved = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", config_text)))
    if unresolved:
        raise KeyError(f"配置模板仍有未赋值占位符: {', '.join(unresolved)}")
    if merged.get("IMPORTED_BOUNDARY_CONFIG"):
        config_text = '\n'.join(line for line in config_text.splitlines()
                                if not line.lstrip().startswith(("MARKER_", "INLET_TYPE=")))
        config_text += '\n% Imported mesh boundary assignments\n' + str(merged["IMPORTED_BOUNDARY_CONFIG"]) + '\n'

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    run_config = output / "run.cfg"
    run_config.write_text(config_text, encoding="utf-8", newline="\n")
    return run_config


def _resolve_executable(executable: str) -> str:
    from .runtime_paths import application_root
    if executable in {"SU2_CFD", "SU2_CFD.exe"}:
        override = os.environ.get("SU2AUTOFOIL_SU2_EXECUTABLE")
        if override:
            candidate = Path(override).expanduser().resolve()
            if not candidate.is_file():
                raise FileNotFoundError(f"SU2AUTOFOIL_SU2_EXECUTABLE does not exist: {candidate}")
            return str(candidate)
        root = application_root()
        # A frozen backend can live below ``runtime/backend`` while the solver
        # bundle remains at the desktop application's root.  Search both that
        # layout and source/developer layouts on Windows and POSIX platforms.
        search_roots = [root]
        if getattr(sys, "frozen", False):
            # Support both <app>/runtime/backend and one-file/folder layouts
            # without assuming a single fixed nesting depth.
            search_roots.extend(list(root.parents[:3]))
        candidates = tuple(
            candidate
            for search_root in search_roots
            for candidate in (
                search_root / "solvers" / "SU2" / "bin" / "SU2_CFD",
                search_root / "solvers" / "SU2" / "bin" / "SU2_CFD.exe",
                search_root / "third_party" / "su2" / "bin" / "SU2_CFD",
                search_root / "third_party" / "su2" / "bin" / "SU2_CFD.exe",
                search_root / "third_party" / "su2" / "build" / "bin" / "SU2_CFD",
                search_root / "third_party" / "su2" / "build" / "bin" / "SU2_CFD.exe",
            )
        )
        for bundled in candidates:
            if bundled.is_file():
                return str(bundled)
    resolved = shutil.which(executable)
    if resolved is None and Path(executable).is_file():
        resolved = str(Path(executable).expanduser().resolve())
    if resolved is None:
        raise FileNotFoundError(
            f"找不到 {executable}。请确认 SU2 的 bin 目录已加入 PATH。"
        )
    return resolved


def run_cfd(
    parameters: Mapping[str, float | int | str] | None = None,
    template_path: str | Path = "config_template.cfg",
    output_dir: str | Path = "output_results",
    executable: str = "SU2_CFD",
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    """生成配置后，在输出目录中同步运行 SU2_CFD。"""
    output = Path(output_dir).expanduser().resolve()
    run_config = generate_config(parameters, template_path, output)
    mesh_path = output / "mesh.su2"
    if not dry_run and not mesh_path.is_file():
        raise FileNotFoundError(f"运行 SU2 前缺少网格文件: {mesh_path}")
    resolved_executable = _resolve_executable(executable)

    command = [resolved_executable]
    if dry_run:
        command.append("-d")
    command.append("run.cfg")
    try:
        # cwd 固定为输出目录，所有 SU2 中间文件都会留在该目录。
        return subprocess.run(command, cwd=output, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"SU2_CFD 运行失败（退出码 {exc.returncode}），配置文件为 {run_config}。"
        ) from exc


def run_cfd_streaming(
    parameters: Mapping[str, float | int | str] | None = None,
    template_path: str | Path = "config_template.cfg",
    output_dir: str | Path = "output_results",
    executable: str = "SU2_CFD",
    threads: int = 1,
    log_callback: Callable[[str], None] | None = None,
    stop_event: Event | None = None,
    process_control: ProcessController | None = None,
) -> int:
    """流式运行 SU2，供 GUI 实时显示日志并响应暂停、继续和终止。"""
    output = Path(output_dir).expanduser().resolve()
    run_config = generate_config(parameters, template_path, output)
    mesh_path = output / "mesh.su2"
    if not mesh_path.is_file():
        raise FileNotFoundError(f"运行 SU2 前缺少网格文件: {mesh_path}")
    if threads < 1:
        raise ValueError("SU2 OpenMP 线程数至少为 1。")
    resolved_executable = _resolve_executable(executable)

    command = [resolved_executable]
    if threads > 1:
        command.extend(("-t", str(threads)))
    command.append("run.cfg")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        cwd=output,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creation_flags,
    )
    if process_control:
        process_control.attach(process)
    try:
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            if log_callback:
                log_callback(line.rstrip("\r\n"))
            if stop_event and stop_event.is_set():
                if process_control:
                    process_control.terminate()
                elif process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise CalculationCancelled("计算已由用户取消。")
        return_code = process.wait()
    finally:
        if process_control:
            process_control.detach(process)
        if process.stdout:
            process.stdout.close()

    if (stop_event and stop_event.is_set()) or (
        process_control and process_control.termination_requested
    ):
        raise CalculationCancelled("计算已由用户终止。")
    if return_code != 0:
        raise RuntimeError(
            f"SU2_CFD 运行失败（退出码 {return_code}），配置文件为 {run_config}。"
        )
    return return_code
