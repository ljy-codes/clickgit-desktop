from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from clickgit.ui.conflict_editor import ConflictEditorDialog


class ConflictEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_choose_ours_and_theirs_updates_result(self) -> None:
        dialog = ConflictEditorDialog(
            file_path="src/app.py",
            base_text="base",
            ours_text="ours",
            theirs_text="theirs",
            result_text="",
        )

        dialog.choose_ours()
        self.assertEqual(dialog.result_text(), "ours")

        dialog.choose_theirs()
        self.assertEqual(dialog.result_text(), "theirs")

    def test_choose_both_preserves_both_versions(self) -> None:
        dialog = ConflictEditorDialog(
            file_path="src/app.py",
            base_text="base",
            ours_text="ours",
            theirs_text="theirs",
            result_text="",
        )

        dialog.choose_both()

        self.assertEqual(dialog.result_text(), "ours\ntheirs")


if __name__ == "__main__":
    unittest.main()
