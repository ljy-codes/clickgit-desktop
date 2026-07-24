from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clickgit.git_runner import GitRunner
from clickgit.models import ChangeKind
from clickgit.repository import OperationConflict, Repository


class RepositoryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.runner = GitRunner()

    def create_repository(self, name: str = "repo") -> Repository:
        repository = Repository.init(self.root / name, self.runner)
        repository.configure_identity("ClickGit Test", "clickgit@example.com")
        return repository

    def test_stage_commit_branch_and_history(self) -> None:
        repository = self.create_repository()
        (repository.path / "中文文件.txt").write_text(
            "hello\n",
            encoding="utf-8",
        )

        self.assertEqual(repository.status()[0].kind, ChangeKind.UNTRACKED)

        repository.stage(["中文文件.txt"])
        commit = repository.commit("initial commit")
        repository.create_branch("feature/login")
        repository.checkout("feature/login")

        self.assertTrue(commit.oid)
        self.assertEqual(repository.current_branch(), "feature/login")
        self.assertEqual(repository.history(limit=10)[0].subject, "initial commit")
        self.assertEqual(repository.status(), [])

    def test_clone_push_pull_remotes_tags_and_stashes(self) -> None:
        remote_path = self.root / "remote.git"
        Repository.init(remote_path, self.runner, bare=True)

        first = Repository.clone(
            str(remote_path),
            self.root / "first clone",
            self.runner,
        )
        first.configure_identity("ClickGit Test", "clickgit@example.com")
        (first.path / "app.txt").write_text("one\n", encoding="utf-8")
        first.stage(["app.txt"])
        first.commit("first")
        first.push(set_upstream=True)
        first.create_tag("v1.0.0")

        second = Repository.clone(
            str(remote_path),
            self.root / "second clone",
            self.runner,
        )
        second.configure_identity("ClickGit Test", "clickgit@example.com")
        self.assertEqual(second.remotes()[0].name, "origin")

        (first.path / "app.txt").write_text("two\n", encoding="utf-8")
        first.stage(["app.txt"])
        first.commit("second")
        first.push()

        second.pull()
        self.assertEqual(
            (second.path / "app.txt").read_text(encoding="utf-8"),
            "two\n",
        )

        (second.path / "draft.txt").write_text("draft\n", encoding="utf-8")
        second.stash_create("draft work", include_untracked=True)
        self.assertEqual(second.stashes()[0].subject, "draft work")
        second.stash_apply("stash@{0}", pop=True)
        self.assertTrue((second.path / "draft.txt").exists())

    def test_merge_conflict_is_reported_and_can_be_aborted(self) -> None:
        repository = self.create_repository()
        file_path = repository.path / "conflict.txt"
        file_path.write_text("base\n", encoding="utf-8")
        repository.stage(["conflict.txt"])
        repository.commit("base")

        repository.create_branch("feature")
        repository.checkout("feature")
        file_path.write_text("feature\n", encoding="utf-8")
        repository.stage(["conflict.txt"])
        repository.commit("feature change")

        repository.checkout("main")
        file_path.write_text("main\n", encoding="utf-8")
        repository.stage(["conflict.txt"])
        repository.commit("main change")

        with self.assertRaises(OperationConflict):
            repository.merge("feature")

        self.assertTrue(repository.conflicted_files())
        repository.abort_merge()
        self.assertEqual(repository.status(), [])
        self.assertEqual(file_path.read_text(encoding="utf-8"), "main\n")

    def test_unstage_restore_and_diff(self) -> None:
        repository = self.create_repository()
        file_path = repository.path / "app.txt"
        file_path.write_text("one\n", encoding="utf-8")
        repository.stage(["app.txt"])
        repository.commit("initial")

        file_path.write_text("two\n", encoding="utf-8")
        self.assertIn("+two", repository.diff("app.txt"))
        repository.stage(["app.txt"])
        self.assertIn("+two", repository.diff("app.txt", staged=True))
        repository.unstage(["app.txt"])
        repository.restore(["app.txt"])

        self.assertEqual(file_path.read_text(encoding="utf-8"), "one\n")
        self.assertEqual(repository.status(), [])


if __name__ == "__main__":
    unittest.main()
