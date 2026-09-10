"""Regression: preview failure must not take down or block the Git UI."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication

from clickgit.document_workflow import TextComparison
from clickgit.ui.html_review import HtmlReviewDialog

PAIR = TextComparison("private.html", "<p>PRIVATE_LEFT</p>", "<p>PRIVATE_RIGHT</p>", "原", "新")
READY = json.dumps({"event": "ready", "checks": {
    "javascript_disabled": True, "profiles_off_record": True, "local_access_disabled": True,
    "visible_text_verified": True, "previews_loaded": 2,
}}) + "\n"


class PreviewIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def spin(self, predicate, timeout=6):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            if predicate():
                return
            time.sleep(.01)
        self.fail("Preview event deadline expired")

    def session(self, code, **kwargs):
        self.assertIsNotNone(importlib.util.find_spec("clickgit.ui.preview_session"),
                             "An independently supervised preview process is required")
        from clickgit.ui.preview_session import PreviewSession
        session = PreviewSession(command=[sys.executable, "-B", "-c", code], **kwargs)
        self.addCleanup(session.stop)
        return session

    def test_review_never_constructs_webengine_in_main_process(self):
        dialog = HtmlReviewDialog(PAIR)
        try:
            # Do not start real rendering in a unit test.
            with patch.object(dialog.preview_session, "start"), \
                    patch("clickgit.ui.html_preview.HtmlPreview") as inline:
                dialog.preview_button.click()
                self.assertFalse(inline.called, "HTML review must delegate to a child process")
        finally:
            dialog.reject()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_crash_is_reported_and_parent_event_loop_keeps_ticking(self):
        session = self.session("import sys; sys.stdin.buffer.read(); sys.exit(17)")
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        try:
            session.start(PAIR)
            self.spin(lambda: session.state == "failed")
            self.spin(lambda: len(ticks) >= 3)
            self.assertEqual(session.failure_reason, "process_exit")
            self.assertFalse(session.running)
        finally:
            timer.stop()

    @unittest.skipUnless(sys.platform == "win32", "Windows native exception")
    def test_native_breakpoint_exit_is_logged_without_material_or_hanging_parent(self):
        from clickgit.diagnostics import DiagnosticLog, set_diagnostics
        # Only this synthetic owned helper receives error-dialog suppression.
        code = ("import sys,ctypes; from clickgit.preview_process import initialize_worker; "
                "initialize_worker(); sys.stdin.buffer.read(); "
                "ctypes.windll.kernel32.RaiseException(0x80000003,0,0,None)")
        session = self.session(code)
        with tempfile.TemporaryDirectory() as folder:
            log = DiagnosticLog(Path(folder))
            set_diagnostics(log)
            try:
                session.start(PAIR)
                self.spin(lambda: session.state == "failed")
                self.assertEqual(session.failure_reason, "process_exit")
                self.assertTrue(log.flush(2))
                rows = [json.loads(line) for line in log.snapshot().splitlines()]
                failures = [row for row in rows if row["event"] == "preview_failed"]
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["exit_code"] & 0xffffffff, 0x80000003)
                self.assertNotIn("PRIVATE", log.path.read_text("utf-8"))
                self.assertNotIn("private.html", log.snapshot())
            finally:
                session.stop()
                set_diagnostics(None)
                log.close()

    def test_hung_child_times_out_without_blocking_and_can_retry(self):
        session = self.session("import sys,time; sys.stdin.buffer.read(); time.sleep(60)",
                               startup_timeout_ms=250)
        for _ in range(2):
            session.start(PAIR)
            self.spin(lambda: session.state == "failed")
            self.assertEqual(session.failure_reason, "startup_timeout")
            self.assertFalse(session.running)

    def test_shutdown_stops_all_owned_previews_before_log_is_closed(self):
        from clickgit.ui import preview_session
        stop_all = getattr(preview_session, "stop_all_previews", None)
        self.assertTrue(callable(stop_all), "Shutdown needs an explicit preview-first boundary")
        from clickgit.diagnostics import DiagnosticLog, set_diagnostics
        with tempfile.TemporaryDirectory() as folder:
            log = DiagnosticLog(Path(folder))
            set_diagnostics(log)
            sessions = [self.session("import sys,time; sys.stdin.buffer.read(); time.sleep(30)")
                        for _ in range(2)]
            try:
                for session in sessions:
                    session.start(PAIR)
                stop_all()
                stop_all()
                self.assertTrue(all(not session.running for session in sessions))
                self.assertTrue(log.flush(2))
                self.assertEqual(log.snapshot().count('"event":"preview_closed"'), 2)
            finally:
                set_diagnostics(None)
                log.close()


    def test_start_failure_and_repeated_close_are_safe(self):
        session = self.session("")
        session.command = [str(Path(sys.executable).parent / "missing-preview-executable.exe")]
        session.start(PAIR)
        self.spin(lambda: session.state == "failed")
        self.assertEqual(session.failure_reason, "start_failed")
        session.stop()
        session.stop()

    def test_bad_protocol_and_output_flood_are_bounded(self):
        for body in ("b'not-json\\n'", "b'x'*100000"):
            with self.subTest(body=body):
                session = self.session(
                    "import sys,time; sys.stdin.buffer.read(); "
                    f"sys.stdout.buffer.write({body}); sys.stdout.buffer.flush(); time.sleep(30)")
                session.start(PAIR)
                self.spin(lambda: session.state == "failed")
                self.assertEqual(session.failure_reason, "invalid_protocol")

    def test_material_only_travels_in_stdin_not_command(self):
        session = self.session("import sys; sys.stdin.buffer.read(); sys.exit(0)")
        session.start(PAIR)
        self.assertNotIn("PRIVATE", " ".join(session.command))
        self.spin(lambda: not session.running)

    def test_loaded_but_unresponsive_child_has_independent_heartbeat_deadline(self):
        session = self.session(
            "import sys,time; sys.stdin.buffer.read(); "
            f"sys.stdout.write({READY!r}); sys.stdout.flush(); time.sleep(60)",
            heartbeat_timeout_ms=200)
        session.start(PAIR)
        self.spin(lambda: session.state == "ready")
        self.spin(lambda: session.state == "failed")
        self.assertEqual(session.failure_reason, "heartbeat_timeout")

    def test_ticks_cannot_extend_startup_deadline(self):
        session = self.session(
            "import sys,time; sys.stdin.buffer.read()\n"
            "while True:\n print('{\"event\":\"tick\"}',flush=True); time.sleep(.01)",
            startup_timeout_ms=300)
        session.start(PAIR)
        self.spin(lambda: session.state == "failed")
        self.assertEqual(session.failure_reason, "startup_timeout")

    def test_windows_ownership_failure_never_sends_material(self):
        session = self.session("import sys; sys.stdin.buffer.read(); sys.exit(0)")
        with patch("clickgit.ui.preview_session.ProcessTree", side_effect=OSError(5, "PRIVATE")), \
                patch("clickgit.ui.preview_session._record") as record:
            session.start(PAIR)
            self.spin(lambda: session.state == "failed")
        failure = [call.kwargs for call in record.call_args_list if call.args == ("preview_failed",)]
        self.assertEqual(failure[0]["error_code"], 5)
        self.assertNotIn("PRIVATE", repr(failure))
        self.assertEqual(session.failure_reason, "ownership_failed")
        self.assertEqual(session._request, b"")

    def test_reject_and_baseline_switch_stop_the_owned_session(self):
        dialog = HtmlReviewDialog(PAIR, baselines=(("base", PAIR.left), ("new", PAIR.right)))
        try:
            with patch.object(dialog.preview_session, "stop") as stop:
                dialog.baseline_combo.setCurrentIndex(1)
                self.assertTrue(stop.called)
                stop.reset_mock()
                dialog.reject()
                self.assertTrue(stop.called)
        finally:
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    @unittest.skipUnless(sys.platform == "win32", "Windows Job Object ownership")
    def test_timeout_kills_only_owned_child_tree(self):
        import ctypes
        from ctypes import wintypes
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            pidfile = Path(folder) / "synthetic-child-pid.txt"
            code = (
                "import sys,subprocess,time,pathlib; sys.stdin.buffer.read(); "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],"
                "creationflags=subprocess.CREATE_NO_WINDOW); "
                f"pathlib.Path({str(pidfile)!r}).write_text(str(child.pid)); "
                f"sys.stdout.write({READY!r}); sys.stdout.flush(); time.sleep(60)"
            )
            session = self.session(code, heartbeat_timeout_ms=500)
            session.start(PAIR)
            self.spin(lambda: pidfile.exists() and session.state == "ready")
            pid = int(pidfile.read_text())
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            self.assertTrue(handle)
            try:
                self.spin(lambda: session.state == "failed")
                def exited():
                    code = wintypes.DWORD()
                    self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
                    return code.value != 259
                self.spin(exited)
                self.assertEqual(session.failure_reason, "heartbeat_timeout")
            finally:
                kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
