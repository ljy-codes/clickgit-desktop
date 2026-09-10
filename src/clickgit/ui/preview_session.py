"""Non-blocking preview supervisor. This module NEVER imports WebEngine."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import uuid
from weakref import WeakSet

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtWidgets import QApplication

from clickgit.preview_process import MAX_REQUEST_BYTES, ProcessTree

_active_sessions = WeakSet()


def stop_all_previews():
    """GUI-thread shutdown boundary: release previews before waiting on Git."""
    for session in tuple(_active_sessions):
        session.stop()

_MESSAGES = {
    "start_failed": "静态预览启动失败，请检查安装是否完整或联系管理员。",
    "ownership_failed": "环境不允许建立预览进程隔离，已停止；请使用源码/需求对比。",
    "startup_timeout": "静态预览启动超时，已关闭本次预览；可以重试，主界面仍可使用。",
    "heartbeat_timeout": "静态预览长时间无响应，已关闭本次预览；可以重试。",
    "process_exit": "静态预览进程异常退出；主界面仍可使用，可以重试。",
    "invalid_protocol": "静态预览返回异常，已停止本次预览。",
    "invalid_input": "HTML 超出预览输入限制，请使用源码/需求对比。",
    "render_failed": "静态预览加载失败；请使用源码/需求对比，或重试。",
}


def _record(event, **fields):
    # Logging must never be a dependency of process teardown.
    from clickgit.diagnostics import record_event
    record_event(event, **fields)


def worker_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--html-preview-worker"]
    executable = Path(sys.executable)
    windowed = executable.with_name("pythonw.exe")
    if sys.platform == "win32" and windowed.is_file():
        executable = windowed
    return [str(executable), "-B", "-m", "clickgit", "--html-preview-worker"]


class PreviewSession(QObject):
    status_changed = Signal(str)

    def __init__(self, parent=None, *, command=None, startup_timeout_ms=25000,
                 heartbeat_timeout_ms=8000):
        super().__init__(parent)
        self.command = list(command) if command is not None else worker_command()
        self.startup_timeout_ms = startup_timeout_ms
        self.heartbeat_timeout_ms = heartbeat_timeout_ms
        self.state = "idle"
        self.failure_reason = ""
        self.ready_details = {}
        self._process = None
        self._tree = None
        self._buffer = bytearray()
        self._request = b""
        self._session_id = ""
        self._started_at = self._last_heartbeat = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._check_deadline)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.stop)

    @property
    def running(self):
        return self._process is not None

    def start(self, pair):
        if self.running:
            return
        self.failure_reason = ""
        self.ready_details = {}
        self._session_id = uuid.uuid4().hex
        self._started_at = self._last_heartbeat = time.monotonic()
        try:
            for text in (pair.left, pair.right):
                if len(text) > 2 * 1024 * 1024 or len(text.encode("utf-8")) > 2 * 1024 * 1024:
                    raise ValueError
            self._request = json.dumps({
                "left": pair.left, "right": pair.right,
                "left_title": pair.left_title[:512], "right_title": pair.right_title[:512],
            }, ensure_ascii=False).encode("utf-8")
            if len(self._request) > MAX_REQUEST_BYTES:
                raise ValueError
        except (ValueError, UnicodeError, TypeError):
            self._fail("invalid_input")
            return
        self._buffer.clear()
        self.state = "starting"
        self.status_changed.emit("正在独立进程中加载静态预览…可随时关闭，不影响源码对比。")
        process = QProcess(QApplication.instance())
        self._process = process
        _active_sessions.add(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        # Native stderr can contain document content/URLs. Do not retain it.
        process.setStandardErrorFile(QProcess.nullDevice())
        process.started.connect(lambda: self._send_request(process))
        process.readyReadStandardOutput.connect(lambda: self._read_status(process))
        process.errorOccurred.connect(lambda error: self._process_error(process, error))
        process.finished.connect(lambda code, status: self._finished(process, code, status))
        process.finished.connect(process.deleteLater)
        self._timer.start()
        _record("preview_start", session_id=self._session_id,
                bytes_left=len(pair.left.encode("utf-8")), bytes_right=len(pair.right.encode("utf-8")))
        process.start(self.command[0], self.command[1:])

    def _send_request(self, process):
        if process is not self._process:
            return
        try:
            self._tree = ProcessTree(int(process.processId()))
        except OSError as exc:
            self._fail("ownership_failed", error_code=exc.errno)
            return
        # QProcess buffers writes asynchronously; no waitForStarted/Finished.
        if process.write(self._request) < 0:
            self._fail("start_failed")
            return
        self._request = b""
        process.closeWriteChannel()

    def _read_status(self, process):
        if process is not self._process:
            return
        self._buffer.extend(bytes(process.read(4097)))
        if len(self._buffer) > 4096 or process.bytesAvailable() > 4096:
            self._fail("invalid_protocol")
            return
        while b"\n" in self._buffer:
            line, _, rest = self._buffer.partition(b"\n")
            self._buffer = bytearray(rest)
            try:
                message = json.loads(line)
                event = message["event"]
                if event not in {"tick", "ready", "failed", "closed"}:
                    raise ValueError
                if event == "ready":
                    checks = message["checks"]
                    if (type(checks) is not dict or set(checks) != {
                            "javascript_disabled", "profiles_off_record", "local_access_disabled",
                            "visible_text_verified", "previews_loaded"}
                            or type(checks["previews_loaded"]) is not int or checks["previews_loaded"] != 2
                            or any(type(checks[key]) is not bool for key in checks if key != "previews_loaded")
                            or not all(checks[key] for key in (
                                "javascript_disabled", "profiles_off_record", "local_access_disabled"))):
                        raise ValueError
                    if self.state == "starting":
                        self.state = "ready"
                        self.ready_details = checks
                        self.status_changed.emit("静态预览已在独立窗口打开；关闭审阅时也会关闭预览。")
                        _record("preview_ready", session_id=self._session_id,
                                pid=int(process.processId()), elapsed_ms=self._elapsed())
                elif event == "failed":
                    self._fail("render_failed")
                    return
                elif event == "closed":
                    self.stop()
                    return
                self._last_heartbeat = time.monotonic()
            except (ValueError, KeyError, TypeError, UnicodeError):
                self._fail("invalid_protocol")
                return

    def _elapsed(self):
        return int((time.monotonic() - self._started_at) * 1000)

    def _check_deadline(self):
        if not self.running:
            return
        if self.state == "starting" and self._elapsed() >= self.startup_timeout_ms:
            self._fail("startup_timeout")
        elif self.state == "ready" and (
                time.monotonic() - self._last_heartbeat) * 1000 >= self.heartbeat_timeout_ms:
            self._fail("heartbeat_timeout")

    def _process_error(self, process, error):
        if process is self._process and error == QProcess.ProcessError.FailedToStart:
            self._fail("start_failed")
            process.deleteLater()
        # Crashed also produces finished with the meaningful native exit code.

    def _finished(self, process, code, status):
        if process is not self._process:
            return
        if code != 0 or status == QProcess.ExitStatus.CrashExit or self.state != "ready":
            self._fail("process_exit", exit_code=code)
        else:
            self.stop()

    def _release(self):
        _active_sessions.discard(self)
        self._timer.stop()
        process, self._process = self._process, None
        tree, self._tree = self._tree, None
        self._request = b""
        self._buffer.clear()
        if tree is not None:
            tree.close()
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _fail(self, reason, *, exit_code=None, error_code=None):
        fields = {"session_id": self._session_id, "reason": reason, "elapsed_ms": self._elapsed()}
        if self._process is not None:
            fields["pid"] = int(self._process.processId())
        if exit_code is not None:
            fields["exit_code"] = exit_code
        if type(error_code) is int and error_code >= 0:
            fields["error_code"] = error_code
        self._release()
        self.state, self.failure_reason = "failed", reason
        _record("preview_failed", **fields)
        self.status_changed.emit(_MESSAGES[reason] + " 详情可在“诊断信息”中查看。")

    def stop(self):
        was_running = self.running
        self._release()
        if was_running:
            self.state = "closed"
            _record("preview_closed", session_id=self._session_id, elapsed_ms=self._elapsed())
            self.status_changed.emit("静态预览已关闭，可以重新打开。")
