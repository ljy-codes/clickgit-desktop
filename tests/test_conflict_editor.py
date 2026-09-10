from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from clickgit.ui.conflict_editor import ConflictEditorDialog


class ConflictEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def dialog(self, result=None, **kwargs):
        dialog = ConflictEditorDialog(
            file_path="src/app.py",
            base_text="FULL BASE",
            ours_text="FULL STAGE TWO",
            theirs_text="FULL STAGE THREE",
            result_text=self.blocks() if result is None else result,
            **kwargs,
        )
        self.addCleanup(self._destroy_dialog, dialog)
        return dialog

    @staticmethod
    def _destroy_dialog(dialog):
        dialog.set_saving(False)
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    @staticmethod
    def blocks():
        return ("prefix\n<<<<<<< HEAD\none ours\n=======\none theirs\n>>>>>>> topic\n"
                "middle\n<<<<<<< HEAD\ntwo ours\n=======\ntwo theirs\n>>>>>>> topic\nsuffix\n")

    def test_dialog_cleanup_destroys_native_windows_even_while_saving(self) -> None:
        for saving in (False, True):
            with self.subTest(saving=saving):
                before = len(QApplication.topLevelWidgets())
                dialog = self.dialog(defer_save=True)
                dialog.show()
                dialog.set_saving(saving)
                self.doCleanups()
                after = len(QApplication.topLevelWidgets())
                print(f"dialog lifecycle saving={saving}: before={before}, after={after}",
                      flush=True)
                self.assertEqual(after, before, "测试清理不能留下顶层窗口")
                self.assertFalse(isValid(dialog), "仍持有 Python 引用时也必须销毁 native dialog")

    def test_choose_ours_changes_only_current_block(self) -> None:
        dialog = self.dialog()
        dialog.choose_ours()
        self.assertEqual(dialog.result_text(), self.blocks().replace(
            "<<<<<<< HEAD\none ours\n=======\none theirs\n>>>>>>> topic\n", "one ours\n"))

    def test_choose_both_never_concatenates_full_documents(self) -> None:
        dialog = self.dialog()
        dialog.choose_both()
        self.assertEqual(dialog.result_text(), self.blocks().replace(
            "<<<<<<< HEAD\none ours\n=======\none theirs\n>>>>>>> topic\n", "one ours\none theirs\n"))

    def test_navigation_targets_second_block_and_counts_update(self) -> None:
        dialog = self.dialog()
        self.assertEqual(dialog.conflict_count, 2)
        dialog.next_conflict()
        dialog.choose_theirs()
        self.assertIn("middle\ntwo theirs\nsuffix", dialog.result_text())
        self.assertIn("one ours\n=======", dialog.result_text())
        self.assertEqual(dialog.conflict_count, 1)
        dialog.previous_conflict()
        dialog.choose_ours()
        self.assertEqual(dialog.conflict_count, 0)
        self.assertTrue(dialog.resolve_button.isEnabled())

    def test_diff3_zdiff3_custom_marker_lengths(self) -> None:
        for size in (1, 2, 3, 7, 12):
            with self.subTest(size=size):
                text = (f"common\n{'<' * size} HEAD\nours\n{'|' * size} base\nbase\n"
                        f"{'=' * size}\ntheirs\n{'>' * size} topic\nshared\n")
                dialog = self.dialog(text)
                dialog.choose_both()
                self.assertEqual(dialog.result_text(), "common\nours\ntheirs\nshared\n")

    def test_manual_edits_reparse_blocks_and_residual_markers_disable_resolution(self) -> None:
        dialog = self.dialog()
        dialog.result_editor.setPlainText("manual\n\n=======\n")
        self.assertFalse(dialog.resolve_button.isEnabled())
        dialog.result_editor.setPlainText("clean result")
        self.assertEqual(dialog.conflict_count, 0)
        self.assertTrue(dialog.resolve_button.isEnabled())
        self.assertTrue(dialog.draft_button.isEnabled())

    def test_no_complete_block_is_never_full_document_fallback(self) -> None:
        for text in ("", "manual", "<<<<<<< HEAD\nbroken\n"):
            dialog = self.dialog(text)
            dialog.choose_ours()
            dialog.choose_theirs()
            dialog.choose_both()
            self.assertEqual(dialog.result_text(), text)

    def test_draft_and_resolved_actions_expose_different_save_intent(self) -> None:
        draft = self.dialog()
        draft.draft_button.click()
        self.assertFalse(draft.mark_resolved)
        self.assertEqual(draft.result(), draft.DialogCode.Accepted)
        solved = self.dialog("solved\n")
        solved.resolve_button.click()
        self.assertTrue(solved.mark_resolved)
        self.assertEqual(solved.result(), solved.DialogCode.Accepted)

    def test_disallowed_session_is_read_only_and_cannot_accept(self) -> None:
        dialog = self.dialog(allowed=False, reason="禁止覆盖链接")
        self.assertTrue(dialog.result_editor.isReadOnly())
        self.assertFalse(dialog.draft_button.isEnabled())
        self.assertFalse(dialog.resolve_button.isEnabled())
        before = dialog.result_text()
        dialog.choose_ours()
        self.assertEqual(dialog.result_text(), before)
        dialog.accept()
        self.assertNotEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_labels_are_stage_neutral_and_base_can_collapse(self) -> None:
        from PySide6.QtWidgets import QLabel
        dialog = self.dialog()
        text = " ".join(label.text() for label in dialog.findChildren(QLabel))
        self.assertIn("stage 2", text.lower())
        self.assertIn("stage 3", text.lower())
        self.assertNotIn("远程版本", text)
        dialog.base_toggle.setChecked(False)
        self.assertTrue(dialog.base_panel.isHidden())

    def test_non_bmp_prefix_cursor_targets_correct_block_and_undo_works(self) -> None:
        dialog = self.dialog("😀\n" + self.blocks())
        dialog.next_conflict()
        dialog.choose_theirs()
        self.assertIn("middle\ntwo theirs\nsuffix", dialog.result_text())
        dialog.result_editor.undo()
        self.assertEqual(dialog.result_text(), "😀\n" + self.blocks())

    def test_malformed_marker_without_space_blocks_resolve(self) -> None:
        dialog = self.dialog("manual\n<<<<<<<HEAD\n")
        self.assertFalse(dialog.resolve_button.isEnabled())

    def test_short_marker_size_remains_known_after_manual_partial_removal(self) -> None:
        dialog = self.dialog("<< HEAD\nours\n==\ntheirs\n>> topic\n")
        dialog.result_editor.setPlainText("resolved\n\n==\n")
        self.assertFalse(dialog.resolve_button.isEnabled())

    def test_manual_cursor_selects_the_block_instead_of_navigation_state(self) -> None:
        from PySide6.QtGui import QTextCursor
        dialog = self.dialog()
        cursor = dialog.result_editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock, n=3)
        dialog.result_editor.setTextCursor(cursor)
        dialog.choose_theirs()
        self.assertIn("middle\ntwo theirs\nsuffix", dialog.result_text())
        self.assertIn("one ours\n=======", dialog.result_text())

    def test_final_result_is_between_stage_two_and_stage_three(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QSplitter
        dialog = self.dialog()
        horizontal = [splitter for splitter in dialog.findChildren(QSplitter)
                      if splitter.orientation() == Qt.Orientation.Horizontal]
        self.assertEqual(len(horizontal), 1)
        splitter = horizontal[0]
        self.assertEqual(splitter.count(), 3)
        for index, editor in enumerate((dialog.ours_editor, dialog.result_editor, dialog.theirs_editor)):
            self.assertTrue(splitter.widget(index).isAncestorOf(editor))
        self.assertFalse(splitter.isAncestorOf(dialog.base_editor))

    def test_base_is_initially_collapsed_and_can_expand_independently(self) -> None:
        dialog = self.dialog()
        self.assertFalse(dialog.base_toggle.isChecked())
        self.assertTrue(dialog.base_panel.isHidden())
        dialog.base_toggle.setChecked(True)
        self.assertFalse(dialog.base_panel.isHidden())
        dialog.base_toggle.setChecked(False)
        self.assertTrue(dialog.base_panel.isHidden())

    def test_current_block_is_highlighted_initially_and_after_navigation(self) -> None:
        dialog = self.dialog("😀\n" + self.blocks())
        highlights = dialog.result_editor.extraSelections()
        self.assertTrue(highlights)
        self.assertIn("one ours", highlights[0].cursor.selectedText())
        self.assertNotIn("two ours", highlights[0].cursor.selectedText())
        self.assertGreater(highlights[0].format.background().color().alpha(), 0)
        dialog.next_conflict()
        highlights = dialog.result_editor.extraSelections()
        self.assertIn("two ours", highlights[0].cursor.selectedText())
        dialog.choose_theirs()
        highlights = dialog.result_editor.extraSelections()
        self.assertIn("one ours", highlights[0].cursor.selectedText())
        dialog.choose_ours()
        self.assertEqual(dialog.result_editor.extraSelections(), [])

    def test_manual_edit_refreshes_highlight_without_selecting_or_replacing_whole_block(self) -> None:
        dialog = self.dialog()
        self.assertFalse(dialog.result_editor.textCursor().hasSelection())
        dialog.result_editor.insertPlainText("note\n")
        highlights = dialog.result_editor.extraSelections()
        self.assertTrue(highlights)
        self.assertIn("one ours", highlights[0].cursor.selectedText())
        self.assertTrue(dialog.result_text().startswith("prefix\nnote\n<<<<<<<"))
        dialog.result_editor.setPlainText("fully manual result")
        self.assertEqual(dialog.result_editor.extraSelections(), [])

    def test_concise_header_chinese_cancel_and_technical_tooltip(self) -> None:
        from PySide6.QtWidgets import QDialogButtonBox, QLabel
        dialog = self.dialog()
        texts = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertIn("逐块取舍后保存；不会自动提交", texts)
        self.assertFalse(any("rebase" in text for text in texts))
        buttons = dialog.findChild(QDialogButtonBox)
        self.assertEqual(buttons.button(QDialogButtonBox.StandardButton.Cancel).text(), "取消")
        tooltips = " ".join(widget.toolTip() for widget in dialog.findChildren(QLabel))
        self.assertIn("rebase", tooltips)
        self.assertIn("stage 2 → stage 3", dialog.both_button.toolTip())

    def test_disallowed_reason_is_visible_separately_from_header(self) -> None:
        from PySide6.QtWidgets import QLabel
        dialog = self.dialog(allowed=False, reason="外部索引已变化，禁止覆盖")
        labels = dialog.findChildren(QLabel)
        error = next(label for label in labels if "外部索引已变化，禁止覆盖" in label.text())
        self.assertFalse(error.isHidden())
        self.assertTrue(error.font().bold())
        self.assertTrue(any(label.text() == "逐块取舍后保存；不会自动提交" for label in labels))

    def test_deferred_draft_emits_intent_without_accepting_and_failure_keeps_text(self) -> None:
        dialog = self.dialog(defer_save=True)
        intents, accepted = [], []
        dialog.save_requested.connect(intents.append)
        dialog.accepted.connect(lambda: accepted.append(True))
        dialog.draft_button.click()
        self.assertEqual(intents, [False])
        self.assertFalse(dialog.mark_resolved)
        self.assertEqual(accepted, [])
        self.assertEqual(dialog.result_text(), self.blocks())
        dialog.set_saving(False)
        self.assertFalse(dialog.result_editor.isReadOnly())
        self.assertTrue(dialog.draft_button.isEnabled())
        self.assertEqual(dialog.result_text(), self.blocks())

    def test_deferred_resolve_stays_open_until_main_explicitly_accepts(self) -> None:
        dialog = self.dialog("resolved\n", defer_save=True)
        intents, accepted = [], []
        dialog.save_requested.connect(intents.append)
        dialog.accepted.connect(lambda: accepted.append(True))
        dialog.resolve_button.click()
        self.assertEqual(intents, [True])
        self.assertTrue(dialog.mark_resolved)
        self.assertEqual(accepted, [])
        dialog.accept()
        self.assertEqual(accepted, [True])
        self.assertTrue(dialog.mark_resolved)

    def test_saving_disables_mutation_duplicate_requests_cancel_escape_and_close(self) -> None:
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QDialogButtonBox
        dialog = self.dialog("resolved\n", defer_save=True)
        intents, rejected = [], []
        dialog.save_requested.connect(intents.append)
        dialog.rejected.connect(lambda: rejected.append(True))
        dialog.set_saving(True)
        self.assertTrue(dialog.result_editor.isReadOnly())
        self.assertTrue(dialog.result_editor.isEnabled(), "仍应允许选择和复制")
        self.assertFalse(dialog.draft_button.isEnabled())
        self.assertFalse(dialog.resolve_button.isEnabled())
        cancel = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel)
        self.assertFalse(cancel.isEnabled())
        dialog.save_draft()
        dialog.save_resolved()
        dialog.choose_ours()
        dialog.reject()  # Esc calls reject as well.
        close = QCloseEvent()
        dialog.closeEvent(close)
        self.assertFalse(close.isAccepted())
        self.assertEqual(intents, [])
        self.assertEqual(rejected, [])
        self.assertEqual(dialog.result_text(), "resolved\n")
        dialog.set_saving(False)
        self.assertTrue(cancel.isEnabled())
        dialog.reject()
        self.assertEqual(rejected, [True])

    def test_deferred_request_enters_saving_before_reentrant_repeat(self) -> None:
        dialog = self.dialog("ready\n", defer_save=True)
        intents = []

        def handle(intent):
            intents.append(intent)
            if len(intents) < 2:
                dialog.save_resolved()

        dialog.save_requested.connect(handle)
        dialog.save_resolved()
        self.assertEqual(intents, [True])
        self.assertTrue(dialog.result_editor.isReadOnly())
        dialog.set_saving(False)

    def test_saving_state_does_not_unlock_disallowed_session_or_residual_markers(self) -> None:
        blocked = self.dialog(allowed=False, reason="过期必须重开", defer_save=True)
        blocked.set_saving(True)
        blocked.set_saving(False)
        self.assertTrue(blocked.result_editor.isReadOnly())
        self.assertFalse(blocked.draft_button.isEnabled())
        self.assertFalse(blocked.resolve_button.isEnabled())
        unresolved = self.dialog(defer_save=True)
        unresolved.set_saving(True)
        unresolved.set_saving(False)
        self.assertTrue(unresolved.draft_button.isEnabled())
        self.assertFalse(unresolved.resolve_button.isEnabled())

    def test_legal_markdown_title_does_not_disable_resolve(self) -> None:
        dialog = self.dialog("Document title\n=======\n\nPRD contents\n")
        self.assertTrue(dialog.resolve_button.isEnabled())
        self.assertEqual(dialog.conflict_count, 0)
        dialog.save_resolved()
        self.assertTrue(dialog.mark_resolved)
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)


if __name__ == "__main__":
    unittest.main()
