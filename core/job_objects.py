"""
Windows Job Objects Process Sandbox Supervisor.

Provides:
- Native Windows Job Object creation and process assignment.
- Hard virtual memory limits (e.g., 128 MB max per tool subprocess).
- Automatic child process termination via JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
- Pure Python ctypes implementation without external compiled dependencies.
"""

import ctypes
from ctypes import wintypes
import os
import subprocess
from typing import Optional, List, Tuple


# Windows API Structures
class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


# Limit Flags
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x0100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x0200
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x0008

JobObjectExtendedLimitInformation = 9

kernel32 = ctypes.windll.kernel32


class WindowsJobObjectSandbox:
    """Manages an isolated Windows Job Object with enforced memory and execution limits."""

    def __init__(self, name: Optional[str] = None, max_memory_mb: int = 128, max_processes: int = 4):
        self.name = name
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.max_processes = max_processes
        self._handle = None
        self._init_job()

    def _init_job(self) -> None:
        """Create Windows Job Object and configure resource limits."""
        self._handle = kernel32.CreateJobObjectW(None, self.name)
        if not self._handle:
            err = kernel32.GetLastError()
            raise OSError(f"CreateJobObjectW failed with error code: {err}")

        # Set extended limit information
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | JOB_OBJECT_LIMIT_JOB_MEMORY
            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        )
        info.BasicLimitInformation.ActiveProcessLimit = self.max_processes
        info.ProcessMemoryLimit = self.max_memory_bytes
        info.JobMemoryLimit = self.max_memory_bytes

        success = kernel32.SetInformationJobObject(
            self._handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not success:
            err = kernel32.GetLastError()
            self.close()
            raise OSError(f"SetInformationJobObject failed with error code: {err}")

    def assign_process(self, process_handle: int) -> bool:
        """Assign an active OS process to this restricted Job Object."""
        if not self._handle:
            raise ValueError("Job Object handle is closed.")
        success = kernel32.AssignProcessToJobObject(self._handle, process_handle)
        return bool(success)

    def run_sandboxed(
        self,
        command: List[str],
        timeout_seconds: float = 10.0,
        cwd: Optional[str] = None
    ) -> Tuple[int, str, str]:
        """Spawn a subprocess and immediately assign it to the restricted Job Object."""
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Immediately bind process into Job Object
        self.assign_process(proc._handle)

        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            return proc.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return -1, stdout, "Execution Timeout: Subprocess terminated by Job Object supervisor."

    def close(self) -> None:
        """Close Job Object handle, terminating all active child processes."""
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
