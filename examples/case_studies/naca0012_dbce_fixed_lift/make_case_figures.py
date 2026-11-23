"""Regenerate the published figures for the NACA0012 D-BCE case study."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent


def history(name: str) -> dict[str, np.ndarray]:
    with (ROOT / name).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = [item.strip().strip('"') for item in next(reader)]
        rows = [dict(zip(header, values)) for values in reader]
    def values(key: str) -> np.ndarray:
        return np.asarray([float(row[key]) for row in rows], dtype=float)
    return {
        "iteration": values("Inner_Iter"),
        "residual": values("rms[Rho]"),
        "cd": values("CD"),
        "cl": values("CL"),
    }


def main() -> None:
    baseline = history("history_baseline.csv")
    optimized = history("history_optimized.csv")
    colors = {"baseline": "#7b8794", "optimized": "#087f6d"}
    fig, axes = plt.subplots(3, 1, figsize=(10.4, 8.2), dpi=150, sharex=True)
    for key, label in (("baseline", "Baseline"), ("optimized", "Optimized")):
        data = baseline if key == "baseline" else optimized
        axes[0].plot(data["iteration"], data["residual"], color=colors[key], label=label)
        axes[1].plot(data["iteration"], data["cd"], color=colors[key], label=label)
        axes[2].plot(data["iteration"], data["cl"], color=colors[key], label=label)
    axes[0].set_ylabel("log10 RMS density")
    axes[1].set_ylabel("CD")
    axes[2].set_ylabel("CL")
    axes[2].set_xlabel("Inner iteration")
    axes[0].legend(frameon=False, ncol=2)
    for axis in axes:
        axis.grid(True, linestyle=":", linewidth=0.6, alpha=0.65)
    fig.suptitle("NACA0012: converged fixed-lift SU2 comparison before / after D-BCE")
    fig.tight_layout()
    fig.savefig(ROOT / "convergence_comparison.png", bbox_inches="tight")

    b_cd, f_cd = baseline["cd"][-1], optimized["cd"][-1]
    b_cl, f_cl = baseline["cl"][-1], optimized["cl"][-1]
    changes = [100.0 * (b_cd - f_cd) / b_cd, 100.0 * ((f_cl / f_cd) / (b_cl / b_cd) - 1.0)]
    fig, axis = plt.subplots(figsize=(7.2, 4.4), dpi=150)
    bars = axis.bar(["CD reduction", "L/D gain"], changes, color=["#007acc", "#087f6d"], width=0.55)
    axis.axhline(0.0, color="#66717b", linewidth=0.8)
    axis.set_ylabel("Improvement (%)")
    axis.set_title("Measured fixed-lift change at Mach 0.15, Re 3e6")
    axis.grid(True, axis="y", linestyle=":", linewidth=0.6, alpha=0.65)
    for bar, value in zip(bars, changes):
        axis.text(bar.get_x() + bar.get_width() / 2, value + 0.08, f"{value:.3f}%", ha="center", weight="bold")
    fig.tight_layout()
    fig.savefig(ROOT / "performance_comparison.png", bbox_inches="tight")


if __name__ == "__main__":
    main()
