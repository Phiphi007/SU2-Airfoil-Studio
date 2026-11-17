"""Tkinter front end for one-click CST/BCE SU2 optimization."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .bridge import prepare_case_config
from .config import load_config
from .su2 import SU2Runner


METHODS = {
    "CST 全局优化": "cst",
    "BCE 局部笔刷": "bce",
    "CST + BCE 混合": "hybrid",
    "CST → BCE 接力（推荐）": "relay",
}
SHAPES = {"弯度": "camber", "厚度": "thickness", "弯度 + 厚度": "both"}
OBJECTIVES = {"固定迎角最小阻力": "fixed_aoa", "固定升力最小阻力": "fixed_lift"}


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def detect_solver_bin() -> Path | None:
    candidates: list[Path] = []
    override = os.environ.get("SU2_PARAMETRIC_BIN")
    if override:
        candidates.append(Path(override))
    root = application_root()
    candidates.extend((
        root / "solvers" / "SU2" / "bin",
        root.parent / "solvers" / "SU2" / "bin",
        Path("E:/MyUniversity/BrainStorm/BrushAirfoil/third_party/SU2-8.5.0-ad/install_ad_mingw/bin"),
    ))
    required = ("SU2_CFD.exe", "SU2_CFD_AD.exe", "SU2_DOT_AD.exe", "SU2_DEF.exe")
    return next((path.resolve() for path in candidates if all((path / name).is_file() for name in required)), None)


def detect_runtime_bin(solver_bin: Path) -> Path | None:
    dlls = ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll")
    if all((solver_bin / name).is_file() for name in dlls):
        return solver_bin
    candidates = (
        Path("E:/MyUniversity/BrainStorm/BrushAirfoil/third_party/msys2-portable/msys64/ucrt64/bin"),
        solver_bin.parent / "runtime",
    )
    return next((path.resolve() for path in candidates if all((path / name).is_file() for name in dlls)), None)


class OptimizerPanel(ttk.Frame):
    """Embeddable optimizer workspace used by both standalone and integrated GUIs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        current_case_provider: Callable[[], Path | None] | None = None,
    ) -> None:
        super().__init__(master)
        self.current_case_provider = current_case_provider
        self.process: subprocess.Popen[str] | None = None
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.last_output: Path | None = None
        self._variables()
        self._layout()
        self._objective_changed()
        self.after(100, self._drain_messages)

    def _variables(self) -> None:
        detected = detect_solver_bin()
        self.case_var = tk.StringVar()
        self.su2_var = tk.StringVar(value=str(detected) if detected else "")
        self.method_var = tk.StringVar(value="CST → BCE 接力（推荐）")
        self.shape_var = tk.StringVar(value="弯度")
        self.objective_var = tk.StringVar(value="固定迎角最小阻力")
        self.steps_var = tk.StringVar(value="6")
        self.cst_var = tk.StringVar(value="16")
        self.bce_var = tk.StringVar(value="8")
        self.relay_var = tk.StringVar(value="3")
        self.target_cl_var = tk.StringVar(value="0.37")
        self.dcl_dalpha_var = tk.StringVar(value="0.22")
        self.dcd_dcl_var = tk.StringVar(value="0.036")
        self.mach_var = tk.StringVar(value="0.15")
        self.reynolds_var = tk.StringVar(value="3000000")
        self.aoa_var = tk.StringVar(value="2.0")
        self.aoa_min_var = tk.StringVar(value="-10.0")
        self.aoa_max_var = tk.StringVar(value="15.0")
        self.min_thickness_var = tk.StringVar(value="0.002")
        self.max_displacement_var = tk.StringVar(value="0.004")
        self.adjoint_iterations_var = tk.StringVar(value="800")
        self.adjoint_cfl_var = tk.StringVar(value="50")
        self.status_var = tk.StringVar(value="请选择算例目录，然后检测环境。")

    def _layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        title = ttk.Frame(self, padding=(16, 12, 16, 6))
        title.grid(row=0, column=0, sticky="ew")
        ttk.Label(title, text="SU2 多参数化伴随优化器", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ttk.Label(
            title,
            text="复用 SU2WorkFlow 结构化网格；支持 CST、紧支撑 BCE、混合与接力优化",
        ).pack(anchor="w", pady=(3, 0))

        settings = ttk.Frame(self, padding=(16, 6))
        settings.grid(row=1, column=0, sticky="ew")
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)
        case_box = ttk.LabelFrame(settings, text="1. 算例与求解器", padding=10)
        case_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        option_box = ttk.LabelFrame(settings, text="2. 优化设置", padding=10)
        option_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._path_row(case_box, 0, "算例目录", self.case_var, self._browse_case)
        self._path_row(case_box, 1, "SU2 bin", self.su2_var, self._browse_su2)
        ttk.Label(
            case_box,
            text="算例目录需包含 mesh.su2、run.cfg 和 restart_flow.dat",
            foreground="#9A9A9A",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        if self.current_case_provider is not None:
            ttk.Button(
                case_box,
                text="使用当前正问题算例",
                command=self.use_current_case,
            ).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        self._combo_row(option_box, 0, "参数化", self.method_var, tuple(METHODS))
        self._combo_row(option_box, 1, "形变类型", self.shape_var, tuple(SHAPES))
        self._combo_row(
            option_box, 2, "目标", self.objective_var, tuple(OBJECTIVES), self._objective_changed
        )
        numeric = ttk.Frame(option_box)
        numeric.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        for col in range(4):
            numeric.columnconfigure(col, weight=1)
        self._small_field(numeric, 0, "尝试步数", self.steps_var)
        self._small_field(numeric, 1, "CST 变量", self.cst_var)
        self._small_field(numeric, 2, "BCE 变量", self.bce_var)
        self._small_field(numeric, 3, "接力换挡步", self.relay_var)

        self.fixed_lift_frame = ttk.Frame(option_box)
        self.fixed_lift_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        for col in range(3):
            self.fixed_lift_frame.columnconfigure(col, weight=1)
        self._small_field(self.fixed_lift_frame, 0, "目标 CL", self.target_cl_var)
        self._small_field(self.fixed_lift_frame, 1, "dCL/dα（每度）", self.dcl_dalpha_var)
        self._small_field(self.fixed_lift_frame, 2, "dCD/dCL", self.dcd_dcl_var)

        conditions = ttk.Frame(option_box)
        conditions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        for col in range(4):
            conditions.columnconfigure(col, weight=1)
        self._small_field(conditions, 0, "Mach", self.mach_var)
        self._small_field(conditions, 1, "Reynolds", self.reynolds_var)
        self._small_field(conditions, 2, "初始 AoA / °", self.aoa_var)
        self._small_field(conditions, 3, "伴随迭代", self.adjoint_iterations_var)

        constraints = ttk.Frame(option_box)
        constraints.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        for col in range(4):
            constraints.columnconfigure(col, weight=1)
        self._small_field(constraints, 0, "AoA 下限 / °", self.aoa_min_var)
        self._small_field(constraints, 1, "AoA 上限 / °", self.aoa_max_var)
        self._small_field(constraints, 2, "最小厚度 / c", self.min_thickness_var)
        self._small_field(constraints, 3, "最大位移 / c", self.max_displacement_var)

        console_box = ttk.LabelFrame(self, text="运行日志", padding=8)
        console_box.grid(row=2, column=0, sticky="nsew", padx=16, pady=(4, 6))
        console_box.columnconfigure(0, weight=1)
        console_box.rowconfigure(0, weight=1)
        self.console = tk.Text(
            console_box, wrap="word", state="disabled", bg="#151515", fg="#D4D4D4",
            insertbackground="white", selectbackground="#094771", font=("Consolas", 9),
            padx=4, pady=3, relief="solid", borderwidth=1,
        )
        scroll = ttk.Scrollbar(console_box, orient="vertical", command=self.console.yview)
        self.console.configure(yscrollcommand=scroll.set)
        self.console.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        actions = ttk.Frame(self, padding=(16, 4, 16, 14))
        actions.grid(row=3, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.check_button = ttk.Button(actions, text="检测环境", command=self.check_environment)
        self.check_button.grid(row=0, column=1, padx=4)
        self.start_button = ttk.Button(actions, text="开始优化", command=self.start_optimization)
        self.start_button.grid(row=0, column=2, padx=4)
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop_optimization, state="disabled")
        self.stop_button.grid(row=0, column=3, padx=4)
        self.open_button = ttk.Button(actions, text="打开结果", command=self.open_results, state="disabled")
        self.open_button.grid(row=0, column=4, padx=(4, 0))
        self.run_progress = ttk.Progressbar(actions, mode="indeterminate", length=260)
        self.run_progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0), padx=(0, 8))
        self.compare_button = ttk.Button(
            actions, text="查看前后对比", command=self.open_comparison, state="disabled"
        )
        self.compare_button.grid(row=1, column=2, padx=4, pady=(7, 0))
        self.export_button = ttk.Button(
            actions, text="导出最终 DAT", command=self.export_airfoil, state="disabled"
        )
        self.export_button.grid(row=1, column=3, padx=4, pady=(7, 0))
        self.discard_button = ttk.Button(
            actions, text="丢弃候选翼型", command=self.discard_airfoil, state="disabled"
        )
        self.discard_button.grid(row=1, column=4, padx=(4, 0), pady=(7, 0))

    def _path_row(
        self, parent: ttk.Widget, row: int, label: str, variable: tk.StringVar,
        command: Callable[[], None],
    ) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label, width=9).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=5, pady=3)
        ttk.Button(parent, text="浏览…", command=command).grid(row=row, column=2, pady=3)

    def _combo_row(
        self, parent: ttk.Widget, row: int, label: str, variable: tk.StringVar,
        values: tuple[str, ...], command: Callable[[], None] | None = None,
    ) -> None:
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label, width=9).grid(row=row, column=0, sticky="w", pady=3)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        if command:
            combo.bind("<<ComboboxSelected>>", lambda _event: command())

    @staticmethod
    def _small_field(parent: ttk.Widget, column: int, label: str, variable: tk.StringVar) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, sticky="ew", padx=3)
        ttk.Label(frame, text=label).pack(anchor="w")
        ttk.Entry(frame, textvariable=variable, width=12).pack(fill="x")

    def _browse_case(self) -> None:
        value = filedialog.askdirectory(title="选择 SU2WorkFlow 算例目录")
        if value:
            self.set_case(Path(value))

    def set_case(self, case_dir: Path | None) -> None:
        if case_dir is not None:
            resolved = case_dir.resolve()
            self.case_var.set(str(resolved))
            self._sync_conditions_from_case(resolved)

    @staticmethod
    def _cfg_value(path: Path, key: str) -> float | None:
        if not path.is_file():
            return None
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*([^%#]+)", re.IGNORECASE)
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = pattern.match(line)
            if match:
                try:
                    return float(match.group(1).strip().split()[0])
                except ValueError:
                    return None
        return None

    def _sync_conditions_from_case(self, case_dir: Path) -> None:
        cfg = case_dir / "run.cfg"
        mapping = (
            ("MACH_NUMBER", self.mach_var),
            ("REYNOLDS_NUMBER", self.reynolds_var),
            ("AOA", self.aoa_var),
        )
        for key, variable in mapping:
            value = self._cfg_value(cfg, key)
            if value is not None:
                variable.set(f"{value:.12g}")
        result = case_dir / "last_result.json"
        if result.is_file():
            try:
                payload = json.loads(result.read_text(encoding="utf-8"))
                metrics = payload.get("metrics", {})
                for key in ("升力系数 CL", "CL"):
                    if key in metrics:
                        self.target_cl_var.set(f"{float(metrics[key]):.9g}")
                        break
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass

    def use_current_case(self) -> None:
        case_dir = self.current_case_provider() if self.current_case_provider else None
        if case_dir is None:
            messagebox.showinfo(
                "尚无当前算例",
                "请先在“计算与结果”中完成一次正问题，或手动选择已有算例目录。",
                parent=self,
            )
            return
        self.set_case(case_dir)
        self.status_var.set("已载入当前正问题算例，可以检测环境。")

    def _browse_su2(self) -> None:
        value = filedialog.askdirectory(title="选择包含 SU2_CFD_AD.exe 的 bin 目录")
        if value:
            self.su2_var.set(value)

    def _objective_changed(self) -> None:
        enabled = OBJECTIVES[self.objective_var.get()] == "fixed_lift"
        for child in self.fixed_lift_frame.winfo_children():
            for item in child.winfo_children():
                if isinstance(item, ttk.Entry):
                    item.configure(state="normal" if enabled else "disabled")

    def _float(self, variable: tk.StringVar, name: str) -> float:
        try:
            return float(variable.get())
        except ValueError as exc:
            raise ValueError(f"{name} 必须是数字") from exc

    def _integer(self, variable: tk.StringVar, name: str, minimum: int = 1) -> int:
        try:
            value = int(variable.get())
        except ValueError as exc:
            raise ValueError(f"{name} 必须是整数") from exc
        if value < minimum:
            raise ValueError(f"{name} 必须不小于 {minimum}")
        return value

    def _prepare(self) -> Path:
        case = Path(self.case_var.get()).expanduser().resolve()
        su2 = Path(self.su2_var.get()).expanduser().resolve()
        objective = OBJECTIVES[self.objective_var.get()]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        config_path = case / "parametric_optimization" / f"study_{timestamp}.json"
        target_cl = self._float(self.target_cl_var, "目标 CL") if objective == "fixed_lift" else None
        dcl = self._float(self.dcl_dalpha_var, "dCL/dα") if objective == "fixed_lift" else None
        dcd = self._float(self.dcd_dcl_var, "dCD/dCL") if objective == "fixed_lift" else None
        prepare_case_config(
            case_dir=case,
            su2_bin=su2,
            output_config=config_path,
            runtime_bin=detect_runtime_bin(su2),
            mode=METHODS[self.method_var.get()],
            objective_mode=objective,
            target_cl=target_cl,
            dcl_dalpha=dcl,
            dcd_dcl=dcd,
        )
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        payload["steps"] = self._integer(self.steps_var, "尝试步数")
        payload["output"] = str((config_path.parent / timestamp).resolve())
        payload["parameterization"].update({
            "shape_mode": SHAPES[self.shape_var.get()],
            "cst_variables": self._integer(self.cst_var, "CST 变量数"),
            "bce_variables": self._integer(self.bce_var, "BCE 变量数"),
            "relay_cst_steps": self._integer(self.relay_var, "接力换挡步"),
        })
        aoa = self._float(self.aoa_var, "初始 AoA")
        aoa_min = self._float(self.aoa_min_var, "AoA 下限")
        aoa_max = self._float(self.aoa_max_var, "AoA 上限")
        if not aoa_min <= aoa <= aoa_max:
            raise ValueError("初始 AoA 必须位于 AoA 上、下限之间")
        payload["case"].update({
            "mach": self._float(self.mach_var, "Mach"),
            "reynolds": self._float(self.reynolds_var, "Reynolds"),
            "aoa_deg": aoa,
            # 工况由本界面显式给定，必须重新求基准流场，不能误用旧系数。
            "initial_cl": None,
            "initial_cd": None,
        })
        payload["constraints"].update({
            "aoa_min_deg": aoa_min,
            "aoa_max_deg": aoa_max,
            "min_thickness": self._float(self.min_thickness_var, "最小厚度"),
            "max_displacement": self._float(self.max_displacement_var, "最大位移"),
        })
        payload["solver"].update({
            "adjoint_iterations": self._integer(self.adjoint_iterations_var, "伴随迭代数"),
            "adjoint_cfl": self._float(self.adjoint_cfl_var, "伴随 CFL"),
        })
        config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.last_output = Path(payload["output"])
        return config_path

    def check_environment(self) -> None:
        try:
            config_path = self._prepare()
            cfg = load_config(config_path)
            SU2Runner(cfg).validate_executables()
        except Exception as exc:
            messagebox.showerror("检测失败", str(exc), parent=self)
            self.status_var.set("环境检测失败。")
            return
        self._log(f"环境检测通过：{config_path}\n")
        self.status_var.set("环境检测通过，可以开始优化。")

    def _worker_command(self, config_path: Path, log_path: Path) -> list[str]:
        args = ["--worker-log", str(log_path), "--worker", "optimize", str(config_path)]
        if getattr(sys, "frozen", False):
            return [sys.executable, *args]
        entry = application_root() / "parametric_adjoint_app.py"
        if not entry.is_file():
            entry = application_root() / "portable_entry.py"
        return [sys.executable, str(entry), *args]

    def start_optimization(self) -> None:
        if self.process and self.process.poll() is None:
            return
        try:
            config_path = self._prepare()
            SU2Runner(load_config(config_path)).validate_executables()
        except Exception as exc:
            messagebox.showerror("无法启动", str(exc), parent=self)
            return
        self._log(f"\n启动优化：{config_path}\n")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        assert self.last_output is not None
        self.last_output.mkdir(parents=True, exist_ok=True)
        worker_log = self.last_output / "optimizer_worker.log"
        worker_log.write_text("", encoding="utf-8")
        self.process = subprocess.Popen(
            self._worker_command(config_path, worker_log),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        self.start_button.configure(state="disabled")
        self.check_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.open_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.discard_button.configure(state="disabled")
        self.compare_button.configure(state="disabled")
        self.run_progress.start(12)
        self.status_var.set("SU2 优化正在后台运行…")
        threading.Thread(target=self._read_process, args=(worker_log,), daemon=True).start()

    def _read_process(self, log_path: Path) -> None:
        import time

        assert self.process is not None
        with log_path.open("r", encoding="utf-8", errors="replace") as stream:
            while self.process.poll() is None:
                chunk = stream.read()
                if chunk:
                    self.messages.put(("log", chunk))
                time.sleep(0.2)
            chunk = stream.read()
            if chunk:
                self.messages.put(("log", chunk))
        code = self.process.wait()
        self.messages.put(("done", str(code)))

    def stop_optimization(self, confirm: bool = True) -> None:
        if not self.process or self.process.poll() is not None:
            return
        if confirm and not messagebox.askyesno(
            "停止优化", "确定终止当前优化及其 SU2 子进程吗？", parent=self
        ):
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        else:
            self.process.terminate()
        self.status_var.set("正在终止…")

    def open_results(self) -> None:
        if self.last_output and self.last_output.exists():
            os.startfile(self.last_output)  # type: ignore[attr-defined]

    def export_airfoil(self) -> None:
        source = self.last_output / "final_airfoil.dat" if self.last_output else None
        if source is None or not source.is_file():
            messagebox.showinfo("没有候选翼型", "本次优化尚未接受新的设计。", parent=self)
            return
        target = filedialog.asksaveasfilename(
            parent=self,
            title="导出优化翼型 DAT",
            defaultextension=".dat",
            initialfile="optimized_airfoil.dat",
            filetypes=[("Airfoil DAT", "*.dat")],
        )
        if target:
            shutil.copy2(source, target)
            self.status_var.set(f"已导出翼型：{target}")

    def open_comparison(self) -> None:
        plot = self.last_output / "airfoil_comparison.png" if self.last_output else None
        if plot is not None and plot.is_file():
            os.startfile(plot)  # type: ignore[attr-defined]

    def discard_airfoil(self) -> None:
        source = self.last_output / "final_airfoil.dat" if self.last_output else None
        if source is None or not source.is_file():
            return
        if not messagebox.askyesno(
            "丢弃候选翼型",
            "只删除最终翼型 DAT；优化日志、收敛记录和 CFD 结果仍保留。是否继续？",
            parent=self,
        ):
            return
        source.unlink()
        self.export_button.configure(state="disabled")
        self.discard_button.configure(state="disabled")
        self.status_var.set("候选翼型已丢弃；数值结果仍保留。")

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "log":
                    self._log(value)
                else:
                    code = int(value)
                    self.run_progress.stop()
                    self.start_button.configure(state="normal")
                    self.check_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    if code == 0:
                        self.status_var.set("优化完成。")
                        self.open_button.configure(state="normal")
                        candidate = self.last_output / "final_airfoil.dat" if self.last_output else None
                        state = "normal" if candidate is not None and candidate.is_file() else "disabled"
                        self.export_button.configure(state=state)
                        self.discard_button.configure(state=state)
                        comparison = self.last_output / "airfoil_comparison.png" if self.last_output else None
                        self.compare_button.configure(
                            state="normal" if comparison is not None and comparison.is_file() else "disabled"
                        )
                        messagebox.showinfo("完成", "优化已完成，结果与总耗时已写入输出目录。", parent=self)
                    else:
                        self.status_var.set(f"优化异常结束（代码 {code}）。")
                        messagebox.showerror("运行失败", "请查看运行日志中的最后一段错误。", parent=self)
        except queue.Empty:
            pass
        self.after(100, self._drain_messages)

    def _log(self, text: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", text)
        self.console.see("end")
        self.console.configure(state="disabled")

    @property
    def is_running(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def shutdown(self) -> None:
        if self.is_running:
            self.stop_optimization(confirm=False)


class OptimizerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SU2 多参数化伴随优化器")
        self.geometry("1080x760")
        self.minsize(930, 680)
        self.panel = OptimizerPanel(self)
        self.panel.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self) -> None:
        if self.panel.is_running:
            if not messagebox.askyesno(
                "仍在运行", "关闭窗口将终止当前优化及 SU2 子进程，确定继续吗？", parent=self
            ):
                return
            self.panel.shutdown()
        self.destroy()


def main() -> int:
    app = OptimizerApp()
    app.mainloop()
    return 0
