import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from clickgit.settings import SettingsStore


class DiagnosticIntegrationTests(unittest.TestCase):
    def test_startup_exception_is_logged_and_hooks_are_restored(self):
        import sys
        from clickgit import __main__ as entry
        from clickgit.diagnostics import DiagnosticLog, get_diagnostics
        logs = []
        def create_log(path):
            log = DiagnosticLog(path)
            logs.append(log)
            return log
        old_hooks = sys.excepthook, threading.excepthook
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(sys, "argv", ["clickgit"]), \
                patch.object(entry, "application_data_dir", return_value=Path(folder)), \
                patch.object(entry, "bundled_git_executable", return_value=Path("synthetic-git")), \
                patch("clickgit.diagnostics.DiagnosticLog", side_effect=create_log), \
                patch("clickgit.app.AppController", side_effect=RuntimeError("PRIVATE_STARTUP")):
            try:
                self.assertEqual(entry.main(), 1)
                self.assertEqual((sys.excepthook, threading.excepthook), old_hooks)
                self.assertIsNone(get_diagnostics())
                self.assertIn("unhandled_exception", logs[0].snapshot())
                self.assertNotIn("PRIVATE_STARTUP", logs[0].snapshot())
                self.assertEqual(logs[0].status, "closed")
            finally:
                sys.excepthook, threading.excepthook = old_hooks
                for log in logs:
                    log.close()

    def test_caught_operation_failure_is_logged_without_changing_error_signal(self):
        from clickgit.app import AppController
        future = Future()
        error = RuntimeError("PRIVATE_OPERATION")
        future.set_exception(error)
        controller = MagicMock()
        controller._pending = 1
        controller._pending_lock = threading.Lock()
        with patch("clickgit.diagnostics.log_exception") as logged:
            AppController._finish_future(controller, future, None, "")
        logged.assert_called_once()
        self.assertEqual(logged.call_args.kwargs, {"event": "operation_failed"})
        controller.operation_failed.emit.assert_called_once_with("操作失败", "PRIVATE_OPERATION")
        self.assertEqual(controller._pending, 0)

    def test_config_diagnostic_describes_actual_read_without_private_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            text = json.dumps({"schema_version": "PRIVATE_KEY", "external_editor": "PRIVATE_PATH"})
            path.write_text(text, encoding="utf-8")
            with patch("clickgit.diagnostics.record_event") as record:
                store = SettingsStore(path)
                store.load()
            entries = [call.kwargs for call in record.call_args_list
                       if call.args == ("config_loaded",) and call.kwargs.get("config_path") == str(path)]
            self.assertEqual(len(entries), 1, "Log the same bytes the loader validated, not another read")
            self.assertEqual(entries[0]["schema_type"], "str")
            self.assertEqual(entries[0]["reason"], "schema_mismatch")
            self.assertTrue(entries[0]["settings_read_only"])
            self.assertNotIn("schema_value", entries[0])
            self.assertNotIn("PRIVATE", repr(entries))
            self.assertEqual(path.read_text("utf-8"), text)

    def test_config_diagnostic_distinguishes_missing_and_supported_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            for content, reason in ((None, "missing"), ('{"schema_version":1}', "ok")):
                if content:
                    path.write_text(content, encoding="utf-8")
                with patch("clickgit.diagnostics.record_event") as record:
                    SettingsStore(path).load()
                entries = [call.kwargs for call in record.call_args_list
                           if call.kwargs.get("config_path") == str(path)]
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["reason"], reason)
                if content:
                    self.assertEqual(entries[0]["schema_value"], 1)


if __name__ == "__main__":
    unittest.main()
