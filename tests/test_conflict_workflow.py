from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clickgit.git_runner import GitRunner
from clickgit.models import GitResult
from clickgit.repository import Repository


MARKERS = "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> topic\n"


class ConflictWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="clickgit-conflict-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = Repository.init(self.root / "repo", GitRunner())
        self.repo.configure_identity("Conflict Test", "conflict@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.file = self.repo.path / "中文 conflict.txt"
        self.file.write_bytes(b"base\n")
        self.git("add", "--", self.file.name)
        self.git("commit", "-m", "base")
        self.git("branch", "topic")
        self.file.write_bytes(b"ours\n")
        self.git("commit", "-am", "ours")
        self.git("checkout", "topic")
        self.file.write_bytes(b"theirs\n")
        self.git("commit", "-am", "theirs")
        self.git("checkout", "main")
        result = self.repo.runner.run(["merge", "topic"], cwd=self.repo.path)
        self.assertEqual(result.returncode, 1)

    def git(self, *args: str, data: bytes | None = None) -> bytes:
        result = self.repo.runner.run(args, cwd=self.repo.path, input_bytes=data)
        self.assertEqual(result.returncode, 0, result.stderr_text)
        return result.stdout

    def workflow(self):
        # Missing service is an explicit assertion failure in the red run.
        import importlib.util
        self.assertIsNotNone(
            importlib.util.find_spec("clickgit.conflict_workflow"),
            "安全冲突服务尚未实现",
        )
        return importlib.import_module("clickgit.conflict_workflow")

    def load(self):
        return self.workflow().load_conflict(self.repo, self.file.name)

    def test_load_exposes_sources_and_private_snapshot(self) -> None:
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        self.assertEqual(session.path, self.file.name)
        self.assertEqual((session.base, session.ours, session.theirs),
                         ("base\n", "ours\n", "theirs\n"))
        self.assertEqual(session.result, self.file.read_text(encoding="utf-8"))

    def test_draft_preserves_bom_crlf_and_missing_final_newline_without_stage(self) -> None:
        self.file.write_bytes(b"\xef\xbb\xbf" + MARKERS.rstrip("\n").replace("\n", "\r\n").encode())
        before = self.git("ls-files", "-s", "-z")
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        self.workflow().save_conflict(self.repo, session, MARKERS, mark_resolved=False)
        self.assertEqual(self.file.read_bytes(),
                         b"\xef\xbb\xbf" + MARKERS.rstrip("\n").replace("\n", "\r\n").encode())
        self.assertEqual(self.git("ls-files", "-s", "-z"), before)

    def test_resolve_preserves_final_newline_and_stages_only_target(self) -> None:
        (self.repo.path / "unrelated.txt").write_bytes(b"unrelated")
        session = self.load()
        self.workflow().save_conflict(self.repo, session, "resolved", mark_resolved=True)
        self.assertEqual(self.file.read_bytes(), b"resolved\n")
        self.assertEqual(self.git("ls-files", "-u"), b"")
        self.assertEqual(self.git("show", ":" + self.file.name), b"resolved\n")
        self.assertEqual(self.git("ls-files", "--", "unrelated.txt"), b"")

    def test_external_file_edit_is_never_overwritten(self) -> None:
        session = self.load()
        self.file.write_bytes(b"external user edit\n")
        with self.assertRaisesRegex(RuntimeError, "变化|改变|重新"):
            self.workflow().save_conflict(self.repo, session, "mine", mark_resolved=False)
        self.assertEqual(self.file.read_bytes(), b"external user edit\n")

    def test_identical_bytes_replaced_externally_are_rejected(self) -> None:
        session = self.load()
        replacement = self.file.with_suffix(".replacement")
        replacement.write_bytes(self.file.read_bytes())
        os.replace(replacement, self.file)
        with self.assertRaises(RuntimeError):
            self.workflow().save_conflict(self.repo, session, "mine", mark_resolved=False)

    def test_index_stage_or_operation_changes_block_save(self) -> None:
        originals = {name: (self.repo.path / ".git" / name).read_bytes()
                     for name in ("index", "HEAD", "MERGE_MSG")}
        for change in ("index", "operation", "head", "resolved"):
            with self.subTest(change=change):
                for name, data in originals.items():
                    (self.repo.path / ".git" / name).write_bytes(data)
                session = self.load()
                self.assertTrue(session.allowed, session.reason)
                before = self.file.read_bytes()
                if change == "index":
                    oid = self.git("hash-object", "-w", "--stdin", data=b"new stage\n").strip()
                    self.git("update-index", "--index-info",
                             data=b"100644 " + oid + b" 2\t" + self.file.name.encode() + b"\n")
                elif change == "operation":
                    with (self.repo.path / ".git" / "MERGE_MSG").open("ab") as stream:
                        stream.write(b"\nexternal operation edit")
                elif change == "head":
                    self.git("symbolic-ref", "HEAD", "refs/heads/topic")
                else:
                    self.git("add", "--", self.file.name)
                with self.assertRaises(RuntimeError):
                    self.workflow().save_conflict(self.repo, session, "mine", mark_resolved=False)
                self.assertEqual(self.file.read_bytes(), before)

    def test_repository_identity_cannot_be_swapped(self) -> None:
        session = self.load()
        other = Repository.init(self.root / "other", self.repo.runner)
        with self.assertRaises(RuntimeError):
            self.workflow().save_conflict(other, session, "mine", mark_resolved=False)

    def test_residual_and_malformed_markers_block_resolution_but_not_draft(self) -> None:
        for text in (MARKERS, "ok\n\n=======\n", "ok\n<<<<<<<<< HEAD\nx\n"):
            with self.subTest(text=text):
                session = self.load()
                before = self.file.read_bytes()
                with self.assertRaisesRegex(RuntimeError, "标记"):
                    self.workflow().save_conflict(self.repo, session, text, mark_resolved=True)
                self.assertEqual(self.file.read_bytes(), before)

    def test_binary_unknown_encoding_and_oversized_files_are_read_only(self) -> None:
        for content in (b"binary\0data", b"\xff\xfehi", b"\x81\x82", b"x" * (2 * 1024 * 1024 + 1)):
            with self.subTest(size=len(content)):
                self.file.write_bytes(content)
                session = self.load()
                self.assertFalse(session.allowed)
                self.assertTrue(session.reason)
                with self.assertRaises(RuntimeError):
                    self.workflow().save_conflict(self.repo, session, "no", mark_resolved=False)
                self.assertEqual(self.file.read_bytes(), content)

    def test_binary_and_oversized_stage_blobs_are_rejected(self) -> None:
        for content in (b"x\0y", b"x" * (2 * 1024 * 1024 + 1)):
            oid = self.git("hash-object", "-w", "--stdin", data=content).strip()
            self.git("update-index", "--index-info",
                     data=b"100644 " + oid + b" 1\t" + self.file.name.encode() + b"\n")
            self.assertFalse(self.load().allowed)

    def test_missing_stage_complex_delete_conflict_is_read_only(self) -> None:
        self.git("update-index", "--index-info",
                 data=b"0 " + b"0" * 40 + b"\t" + self.file.name.encode() + b"\n")
        oid = self.git("hash-object", "-w", "--stdin", data=b"ours\n").strip()
        self.git("update-index", "--index-info",
                 data=b"100644 " + oid + b" 2\t" + self.file.name.encode() + b"\n")
        session = self.load()
        self.assertFalse(session.allowed)
        self.assertTrue(session.reason)

    def test_unsafe_paths_and_hardlinks_are_read_only(self) -> None:
        service = self.workflow()
        for path in ("../outside", ".git/config", ".GIT/config", str(self.file), "dir/../x"):
            self.assertFalse(service.load_conflict(self.repo, path).allowed, path)
        os.link(self.file, self.root / "hardlink")
        self.assertFalse(self.load().allowed)

    def test_symlink_file_and_parent_are_read_only(self) -> None:
        service = self.workflow()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "x.txt").write_text("keep")
        try:
            (self.repo.path / "linked").symlink_to(outside, target_is_directory=True)
            (self.repo.path / "link.txt").symlink_to(outside / "x.txt")
        except OSError as error:
            self.skipTest(f"当前系统未授予 symlink 权限: {error}")
        self.assertFalse(service.load_conflict(self.repo, "linked/x.txt").allowed)
        self.assertFalse(service.load_conflict(self.repo, "link.txt").allowed)

    def test_stage_failure_keeps_saved_user_file_and_reports_error(self) -> None:
        session = self.load()
        original_run = self.repo.runner.run

        def fail_add(args, **kwargs):
            if "add" in args:
                return GitResult(tuple(args), self.repo.path, 1, b"", b"index.lock exists", 0)
            return original_run(args, **kwargs)

        with patch.object(self.repo.runner, "run", side_effect=fail_add):
            with self.assertRaisesRegex(RuntimeError, "暂存"):
                self.workflow().save_conflict(self.repo, session, "user result", mark_resolved=True)
        self.assertEqual(self.file.read_bytes(), b"user result\n")
        self.assertTrue(self.git("ls-files", "-u"))

    def test_external_change_during_preparation_is_blocked_by_last_check(self) -> None:
        service = self.workflow()
        session = self.load()
        original = service.os.fsync

        def change_after_temp_flush(fd):
            original(fd)
            self.file.write_bytes(b"concurrent user\n")

        with patch.object(service.os, "fsync", side_effect=change_after_temp_flush):
            with self.assertRaises(RuntimeError):
                service.save_conflict(self.repo, session, "mine", mark_resolved=False)
        self.assertEqual(self.file.read_bytes(), b"concurrent user\n")
        self.assertFalse(list(self.repo.path.glob(".clickgit-conflict-*")))

    def test_atomic_replace_failure_does_not_truncate_original(self) -> None:
        service = self.workflow()
        session = self.load()
        before = self.file.read_bytes()
        with patch.object(service.os, "replace", side_effect=OSError("sharing violation")):
            with self.assertRaises(RuntimeError):
                service.save_conflict(self.repo, session, "mine", mark_resolved=False)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertFalse(list(self.repo.path.glob(".clickgit-conflict-*")))

    def test_short_custom_marker_and_malformed_residual_cannot_be_resolved(self) -> None:
        (self.repo.path / ".gitattributes").write_text(
            "* conflict-marker-size=2\n", encoding="utf-8")
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        for text in ("ok\n\n==\n", "ok\n<<<<<<<HEAD\n", "ok\n>>>>>>>topic\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(RuntimeError, "标记"):
                    self.workflow().save_conflict(self.repo, session, text, mark_resolved=True)

    def test_parent_reparse_attribute_is_rejected_without_following_it(self) -> None:
        from types import SimpleNamespace
        service = self.workflow()
        original = Path.lstat

        def reparse(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == self.repo.path.parent:
                values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                values["st_file_attributes"] = 0x400
                return SimpleNamespace(**values)
            return info

        with patch.object(Path, "lstat", reparse):
            session = self.load()
        self.assertFalse(session.allowed)
        self.assertIn("reparse", session.reason)

    def test_index_lock_added_after_load_blocks_overwrite(self) -> None:
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        before = self.file.read_bytes()
        (self.repo.path / ".git" / "index.lock").write_bytes(b"other process")
        with self.assertRaises(RuntimeError):
            self.workflow().save_conflict(self.repo, session, "mine", mark_resolved=False)
        self.assertEqual(self.file.read_bytes(), before)

    def test_after_replace_external_edit_is_detected_and_never_rolled_back(self) -> None:
        service = self.workflow()
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        replace = service.os.replace

        def concurrent_replace(source, destination):
            replace(source, destination)
            Path(destination).write_bytes(b"new external edit\n")

        with patch.object(service.os, "replace", side_effect=concurrent_replace):
            with self.assertRaises(RuntimeError):
                service.save_conflict(self.repo, session, "mine", mark_resolved=True)
        self.assertEqual(self.file.read_bytes(), b"new external edit\n")
        self.assertTrue(self.git("ls-files", "-u"))

    def test_successful_git_exit_without_staging_is_not_reported_resolved(self) -> None:
        service = self.workflow()
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        original = self.repo.runner.run

        def ignore_add(args, **kwargs):
            if "add" in args:
                return GitResult(tuple(args), self.repo.path, 0, b"", b"", 0)
            return original(args, **kwargs)

        with patch.object(self.repo.runner, "run", side_effect=ignore_add):
            with self.assertRaisesRegex(RuntimeError, "暂存"):
                service.save_conflict(self.repo, session, "mine", mark_resolved=True)
        self.assertEqual(self.file.read_bytes(), b"mine\n")
        self.assertTrue(self.git("ls-files", "-u"))

    def test_filters_and_mixed_newlines_are_read_only(self) -> None:
        service = self.workflow()
        self.file.write_bytes(b"a\r\nb\n")
        self.assertFalse(self.load().allowed)
        self.file.write_bytes(MARKERS.encode())
        for attribute in ("filter=custom", "working-tree-encoding=UTF-16", "-text"):
            (self.repo.path / ".gitattributes").write_text("* " + attribute + "\n")
            session = service.load_conflict(self.repo, self.file.name)
            self.assertFalse(session.allowed, attribute)

    def test_size_limit_rejects_result_before_any_write(self) -> None:
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        before = self.file.read_bytes()
        with self.assertRaises(RuntimeError):
            self.workflow().save_conflict(self.repo, session, "文" * 800000, mark_resolved=False)
        self.assertEqual(self.file.read_bytes(), before)

    def test_read_time_file_change_disables_session(self) -> None:
        service = self.workflow()
        original = self.repo.runner.run
        changed = False

        def change_on_blob(args, **kwargs):
            nonlocal changed
            result = original(args, **kwargs)
            if "blob" in args and not changed:
                changed = True
                self.file.write_bytes(b"external during load\n")
            return result

        with patch.object(self.repo.runner, "run", side_effect=change_on_blob):
            session = service.load_conflict(self.repo, self.file.name)
        self.assertFalse(session.allowed)
        self.assertEqual(self.file.read_bytes(), b"external during load\n")

    def test_plain_rebase_conflict_can_be_edited_with_neutral_sources(self) -> None:
        self.git("merge", "--abort")
        self.git("checkout", "topic")
        result = self.repo.runner.run(["rebase", "main"], cwd=self.repo.path)
        self.assertEqual(result.returncode, 1)
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        self.assertEqual((session.ours, session.theirs), ("ours\n", "theirs\n"))
        self.workflow().save_conflict(self.repo, session, "resolved", mark_resolved=True)
        self.assertEqual(self.git("ls-files", "-u"), b"")

    def test_renamed_conflict_path_during_rebase_is_read_only(self) -> None:
        self.git("merge", "--abort")
        # Rebase changes a target that main renamed: Git can produce 1/2/3
        # under the new name, but this service must not treat it as simple text.
        old_name = self.file.name
        new_name = "renamed.txt"
        self.git("checkout", "-b", "rename-main", "main~1")
        shared = b"".join(f"shared line {n}\n".encode() for n in range(40))
        self.file.write_bytes(b"base\n" + shared)
        self.git("commit", "-am", "long common content for rename detection")
        self.git("branch", "rename-topic")
        self.file.write_bytes(b"ours\n" + shared)
        self.git("mv", "--", old_name, new_name)
        self.git("commit", "-am", "rename on main")
        self.git("checkout", "rename-topic")
        self.file.write_bytes(b"theirs\n" + shared)
        self.git("commit", "-am", "change old name")
        result = self.repo.runner.run(["rebase", "rename-main"], cwd=self.repo.path)
        self.assertEqual(result.returncode, 1)
        stages = self.git("ls-files", "-u", "-z", "--", new_name).split(b"\0")
        self.assertEqual(len([record for record in stages if record]), 3)
        session = self.workflow().load_conflict(self.repo, new_name)
        self.assertFalse(session.allowed, session.reason)

    def test_add_add_conflict_can_be_saved(self) -> None:
        self.git("merge", "--abort")
        self.git("checkout", "-b", "add-main", "main~1")
        added = self.repo.path / "new.txt"
        added.write_bytes(b"left\n")
        self.git("add", "--", "new.txt")
        self.git("commit", "-m", "add left")
        self.git("checkout", "-b", "add-topic", "main~1")
        added.write_bytes(b"right\n")
        self.git("add", "--", "new.txt")
        self.git("commit", "-m", "add right")
        self.git("checkout", "add-main")
        result = self.repo.runner.run(["merge", "add-topic"], cwd=self.repo.path)
        self.assertEqual(result.returncode, 1)
        session = self.workflow().load_conflict(self.repo, "new.txt")
        self.assertTrue(session.allowed, session.reason)
        self.assertEqual(session.base, "")
        self.workflow().save_conflict(self.repo, session, "left\nright\n", mark_resolved=True)
        self.assertEqual(self.git("show", ":new.txt"), b"left\nright\n")

    def test_temp_changed_during_last_repository_check_never_replaces_original(self) -> None:
        service = self.workflow()
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        before = self.file.read_bytes()
        verify = service._verify

        def tamper_after_check(*args, **kwargs):
            result = verify(*args, **kwargs)
            for candidate in self.repo.path.glob(".clickgit-conflict-*"):
                candidate.write_bytes(b"tampered temp result\n")
            return result

        with patch.object(service, "_verify", side_effect=tamper_after_check):
            with self.assertRaises(RuntimeError):
                service.save_conflict(self.repo, session, "my intended text", mark_resolved=False)
        self.assertEqual(self.file.read_bytes(), before)

    def test_short_markers_in_worktree_remain_guarded_without_matching_attribute(self) -> None:
        self.file.write_bytes(b"<< HEAD\nours\n==\ntheirs\n>> topic\n")
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        for text in (session.result, "partially edited\n\n==\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(RuntimeError, "标记"):
                    self.workflow().save_conflict(self.repo, session, text, mark_resolved=True)

    def test_cleanup_does_not_unlink_a_replacement_at_the_temporary_path(self) -> None:
        service = self.workflow()
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        before = self.file.read_bytes()
        original_replace = service.os.replace
        paths = []

        def replace_temp_then_fail(source, destination):
            temporary = Path(source)
            paths.append(temporary)
            foreign = temporary.with_name("foreign-file")
            foreign.write_bytes(b"belongs to someone else\n")
            original_replace(foreign, temporary)
            raise OSError("replacement failed")

        with patch.object(service.os, "replace", side_effect=replace_temp_then_fail):
            with self.assertRaisesRegex(RuntimeError, "人工检查"):
                service.save_conflict(self.repo, session, "mine", mark_resolved=False)
        self.assertTrue(paths[0].exists())
        self.assertEqual(paths[0].read_bytes(), b"belongs to someone else\n")
        self.assertEqual(self.file.read_bytes(), before)

    def test_cleanup_keeps_a_temporary_file_that_became_hardlinked(self) -> None:
        service = self.workflow()
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        paths = []

        def link_temp_then_fail(source, destination):
            temporary = Path(source)
            paths.append(temporary)
            os.link(temporary, self.root / "new-hardlink")
            raise OSError("replacement failed")

        with patch.object(service.os, "replace", side_effect=link_temp_then_fail):
            with self.assertRaisesRegex(RuntimeError, "人工检查"):
                service.save_conflict(self.repo, session, "mine", mark_resolved=False)
        self.assertTrue(paths[0].exists())
        self.assertEqual(paths[0].stat().st_nlink, 2)

    def test_cleanup_refuses_a_parent_that_became_reparse(self) -> None:
        from types import SimpleNamespace
        service = self.workflow()
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        original_lstat = Path.lstat
        paths = []
        changed = False

        def fail_replace(source, destination):
            nonlocal changed
            paths.append(Path(source))
            changed = True
            raise OSError("replacement failed")

        def parent_reparse(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if changed and path == self.repo.path:
                values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                values["st_file_attributes"] = 0x400
                return SimpleNamespace(**values)
            return info

        with patch.object(service.os, "replace", side_effect=fail_replace):
            with patch.object(Path, "lstat", parent_reparse):
                with self.assertRaisesRegex(RuntimeError, "人工检查"):
                    service.save_conflict(self.repo, session, "mine", mark_resolved=False)
        self.assertTrue(paths[0].exists())

    def test_legal_markdown_setext_heading_can_be_marked_resolved(self) -> None:
        service = self.workflow()
        session = self.load()
        self.assertTrue(session.allowed, session.reason)
        text = "Document title\n=======\n\n产品需求正文\n"
        service.save_conflict(self.repo, session, text, mark_resolved=True)
        self.assertEqual(self.file.read_bytes(), text.encode())
        self.assertEqual(self.git("ls-files", "-u"), b"")


class ConflictMarkerTests(unittest.TestCase):
    def test_setext_titles_are_allowed_but_actual_and_orphan_markers_are_not(self) -> None:
        from clickgit.conflict_workflow import contains_conflict_markers
        for text in ("Document title\n=======", "产品需求\n===\n", "Title\n=======\nBody\n"):
            with self.subTest(allowed=text):
                self.assertFalse(contains_conflict_markers(text))
        for text in (MARKERS, "=======\n", "\n=======\n", "<<<<<<< HEAD\n",
                     ">>>>>>> topic\n", "||||||| base\n", "Title\n=======\n" + MARKERS):
            with self.subTest(blocked=text):
                self.assertTrue(contains_conflict_markers(text))


if __name__ == "__main__":
    unittest.main()
