import importlib
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from clickgit.diagnostics import DiagnosticLog, set_diagnostics


class DiagnosticsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = DiagnosticLog(self.root)
        self.addCleanup(self.log.close)
        self.assertTrue(callable(getattr(self.log, "flush", None)), "async flush API is required")
        self.log.flush(timeout=2)
        set_diagnostics(self.log)
        self.addCleanup(set_diagnostics, None)

    def api(self):
        try:
            return importlib.import_module("clickgit.ui.diagnostics_dialog")
        except ModuleNotFoundError:
            self.fail("clickgit.ui.diagnostics_dialog has not been implemented")

    def dialog(self):
        dialog = self.api().DiagnosticsDialog()
        self.addCleanup(self.dispose, dialog)
        return dialog

    @staticmethod
    def dispose(widget):
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_readonly_view_explicit_privacy_notice_and_no_automatic_copy(self):
        clipboard = self.app.clipboard()
        with patch.object(clipboard, "setText") as copied:
            self.log.record("app_start", config_path="C:/Users/local/settings.json")
            dialog = self.dialog()
        copied.assert_not_called()
        self.assertTrue(dialog.viewer.isReadOnly())
        self.assertIn("app_start", dialog.viewer.toPlainText())
        self.assertIn("本机", dialog.privacy_notice.text())
        self.assertIn("路径", dialog.privacy_notice.text())
        self.assertIn("不会自动上传", dialog.privacy_notice.text())
        self.assertEqual(dialog.status_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertIn(str(self.log.path), dialog.status_label.text())
        self.assertTrue(dialog.copy_button.isEnabled())

    def test_manual_refresh_and_copy_use_only_displayed_snapshot(self):
        dialog = self.dialog()
        self.log.record("preview_ready", elapsed_ms=88)
        self.assertNotIn("preview_ready", dialog.viewer.toPlainText())
        dialog.refresh_button.click()
        self.assertIn("preview_ready", dialog.viewer.toPlainText())
        with patch.object(self.app.clipboard(), "setText") as copied:
            dialog.copy_button.click()
        copied.assert_called_once_with(dialog.viewer.toPlainText())

    def test_unconfigured_is_explicit_and_does_not_create_default_storage(self):
        set_diagnostics(None)
        with patch("clickgit.diagnostics.DiagnosticLog") as constructor:
            dialog = self.dialog()
        constructor.assert_not_called()
        self.assertIn("未启用", dialog.viewer.toPlainText())
        self.assertFalse(dialog.copy_button.isEnabled())
        set_diagnostics(self.log)
        self.log.record("preview_start")
        dialog.refresh_button.click()
        self.assertTrue(dialog.copy_button.isEnabled())
        self.assertIn("preview_start", dialog.viewer.toPlainText())

    def test_closed_log_is_explicit_and_filtered_memory_can_be_copied(self):
        self.log.record("preview_failed", reason="start_failed", message="SECRET")
        self.log.flush(timeout=2)
        self.log.close()
        dialog = self.dialog()
        self.assertIn("不可用", dialog.viewer.toPlainText())
        self.assertIn("不可用", dialog.status_label.text())
        self.assertTrue(dialog.copy_button.isEnabled())
        self.assertNotIn("SECRET", dialog.viewer.toPlainText())
        with patch.object(self.app.clipboard(), "setText") as copied:
            dialog.copy_button.click()
        copied.assert_called_once_with(dialog.viewer.toPlainText())

    def test_writer_error_still_allows_copy_and_reports_unavailable(self):
        self.log.record("preview_start")
        self.log.flush(timeout=2)
        dialog = self.dialog()
        with patch("clickgit.diagnostics._FileWriter.write", side_effect=OSError("SECRET")):
            self.log.record("preview_failed", reason="render_failed")
            self.assertFalse(self.log.flush(timeout=2))
            dialog.refresh_button.click()
        self.assertNotIn("SECRET", dialog.viewer.toPlainText())
        self.assertIn("不可用", dialog.viewer.toPlainText())
        self.assertTrue(dialog.copy_button.isEnabled())
        with patch.object(self.app.clipboard(), "setText") as copied:
            dialog.copy_button.click()
        copied.assert_called_once_with(dialog.viewer.toPlainText())

    def test_refresh_only_reads_memory_not_disk(self):
        dialog = self.dialog()
        self.log.record("preview_ready")
        self.log.flush(timeout=2)
        with patch.object(Path, "open", side_effect=AssertionError("no GUI file reads")):
            dialog.refresh_button.click()
        self.assertIn("preview_ready", dialog.viewer.toPlainText())

    def test_pending_is_not_misreported_as_unavailable(self):
        release = threading.Event()
        original = Path.mkdir

        def slow_mkdir(path, *args, **kwargs):
            release.wait(2)
            return original(path, *args, **kwargs)

        with patch.object(Path, "mkdir", slow_mkdir):
            pending = DiagnosticLog(self.root / "pending")
            self.addCleanup(pending.close)
            set_diagnostics(pending)
            try:
                pending.record("preview_failed", reason="startup_timeout", message="SECRET")
                dialog = self.dialog()
                self.assertIn("初始化中", dialog.status_label.text())
                self.assertNotIn("不可用", dialog.status_label.text())
                self.assertIn("历史", dialog.privacy_notice.text())
                self.assertIn("内存", dialog.privacy_notice.text())
                self.assertTrue(dialog.copy_button.isEnabled())
                self.assertNotIn("SECRET", dialog.viewer.toPlainText())
                with patch.object(self.app.clipboard(), "setText") as copied:
                    dialog.copy_button.click()
                copied.assert_called_once_with(dialog.viewer.toPlainText())
            finally:
                release.set()
                pending.flush(timeout=2)
        dialog.refresh_button.click()
        self.assertIn("可用", dialog.status_label.text())

    def test_closing_viewer_does_not_close_shared_log(self):
        dialog = self.dialog()
        dialog.close()
        self.log.record("preview_closed", reason="closed")
        self.assertTrue(self.log.available)
        self.assertIn("preview_closed", self.log.snapshot())

    def test_show_helper_uses_parent_and_disposes_modal_without_external_open(self):
        api = self.api()
        parent = QWidget()
        self.addCleanup(self.dispose, parent)
        seen = []

        def run(dialog):
            seen.append(dialog.parent() is parent)
            return QDialog.DialogCode.Rejected

        with patch.object(api.DiagnosticsDialog, "exec", run), \
                patch("PySide6.QtGui.QDesktopServices.openUrl") as external:
            api.show_diagnostics(parent)
        self.assertEqual(seen, [True])
        external.assert_not_called()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
