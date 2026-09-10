"""Private preview process ownership and anonymous pipe I/O.

No shell, process-name termination, shared browser profile, or temporary HTML.
Windows ownership must be established BEFORE the parent sends any material.
"""
from __future__ import annotations

import ctypes
import os
import signal
import sys

MAX_REQUEST_BYTES = 5 * 1024 * 1024


class ProcessTree:
    def __init__(self, pid: int):
        self.pid = pid
        self.handle = None
        if sys.platform != "win32":
            return  # Worker establishes its own session before reading stdin.
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [
                ("ProcessTime", ctypes.c_longlong), ("JobTime", ctypes.c_longlong),
                ("Flags", w.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcesses", w.DWORD),
                ("Affinity", ctypes.c_size_t), ("Priority", w.DWORD),
                ("Scheduling", w.DWORD),
            ]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperations", "WriteOperations", "OtherOperations",
                "ReadBytes", "WriteBytes", "OtherBytes")]

        class Limits(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("IO", IO),
                        ("ProcessMemory", ctypes.c_size_t), ("JobMemory", ctypes.c_size_t),
                        ("PeakProcessMemory", ctypes.c_size_t), ("PeakJobMemory", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        self._kernel = kernel
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "preview ownership unavailable")
        process = None
        try:
            limits = Limits()
            limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise OSError(ctypes.get_last_error(), "preview ownership unavailable")
            process = kernel.OpenProcess(0x0100 | 0x0001, False, pid)
            if not process or not kernel.AssignProcessToJobObject(job, process):
                raise OSError(ctypes.get_last_error(), "preview ownership unavailable")
            self.handle = job
        except BaseException:
            kernel.CloseHandle(job)
            raise
        finally:
            if process:
                kernel.CloseHandle(process)

    def close(self):
        if sys.platform == "win32":
            handle, self.handle = self.handle, None
            if handle:
                self._kernel.CloseHandle(handle)
        elif self.pid:
            pid, self.pid = self.pid, 0
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def initialize_worker():
    if sys.platform == "win32":
        # Only this child: avoid native error-dialog hangs after a fatal assert.
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002)
    else:
        os.setsid()


def _windows_pipe(input_pipe: bool, data_or_size):
    """Windowed frozen builds have sys.stdin/stdout=None; use inherited handles."""
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [w.DWORD]
    kernel.GetStdHandle.restype = w.HANDLE
    handle = kernel.GetStdHandle((-10 if input_pipe else -11) & 0xFFFFFFFF)
    count = w.DWORD()
    if input_pipe:
        function = kernel.ReadFile
        buffer = ctypes.create_string_buffer(data_or_size)
        size = data_or_size
    else:
        function = kernel.WriteFile
        buffer = ctypes.create_string_buffer(data_or_size)
        size = len(data_or_size)
    function.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    function.restype = w.BOOL
    ok = function(handle, buffer, size, ctypes.byref(count), None)
    if not ok:
        if input_pipe and ctypes.get_last_error() == 109:  # EOF / broken input pipe
            return b""
        raise OSError("preview pipe unavailable")
    return buffer.raw[:count.value] if input_pipe else count.value


def read_request() -> bytes:
    result = bytearray()
    while True:
        limit = min(65536, MAX_REQUEST_BYTES + 1 - len(result))
        chunk = _windows_pipe(True, limit) if sys.platform == "win32" else os.read(0, limit)
        if not chunk:
            return bytes(result)
        result.extend(chunk)
        if len(result) > MAX_REQUEST_BYTES:
            raise ValueError("preview input too large")


def write_status(data: bytes):
    while data:
        count = _windows_pipe(False, data) if sys.platform == "win32" else os.write(1, data)
        if count <= 0:
            raise OSError("preview pipe closed")
        data = data[count:]
