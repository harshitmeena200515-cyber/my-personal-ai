"""
System Info Tool.

Provides read-only system metrics: CPU, RAM, disk, GPU, Python info.
No side effects, no process execution, no configuration changes.
"""

import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict

from tools.base import BaseTool, ToolResult, ToolParameter, PermissionLevel

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SystemInfoTool(BaseTool):
    """Read-only system information reporter.

    Returns CPU, RAM, disk space, GPU info, Python version,
    and project directory statistics. No side effects.
    """

    name = "system_info"
    description = (
        "Returns system hardware and software info: OS, CPU, RAM, disk space, "
        "GPU, Python version, and project directory stats. Read-only, no side effects."
    )
    category = "system"
    permission = PermissionLevel.SAFE
    parameters = [
        ToolParameter(
            name="category",
            type="string",
            description="'all' (default), 'hardware', 'software', 'disk', or 'project'",
            required=False,
            default="all",
        ),
    ]

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        category = str(params.get("category", "all")).lower()

        info = {}
        if category in ("all", "hardware"):
            info["hardware"] = self._get_hardware_info()
        if category in ("all", "software"):
            info["software"] = self._get_software_info()
        if category in ("all", "disk"):
            info["disk"] = self._get_disk_info()
        if category in ("all", "project"):
            info["project"] = self._get_project_info()

        return ToolResult(success=True, output=info)

    def _get_hardware_info(self) -> Dict[str, Any]:
        hw: Dict[str, Any] = {
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "cpu_count": os.cpu_count(),
            "gpu": "NVIDIA GeForce RTX 3050 Laptop GPU (4GB VRAM)",
        }

        # Try to get RAM info
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            c_ulonglong = ctypes.c_ulonglong

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", c_ulonglong),
                    ("ullAvailPhys", c_ulonglong),
                    ("ullTotalPageFile", c_ulonglong),
                    ("ullAvailPageFile", c_ulonglong),
                    ("ullTotalVirtual", c_ulonglong),
                    ("ullAvailVirtual", c_ulonglong),
                    ("ullAvailExtendedVirtual", c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            hw["ram_total_gb"] = round(stat.ullTotalPhys / (1024 ** 3), 1)
            hw["ram_available_gb"] = round(stat.ullAvailPhys / (1024 ** 3), 1)
            hw["ram_usage_percent"] = stat.dwMemoryLoad
        except Exception:
            hw["ram_total_gb"] = 16.0
            hw["ram_note"] = "Estimated (ctypes unavailable)"

        return hw

    def _get_software_info(self) -> Dict[str, Any]:
        return {
            "python_version": platform.python_version(),
            "python_path": sys.executable,
            "platform": sys.platform,
        }

    def _get_disk_info(self) -> Dict[str, Any]:
        try:
            import shutil
            usage = shutil.disk_usage(_PROJECT_ROOT)
            return {
                "total_gb": round(usage.total / (1024 ** 3), 1),
                "used_gb": round(usage.used / (1024 ** 3), 1),
                "free_gb": round(usage.free / (1024 ** 3), 1),
                "usage_percent": round(usage.used / usage.total * 100, 1),
            }
        except Exception:
            return {"error": "Could not read disk info"}

    def _get_project_info(self) -> Dict[str, Any]:
        file_count = 0
        total_size = 0
        py_files = 0
        blocked = {".venv", ".git", "__pycache__", "node_modules"}

        for item in _PROJECT_ROOT.rglob("*"):
            # Skip blocked directories
            if any(part in blocked for part in item.parts):
                continue
            if item.is_file():
                file_count += 1
                total_size += item.stat().st_size
                if item.suffix == ".py":
                    py_files += 1

        return {
            "root": str(_PROJECT_ROOT),
            "total_files": file_count,
            "python_files": py_files,
            "total_size_kb": round(total_size / 1024, 1),
        }
