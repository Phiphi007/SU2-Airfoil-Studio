"""Dependency-free client for AutoFoilCLI.exe (Python 3.9+)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess


class AutoFoilError(RuntimeError):
    def __init__(self, result: dict, returncode: int, logs: str = ""):
        self.result, self.returncode, self.logs = result, returncode, logs
        super().__init__(result.get("error", {}).get("message", f"AutoFoil exited with {returncode}"))


class AutoFoilClient:
    def __init__(self, executable: str | Path | None = None):
        self.executable = Path(executable or Path(__file__).resolve().parents[1] / "AutoFoilCLI.exe").resolve()
        if not self.executable.is_file():
            raise FileNotFoundError(self.executable)

    def _call(self, command: list[str], request: dict | None = None) -> dict:
        completed = subprocess.run(
            [str(self.executable), *command],
            input=json.dumps(request, ensure_ascii=False, allow_nan=False) if request is not None else None,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AutoFoilError({"error": {"message": "EXE returned no valid JSON; check its dependencies and logs."}},
                                completed.returncode, completed.stderr) from exc
        if completed.returncode or not result.get("ok"):
            raise AutoFoilError(result, completed.returncode, completed.stderr)
        return result

    def info(self) -> dict:
        return self._call(["info"])

    def doctor(self) -> dict:
        return self._call(["doctor"])

    def schema(self) -> dict:
        return self._call(["schema"])

    def run(self, airfoil: str = "builtin://naca0012", *, mode: str = "mesh",
            output_dir: str | Path | None = None, parameters: dict | None = None) -> dict:
        request = {"api_version": 1, "mode": mode, "airfoil": str(airfoil), "parameters": parameters or {}}
        if output_dir is not None:
            request["output_dir"] = str(Path(output_dir).resolve())
        if not request["airfoil"].startswith("builtin://"):
            request["airfoil"] = str(Path(airfoil).resolve())
        return self._call(["run", "--request", "-"], request)
