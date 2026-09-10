"""Current-product contract: Git and HTML review without any AI subsystem."""
import dataclasses
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from clickgit.app import AppController
from clickgit.models import AppSettings
from clickgit.settings import SettingsStore
from clickgit.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]


class ProductWithoutAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = SettingsStore(Path(directory.name) / "settings.json")
        self.controller = AppController(settings_store=self.store)
        self.addCleanup(self.controller.shutdown)
        self.window = MainWindow(self.controller)
        self.addCleanup(self.window.close)

    def test_navigation_and_settings_work_without_repository(self):
        labels = [self.window.navigation.item(i).text()
                  for i in range(self.window.navigation.count())]
        self.assertEqual(labels, ["工作区", "提交历史", "分支", "标签", "贮藏记录",
                                  "远程仓库", "恢复中心", "高级操作", "设置"])
        self.assertEqual(self.window.pages.count(), len(labels))
        self.window.navigation.setCurrentRow(8)
        self.assertEqual(self.window.content_host.currentIndex(), 1)
        self.assertEqual(self.window.pages.currentIndex(), 8)
        self.assertFalse(hasattr(self.window, "ai_panel"))

    def test_configuration_has_no_ai_fields(self):
        names = {field.name for field in dataclasses.fields(AppSettings)}
        self.assertTrue({"ai_enabled", "provider_profile_id"}.isdisjoint(names))
        self.assertNotIn("ai", self.store._settings_data(AppSettings()))

    def test_startup_does_not_import_ai_or_create_ai_data(self):
        prohibited = ("clickgit.ai", "clickgit.local_ai", "clickgit.ui.ai",
                      "clickgit.ui.local_models", "clickgit.ui.remote_models")
        self.assertFalse([name for name in sys.modules if name.startswith(prohibited)])
        self.assertFalse((self.store.path.parent / "ai").exists())

    def test_close_shuts_down_git_controller(self):
        with patch.object(self.controller, "shutdown") as shutdown:
            self.assertTrue(self.window.close())
            shutdown.assert_called_once()

    def test_html_compare_and_manual_merge_remain(self):
        self.assertIsNotNone(self.window.document_viewer)
        self.assertIsNotNone(self.window.html_review_button)
        self.assertIsNotNone(self.window.merge_review_button)
        for module in ("html_document.py", "html_preview_policy.py",
                       "ui/html_review.py", "ui/conflict_editor.py"):
            self.assertTrue((ROOT / "src/clickgit" / module).is_file())


if __name__ == "__main__":
    unittest.main()
