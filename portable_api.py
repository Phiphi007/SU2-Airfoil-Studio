"""Versioned JSON-over-stdio API. Progress goes to stderr; stdout is one JSON object."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import csv
from datetime import datetime
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import uuid

from core_modules.runtime_paths import APP_VERSION, application_root, data_root, resource_root

API_VERSION = 1
VERSION = APP_VERSION
RESERVED = {"help", "airfoil", "output_dir", "mesh_only", "post_only", "show_gmsh"}


class RequestError(ValueError):
    pass


def parameter_actions() -> dict:
    from main_pipeline import build_parser
    return {a.dest: a for a in build_parser()._actions if a.dest not in RESERVED}


def schema() -> dict:
    return {key: {"default": action.default,
                  "type": ("boolean" if isinstance(action.default, bool) else
                           "integer" if action.type is int else
                           "number" if action.type else "string"),
                  "choices": action.choices, "description": action.help}
            for key, action in parameter_actions().items()}


def parse_request(request: dict):
    from main_pipeline import build_parser, validate_args
    if not isinstance(request, dict):
        raise RequestError("Request must be a JSON object.")
    unknown = set(request) - {"api_version", "mode", "airfoil", "output_dir", "parameters"}
    if unknown:
        raise RequestError(f"Unknown request fields: {sorted(unknown)}")
    version = request.get("api_version", API_VERSION)
    if type(version) is not int or version != API_VERSION:
        raise RequestError("Only api_version=1 is supported.")
    mode = request.get("mode", "mesh")
    if mode not in ("mesh", "solve", "report"):
        raise RequestError("mode must be mesh, solve or report.")
    airfoil = request.get("airfoil", "builtin://naca0012")
    if not isinstance(airfoil, str) or not airfoil.strip():
        raise RequestError("airfoil must be a non-empty file path or builtin://nacaNNNN.")
    if mode != "report" and not airfoil.startswith("builtin://") and not Path(airfoil).is_file():
        raise RequestError(f"Airfoil file not found: {airfoil}")
    output = request.get("output_dir")
    if output is not None and (not isinstance(output, str) or not output.strip()):
        raise RequestError("output_dir must be a non-empty path string.")
    if mode == "report" and output is None:
        raise RequestError("report mode requires an existing output_dir.")
    if output is None:
        name = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        output = str(data_root() / "api_cases" / name)
    output_path = Path(output).expanduser().resolve()
    if mode == "report":
        for name in ("history.csv", "surface_flow.csv"):
            if not (output_path / name).is_file():
                raise RequestError(f"report mode requires {output_path / name}")
    elif output_path.exists():
        raise RequestError("output_dir already exists; use a new directory to avoid overwriting results.")
    params = request.get("parameters", {})
    if not isinstance(params, dict):
        raise RequestError("parameters must be a JSON object.")
    actions = parameter_actions()
    unknown = set(params) - actions.keys()
    if unknown:
        raise RequestError(f"Unknown parameters: {sorted(unknown)}")
    args = build_parser().parse_args([])
    for key, value in params.items():
        action = actions[key]
        if isinstance(action.default, bool):
            valid = type(value) is bool
        elif action.type is int:
            valid = type(value) is int
        elif action.type:
            valid = type(value) in (int, float) and math.isfinite(value)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise RequestError(f"Invalid type or non-finite value for parameter {key}.")
        try:
            converted = action.type(str(value)) if action.type else value
        except (ValueError, argparse.ArgumentTypeError) as exc:
            raise RequestError(f"{key}: {exc}") from exc
        if action.choices and converted not in action.choices:
            raise RequestError(f"{key} must be one of {list(action.choices)}.")
        setattr(args, key, converted)
    args.airfoil, args.output_dir = airfoil, str(output_path)
    args.mesh_only, args.post_only = mode == "mesh", mode == "report"
    try:
        validate_args(args)
    except ValueError as exc:
        raise RequestError(str(exc)) from exc
    return args, mode, output_path


def read_last_values(output: Path) -> dict:
    path = output / "history.csv"
    if not path.is_file():
        return {}
    values = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, skipinitialspace=True):
            candidate = {}
            for key, value in row.items():
                if key is None:
                    continue
                try:
                    number = float(value)
                except (ValueError, TypeError):
                    continue
                if math.isfinite(number):
                    candidate[key.strip().strip('"')] = number
            if candidate:
                values = candidate
    return values


def result_files(output: Path) -> dict:
    return {p.relative_to(output).as_posix(): str(p.resolve())
            for p in sorted(output.rglob("*")) if p.is_file() and not p.name.startswith(".")}


def execute(request: dict) -> tuple[dict, int]:
    if isinstance(request, dict) and request.get("mode") == "optimize":
        return execute_optimization(request)
    from main_pipeline import run_pipeline
    from core_modules.process_control import ProcessController
    from core_modules.solver_control import SolverControlMonitor
    from core_modules.su2_driver import CalculationCancelled
    args, mode, output = parse_request(request)
    if mode != "report":
        # The exclusive creation also protects simultaneous API calls using the same path.
        try:
            output.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise RequestError("output_dir was created by another request; choose a new directory.") from exc
        (output / "case_request.json").write_text(
            json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    response = {"api_version": API_VERSION, "version": VERSION, "mode": mode,
                "output_dir": str(output), "ok": True, "status": "completed"}
    exit_code = 0
    controller = ProcessController()
    monitor = SolverControlMonitor(output, controller) if mode == "solve" else None
    if monitor:
        monitor.start()
    with (output / "api_run.log").open("a", encoding="utf-8") as log:
        class Progress:
            def write(self, message):
                log.write(message)
                log.flush()
                sys.stderr.write(message)
                sys.stderr.flush()
                return len(message)

            def flush(self):
                log.flush()
                sys.stderr.flush()

        try:
            with redirect_stdout(Progress()):
                report = run_pipeline(args, process_control=controller)
                mesh_data = output / "mesh_preview.npz"
                if mesh_data.is_file():
                    try:
                        from core_modules.view_data import write_mesh_view
                        write_mesh_view(mesh_data, output / "mesh_view.bin")
                    except Exception as render_error:
                        print(f"Mesh view unavailable: {render_error}")
                flow = output / "flow.vtu"
                if mode == "solve" and flow.is_file():
                    try:
                        import numpy as np
                        from core_modules.airfoil_processor import process_airfoil
                        from core_modules.view_data import write_flow_view
                        airfoil_geometry = process_airfoil(args.airfoil, surface_point_count=args.surface_points)
                        airfoil_points = np.column_stack((airfoil_geometry.x, airfoil_geometry.y))
                        write_flow_view(flow, airfoil_points, output / "flow_view.bin")
                    except Exception as render_error:
                        print(f"Flow view unavailable: {render_error}")
            response["report"] = str(report) if report else None
        except CalculationCancelled:
            response["status"] = (
                "stopped_after_save" if controller.stop_mode == "after_save" else "stopped"
            )
            response["stop_mode"] = controller.stop_mode or "immediate"
        except Exception as exc:
            response.update(ok=False, status="failed", error={"type": type(exc).__name__, "message": str(exc)})
            exit_code = 1
        finally:
            if monitor:
                monitor.close()
    values = read_last_values(output)
    response["last_values"] = values
    residual = next((values[k] for k in ("rms[Rho]", "RMS_Density", "RMS_Rho", "Res_Density") if k in values), None)
    # A successful process exit is not evidence of aerodynamic convergence.
    response["residual_target_met"] = residual <= args.residual_min if residual is not None and mode == "solve" else None
    response["convergence_note"] = "Process completion is not CFD validation; check residuals, forces, Y+ and mesh independence."
    response["files"] = result_files(output)
    result_path = output / "api_result.json"
    response["files"][result_path.name] = str(result_path)
    result_path.write_text(json.dumps(response, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return response, exit_code


def execute_optimization(request: dict) -> tuple[dict, int]:
    """Run a validated direct case through the discrete-adjoint backend."""
    from parametric_adjoint.bridge import prepare_case_config
    from parametric_adjoint.config import load_config
    from parametric_adjoint.optimizer import AdjointOptimizer
    from core_modules.su2_driver import _resolve_executable

    allowed = {"api_version", "mode", "case_dir", "output_dir", "method", "steps"}
    if set(request) - allowed:
        raise RequestError(f"Unknown optimization fields: {sorted(set(request)-allowed)}")
    if request.get("api_version", API_VERSION) != API_VERSION:
        raise RequestError("Only api_version=1 is supported.")
    method = request.get("method", "cst")
    if method not in ("cst", "bce", "hybrid", "relay"):
        raise RequestError("method must be cst, bce, hybrid, or relay.")
    steps = request.get("steps", 3)
    if type(steps) is not int or not 1 <= steps <= 100:
        raise RequestError("steps must be an integer from 1 to 100.")
    case_value, output_value = request.get("case_dir"), request.get("output_dir")
    if not isinstance(case_value, str) or not isinstance(output_value, str) or not case_value or not output_value:
        raise RequestError("case_dir and output_dir must be non-empty paths.")
    case_dir = Path(case_value).expanduser().resolve()
    output = Path(output_value).expanduser().resolve()
    result_file = case_dir / "api_result.json"
    if not result_file.is_file():
        raise RequestError("Optimization requires a completed API CFD case.")
    baseline = json.loads(result_file.read_text(encoding="utf-8"))
    if baseline.get("mode") != "solve" or baseline.get("ok") is not True:
        raise RequestError("Optimization requires a successful direct CFD case.")
    if baseline.get("residual_target_met") is not True:
        raise RequestError("The direct CFD case has not met its residual target. Converge it before optimization.")
    if output.exists():
        raise RequestError("output_dir already exists; choose a new optimization directory.")
    su2_bin = Path(_resolve_executable("SU2_CFD")).parent
    output.mkdir(parents=True)
    response = {"api_version": API_VERSION, "version": VERSION, "mode": "optimize",
                "output_dir": str(output), "ok": True, "status": "completed"}
    (output / "case_request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        config_file = prepare_case_config(case_dir=case_dir, su2_bin=su2_bin,
                                          output_config=output / "optimization_config.json",
                                          runtime_bin=None, mode=method, objective_mode="fixed_aoa",
                                          target_cl=None, dcl_dalpha=None, dcd_dcl=None)
        config_payload = json.loads(config_file.read_text(encoding="utf-8"))
        config_payload["steps"] = steps
        config_payload["output"] = str(output)
        config_file.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with (output / "optimization.log").open("w", encoding="utf-8") as log:
            def progress(message: str) -> None:
                line = f"[Progress] {message}\n"
                log.write(line)
                log.flush()
                sys.stderr.write(line)
                sys.stderr.flush()
            optimizer = AdjointOptimizer(load_config(config_file), progress=progress)
            response["study"] = optimizer.run()
    except Exception as exc:
        response.update(ok=False, status="failed", error={"type": type(exc).__name__, "message": str(exc)})
    response["files"] = result_files(output)
    response_path = output / "api_result.json"
    response["files"][response_path.name] = str(response_path)
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return response, 0 if response["ok"] else 1


def info() -> dict:
    from core_modules.su2_driver import _resolve_executable
    try:
        solver = _resolve_executable("SU2_CFD")
    except FileNotFoundError:
        solver = None
    try:
        import gmsh
        gmsh_version = gmsh.__version__
    except (ImportError, OSError):
        gmsh_version = None
    adjoint = {}
    if solver:
        solver_dir = Path(solver).parent
        suffix = ".exe" if os.name == "nt" else ""
        adjoint = {name: str(solver_dir / f"{name}{suffix}") if (solver_dir / f"{name}{suffix}").is_file() else None
                   for name in ("SU2_CFD_AD", "SU2_DOT_AD", "SU2_DEF")}
    return {"api_version": API_VERSION, "version": VERSION, "ok": True,
            "frozen": bool(getattr(sys, "frozen", False)), "platform": sys.platform,
            "application_dir": str(application_root()), "resources_dir": str(resource_root()),
            "default_data_dir": str(data_root()), "su2_executable": solver,
            "gmsh_version": gmsh_version, "adjoint_executables": adjoint,
            "modes": ["mesh", "solve", "report", "optimize"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SU2 AutoFoil JSON API v1; logs on stderr, JSON on stdout.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="Paths and solver discovery (JSON).")
    sub.add_parser("schema", help="Parameter names, types and defaults (JSON).")
    sub.add_parser("doctor", help="Check the bundled GUI, Gmsh library and SU2 executable (JSON).")
    run = sub.add_parser("run", help="Run a JSON request; --request - reads UTF-8 JSON on stdin.")
    run.add_argument("--request", default="-", help="UTF-8 JSON file or - for stdin.")
    args = parser.parse_args(argv)
    code = 0
    try:
        if args.command == "info":
            result = info()
        elif args.command == "schema":
            result = {"ok": True, "api_version": API_VERSION, "parameters": schema()}
        elif args.command == "doctor":
            result = info()
            with redirect_stdout(sys.stderr):
                import gmsh
                os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
                from PySide6.QtWidgets import QApplication
                from qt_app.main_window import MainWindow
                from qt_app.theme import apply_industrial_theme
                app = QApplication.instance() or QApplication([])
                apply_industrial_theme(app)
                window = MainWindow()
                try:
                    window.show()
                    app.processEvents()
                    if (
                        window.tabs.count() != 5
                        or window.mesh_viewer is window.result_viewer
                        or window.result_display_tabs.indexOf(window.result_viewer) != 0
                        or len(window.solver_monitor.lines) != 3
                    ):
                        raise RuntimeError("Qt workspace initialization failed.")
                finally:
                    window.close()
                    app.processEvents()
            if not result["su2_executable"]:
                raise FileNotFoundError("SU2 executable not found.")
            check = subprocess.run([result["su2_executable"], "--help"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=20,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if check.returncode:
                raise RuntimeError(f"SU2 dependency check failed: exit {check.returncode}")
            result.update(gui="qt-passed", gmsh=gmsh.__version__, su2=check.stdout.splitlines()[0])
        else:
            payload = sys.stdin.read() if args.request == "-" else Path(args.request).read_text(encoding="utf-8-sig")
            request = json.loads(payload)
            result, code = execute(request)
    except (RequestError, json.JSONDecodeError) as exc:
        result, code = {"ok": False, "api_version": API_VERSION, "error": {"type": "InvalidRequest", "message": str(exc)}}, 2
    except Exception as exc:
        result, code = {"ok": False, "api_version": API_VERSION, "error": {"type": type(exc).__name__, "message": str(exc)}}, 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
