import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from clickgit.app import AppController
from clickgit.document_workflow import TextComparison, ComparisonList
from clickgit.settings import SettingsStore
from clickgit.ui.main_window import MainWindow
from clickgit.ui.document_dialogs import ExpandedDiffDialog, DocumentComparisonDialog
from clickgit.ui.conflict_editor import ConflictEditorDialog


PAIR = TextComparison("原型.html", "<h2>原</h2>", "<h2>新</h2>", "原版本", "新版本")


class HtmlEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.controller = AppController(settings_store=SettingsStore(Path(self.temp.name) / "settings.json"))
        self.window = MainWindow(self.controller)

    def tearDown(self):
        self.window.close()
        self.controller.shutdown()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def test_workspace_entry_only_for_loaded_html_and_clears_on_refresh(self):
        self.assertFalse(self.window.html_review_button.isEnabled())
        self.window._apply_document(PAIR, "")
        self.assertTrue(self.window.html_review_button.isEnabled())
        with patch("clickgit.ui.main_window.open_html_review") as review:
            self.window.html_review_button.click()
            self.assertEqual(review.call_args.args[0], PAIR)
        self.window._populate_changes(())
        self.assertFalse(self.window.html_review_button.isEnabled())
        self.window._apply_document(TextComparison("需求.md", "a", "b", "a", "b"), "")
        self.assertFalse(self.window.html_review_button.isEnabled())

    def test_expanded_entry_passes_original_pair(self):
        dialog = ExpandedDiffDialog(PAIR)
        with patch("clickgit.ui.document_dialogs.open_html_review") as review:
            dialog.html_review_button.click()
            self.assertEqual(review.call_args.args[0], PAIR)
        dialog.reject()
        dialog.deleteLater()

    def test_merge_review_html_never_bypasses_failed_source_gate(self):
        listing = ComparisonList(self.temp.name, "检查", "a", "b", ("原型.html",), "原", "新")
        with patch.object(self.controller, "load_comparison_file"):
            dialog = DocumentComparisonDialog(self.controller, listing, action_text="完成合并")
        try:
            self.assertFalse(dialog.html_review_button.isEnabled())
            too_long = TextComparison(PAIR.path, "x" * 9000, "<p>新</p>", "原", "新")
            dialog._apply(listing, too_long, dialog._request_id)
            dialog.acknowledge.setChecked(True)
            self.assertFalse(dialog.action_button.isEnabled())
            self.assertTrue(dialog.html_review_button.isEnabled())
            dialog._failed(listing, PAIR.path, dialog._request_id, "读取失败")
            self.assertFalse(dialog.html_review_button.isEnabled())
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_conflict_check_uses_unsaved_buffer_and_three_baselines(self):
        dialog = ConflictEditorDialog(
            file_path="需求.html", base_text="<p>基准</p>", ours_text="<p>当前</p>",
            theirs_text="<p>对方</p>", result_text="<p>结果</p>")
        try:
            dialog.result_editor.setPlainText("<p>尚未保存</p>")
            with patch("clickgit.ui.conflict_editor.open_html_review") as review:
                dialog.html_review_button.click()
                self.assertEqual(review.call_args.args[0].right, "<p>尚未保存</p>")
                self.assertEqual(len(review.call_args.kwargs["baselines"]), 3)
            self.assertFalse(dialog.mark_resolved)
            dialog.set_saving(True)
            self.assertFalse(dialog.html_review_button.isEnabled())
            dialog.set_saving(False)
        finally:
            dialog.reject()
            dialog.deleteLater()

    def test_packaging_does_not_exclude_preview_engine(self):
        spec = (Path(__file__).resolve().parents[1] / "installer/clickgit.spec").read_text("utf-8")
        excludes = spec.split("excludes=[", 1)[1].split("]", 1)[0]
        self.assertNotIn("QtWebEngineCore", excludes)
        self.assertNotIn("QtWebEngineWidgets", excludes)


if __name__ == "__main__":
    unittest.main()
