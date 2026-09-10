import importlib
import io
import json
import logging
import sys
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def api(self):
        # A missing new module is an explicit feature failure, not a collection error.
        try:
            module = importlib.import_module("clickgit.diagnostics")
        except ModuleNotFoundError:
            self.fail("clickgit.diagnostics has not been implemented")
        self.addCleanup(module.set_diagnostics, None)
        return module

    def log(self):
        log = self.api().DiagnosticLog(self.root)
        self.addCleanup(log.close)
        self.assertTrue(callable(getattr(log, "flush", None)), "async flush API is required")
        log.flush(timeout=2)
        return log

    def rows(self, log):
        log.flush(timeout=2)
        return [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]

    def test_creates_log_and_writes_fixed_startup_identity(self):
        log = self.log()
        log.record("app_start", executable_path="C:/ClickGit/ClickGit.exe",
                   config_path="C:/Users/local/ClickGit/settings.json",
                   build="secret-build", version="secret-version")
        self.assertTrue(log.available)
        self.assertEqual(log.path, self.root / "diagnostics" / "clickgit.log")
        row = self.rows(log)[0]
        self.assertEqual(row["event"], "app_start")
        self.assertEqual(row["version"], "0.2.0")
        self.assertEqual(row["build"], "2026-09-10-source-inline-highlight")
        self.assertEqual(str(uuid.UUID(row["session_id"])), log.session_id)
        self.assertIs(type(row["pid"]), int)
        self.assertEqual(row["executable_path"], "C:/ClickGit/ClickGit.exe")
        self.assertIn("timestamp", row)

    def test_preview_events_preserve_typed_correlation_fields_only(self):
        log = self.log()
        session = str(uuid.uuid4())
        for event in ("preview_start", "preview_ready", "preview_failed", "preview_closed"):
            log.record(event, session_id=session, pid=123, exit_code=-9,
                       elapsed_ms=4, bytes_left=12, bytes_right=24, reason="timeout")
        for row in self.rows(log):
            self.assertEqual(row["session_id"], session)
            self.assertEqual(row["pid"], 123)
            self.assertEqual(row["elapsed_ms"], 4)
            self.assertEqual(row["reason"], "timeout")
        self.assertEqual(self.rows(log)[-1]["exit_code"], -9)

    def test_rejects_messages_html_keys_repo_paths_unknown_events_and_wrong_types(self):
        log = self.log()
        log.record("SECRET event")
        log.record("preview_failed", reason="SECRET failure", message="SECRET",
                   html="<html>SECRET</html>", key="SECRET", repo_path="D:/SECRET",
                   executable_path="D:/SECRET", config_path="D:/SECRET",
                   session_id="SECRET", pid=True, exit_code="1", elapsed_ms=-1,
                   bytes_left=True, bytes_right=1.5,
                   exception_type="SECRET", frames=[{"file": "SECRET"}])
        row = self.rows(log)[0]
        self.assertEqual(len(self.rows(log)), 1)
        for key in ("reason", "message", "html", "key", "repo_path", "executable_path",
                    "config_path", "exit_code", "elapsed_ms", "bytes_left", "bytes_right",
                    "exception_type", "frames"):
            self.assertNotIn(key, row)
        self.assertIs(type(row["pid"]), int)
        self.assertNotIn("SECRET", log.snapshot())

    def test_config_schema_types_do_not_leak_invalid_values_or_disable_logging(self):
        log = self.log()
        for schema_type in ("missing", "int", "str", "bool", "float", "dict", "list", "null"):
            log.record("config_loaded", schema_type=schema_type, schema_value="SECRET",
                       expected_schema=1, settings_read_only=True)
        log.record("config_loaded", schema_type="SECRET", schema_value=True,
                   expected_schema=True, settings_read_only="SECRET")
        log.record("config_loaded", schema_type="int", schema_value=99)
        self.assertTrue(log.available)
        self.assertNotIn("SECRET", log.snapshot())
        rows = self.rows(log)
        self.assertTrue(all("schema_value" not in row for row in rows[:-1]))
        self.assertEqual(rows[-1]["schema_value"], 99)
        self.assertTrue(rows[0]["settings_read_only"])

    def test_supervisor_failure_reasons_are_preserved(self):
        log = self.log()
        reasons = ("start_failed", "ownership_failed", "startup_timeout", "heartbeat_timeout",
                   "process_exit", "invalid_protocol", "invalid_input", "render_failed")
        for reason in reasons:
            log.record("preview_failed", reason=reason)
        self.assertEqual([row.get("reason") for row in self.rows(log)], list(reasons))

    def test_supervisor_uuid_hex_session_is_preserved_for_correlation(self):
        log = self.log()
        session = uuid.uuid4().hex
        log.record("preview_start", session_id=session)
        log.record("preview_ready", session_id=session)
        self.assertEqual([row["session_id"] for row in self.rows(log)], [session, session])
        self.assertIn(session, log.snapshot())

    def test_preview_error_code_is_typed_separate_from_exit_code_and_failure_only(self):
        log = self.log()
        log.record("preview_failed", reason="start_failed", error_code=0, exit_code=-9)
        row = self.rows(log)[0]
        self.assertEqual(row.get("error_code"), 0)
        self.assertEqual(row["exit_code"], -9)
        log.record("preview_failed", reason="process_exit", error_code=123)
        self.assertEqual(self.rows(log)[-1].get("error_code"), 123)
        for value in (True, "SECRET error", 1.0, -1, 2**63, None):
            log.record("preview_failed", error_code=value)
            self.assertNotIn("error_code", self.rows(log)[-1])
        for event in ("preview_start", "preview_ready", "preview_closed", "app_start",
                      "config_loaded", "unhandled_exception"):
            log.record(event, error_code=1)
            self.assertNotIn("error_code", self.rows(log)[-1])
        self.assertNotIn("SECRET", log.snapshot())
        self.assertIn('"error_code":123', log.snapshot())

    def test_startup_and_config_paths_reject_relative_control_and_non_string_values(self):
        log = self.log()
        for value in ("settings.json", "C:settings.json", "C:/SECRET\nsettings.json",
                      "<html>SECRET</html>", True, 123, None):
            log.record("app_start", executable_path=value, config_path=value)
            log.record("config_loaded", config_path=value)
        for row in self.rows(log):
            self.assertNotIn("executable_path", row)
            self.assertNotIn("config_path", row)
            self.assertEqual(row["build"], "2026-09-10-source-inline-highlight")
            self.assertEqual(row["version"], "0.2.0")
        self.assertNotIn("SECRET", log.snapshot())

    def test_config_contract_allows_only_config_path_types_and_event_specific_reasons(self):
        log = self.log()
        reasons = ("missing", "read_failed", "invalid_json", "schema_mismatch", "ok")
        for reason in reasons:
            log.record("config_loaded", config_path="C:/ClickGit/settings.json", reason=reason,
                       executable_path="C:/SECRET.exe")
        for schema_type in ("missing", "int", "str", "float", "bool", "null", "list", "dict"):
            log.record("config_loaded", schema_type=schema_type)
        rows = self.rows(log)
        self.assertEqual([row.get("reason") for row in rows[:5]], list(reasons))
        self.assertTrue(all(row.get("config_path") == "C:/ClickGit/settings.json" for row in rows[:5]))
        self.assertEqual([row.get("schema_type") for row in rows[5:]],
                         ["missing", "int", "str", "float", "bool", "null", "list", "dict"])
        log.record("config_loaded", reason="startup_timeout", schema_type="SECRET")
        log.record("preview_failed", reason="invalid_json", config_path="C:/SECRET/settings.json")
        self.assertNotIn("reason", self.rows(log)[-2])
        self.assertNotIn("reason", self.rows(log)[-1])
        self.assertNotIn("SECRET", log.snapshot())

    def test_schema_integer_is_json_safe_not_bool_or_unbounded_integer(self):
        log = self.log()
        for value in (True, False, 1.0, "1", 2**53, -(2**53), 10**1000):
            log.record("config_loaded", schema_value=value)
        log.record("config_loaded", schema_value=2**53 - 1)
        rows = self.rows(log)
        self.assertTrue(all("schema_value" not in row for row in rows[:-1]))
        self.assertEqual(rows[-1]["schema_value"], 2**53 - 1)

    def test_values_are_never_stringified_or_coerced(self):
        class Hostile:
            def __str__(self):
                raise AssertionError("must not stringify")

        log = self.log()
        value = Hostile()
        log.record(value, reason=value)
        log.record("app_start", executable_path=value, config_path=value)
        log.record("preview_failed", reason=value, elapsed_ms=value, session_id=value)
        self.assertEqual(len(self.rows(log)), 2)

    def test_exception_records_type_and_sanitized_frames_never_text_or_locals(self):
        log = self.log()
        try:
            secret_local = "SECRET credentials"
            raise ValueError(secret_local)
        except ValueError:
            log.log_exception(*sys.exc_info())
        row = self.rows(log)[0]
        self.assertEqual(row["event"], "unhandled_exception")
        self.assertEqual(row["exception_type"], "ValueError")
        self.assertTrue(row["frames"])
        for frame in row["frames"]:
            self.assertEqual(set(frame), {"file", "function", "line"})
            self.assertNotIn("/", frame["file"])
            self.assertNotIn("\\", frame["file"])
            self.assertIs(type(frame["line"]), int)
        self.assertNotIn("SECRET", log.path.read_text(encoding="utf-8"))
        self.assertNotIn(str(self.root), log.snapshot())

    def test_caught_operation_exceptions_use_distinct_event_without_business_data(self):
        from clickgit.git_runner import GitCommandError
        from clickgit.models import GitResult
        from clickgit.repository import OperationConflict

        log = self.log()
        result = GitResult(("git", "-C", "D:/SECRET"), self.root / "SECRET", 1,
                           b"SECRET stdout", b"SECRET stderr", 0.1)
        errors = (GitCommandError(result), OperationConflict("SECRET operation", result))
        for error in errors:
            try:
                raise error
            except Exception as exc:
                with patch.object(type(exc), "__str__", side_effect=AssertionError("must not format")):
                    log.log_exception(type(exc), exc, exc.__traceback__, event="operation_failed")
        rows = self.rows(log)
        self.assertEqual([row["event"] for row in rows], ["operation_failed"] * 2)
        self.assertEqual([row["exception_type"] for row in rows],
                         ["GitCommandError", "OperationConflict"])
        self.assertTrue(all(row["frames"] for row in rows))
        for row in rows:
            for frame in row["frames"]:
                self.assertEqual(set(frame), {"file", "function", "line"})
        self.assertNotIn("SECRET", log.snapshot())
        self.assertNotIn("unhandled_exception", log.snapshot())
        self.assertNotIn(str(self.root), log.snapshot())

    def test_global_exception_event_keyword_is_optional_restricted_and_safe_unconfigured(self):
        api = self.api()
        api.set_diagnostics(None)
        api.log_exception(ValueError, ValueError("SECRET"), None, event="operation_failed")
        log = self.log()
        api.set_diagnostics(log)
        api.log_exception(ValueError, ValueError("SECRET"), None, event="operation_failed")
        api.log_exception(TypeError, TypeError("SECRET"), None)
        for event in ("preview_failed", "SECRET", "", None, [], True):
            api.log_exception(ValueError, ValueError("SECRET"), None, event=event)
            log.log_exception(ValueError, ValueError("SECRET"), None, event=event)
        self.assertEqual([row["event"] for row in self.rows(log)],
                         ["operation_failed", "unhandled_exception"])
        self.assertNotIn("SECRET", log.snapshot())

    def test_operation_failed_uses_exception_whitelist_and_survives_history_reload(self):
        log = self.log()
        log.record("operation_failed", exception_type="GitCommandError", frames=[
            {"file": "D:/SECRET/safe.py", "function": "safe", "line": 2, "locals": "SECRET"},
        ], message="SECRET", repo_path="D:/SECRET", html="SECRET", key="SECRET",
            executable_path="D:/SECRET.exe", config_path="D:/SECRET.json", error_code=1)
        rows = self.rows(log)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["event"], "operation_failed")
        self.assertEqual(row["exception_type"], "GitCommandError")
        self.assertEqual(row["frames"], [{"file": "safe.py", "function": "safe", "line": 2}])
        for key in ("message", "repo_path", "html", "key", "executable_path", "config_path", "error_code"):
            self.assertNotIn(key, row)
        log.close()
        reloaded = self.log()
        self.assertIn("operation_failed", reloaded.snapshot())
        self.assertNotIn("SECRET", reloaded.snapshot())

    def test_unknown_exception_and_untrusted_frames_are_bounded(self):
        log = self.log()
        secret_type = type("SECRETException", (Exception,), {})
        log.log_exception(secret_type, secret_type("SECRET message"), None)
        log.record("unhandled_exception", exception_type="SECRETException", frames=[
            {"file": "D:\\SECRET\\safe.py", "function": "safe", "line": 8,
             "locals": "SECRET", "source": "SECRET"} for _ in range(200)
        ])
        log.record("unhandled_exception", exception_type="<SECRET>", frames=[
            {"file": "<SECRET>", "function": "<SECRET>", "line": True},
        ])
        rows = self.rows(log)
        self.assertEqual(rows[0]["exception_type"], "UnknownException")
        self.assertLessEqual(len(rows[1]["frames"]), 16)
        self.assertEqual(rows[1]["frames"][0], {"file": "safe.py", "function": "safe", "line": 8})
        self.assertNotIn("SECRET", log.snapshot())

    def test_unconfigured_global_functions_are_safe_and_configured_log_is_used(self):
        api = self.api()
        api.set_diagnostics(None)
        self.assertIsNone(api.get_diagnostics())
        api.record_event("app_start")
        api.log_exception(ValueError, ValueError("SECRET"), None)
        log = self.log()
        api.set_diagnostics(log)
        self.assertIs(api.get_diagnostics(), log)
        api.record_event("preview_ready", elapsed_ms=12)
        api.log_exception(TypeError, TypeError("SECRET"), None)
        self.assertEqual([row["event"] for row in self.rows(log)],
                         ["preview_ready", "unhandled_exception"])

    def test_unwritable_directory_reports_unavailable_without_exception_text(self):
        self.root.joinpath("diagnostics").write_text("occupied", encoding="utf-8")
        log = self.log()
        self.assertFalse(log.available)
        self.assertIn("不可用", log.snapshot())
        log.record("app_start")
        log.close()
        log.close()

    def test_write_failure_is_silent_and_changes_availability(self):
        log = self.log()
        with patch("clickgit.diagnostics._FileWriter.write", side_effect=OSError("SECRET")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            log.record("preview_start")
            self.assertFalse(log.flush(timeout=2))
        self.assertFalse(log.available)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("不可用", log.snapshot())
        self.assertNotIn("SECRET", log.snapshot())

    def test_rotation_error_path_never_prints_traceback(self):
        log = self.log()
        with patch("clickgit.diagnostics._FileWriter.rotate",
                   side_effect=OSError("SECRET")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            for _ in range(70):
                log.record("app_start", config_path="C:/" + "界" * 2000 + "/settings.json")
            self.assertFalse(log.flush(timeout=2))
        self.assertFalse(log.available)
        self.assertEqual(stderr.getvalue(), "")

    def test_close_is_terminal_idempotent_and_does_not_change_root_logging(self):
        before = tuple(logging.getLogger().handlers)
        log = self.log()
        log.record("app_start")
        self.assertTrue(log.flush(timeout=2))
        original = log.path.read_bytes()
        log.close()
        log.close()
        log.record("app_start")
        self.assertFalse(log.available)
        self.assertEqual(log.path.read_bytes(), original)
        self.assertEqual(tuple(logging.getLogger().handlers), before)

    def test_rotation_has_three_bounded_files_and_snapshot_is_bounded(self):
        log = self.log()
        for _ in range(400):
            log.record("app_start", executable_path="C:/" + "界" * 1000 + "/ClickGit.exe",
                       config_path="C:/" + "文" * 1000 + "/settings.json")
        self.assertTrue(log.flush(timeout=2))
        files = sorted(log.path.parent.glob("clickgit.log*"))
        self.assertEqual([path.name for path in files], ["clickgit.log", "clickgit.log.1", "clickgit.log.2"])
        for path in files:
            self.assertLessEqual(path.stat().st_size, 512 * 1024)
            self.assertTrue(all(json.loads(line)["event"] == "app_start"
                                for line in path.read_text(encoding="utf-8").splitlines()))
        self.assertLessEqual(len(log.snapshot().encode("utf-8")), 64 * 1024)
        self.assertIn("app_start", log.snapshot())

    def test_snapshot_does_not_read_quarantine_or_untrusted_legacy_text(self):
        log = self.log()
        log.record("preview_ready")
        self.assertTrue(log.flush(timeout=2))
        log.close()
        log.path.parent.joinpath("settings.json.corrupt").write_text("SECRET", encoding="utf-8")
        with log.path.open("a", encoding="utf-8") as stream:
            stream.write("SECRET legacy text\n")
            stream.write(json.dumps({"event": "preview_failed", "message": "SECRET",
                                     "reason": "SECRET"}) + "\n")
        log = self.log()
        self.assertNotIn("SECRET", log.snapshot())
        self.assertIn("preview_ready", log.snapshot())

    def test_history_read_failure_is_explicit_and_safe(self):
        log = self.log()
        log.close()
        with patch.object(Path, "open", side_effect=PermissionError("SECRET")):
            log = self.log()
            snapshot = log.snapshot()
        self.assertIn("不可用", snapshot)
        self.assertNotIn("SECRET", snapshot)
        self.assertFalse(log.available)

    def test_concurrent_threads_write_complete_records(self):
        log = self.log()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda number: log.record("preview_ready", elapsed_ms=number), range(200)))
        self.assertEqual(len(self.rows(log)), 200)
        self.assertEqual({row["elapsed_ms"] for row in self.rows(log)}, set(range(200)))

    def test_record_snapshot_flush_timeout_and_close_do_not_wait_for_slow_disk(self):
        log = self.log()
        entered, release = threading.Event(), threading.Event()

        def slow_write(writer, line):
            entered.set()
            release.wait(3)

        with patch("clickgit.diagnostics._FileWriter.write", slow_write):
            log.record("preview_start")
            self.assertTrue(entered.wait(1))
            try:
                started = time.monotonic()
                for number in range(400):
                    log.record("preview_ready", elapsed_ms=number)
                snapshot = log.snapshot()
                self.assertLess(time.monotonic() - started, 0.5)
                self.assertGreater(log.dropped_records, 0)
                self.assertIn("preview_ready", snapshot)
                self.assertIn("丢弃", snapshot)
                self.assertLessEqual(len(snapshot.encode("utf-8")), 64 * 1024)
                self.assertFalse(log.flush(timeout=0.01))
                started = time.monotonic()
                log.close()
                self.assertLess(time.monotonic() - started, 0.5)
                self.assertFalse(log.available)
            finally:
                release.set()
                self.assertTrue(log._finished.wait(2))

    def test_constructor_initializes_directory_only_in_background(self):
        api = self.api()
        release = threading.Event()
        original = Path.mkdir

        def slow_mkdir(path, *args, **kwargs):
            release.wait(2)
            return original(path, *args, **kwargs)

        with patch.object(Path, "mkdir", slow_mkdir):
            started = time.monotonic()
            log = api.DiagnosticLog(self.root)
            elapsed = time.monotonic() - started
            self.addCleanup(log.close)
            try:
                self.assertLess(elapsed, 0.5)
                self.assertEqual(log.status, "pending")
                self.assertFalse(log.available)
                log.record("app_start")
                self.assertIn("初始化中", log.snapshot())
            finally:
                release.set()
                if callable(getattr(log, "flush", None)):
                    log.flush(timeout=2)
        self.assertEqual(log.status, "available")
        self.assertEqual(self.rows(log)[0]["event"], "app_start")

    def test_permission_denied_initialization_and_callbacks_are_bounded_and_silent(self):
        api = self.api()
        with patch.object(Path, "mkdir", side_effect=PermissionError("SECRET permission")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            started = time.monotonic()
            log = api.DiagnosticLog(self.root)
            self.addCleanup(log.close)
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertFalse(log.flush(timeout=2))
            self.assertEqual(log.status, "unavailable")
            started = time.monotonic()
            log.record("preview_failed", error_code=5, reason="start_failed")
            snapshot = log.snapshot()
            log.close()
            self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("不可用", snapshot)
        self.assertNotIn("SECRET", snapshot)
        self.assertFalse(log.available)

    def test_snapshot_has_no_file_io_and_contains_previous_run_records(self):
        previous = self.log()
        previous.record("preview_failed", reason="startup_timeout")
        self.assertTrue(previous.flush(timeout=2))
        previous.close()
        current = self.log()
        current.record("preview_ready")
        self.assertTrue(current.flush(timeout=2))
        with patch.object(Path, "open", side_effect=AssertionError("no GUI disk reads")):
            snapshot = current.snapshot()
        self.assertIn("startup_timeout", snapshot)
        self.assertIn("preview_ready", snapshot)
        self.assertTrue(current.available)

    def test_flush_timeout_validation_cannot_overflow_or_wait_unbounded(self):
        log = self.log()
        for value in (None, True, "1", float("inf"), float("nan")):
            self.assertFalse(log.flush(timeout=value))
        self.assertTrue(log.flush(timeout=10**1000))
        self.assertTrue(log.flush(timeout=0))


if __name__ == "__main__":
    unittest.main()
