"""Read flushed SU2 history independently of buffered console output."""
import csv
import math
from collections import deque
from pathlib import Path


def assess_convergence(path: Path, target: float, window: int = 200, *, all_residuals=False) -> dict:
    """Evaluate the final residual and a contiguous force-stability window.

    A residual target is an end-state threshold, not a requirement that every
    sample in the preceding force window already be below that threshold.
    Requiring the latter adds up to ``window`` unnecessary iterations after a
    monotone residual first reaches its target and disagrees with SU2's native
    stopping semantics.  CL/CD still use the full window so an oscillatory
    force history cannot be reported as converged from one fortunate sample.
    """
    samples = deque(maxlen=window)
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, skipinitialspace=True)
            for row in reader:
                fields = {key.strip().strip('"'): value for key, value in row.items() if key}
                try:
                    step = int(fields["Inner_Iter"])
                    values = {key: float(fields[key]) for key in ("rms[Rho]", "CL", "CD")}
                    residuals = {key: float(value) for key, value in fields.items()
                                 if key.startswith("rms[")}
                    if not all(math.isfinite(value) for value in (*values.values(), *residuals.values())):
                        samples.clear()
                        continue
                except (TypeError, ValueError, KeyError):
                    samples.clear()
                    continue
                if samples and step != samples[-1][0] + 1:
                    samples.clear()
                samples.append((step, values, residuals))
    except (OSError, UnicodeError, csv.Error):
        samples.clear()
    result = {"window": window, "samples": len(samples), "target": target,
              "cl_tolerance": 1e-4, "cd_tolerance": 1e-5, "passed": False}
    if not samples:
        return result
    for name in ("CL", "CD"):
        coefficients = [values[name] for _, values, _ in samples]
        result[name.lower() + "_range"] = max(coefficients) - min(coefficients)
    result["residual_max"] = {name: max(residuals[name] for _, _, residuals in samples)
                              for name in samples[-1][2]
                              if all(name in residuals for _, _, residuals in samples)}
    result["residual_final"] = dict(samples[-1][2])
    checked = (result["residual_final"].values() if all_residuals
               else (result["residual_final"]["rms[Rho]"],))
    result["all_residuals_checked"] = all_residuals
    result["passed"] = (len(samples) == window
                        and max(checked) <= target
                        and result["cl_range"] <= result["cl_tolerance"]
                        and result["cd_range"] <= result["cd_tolerance"])
    return result


def read_history_points(path: Path, after_iteration: int = -1):
    """Return complete finite rows from the recent history tail in file order."""
    try:
        with path.open('rb') as stream:
            header = stream.readline().decode('utf-8-sig')
            start = stream.tell()
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(start, size - 131072))
            if stream.tell() > start:
                stream.readline()  # discard a possibly partial first tail row
            content = stream.read()
        # SU2 can be in the middle of writing the last row.
        if content and not content.endswith(b'\n'):
            content = content[:content.rfind(b'\n')+1]
        reader = csv.DictReader([header] + content.decode('utf-8').splitlines(),
                                skipinitialspace=True)
        points = []
        for row in reader:
            normalized = {key.strip().strip('"'): value for key, value in row.items() if key}
            try:
                point = tuple(float(normalized[key]) for key in ('Inner_Iter', 'rms[Rho]', 'CL', 'CD'))
                if all(math.isfinite(value) for value in point) and point[0] > after_iteration:
                    points.append((int(point[0]), *point[1:]))
            except (KeyError, ValueError, TypeError):
                continue
        return points
    except (OSError, UnicodeError, csv.Error):
        return []
