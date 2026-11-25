"""Read external power status without installing a system dependency."""

import platform
from pathlib import Path
import subprocess


def linux_power(root=Path("/sys/class/power_supply")):
    supplies = list(root.iterdir())
    battery = False
    external = False
    for supply in supplies:
        kind = (supply / "type").read_text().strip()
        if kind == "Battery":
            battery = True
            continue
        online = supply / "online"
        if online.is_file() and online.read_text().strip() == "1":
            external = True
    return "ac" if external else "battery" if battery else "unknown"


def windows_power():
    from ctypes import Structure, byref, c_ubyte, c_uint32, windll

    class Status(Structure):
        _fields_ = [
            ("ac", c_ubyte), ("battery_flags", c_ubyte), ("battery_percent", c_ubyte),
            ("system_flags", c_ubyte), ("battery_life", c_uint32), ("full_life", c_uint32),
        ]

    status = Status()
    if not windll.kernel32.GetSystemPowerStatus(byref(status)):
        return "unknown"
    return {0: "battery", 1: "ac"}.get(status.ac, "unknown")


def power_source():
    try:
        system = platform.system()
        if system == "Darwin":
            report = subprocess.check_output(["/usr/bin/pmset", "-g", "batt"], text=True, timeout=2)
            first_line = report.splitlines()[0]
            if "AC Power" in first_line:
                return "ac"
            if "Battery Power" in first_line:
                return "battery"
        elif system == "Linux":
            return linux_power()
        elif system == "Windows":
            return windows_power()
    except (OSError, IndexError, subprocess.SubprocessError):
        pass
    return "unknown"
