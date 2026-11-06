from __future__ import annotations

import platform
import subprocess

from mediakit.enums import OperatingSystem


def detect_os() -> OperatingSystem:
    system = platform.system()
    match system:
        case "Windows":
            return OperatingSystem.WINDOWS
        case "Darwin":
            return OperatingSystem.MACOS
        case "Linux":
            release = platform.uname().release.lower()
            version = platform.version().lower()
            if "microsoft" in release or "microsoft" in version or "wsl" in release:
                return OperatingSystem.WSL
            return OperatingSystem.LINUX
        case _:
            return OperatingSystem.UNKNOWN


def get_wsl_windows_host() -> str | None:
    try:
        result = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=2, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "default" and parts[1] == "via":
            return parts[2]
    return None
