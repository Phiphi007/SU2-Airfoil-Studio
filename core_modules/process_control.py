"""线程安全的外部计算进程暂停、继续与终止控制。"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import threading


def _suspend_process(process: subprocess.Popen[str]) -> None:
    """挂起一个仍在运行的子进程及其线程。"""
    if process.poll() is not None:
        return
    if os.name == "nt":
        ntdll = ctypes.WinDLL("ntdll")
        suspend = ntdll.NtSuspendProcess
        suspend.argtypes = [ctypes.c_void_p]
        suspend.restype = ctypes.c_long
        status = int(suspend(ctypes.c_void_p(int(process._handle))))  # type: ignore[attr-defined]
        if status < 0:
            raise OSError(f"Windows 无法暂停计算进程（NTSTATUS=0x{status & 0xFFFFFFFF:08X}）。")
    else:
        os.kill(process.pid, signal.SIGSTOP)


def _resume_process(process: subprocess.Popen[str]) -> None:
    """继续一个已挂起的子进程及其线程。"""
    if process.poll() is not None:
        return
    if os.name == "nt":
        ntdll = ctypes.WinDLL("ntdll")
        resume = ntdll.NtResumeProcess
        resume.argtypes = [ctypes.c_void_p]
        resume.restype = ctypes.c_long
        status = int(resume(ctypes.c_void_p(int(process._handle))))  # type: ignore[attr-defined]
        if status < 0:
            raise OSError(f"Windows 无法继续计算进程（NTSTATUS=0x{status & 0xFFFFFFFF:08X}）。")
    else:
        os.kill(process.pid, signal.SIGCONT)


class ProcessController:
    """控制工作流当前的耗时子进程，并保留跨阶段的控制请求。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._pause_requested = False
        self._paused = False
        self._termination_requested = False
        self._stop_mode: str | None = None

    @property
    def pause_requested(self) -> bool:
        with self._lock:
            return self._pause_requested

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def termination_requested(self) -> bool:
        with self._lock:
            return self._termination_requested

    @property
    def stop_mode(self) -> str | None:
        with self._lock:
            return self._stop_mode

    @property
    def has_active_process(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def attach(self, process: subprocess.Popen[str]) -> None:
        """登记新的工作流子进程，并应用此前发出的控制请求。"""
        with self._lock:
            self._process = process
            self._paused = False
            if self._termination_requested:
                process.terminate()
            elif self._pause_requested:
                _suspend_process(process)
                self._paused = True

    def detach(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._process is process:
                self._process = None
                self._paused = False

    def pause(self) -> bool:
        """请求暂停；返回当前是否已经实际挂起一个子进程。"""
        with self._lock:
            if self._termination_requested:
                return False
            self._pause_requested = True
            process = self._process
            if process is None or process.poll() is not None:
                return False
            if not self._paused:
                try:
                    _suspend_process(process)
                except Exception:
                    self._pause_requested = False
                    raise
                self._paused = True
            return True

    def resume(self) -> bool:
        """清除暂停请求；返回当前是否实际继续了一个子进程。"""
        with self._lock:
            self._pause_requested = False
            process = self._process
            if process is None or process.poll() is not None or not self._paused:
                self._paused = False
                return False
            _resume_process(process)
            self._paused = False
            return True

    def terminate(self, mode: str = "immediate") -> bool:
        """请求终止；若当前有子进程则立即结束，返回是否发出了结束信号。"""
        with self._lock:
            self._stop_mode = mode
            self._termination_requested = True
            self._pause_requested = False
            process = self._process
            if process is None or process.poll() is not None:
                self._paused = False
                return False
            if self._paused:
                try:
                    _resume_process(process)
                except OSError:
                    # 已挂起的进程仍可由操作系统直接终止，继续失败不能阻止回收。
                    pass
                self._paused = False
            process.terminate()
            return True
