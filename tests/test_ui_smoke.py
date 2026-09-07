from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clickgit.app import AppController
from clickgit.git_runner import GitRunner
from clickgit.recovery import RecoveryPoint
from clickgit.repository import Repository
from clickgit.settings import SettingsStore
from clickgit.ui.main_window import MainWindow


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        settings = SettingsStore(Path(self.temp_dir.name) / "settings.json")
        self.controller = AppController(settings_store=settings)
        self.addCleanup(self.controller.shutdown)

    def test_main_window_constructs_without_repository(self) -> None:
        window = MainWindow(self.controller)
        self.addCleanup(window.close)

        self.assertEqual(window.windowTitle(), "ClickGit")
        self.assertIsNone(window.repository_path)
        self.assertGreaterEqual(window.navigation.count(), 8)
        self.assertIsNotNone(window.findChild(object, "openRepositoryAction"))
        self.assertIsNotNone(window.findChild(object, "commitButton"))

    def test_repository_actions_start_disabled(self) -> None:
        window = MainWindow(self.controller)
        self.addCleanup(window.close)

        self.assertFalse(window.fetch_action.isEnabled())
        self.assertFalse(window.pull_action.isEnabled())
        self.assertFalse(window.push_action.isEnabled())
        self.assertFalse(window.commit_button.isEnabled())

    def test_open_repository_refreshes_workspace_without_command_line(self) -> None:
        repository = Repository.init(
            Path(self.temp_dir.name) / "中文 仓库",
            GitRunner(),
        )
        changed_file = repository.path / "待提交.txt"
        changed_file.write_text("click only\n", encoding="utf-8")
        window = MainWindow(self.controller)
        self.addCleanup(window.close)

        self.controller.open_repository(repository.path)
        self._wait_until(
            lambda: window.repository_path == repository.path
            and window.change_tree.topLevelItemCount() == 2
            and window.change_tree.topLevelItem(0).childCount() == 1
        )

        self.assertTrue(window.fetch_action.isEnabled())
        self.assertEqual(window.repository_name.text(), "中文 仓库")
        self.assertEqual(
            window.change_tree.topLevelItem(0).child(0).text(1),
            "待提交.txt",
        )

    def test_stage_and_commit_can_be_completed_with_buttons(self) -> None:
        repository = Repository.init(
            Path(self.temp_dir.name) / "button-workflow",
            GitRunner(),
        )
        repository.configure_identity("ClickGit User", "clickgit@example.com")
        changed_file = repository.path / "button.txt"
        changed_file.write_text("button workflow\n", encoding="utf-8")
        window = MainWindow(self.controller)
        self.addCleanup(window.close)
        self.controller.open_repository(repository.path)
        self._wait_until(
            lambda: window.change_tree.topLevelItemCount() == 2
            and window.change_tree.topLevelItem(0).childCount() == 1
        )

        window.change_tree.topLevelItem(0).child(0).setSelected(True)
        window.stage_button.click()
        self._wait_until(
            lambda: window.change_tree.topLevelItem(1).childCount() == 1
        )
        window.commit_message.setPlainText("button commit")
        self.assertTrue(window.commit_button.isEnabled())
        window.commit_button.click()
        self._wait_until(
            lambda: window.change_tree.topLevelItem(0).childCount() == 0
            and window.change_tree.topLevelItem(1).childCount() == 0
        )

        verifier = Repository(repository.path, GitRunner())
        self.assertEqual(verifier.history(limit=1)[0].subject, "button commit")

    def test_dangerous_actions_create_recovery_records(self) -> None:
        repository = Repository.init(
            Path(self.temp_dir.name) / "recovery-workflow",
            GitRunner(),
        )
        repository.configure_identity("ClickGit User", "clickgit@example.com")
        tracked = repository.path / "tracked.txt"
        tracked.write_text("one\n", encoding="utf-8")
        repository.stage(["tracked.txt"])
        first = repository.commit("first")
        tracked.write_text("two\n", encoding="utf-8")
        repository.stage(["tracked.txt"])
        repository.commit("second")
        window = MainWindow(self.controller)
        self.addCleanup(window.close)
        self.controller.open_repository(repository.path)
        self._wait_until(lambda: window.repository_path == repository.path)

        self.controller.reset(first.oid, mode="hard")
        self._wait_until(
            lambda: tracked.exists()
            and tracked.read_text(encoding="utf-8") == "one\n"
            and len(list(self.controller.recovery_root.glob("*/manifest.json")))
            == 1
        )
        untracked = repository.path / "remove-me.tmp"
        untracked.write_text("recoverable\n", encoding="utf-8")
        self.controller.quarantine_untracked(["remove-me.tmp"])
        self._wait_until(
            lambda: not untracked.exists()
            and len(list(self.controller.recovery_root.glob("*/manifest.json")))
            == 2
        )

        self.assertTrue(
            any(
                (path.parent / "files" / "remove-me.tmp").exists()
                for path in self.controller.recovery_root.glob(
                    "*/manifest.json"
                )
            )
        )

    def test_hard_reset_refuses_a_dirty_worktree(self) -> None:
        repository = Repository.init(
            Path(self.temp_dir.name) / "dirty-hard-reset",
            GitRunner(),
        )
        repository.configure_identity("ClickGit User", "clickgit@example.com")
        tracked = repository.path / "tracked.txt"
        tracked.write_text("committed\n", encoding="utf-8")
        repository.stage(["tracked.txt"])
        first = repository.commit("first")
        tracked.write_text("uncommitted\n", encoding="utf-8")
        failures: list[tuple[str, str]] = []
        self.controller.operation_failed.connect(
            lambda title, detail: failures.append((title, detail))
        )
        self.controller.open_repository(repository.path)
        self._wait_until(
            lambda: self.controller.repository_path == repository.path
        )

        self.controller.reset(first.oid, mode="hard")
        self._wait_until(lambda: bool(failures))

        self.assertIn("未提交", failures[-1][1])
        self.assertEqual(
            tracked.read_text(encoding="utf-8"),
            "uncommitted\n",
        )
        self.assertFalse(
            list(self.controller.recovery_root.glob("*/manifest.json"))
        )

    def test_failed_recovery_does_not_report_success(self) -> None:
        repository = Repository.init(
            Path(self.temp_dir.name) / "failed-recovery",
            GitRunner(),
        )
        failures: list[tuple[str, str]] = []
        completions: list[str] = []
        self.controller.operation_failed.connect(
            lambda title, detail: failures.append((title, detail))
        )
        self.controller.operation_finished.connect(completions.append)
        self.controller.open_repository(repository.path)
        self._wait_until(
            lambda: self.controller.repository_path == repository.path
        )
        point = RecoveryPoint(
            identifier="missing",
            kind="quarantine",
            reason="test",
            repository_path=repository.path,
            created_at=datetime.now().astimezone(),
            manifest_path=Path(self.temp_dir.name) / "missing.json",
            _restore_callback=lambda _point: False,
        )

        self.controller.restore_recovery_point(point)
        self._wait_until(lambda: bool(failures))

        self.assertIn("未恢复", failures[-1][1])
        self.assertNotIn("恢复完成", completions)

    @staticmethod
    def _wait_until(predicate, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if predicate():
                return
            QTest.qWait(20)
        raise AssertionError("Timed out waiting for Qt background operation")


if __name__ == "__main__":
    unittest.main()
