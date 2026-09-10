from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from clickgit.git_runner import GitRunner, GitCommandError
from clickgit.repository import Repository
from clickgit.document_workflow import DocumentWorkflow, DocumentError


class DocumentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Repository.init(Path(self.temp.name) / "repo", GitRunner())
        self.repo.configure_identity("Document Test", "doc@example.invalid")
        self.repo._run(["config", "core.autocrlf", "false"])
        self.flow = DocumentWorkflow(self.repo)

    def commit_text(self, text, message="文档", path="需求.md"):
        (self.repo.path / path).write_bytes(text.encode("utf-8"))
        self.repo.stage([path])
        return self.repo.commit(message).oid

    def test_untracked_and_unborn_staged_content(self):
        (self.repo.path / "需求.md").write_text("新文档\n", encoding="utf-8", newline="")
        pair = self.flow.workspace("需求.md")
        self.assertEqual((pair.left, pair.right), ("", "新文档\n"))
        self.repo.stage(["需求.md"])
        pair = self.flow.workspace("需求.md", staged=True)
        self.assertEqual(pair.left, "")
        self.assertIn("首次提交", pair.left_title)

    def test_worktree_and_staged_have_different_baselines(self):
        self.commit_text("原内容\n")
        (self.repo.path / "需求.md").write_text("暂存内容\n", encoding="utf-8", newline="")
        self.repo.stage(["需求.md"])
        (self.repo.path / "需求.md").write_text("工作内容\n", encoding="utf-8", newline="")
        pair = self.flow.workspace("需求.md")
        staged = self.flow.workspace("需求.md", staged=True)
        self.assertEqual((pair.left, pair.right), ("暂存内容\n", "工作内容\n"))
        self.assertEqual((staged.left, staged.right), ("原内容\n", "暂存内容\n"))

    def test_history_fixed_revisions_and_deleted_file(self):
        original = self.commit_text("原内容\n")
        changed = self.commit_text("新内容\n")
        listing = self.flow.compare_revisions(original, changed)
        self.assertEqual(len(listing.files), 1)
        pair = self.flow.comparison_file(listing, "需求.md")
        self.assertEqual((pair.left, pair.right), ("原内容\n", "新内容\n"))
        (self.repo.path / "需求.md").unlink()
        self.repo.stage(["需求.md"])
        pair = self.flow.workspace("需求.md", staged=True)
        self.assertEqual((pair.left, pair.right), ("新内容\n", ""))

    def test_binary_is_not_lossily_decoded(self):
        self.commit_text("文本\n")
        (self.repo.path / "需求.md").write_bytes(b"\x00\xff\x01")
        pair = self.flow.workspace("需求.md")
        self.assertFalse(pair.supported)
        self.assertIn("文本", pair.notice)

    def test_unsafe_paths_are_rejected(self):
        for name in ("../outside", ".git/config", "D:/outside", "/outside"):
            with self.subTest(name=name), self.assertRaises(DocumentError):
                self.flow.workspace(name)

    def test_rename_uses_old_head_path(self):
        self.commit_text("原内容\n", path="旧名.md")
        self.repo._run(["mv", "旧名.md", "新名.md"])
        pair = self.flow.workspace("新名.md", staged=True, original_path="旧名.md")
        self.assertEqual((pair.left, pair.right), ("原内容\n", "原内容\n"))
        self.assertIn("旧名.md", pair.left_title)

    def make_branches(self):
        base = self.commit_text("共同\n")
        self.repo.create_branch("feature")
        self.repo.checkout("feature")
        source = self.commit_text("共同\n新增\n")
        self.repo.checkout("main")
        return base, source

    def test_prepare_merge_is_read_only_and_stale_plan_rejected(self):
        base, source = self.make_branches()
        plan = self.flow.plan_merge("feature")
        self.assertEqual(self.repo.head_oid(), base)
        self.assertEqual(self.repo.status(), [])
        self.assertEqual(plan.source_oid, source)
        self.commit_text("外部修改\n")
        with self.assertRaises(DocumentError):
            self.flow.start_merge(plan)

    def test_dirty_worktree_blocks_merge_without_deleting_files(self):
        self.make_branches()
        plan = self.flow.plan_merge("feature")
        draft = self.repo.path / "未跟踪.md"
        draft.write_text("材料", encoding="utf-8")
        with self.assertRaises(DocumentError):
            self.flow.start_merge(plan)
        self.assertEqual(draft.read_text(encoding="utf-8"), "材料")

    def test_merge_does_not_overwrite_ignored_local_material(self):
        self.commit_text("共同\n")
        self.repo.create_branch("feature")
        self.repo.checkout("feature")
        self.commit_text("来源文件\n", path="私人草稿.md")
        self.repo.checkout("main")
        self.commit_text("私人草稿.md\n", path=".gitignore")
        draft = self.repo.path / "私人草稿.md"
        draft.write_bytes("不可覆盖的本机材料\n".encode("utf-8"))
        plan = self.flow.plan_merge("feature")
        self.assertEqual(self.repo.status(), [])
        with self.assertRaises((DocumentError, GitCommandError)):
            self.flow.start_merge(plan)
        self.assertEqual(draft.read_text("utf-8"), "不可覆盖的本机材料\n")
        self.assertFalse(self.flow.merge_active())

    def test_fast_forward_stops_for_review_and_can_finish(self):
        base, source = self.make_branches()
        plan = self.flow.plan_merge("feature")
        self.flow.start_merge(plan)
        self.assertEqual(self.repo.head_oid(), base)
        self.assertTrue(self.flow.merge_active())
        listing = self.flow.merge_result()
        pair = self.flow.comparison_file(listing, "需求.md")
        self.assertEqual((pair.left, pair.right), ("共同\n", "共同\n新增\n"))
        self.flow.finish_merge(listing)
        self.assertFalse(self.flow.merge_active())
        self.assertEqual(self.repo.history(limit=1)[0].parents, (base, source))
        result = self.flow.compare_revisions(base, self.repo.head_oid())
        self.assertEqual(len(result.files), 1)

    def test_cancel_merge_restores_original(self):
        base, _ = self.make_branches()
        self.flow.start_merge(self.flow.plan_merge("feature"))
        self.flow.abort_merge()
        self.assertEqual(self.repo.head_oid(), base)
        self.assertFalse(self.flow.merge_active())
        self.assertEqual((self.repo.path / "需求.md").read_text(encoding="utf-8"), "共同\n")

    def test_finish_refuses_changed_index_after_review(self):
        self.make_branches()
        self.flow.start_merge(self.flow.plan_merge("feature"))
        listing = self.flow.merge_result()
        (self.repo.path / "需求.md").write_text("未审阅内容\n", encoding="utf-8")
        self.repo.stage(["需求.md"])
        with self.assertRaises(DocumentError):
            self.flow.finish_merge(listing)
        self.assertTrue(self.flow.merge_active())

    def test_conflicts_cannot_be_completed(self):
        self.make_branches()
        self.commit_text("主分支不同内容\n")
        self.flow.start_merge(self.flow.plan_merge("feature"))
        self.assertTrue(self.repo.conflicted_files())
        with self.assertRaises(DocumentError):
            self.flow.merge_result()

    def test_staged_conflict_markers_cannot_bypass_final_review(self):
        self.make_branches()
        self.flow.start_merge(self.flow.plan_merge("feature"))
        (self.repo.path / "需求.md").write_bytes(b"<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> source\n")
        self.repo.stage(["需求.md"])
        listing = self.flow.merge_result()
        with self.assertRaises(DocumentError):
            self.flow.finish_merge(listing)

    def test_source_branch_changes_after_preview_are_rejected(self):
        self.make_branches()
        plan = self.flow.plan_merge("feature")
        self.repo.checkout("feature")
        self.commit_text("新的来源\n")
        self.repo.checkout("main")
        with self.assertRaises(DocumentError):
            self.flow.start_merge(plan)

    def test_bom_and_crlf_are_visible_without_modification(self):
        self.commit_text("原\n")
        content = b"\xef\xbb\xbf" + "新\r\n".encode("utf-8")
        target = self.repo.path / "需求.md"
        target.write_bytes(content)
        pair = self.flow.workspace("需求.md")
        self.assertEqual(pair.right, "新\r\n")
        self.assertIn("BOM", pair.notice)
        self.assertIn("CRLF", pair.notice)
        self.assertEqual(target.read_bytes(), content)

    def test_root_commit_can_be_compared(self):
        oid = self.commit_text("第一版\n")
        listing = self.flow.compare_revisions("", oid)
        pair = self.flow.comparison_file(listing, "需求.md")
        self.assertEqual((pair.left, pair.right), ("", "第一版\n"))

    def test_large_file_does_not_enter_text_viewer(self):
        target = self.repo.path / "需求.md"
        target.write_bytes(b"a" * (2 * 1024 * 1024 + 1))
        pair = self.flow.workspace("需求.md")
        self.assertFalse(pair.supported)
        self.assertIn("2 MiB", pair.notice)

    def test_operation_change_after_review_is_rejected(self):
        base, _ = self.make_branches()
        self.flow.start_merge(self.flow.plan_merge("feature"))
        listing = self.flow.merge_result()
        self.flow.abort_merge()
        with self.assertRaises(DocumentError):
            self.flow.finish_merge(listing)
        self.assertEqual(self.repo.head_oid(), base)

    def test_external_head_change_during_merge_invalidates_result(self):
        _, source = self.make_branches()
        self.flow.start_merge(self.flow.plan_merge("feature"))
        self.repo._run(["update-ref", "refs/heads/main", source])
        with self.assertRaises(DocumentError):
            self.flow.merge_result()

    def test_index_change_during_final_scan_does_not_get_committed(self):
        base, _ = self.make_branches()
        self.flow.start_merge(self.flow.plan_merge("feature"))
        reviewed = self.flow.merge_result()
        original = self.flow._blob
        def change_index(record):
            value = original(record)
            (self.repo.path / "需求.md").write_bytes(b"UNREVIEWED CONTENT\n")
            self.repo.stage(["需求.md"])
            return value
        with patch.object(self.flow, "_blob", side_effect=change_index):
            with self.assertRaises(DocumentError):
                self.flow.finish_merge(reviewed)
        self.assertEqual(self.repo.head_oid(), base)

    def test_unsupported_source_is_rejected_before_merge_changes_worktree(self):
        base = self.commit_text("原\n")
        self.repo.create_branch("feature")
        self.repo.checkout("feature")
        (self.repo.path / "图片.bin").write_bytes(b"\x00" * (2 * 1024 * 1024 + 1))
        self.repo.stage(["图片.bin"])
        self.repo.commit("大文件")
        self.repo.checkout("main")
        with self.assertRaises(DocumentError):
            self.flow.start_merge(self.flow.plan_merge("feature"))
        self.assertEqual(self.repo.head_oid(), base)
        self.assertFalse(self.flow.merge_active())
        self.assertFalse((self.repo.path / "图片.bin").exists())

    def test_legal_markdown_setext_title_can_be_merged(self):
        self.make_branches()
        self.flow.start_merge(self.flow.plan_merge("feature"))
        (self.repo.path / "需求.md").write_bytes(b"Document title\n=======\n\nContent\n")
        self.repo.stage(["需求.md"])
        self.flow.finish_merge(self.flow.merge_result())
        self.assertFalse(self.flow.merge_active())


if __name__ == "__main__":
    unittest.main()
