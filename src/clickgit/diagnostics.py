"""Opt-in local diagnostics. No imports of settings, Qt, or repository services.

Only the parent application should own this writer (thread-safe, not a
multi-process log sink). Preview children report typed status to the parent.
Construct once, set_diagnostics(log), and close on application shutdown.
Settings read-only mode does not affect the independent log directory.

Unknown events/fields and invalid values are discarded, never stringified.
Only app_start accepts executable_path; app_start/config_loaded accept
config_path. Callers must provide trusted local application paths, never
repository paths. Traceback values, source and locals are never read.
No exception hooks or root logging handlers are installed.

All file I/O (including startup/history) runs on one daemon worker. record() and
snapshot() only touch bounded memory. flush(timeout) is for tests/non-GUI code;
close() waits at most 100 ms. A full queue drops new disk records explicitly.
Process termination or a stalled disk can lose queued records; no fsync promise.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
from threading import Condition, Event, Thread
from time import monotonic
from types import TracebackType
from uuid import UUID, uuid4

__all__ = [
    "DiagnosticLog", "set_diagnostics", "get_diagnostics", "record_event",
    "log_exception", "BUILD", "VERSION", "REASONS",
]

VERSION = "0.2.0"
BUILD = "2026-09-10-source-inline-highlight"
MAX_FILE_BYTES = 512 * 1024
BACKUP_COUNT = 2
SNAPSHOT_MAX_BYTES = 64 * 1024
MAX_FRAMES = 16
QUEUE_CAPACITY = 256
_MEMORY_BYTES = SNAPSHOT_MAX_BYTES - 1024  # Reserve space for status notices.
UNAVAILABLE = "本机诊断日志不可用（目录无法读写或发生 I/O 错误）；以下仅为内存快照。"
REASONS = frozenset({
    "start_failed", "ownership_failed", "startup_timeout", "heartbeat_timeout",
    "process_exit", "invalid_protocol", "invalid_input", "render_failed",
    "requested", "ready", "closed", "cancelled", "timeout", "shutdown", "unknown",
})
_CONFIG_REASONS = frozenset({"missing", "read_failed", "invalid_json", "schema_mismatch", "ok"})
_PREVIEW_FIELDS = frozenset({
    "session_id", "pid", "exit_code", "reason", "elapsed_ms", "bytes_left", "bytes_right",
})
_EXCEPTION_FIELDS = frozenset({"session_id", "pid", "exception_type", "frames"})
_EXCEPTION_EVENTS = frozenset({"unhandled_exception", "operation_failed"})
_EVENT_FIELDS = {
    "preview_start": _PREVIEW_FIELDS,
    "preview_ready": _PREVIEW_FIELDS,
    "preview_failed": _PREVIEW_FIELDS | {"error_code"},
    "preview_closed": _PREVIEW_FIELDS,
    "app_start": frozenset({"session_id", "pid", "executable_path", "config_path"}),
    "config_loaded": frozenset({
        "session_id", "pid", "schema_type", "schema_value", "expected_schema",
        "settings_read_only", "config_path", "reason",
    }),
    "unhandled_exception": _EXCEPTION_FIELDS,
    "operation_failed": _EXCEPTION_FIELDS,
}
_SCHEMA_TYPES = frozenset({"missing", "int", "str", "float", "bool", "null", "list", "dict"})
_EXCEPTION_TYPES = frozenset({
    "BaseException", "Exception", "RuntimeError", "ValueError", "TypeError",
    "KeyError", "IndexError", "AttributeError", "AssertionError", "OSError",
    "FileNotFoundError", "PermissionError", "IsADirectoryError", "NotADirectoryError",
    "FileExistsError", "TimeoutError", "ConnectionError", "BrokenPipeError",
    "ImportError", "ModuleNotFoundError", "MemoryError", "RecursionError",
    "UnicodeError", "UnicodeDecodeError", "UnicodeEncodeError", "OverflowError",
    "ZeroDivisionError", "NotImplementedError", "SystemError", "EOFError",
    "StopIteration", "KeyboardInterrupt", "SystemExit", "JSONDecodeError",
    "SettingsValidationError", "ProjectsSaveError", "GitCommandError",
    "OperationConflict", "UnknownException",
})
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,95}\Z")
_BASENAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}\Z")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00\Z")


def _integer(value: object, *, signed: bool = False) -> bool:
    return type(value) is int and (-(2**63) if signed else 0) <= value < 2**63


def _frames(value: object) -> list[dict]:
    result = []
    if type(value) is not list:
        return result
    for frame in value[:MAX_FRAMES]:
        if type(frame) is not dict:
            continue
        filename, function, line = (frame.get(key) for key in ("file", "function", "line"))
        if type(filename) is not str or len(filename) > 4096:
            continue
        basename = PureWindowsPath(filename).name
        if not _BASENAME.fullmatch(basename):
            basename = "unknown"
        if type(function) is not str or (
            function != "<module>" and not _IDENTIFIER.fullmatch(function)
        ):
            function = "unknown"
        if not _integer(line):
            continue
        result.append({"file": basename, "function": function, "line": line})
    return result


def _clean_fields(event: str, fields: dict) -> dict:
    result = {}
    for key in _EVENT_FIELDS[event]:
        value = fields.get(key)
        if key in {"pid", "elapsed_ms", "bytes_left", "bytes_right", "expected_schema", "error_code"}:
            if _integer(value):
                result[key] = value
        elif key == "exit_code":
            if _integer(value, signed=True):
                result[key] = value
        elif key == "schema_value":
            if type(value) is int and -(2**53) < value < 2**53:
                result[key] = value
        elif key == "settings_read_only":
            if type(value) is bool:
                result[key] = value
        elif key == "session_id":
            if type(value) is str and len(value) in (32, 36):
                try:
                    session = UUID(value)
                    result[key] = session.hex if len(value) == 32 else str(session)
                except ValueError:
                    pass
        elif key == "reason":
            allowed = _CONFIG_REASONS if event == "config_loaded" else REASONS
            if type(value) is str and len(value) <= 64 and value in allowed:
                result[key] = value
        elif key == "schema_type":
            if type(value) is str and len(value) <= 16 and value in _SCHEMA_TYPES:
                result[key] = value
        elif key == "exception_type":
            result[key] = (
                value if type(value) is str and len(value) <= 64 and value in _EXCEPTION_TYPES
                else "UnknownException"
            )
        elif key == "frames":
            result[key] = _frames(value)
        elif key in {"executable_path", "config_path"}:
            if (
                type(value) is str and 0 < len(value) <= 4096
                and not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value)
                and (Path(value).is_absolute() or PureWindowsPath(value).is_absolute())
            ):
                result[key] = value
    return result


def _encode(row: dict) -> str:
    # ASCII gives exact byte accounting for the memory buffer and disk rotation.
    return json.dumps(row, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _history_lines(path: Path) -> list[str]:
    """Worker only: bounded reads of the three exact log names, never quarantine."""
    lines = deque()
    size = 0
    for name in ("clickgit.log.2", "clickgit.log.1", "clickgit.log"):
        try:
            with path.with_name(name).open("rb") as stream:
                end = stream.seek(0, os.SEEK_END)
                start = max(0, end - SNAPSHOT_MAX_BYTES)
                stream.seek(start)
                data = stream.read(SNAPSHOT_MAX_BYTES)
        except FileNotFoundError:
            continue
        if start:
            data = data.partition(b"\n")[2]
        for raw in data.splitlines():
            try:
                row = json.loads(raw)
                if type(row) is not dict:
                    continue
                event = row.get("event")
                if type(event) is not str or len(event) > 32 or event not in _EVENT_FIELDS:
                    continue
                safe = {"event": event, **_clean_fields(event, row)}
                for key, constant in (("build", BUILD), ("version", VERSION)):
                    if row.get(key) == constant:
                        safe[key] = constant
                timestamp = row.get("timestamp")
                if type(timestamp) is str and _TIMESTAMP.fullmatch(timestamp):
                    safe["timestamp"] = timestamp
                line = _encode(safe) + "\n"
                if len(line) > _MEMORY_BYTES:
                    continue
                lines.append(line)
                size += len(line)
                while size > _MEMORY_BYTES:
                    size -= len(lines.popleft())
            except (ValueError, UnicodeError, RecursionError):
                continue
    return list(lines)


class _FileWriter:
    """Worker-owned binary sink; not registered in logging's atexit shutdown.

    Using an ordinary logging.Handler would let logging.shutdown() synchronously
    flush a stalled daemon's stream on the main thread at process exit.
    """

    def __init__(self, path: Path):
        self.path = path
        self.stream = path.open("ab")
        self.size = self.stream.tell()

    def rotate(self):
        self.stream.close()
        for index in range(BACKUP_COUNT, 0, -1):
            source = self.path if index == 1 else self.path.with_name(f"clickgit.log.{index - 1}")
            target = self.path.with_name(f"clickgit.log.{index}")
            try:
                source.replace(target)
            except FileNotFoundError:
                pass
        self.stream = self.path.open("ab")
        self.size = 0

    def write(self, line: str):
        payload = line.encode("ascii")
        if self.size + len(payload) > MAX_FILE_BYTES:
            self.rotate()
        self.stream.write(payload)
        self.stream.flush()
        self.size += len(payload)

    def close(self):
        self.stream.close()


class DiagnosticLog:
    """One writer per application; pending/available/unavailable/closed status."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "diagnostics" / "clickgit.log"
        self.session_id = str(uuid4())
        self._condition = Condition()
        self._pending: deque[str] = deque()
        self._recent: deque[str] = deque()
        self._recent_bytes = 0
        self._submitted = 0
        self._completed = 0
        self._dropped = 0
        self._initialized = False
        self._failed = False
        self._closing = False
        self._finished = Event()
        self._worker = Thread(target=self._run, name="ClickGit-diagnostics", daemon=True)
        try:
            self._worker.start()
        except Exception:
            self._failed = True
            self._finished.set()

    @property
    def status(self) -> str:
        with self._condition:
            if self._closing:
                return "closed"
            if self._failed:
                return "unavailable"
            return "available" if self._initialized else "pending"

    @property
    def available(self) -> bool:
        return self.status == "available"

    @property
    def dropped_records(self) -> int:
        with self._condition:
            return self._dropped

    def _remember(self, line: str) -> None:
        if len(line) > _MEMORY_BYTES:
            return
        self._recent.append(line)
        self._recent_bytes += len(line)
        while self._recent_bytes > _MEMORY_BYTES:
            self._recent_bytes -= len(self._recent.popleft())

    def _run(self) -> None:
        writer = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            history = _history_lines(self.path)
            writer = _FileWriter(self.path)
            with self._condition:
                current = list(self._recent)
                self._recent.clear()
                self._recent_bytes = 0
                for line in history + current:
                    self._remember(line)
                self._initialized = True
                self._condition.notify_all()
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._pending or self._closing)
                    if not self._pending:
                        break
                    line = self._pending.popleft()
                # Never hold the condition across a filesystem operation.
                writer.write(line)
                with self._condition:
                    self._completed += 1
                    self._condition.notify_all()
        except Exception:
            with self._condition:
                self._failed = True
                self._pending.clear()
                self._condition.notify_all()
        finally:
            if writer is not None:
                try:
                    writer.close()
                except Exception:
                    with self._condition:
                        self._failed = True
                        self._condition.notify_all()
            self._finished.set()

    def record(self, event: str, **fields) -> None:
        """Nonblocking disk enqueue; invalid fields are omitted, never formatted."""
        if type(event) is not str or len(event) > 32 or event not in _EVENT_FIELDS:
            return
        try:
            row = {
                "event": event, "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                "session_id": self.session_id, "pid": os.getpid(),
                "build": BUILD, "version": VERSION,
                **_clean_fields(event, fields),
            }
            line = _encode(row) + "\n"
        except Exception:
            return
        with self._condition:
            if self._closing:
                return
            self._remember(line)
            if self._failed:
                return
            if len(self._pending) >= QUEUE_CAPACITY:
                self._dropped += 1
                return
            self._pending.append(line)
            self._submitted += 1
            self._condition.notify_all()

    def log_exception(self, exception_type, value, tb, *, event="unhandled_exception") -> None:
        """Hook-compatible; use operation_failed for caught errors, never inspect value."""
        if type(event) is not str or len(event) > 32 or event not in _EXCEPTION_EVENTS:
            return
        try:
            name = (
                type.__getattribute__(exception_type, "__name__")
                if isinstance(exception_type, type) else "UnknownException"
            )
            frames = []
            # Traverse without traceback formatting/linecache (no source reads).
            while type(tb) is TracebackType:
                code = tb.tb_frame.f_code
                frames.append({"file": code.co_filename, "function": code.co_name, "line": tb.tb_lineno})
                frames = frames[-MAX_FRAMES:]
                tb = tb.tb_next
            self.record(event, exception_type=name, frames=frames)
        except Exception:
            self.record(event, exception_type="UnknownException")

    def snapshot(self) -> str:
        """At most 64 KiB of memory; includes bounded, background-loaded history."""
        with self._condition:
            notices = []
            status = self.status
            if status == "pending":
                notices.append("本机诊断日志初始化中；历史记录正在后台加载。")
            elif status == "unavailable":
                notices.append(UNAVAILABLE)
            elif status == "closed":
                notices.append("本机诊断日志不可用（已关闭）；以下仅为内存快照。")
            if self._dropped:
                notices.append(f"写入队列已满，已丢弃 {self._dropped} 条磁盘记录；内存记录不保证已落盘。")
            text = "".join(self._recent) or "暂无诊断记录。"
            return ("\n".join(notices) + "\n" if notices else "") + text

    def flush(self, timeout: float = 1.0) -> bool:
        """Wait <= timeout (capped at 5 seconds) for accepted writes; not for GUI.

        False means pending, timed out or failed; True does not cover dropped
        records or promise power-loss durability. No filesystem work here.
        """
        if type(timeout) not in (int, float):
            return False
        if type(timeout) is float and not math.isfinite(timeout):
            return False
        deadline = monotonic() + min(5.0, max(0.0, timeout))
        with self._condition:
            target = self._submitted
            while not self._failed and (not self._initialized or self._completed < target):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return not self._failed and self._initialized and self._completed >= target

    def close(self) -> None:
        """Terminal; request drain/close on worker, wait at most 100 ms."""
        with self._condition:
            if self._closing:
                return
            self._closing = True
            self._condition.notify_all()
        self._finished.wait(0.1)


_diagnostics: DiagnosticLog | None = None


def set_diagnostics(log: DiagnosticLog | None) -> None:
    """Register without closing the previous writer; lifetime belongs to caller."""
    global _diagnostics
    _diagnostics = log


def get_diagnostics() -> DiagnosticLog | None:
    return _diagnostics


def record_event(event: str, **fields) -> None:
    log = get_diagnostics()
    if log is not None:
        log.record(event, **fields)


def log_exception(exception_type, value, tb, *, event="unhandled_exception") -> None:
    log = get_diagnostics()
    if log is not None:
        log.log_exception(exception_type, value, tb, event=event)
