from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clickgit.git_runner import GitRunner
from clickgit.recovery import RecoveryManager, RecoveryPathError
from clickgit.repository import Repository


class RecoveryManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repository = Repository.init(self.root / "repo", GitRunner())
        self.repository.configure_identity(
            "ClickGit Test",
            "clickgit@example.com",
        )
        tracked = self.repository.path / "tracked.txt"
        tracked.write_text("base\n", encoding="utf-8")
        self.repository.stage(["tracked.txt"])
        self.repository.commit("initial")
        self.manager = RecoveryManager(
            self.repository,
            self.root / "recovery",
        )

    def test_create_commit_recovery_ref(self) -> None:
        point = self.manager.protect_commit_graph("hard-reset")

        self.assertTrue(
            point.ref_name.startswith("refs/clickgit/recovery/")
        )
        self.assertEqual(
            self.repository.rev_parse(point.ref_name),
            self.repository.head_oid(),
        )
        self.assertTrue(point.manifest_path.exists())

    def test_quarantine_and_restore_untracked_file(self) -> None:
        path = self.repository.path / "build" / "large.tmp"
        path.parent.mkdir()
        path.write_text("data", encoding="utf-8")

        point = self.manager.quarantine([path])

        self.assertFalse(path.exists())
        self.assertTrue(point.restore())
        self.assertEqual(path.read_text(encoding="utf-8"), "data")

    def test_quarantine_rejects_path_outside_repository(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("do not move", encoding="utf-8")

        with self.assertRaises(RecoveryPathError):
            self.manager.quarantine([outside])

        self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()

