from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clickgit.git_runner import GitCommandError, GitRunner
from clickgit.models import ChangeKind, GitResult
from clickgit.repository import (
    InvalidGitNameError,
    OperationConflict,
    Repository,
    UnsafeRepositoryPathError,
)


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

    def test_file_operations_treat_pathspec_characters_literally(self) -> None:
        repository = self.create_repository()
        literal_path = repository.path / "[ab].txt"
        matched_path = repository.path / "a.txt"
        literal_path.write_text("literal base\n", encoding="utf-8")
        matched_path.write_text("matched base\n", encoding="utf-8")
        repository.stage(["[ab].txt", "a.txt"])
        repository.commit("base files")

        literal_path.write_text("literal changed\n", encoding="utf-8")
        matched_path.write_text("matched changed\n", encoding="utf-8")

        repository.restore(["[ab].txt"])

        self.assertEqual(
            literal_path.read_text(encoding="utf-8"),
            "literal base\n",
        )
        self.assertEqual(
            matched_path.read_text(encoding="utf-8"),
            "matched changed\n",
        )

    def test_ref_arguments_reject_git_option_injection(self) -> None:
        repository = self.create_repository()
        tracked = repository.path / "tracked.txt"
        tracked.write_text("base\n", encoding="utf-8")
        repository.stage(["tracked.txt"])
        repository.commit("base")
        tracked.write_text("draft\n", encoding="utf-8")
        repository.stash_create("keep me")

        with self.assertRaises(InvalidGitNameError):
            repository.checkout("--detach")
        with self.assertRaises(InvalidGitNameError):
            repository.stash_drop("--quiet")

        self.assertEqual(repository.current_branch(), "main")
        self.assertEqual(len(repository.stashes()), 1)

    def test_default_push_uses_configured_upstream_remote(self) -> None:
        remote_path = self.root / "upstream remote.git"
        Repository.init(remote_path, self.runner, bare=True)
        repository = self.create_repository()
        repository.add_remote("upstream", str(remote_path))
        configured_remote = repository.remotes()[0]
        self.assertEqual(configured_remote.fetch_url, str(remote_path))
        self.assertEqual(configured_remote.push_url, str(remote_path))
        tracked = repository.path / "tracked.txt"
        tracked.write_text("one\n", encoding="utf-8")
        repository.stage(["tracked.txt"])
        repository.commit("first")
        repository.push(
            remote="upstream",
            branch="HEAD",
            set_upstream=True,
        )

        tracked.write_text("two\n", encoding="utf-8")
        repository.stage(["tracked.txt"])
        repository.commit("second")
        repository.push()

        verifier = Repository.clone(
            str(remote_path),
            self.root / "verifier",
            self.runner,
        )
        self.assertEqual(
            (verifier.path / "tracked.txt").read_text(encoding="utf-8"),
            "two\n",
        )

    def test_pull_branch_requires_explicit_remote(self) -> None:
        repository = self.create_repository()

        with self.assertRaises(ValueError):
            repository.pull(branch="main")

    def test_default_pull_preserves_repository_rebase_configuration(self) -> None:
        class RecordingRunner:
            def __init__(self) -> None:
                self.commands = []

            def run(self, args, *, cwd=None):
                self.commands.append(tuple(args))
                return GitResult(
                    command=tuple(args),
                    cwd=cwd,
                    returncode=0,
                    stdout=b"",
                    stderr=b"",
                    duration_seconds=0.0,
                )

        runner = RecordingRunner()
        repository = object.__new__(Repository)
        repository.path = self.root
        repository.runner = runner

        repository.pull()
        repository.pull(rebase=False)
        repository.pull(rebase=True)

        self.assertEqual(
            runner.commands,
            [
                ("pull",),
                ("pull", "--no-rebase"),
                ("pull", "--rebase"),
            ],
        )

    def test_opening_subdirectory_normalizes_to_repository_root(self) -> None:
        repository = self.create_repository()
        nested = repository.path / "src" / "main"
        nested.mkdir(parents=True)
        opened = Repository(nested, self.runner)
        file_path = repository.path / "root.txt"
        file_path.write_text("root\n", encoding="utf-8")

        opened.stage(["root.txt"])

        self.assertEqual(opened.path, repository.path)
        self.assertTrue(opened.status()[0].staged)

    def test_stash_conflict_uses_operation_conflict(self) -> None:
        repository = self.create_repository()
        file_path = repository.path / "stash-conflict.txt"
        file_path.write_text("base\n", encoding="utf-8")
        repository.stage(["stash-conflict.txt"])
        repository.commit("base")

        file_path.write_text("stash change\n", encoding="utf-8")
        repository.stash_create("conflicting stash")
        file_path.write_text("main change\n", encoding="utf-8")
        repository.stage(["stash-conflict.txt"])
        repository.commit("main change")

        with self.assertRaises(OperationConflict):
            repository.stash_apply("stash@{0}")

        self.assertTrue(repository.conflicted_files())

    def test_rebase_conflict_can_be_resolved_and_continued(self) -> None:
        repository = self.create_repository()
        file_path = repository.path / "rebase.txt"
        file_path.write_text("base\n", encoding="utf-8")
        repository.stage(["rebase.txt"])
        repository.commit("base")

        repository.create_branch("feature")
        repository.checkout("feature")
        file_path.write_text("feature\n", encoding="utf-8")
        repository.stage(["rebase.txt"])
        repository.commit("feature change")

        repository.checkout("main")
        file_path.write_text("main\n", encoding="utf-8")
        repository.stage(["rebase.txt"])
        repository.commit("main change")
        repository.checkout("feature")

        with self.assertRaises(OperationConflict):
            repository.rebase("main")

        file_path.write_text("resolved\n", encoding="utf-8")
        repository.stage(["rebase.txt"])
        repository.continue_rebase()

        self.assertEqual(repository.current_branch(), "feature")
        self.assertEqual(repository.status(), [])
        self.assertEqual(file_path.read_text(encoding="utf-8"), "resolved\n")

    def test_repository_path_validation_rejects_escape(self) -> None:
        repository = self.create_repository()
        outside = self.root / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")

        with self.assertRaises(UnsafeRepositoryPathError):
            repository.stage([str(outside)])

    def test_current_branch_reports_detached_head(self) -> None:
        repository = self.create_repository()
        file_path = repository.path / "detached.txt"
        file_path.write_text("base\n", encoding="utf-8")
        repository.stage(["detached.txt"])
        commit = repository.commit("base")
        repository._run(["switch", "--detach", commit.oid])

        self.assertEqual(repository.current_branch(), "(detached HEAD)")

    def test_current_branch_does_not_hide_repository_errors(self) -> None:
        class FailingRunner:
            def run(self, args, *, cwd=None):
                return GitResult(
                    command=tuple(args),
                    cwd=cwd,
                    returncode=128,
                    stdout=b"",
                    stderr=b"fatal: unable to read HEAD",
                    duration_seconds=0.0,
                )

        repository = object.__new__(Repository)
        repository.path = self.root
        repository.runner = FailingRunner()

        with self.assertRaises(GitCommandError):
            repository.current_branch()


if __name__ == "__main__":
    unittest.main()
