import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from clickgit.app import AppController, RepositorySnapshot
from clickgit.document_workflow import TextComparison
from clickgit.document_workflow import ComparisonList
from clickgit.ui.document_dialogs import DocumentComparisonDialog
from clickgit.models import ChangeKind, FileChange
from clickgit.settings import SettingsStore
from clickgit.ui.main_window import MainWindow


class DocumentUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

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

    def test_workspace_default_is_side_by_side_with_raw_tab(self):
        self.assertEqual(self.window.diff_tabs.tabText(0), "左右对比")
        self.assertEqual(self.window.diff_tabs.tabText(1), "原始差异")
        self.assertTrue(self.window.document_viewer.left_editor.isReadOnly())

    def test_refresh_clears_old_preview(self):
        self.window._apply_document(TextComparison("old.md", "before", "after", "原", "新"), "old raw")
        self.window._populate_changes(())
        self.assertEqual(self.window.diff_editor.toPlainText(), "")
        self.assertEqual(self.window.document_viewer.right_editor.toPlainText(), "")

    def test_workspace_merge_controls_are_visible_only_during_merge(self):
        self.window.show()
        snapshot = RepositorySnapshot(Path(self.temp.name), "main", (), (), merge_active=True)
        self.window._apply_snapshot(snapshot)
        self.assertFalse(self.window.merge_bar.isHidden())
        self.assertFalse(self.window.merge_review_button.isHidden())
        snapshot = RepositorySnapshot(Path(self.temp.name), "main", (), (), merge_active=False)
        self.window._apply_snapshot(snapshot)
        self.assertTrue(self.window.merge_bar.isHidden())

    def test_conflict_selection_shows_discoverable_action(self):
        change = FileChange("需求.md", ChangeKind.CONFLICTED, conflicted=True)
        with patch.object(self.controller, "load_document"):
            self.window._populate_changes((change,))
            item = self.window.change_tree.topLevelItem(0).child(0)
            self.window.change_tree.setCurrentItem(item)
            self.assertTrue(self.window.resolve_button.isEnabled())

    def test_history_has_content_comparison_entry(self):
        self.assertEqual(self.window.history_compare_button.text(), "查看内容变化")

    def test_late_document_callback_after_selection_change_is_ignored(self):
        self.controller.repository = SimpleNamespace(path=Path(self.temp.name))
        callbacks = []
        received = []
        self.controller.document_ready.connect(lambda *args: received.append(args))
        with patch.object(self.controller, "_submit", side_effect=lambda *args, **kwargs: callbacks.append(kwargs["on_success"])):
            self.controller.load_document("旧.md")
            self.controller.invalidate_document()
        callbacks[0]((TextComparison("旧.md", "a", "b", "原", "新"), "raw"))
        self.assertEqual(received, [])

    def test_late_comparison_callback_after_repository_change_is_ignored(self):
        self.controller.repository = SimpleNamespace(path=Path(self.temp.name))
        callbacks = []
        received = []
        self.controller.comparison_ready.connect(received.append)
        with patch.object(self.controller, "_submit", side_effect=lambda *args, **kwargs: callbacks.append(kwargs["on_success"])):
            self.controller.load_comparison("HEAD~1", "HEAD")
        self.controller.repository = None
        callbacks[0]("stale")
        self.assertEqual(received, [])

    def test_ordinary_commit_disabled_while_merge_is_active(self):
        self.window.repository_path = Path(self.temp.name)
        self.window._merge_active = True
        self.window._populate_changes((FileChange("需求.md", ChangeKind.MODIFIED, staged=True),))
        self.window.commit_message.setPlainText("不能绕过审阅")
        self.window._update_commit_enabled()
        self.assertFalse(self.window.commit_button.isEnabled())

    def test_frozen_diagnostic_advertises_document_features_without_version_change(self):
        source = (Path(__file__).resolve().parents[1] / "src/clickgit/__main__.py").read_text("utf-8")
        self.assertIn('"document_compare_available"', source)
        self.assertIn('"reviewed_merge_available"', source)

    def test_zoom_only_available_for_loaded_text_and_merge_hides_commit_form(self):
        self.assertFalse(self.window.zoom_diff_button.isEnabled())
        self.window._apply_document(TextComparison("需求.md", "原", "新", "原版本", "新版本"), "")
        self.assertTrue(self.window.zoom_diff_button.isEnabled())
        self.window._populate_changes(())
        self.assertFalse(self.window.zoom_diff_button.isEnabled())
        snapshot = RepositorySnapshot(Path(self.temp.name), "main", (), (), merge_active=True)
        self.window._apply_snapshot(snapshot)
        self.assertTrue(self.window.commit_form.isHidden())

    def test_unsupported_pair_never_says_contents_are_equal(self):
        self.window._apply_document(TextComparison("图片.bin", "", "", "原", "新", "二进制不能比较", False), "")
        self.assertNotIn("内容相同", self.window.document_viewer.status_label.text())
        self.assertIn("二进制", self.window.document_viewer.status_label.text())

    def test_merge_confirmation_disabled_until_all_files_loaded(self):
        listing = ComparisonList(self.temp.name, "检查", "a", "b", ("a.md", "b.md"), "原", "新")
        with patch.object(self.controller, "load_comparison_file"):
            dialog = DocumentComparisonDialog(self.controller, listing, action_text="完成合并")
            dialog.acknowledge.setChecked(True)
            self.assertFalse(dialog.action_button.isEnabled())
            dialog._apply(listing, TextComparison("a.md", "a", "b", "原", "新"), dialog._request_id)
            self.assertFalse(dialog.action_button.isEnabled())
            dialog.files.setCurrentRow(1)
            dialog._apply(listing, TextComparison("b.md", "a", "c", "原", "新"), dialog._request_id)
            self.assertFalse(dialog.action_button.isEnabled())
            dialog.acknowledge.setChecked(True)
            self.assertTrue(dialog.action_button.isEnabled())
            dialog.reject()
            dialog.deleteLater()

    def test_unsupported_or_overbudget_preview_cannot_be_confirmed(self):
        listing = ComparisonList(self.temp.name, "检查", "a", "b", ("a.md",), "原", "新")
        with patch.object(self.controller, "load_comparison_file"):
            dialog = DocumentComparisonDialog(self.controller, listing, action_text="完成合并")
            dialog._apply(listing, TextComparison("a.md", "", "", "原", "新", "二进制", False), dialog._request_id)
            dialog.acknowledge.setChecked(True)
            self.assertFalse(dialog.action_button.isEnabled())
            self.assertNotIn("内容相同", dialog.viewer.status_label.text())
            dialog._apply(listing, TextComparison("a.md", "", "a" * 9000, "原", "新"), dialog._request_id)
            dialog.acknowledge.setChecked(True)
            self.assertFalse(dialog.action_button.isEnabled())
            dialog.reject()
            dialog.deleteLater()

    def test_switch_repository_immediately_clears_old_document(self):
        self.window._apply_document(TextComparison("old.md", "原", "旧", "原", "新"), "raw")
        self.window._repository_changed(Path(self.temp.name) / "other")
        self.assertEqual(self.window.document_viewer.right_editor.toPlainText(), "")
        self.assertFalse(self.window.zoom_diff_button.isEnabled())

    def test_comparison_failure_allows_retry_but_stale_failure_is_ignored(self):
        listing = ComparisonList(self.temp.name, "检查", "a", "b", ("a.md",), "原", "新")
        with patch.object(self.controller, "load_comparison_file"):
            dialog = DocumentComparisonDialog(self.controller, listing, action_text="完成合并")
            request = dialog._request_id
            dialog._failed(listing, "a.md", request, "文件读取失败")
            self.assertIn("文件读取失败", dialog.viewer.status_label.text())
            self.assertFalse(dialog.retry_button.isHidden())
            dialog._load("a.md")
            dialog._failed(listing, "a.md", request, "旧失败")
            self.assertNotIn("旧失败", dialog.viewer.status_label.text())
            pair = TextComparison("a.md", "a", "b", "原", "新")
            dialog._apply(listing, pair, dialog._request_id)
            dialog.acknowledge.setChecked(True)
            self.assertTrue(dialog.action_button.isEnabled())
            dialog.reject()
            dialog.deleteLater()

    def test_raw_diff_rejects_huge_line_before_computing(self):
        self.controller.repository = SimpleNamespace(path=Path(self.temp.name))
        jobs = []
        received = []
        self.controller.document_ready.connect(lambda *args: received.append(args))
        pair = TextComparison("large.md", "a" * 100000, "b" * 100000, "原", "新")
        with patch.object(self.controller, "_submit", side_effect=lambda *args, **kw: jobs.append((args[1], kw["on_success"]))):
            self.controller.load_document("large.md")
        with patch("clickgit.app.DocumentWorkflow") as flow, patch("clickgit.app.difflib.unified_diff") as diff:
            flow.return_value.workspace.return_value = pair
            jobs[0][1](jobs[0][0]())
        diff.assert_not_called()
        self.assertLess(len(received[0][1]), 200)

    def test_document_failure_ends_loading_without_stale_error(self):
        self.controller.repository = SimpleNamespace(path=Path(self.temp.name))
        jobs = []
        with patch.object(self.controller, "_submit", side_effect=lambda *args, **kw: jobs.append((args[1], kw["on_success"]))):
            self.controller.load_document("a.md")
        with patch("clickgit.app.DocumentWorkflow") as flow:
            flow.return_value.workspace.side_effect = ValueError("读取失败")
            result = jobs[0][0]()
        jobs[0][1](result)
        self.assertIn("读取失败", self.window.document_viewer.status_label.text())
        self.window.document_viewer.clear("新选择")
        self.controller.invalidate_document()
        jobs[0][1](result)
        self.assertEqual(self.window.document_viewer.status_label.text(), "新选择")


if __name__ == "__main__":
    unittest.main()
