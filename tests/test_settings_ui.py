from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from clickgit.app import AppController
from clickgit.models import AppSettings
from clickgit.repository import Repository
from clickgit.settings import SettingsStore
from clickgit.ui.dialogs import SettingsDialog
from clickgit.ui.main_window import MainWindow


class SettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "settings.json"
        self.store = SettingsStore(self.path)

    def controller(self) -> AppController:
        controller = AppController(settings_store=self.store)
        self.addCleanup(controller.shutdown)
        return controller

    def test_save_failure_keeps_memory_value_and_reports_nonblocking_warning(self) -> None:
        controller = self.controller()
        notices = []
        controller.settings_notice_changed.connect(notices.append)
        settings = AppSettings(external_editor="editor.exe")
        with patch.object(self.store, "save", side_effect=PermissionError("private-token")):
            controller.update_settings(settings)
        self.assertEqual(controller.settings.external_editor, "editor.exe")
        self.assertIn("未保存", controller.settings_notice)
        self.assertNotIn("private-token", controller.settings_notice)
        self.assertTrue(notices)
        controller.update_settings(settings)
        self.assertEqual(controller.settings_notice, "")

    def test_recent_save_failure_does_not_interrupt_accept_repository(self) -> None:
        controller = self.controller()
        repository = Repository.init(self.path.parent / "repo", controller.runner)
        accepted = []
        controller.repository_changed.connect(accepted.append)
        with patch.object(self.store, "save_projects", side_effect=PermissionError("locked")):
            with patch.object(controller, "refresh") as refresh:
                controller._accept_repository(repository)
        self.assertEqual(accepted, [repository.path])
        self.assertEqual(controller.repository_path, repository.path)
        self.assertEqual(controller.settings.recent_repositories, [str(repository.path)])
        refresh.assert_called_once()
        self.assertIn("最近项目", controller.settings_notice)

    def test_startup_notice_is_visible_and_not_erased_by_task_success(self) -> None:
        self.path.write_text('{"schema_version":99}', encoding="utf-8")
        controller = self.controller()
        window = MainWindow(controller)
        self.addCleanup(window.close)
        self.assertFalse(window.settings_notice_label.isHidden())
        self.assertIn("只读", window.settings_notice_label.text())
        window._operation_finished("完成")
        self.assertIn("只读", window.settings_notice_label.text())

    def test_successful_recent_save_does_not_clear_unsaved_preferences_warning(self) -> None:
        controller = self.controller()
        with patch.object(self.store, "save", side_effect=PermissionError("locked")):
            controller.update_settings(AppSettings(theme="dark"))
        repository = Repository.init(self.path.parent / "repo", controller.runner)
        with patch.object(controller, "refresh"):
            controller._accept_repository(repository)
        self.assertIn("未保存设置", controller.settings_notice)

    def test_dialog_preserves_preferences_it_does_not_edit(self) -> None:
        original = AppSettings(
            mode="professional", font_size_px=18, density="compact",
            onboarding_completed=True,
        )
        dialog = SettingsDialog(original)
        self.addCleanup(dialog.close)
        dialog.editor_edit.setText("editor.exe")
        updated = dialog.build_settings(original)
        self.assertEqual(updated.font_size_px, 18)
        self.assertEqual(updated.mode, "professional")
        self.assertEqual(updated.density, "compact")
        self.assertTrue(updated.onboarding_completed)
        self.assertEqual(updated.external_editor, "editor.exe")

    def test_notice_updates_after_save_failure_and_retry(self) -> None:
        controller = self.controller()
        window = MainWindow(controller)
        self.addCleanup(window.close)
        self.assertTrue(window.settings_notice_label.isHidden())
        with patch.object(self.store, "save", side_effect=OSError("disk full")):
            controller.update_settings(AppSettings())
        self.assertFalse(window.settings_notice_label.isHidden())
        self.assertIn("未保存", window.settings_notice_label.text())
        controller.update_settings(AppSettings())
        self.assertTrue(window.settings_notice_label.isHidden())

    def test_editing_editor_does_not_reset_tech_theme(self) -> None:
        original = AppSettings(theme="tech")
        dialog = SettingsDialog(original)
        self.addCleanup(dialog.close)
        dialog.editor_edit.setText("editor.exe")
        self.assertEqual(dialog.build_settings(original).theme, "tech")

    def test_invalid_preferences_do_not_replace_current_memory_values(self) -> None:
        controller = self.controller()
        original = controller.settings
        with patch.object(self.store, "save") as save:
            controller.update_settings(AppSettings(external_editor="x" * 4097))
        self.assertIs(controller.settings, original)
        save.assert_not_called()
        self.assertIn("4096", controller.settings_notice)
        self.assertNotIn("磁盘", controller.settings_notice)

    def test_dialog_does_not_accept_invalid_editor(self) -> None:
        dialog = SettingsDialog(AppSettings())
        self.addCleanup(dialog.close)
        dialog.editor_edit.setText("x" * 4097)
        dialog.accept()
        self.assertEqual(dialog.result(), 0)
        self.assertIn("4096", dialog.validation_label.text())
        dialog.editor_edit.setText("editor.exe")
        dialog.accept()
        self.assertEqual(dialog.result(), 1)

    def test_project_only_failure_clears_after_project_retry(self) -> None:
        controller = self.controller()
        project_path = self.path.with_name("projects.json")
        replace = Path.replace

        def fail_projects(source, target):
            if Path(target) == project_path:
                raise PermissionError("locked")
            return replace(source, target)

        with patch.object(Path, "replace", new=fail_projects):
            controller.update_settings(AppSettings(external_editor="editor.exe"))
        self.assertIn("项目", controller.settings_notice)
        self.assertEqual(SettingsStore(self.path).load().external_editor, "editor.exe")
        repository = Repository.init(self.path.parent / "repo", controller.runner)
        with patch.object(controller, "refresh"):
            controller._accept_repository(repository)
        self.assertEqual(controller.settings_notice, "")
        self.assertEqual(SettingsStore(self.path).load(), controller.settings)
