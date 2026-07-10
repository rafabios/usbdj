from __future__ import annotations

import ctypes
import sys
from pathlib import Path
import subprocess


def _gui_python_executable() -> str:
    executable = Path(sys.executable)
    if executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(executable)


def _write_elevation_log(message: str) -> None:
    try:
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "elevation.log").open("a", encoding="utf-8") as file:
            file.write(message.rstrip() + "\n")
    except OSError:
        pass


def relaunch_with_windows_permission() -> bool:
    """Ask Windows to relaunch the current app with elevated permission."""
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = ""
    else:
        executable = _gui_python_executable()
        launcher = Path.cwd() / "run_gui.py"
        params = f'"{launcher}"'

    _write_elevation_log(f"relaunch executable={executable}")
    _write_elevation_log(f"relaunch params={params}")
    _write_elevation_log(f"relaunch cwd={Path.cwd()}")

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        params,
        str(Path.cwd()),
        1,
    )
    _write_elevation_log(f"ShellExecuteW result={result}")
    return result > 32


def run_worker_with_windows_permission(args: list[str]) -> bool:
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(["--worker", *args])
    else:
        executable = _gui_python_executable()
        launcher = Path.cwd() / "run_worker.py"
        params = subprocess.list2cmdline([str(launcher), *args])

    _write_elevation_log(f"worker executable={executable}")
    _write_elevation_log(f"worker params={params}")
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        params,
        str(Path.cwd()),
        1,
    )
    _write_elevation_log(f"worker ShellExecuteW result={result}")
    return result > 32
