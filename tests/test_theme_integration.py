from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel

from clickgit.app import AppController
from clickgit.models import AppSettings
from clickgit.settings import SettingsStore
from clickgit.ui.dialogs import CleanPreviewDialog, SettingsDialog
from clickgit.ui.main_window import MainWindow
from clickgit.ui.themes import theme_values


class ThemeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = SettingsStore(Path(directory.name) / "settings.json")
        self.controller = AppController(settings_store=self.store)
        self.addCleanup(self.controller.shutdown)

    def test_loaded_theme_and_live_changes_reach_main_window(self) -> None:
        self.controller.update_settings(AppSettings(theme="dark"))
        window = MainWindow(self.controller)
        self.addCleanup(window.close)
        self.assertEqual(window.theme_manager.effective_theme, "dark")
        dark = self.application.styleSheet()
        self.controller.update_settings(replace(self.controller.settings, theme="tech"))
        self.assertEqual(window.theme_manager.effective_theme, "tech")
        self.assertNotEqual(self.application.styleSheet(), dark)
        self.assertNotIn("待完成", window.settings_summary.text())

    def test_save_failure_keeps_theme_effective(self) -> None:
        window = MainWindow(self.controller)
        self.addCleanup(window.close)
        with patch.object(self.store, "save", side_effect=PermissionError("locked")):
            self.controller.update_settings(AppSettings(theme="dark", font_size_px=18))
        self.assertEqual(window.theme_manager.effective_theme, "dark")
        self.assertIn("18px", self.application.styleSheet())
        self.assertIn("未保存", window.settings_notice_label.text())

    def test_danger_labels_follow_effective_theme_without_local_override(self) -> None:
        window = MainWindow(self.controller)
        self.addCleanup(window.close)
        dialog = CleanPreviewDialog(["sample.md"], window)
        self.addCleanup(dialog.close)
        for theme in ("dark", "tech", "light"):
            self.controller.update_settings(replace(self.controller.settings, theme=theme))
            labels = [window.conflict_label] + [
                label for label in window.findChildren(QLabel)
                if "这些操作会重写提交历史" in label.text()
            ]
            labels += [label for label in dialog.findChildren(QLabel)
                       if "选中的文件不会直接删除" in label.text()]
            self.assertEqual(len(labels), 3)
            for label, semantic in zip(labels, ("danger", "warning", "warning")):
                label.ensurePolished()
                self.assertEqual(label.styleSheet(), "")
                self.assertEqual(label.palette().color(QPalette.WindowText).name(),
                                 theme_values(theme)[semantic])

    def test_font_and_density_controls_round_trip(self) -> None:
        dialog = SettingsDialog(AppSettings())
        self.addCleanup(dialog.close)
        dialog.font_size_combo.setCurrentIndex(dialog.font_size_combo.findData(18))
        dialog.density_combo.setCurrentIndex(dialog.density_combo.findData("compact"))
        result = dialog.build_settings(AppSettings())
        self.assertEqual(result.font_size_px, 18)
        self.assertEqual(result.density, "compact")
