from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


class ConflictEditorDialog(QDialog):
    def __init__(
        self,
        *,
        file_path: str,
        base_text: str,
        ours_text: str,
        theirs_text: str,
        result_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"解决冲突 - {file_path}")
        self.resize(1200, 760)

        self.base_editor = self._read_only_editor(base_text)
        self.ours_editor = self._read_only_editor(ours_text)
        self.theirs_editor = self._read_only_editor(theirs_text)
        self.result_editor = QPlainTextEdit(result_text)

        source_splitter = QSplitter(Qt.Orientation.Horizontal)
        source_splitter.addWidget(
            self._editor_panel("共同版本", self.base_editor)
        )
        source_splitter.addWidget(
            self._editor_panel("本地版本", self.ours_editor)
        )
        source_splitter.addWidget(
            self._editor_panel("远程版本", self.theirs_editor)
        )
        source_splitter.setSizes([400, 400, 400])

        result_panel = self._editor_panel("最终结果", self.result_editor)
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        vertical_splitter.addWidget(source_splitter)
        vertical_splitter.addWidget(result_panel)
        vertical_splitter.setSizes([330, 330])

        choose_ours = QPushButton("使用本地版本")
        choose_ours.clicked.connect(self.choose_ours)
        choose_theirs = QPushButton("使用远程版本")
        choose_theirs.clicked.connect(self.choose_theirs)
        choose_both = QPushButton("保留两边内容")
        choose_both.clicked.connect(self.choose_both)

        actions = QHBoxLayout()
        actions.addWidget(choose_ours)
        actions.addWidget(choose_theirs)
        actions.addWidget(choose_both)
        actions.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存结果")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(vertical_splitter, 1)
        layout.addWidget(buttons)

    def choose_ours(self) -> None:
        self.result_editor.setPlainText(self.ours_editor.toPlainText())

    def choose_theirs(self) -> None:
        self.result_editor.setPlainText(self.theirs_editor.toPlainText())

    def choose_both(self) -> None:
        ours = self.ours_editor.toPlainText()
        theirs = self.theirs_editor.toPlainText()
        separator = "" if ours.endswith("\n") or not ours else "\n"
        self.result_editor.setPlainText(f"{ours}{separator}{theirs}")

    def result_text(self) -> str:
        return self.result_editor.toPlainText()

    @staticmethod
    def _read_only_editor(text: str) -> QPlainTextEdit:
        editor = QPlainTextEdit(text)
        editor.setReadOnly(True)
        return editor

    @staticmethod
    def _editor_panel(title: str, editor: QPlainTextEdit) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        layout.addWidget(editor, 1)
        return panel
