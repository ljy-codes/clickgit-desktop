from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QCloseEvent, QPalette, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from clickgit.conflict_workflow import contains_conflict_markers, parse_conflict_blocks
from clickgit.document_workflow import TextComparison
from clickgit.ui.html_review import is_html_path, open_html_review


class ConflictEditorDialog(QDialog):
    save_requested = Signal(bool)

    def __init__(
        self,
        *,
        file_path: str,
        base_text: str,
        ours_text: str,
        theirs_text: str,
        result_text: str,
        parent: QWidget | None = None,
        allowed: bool = True,
        reason: str = "",
        defer_save: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"解决冲突 - {file_path}")
        self.resize(1200, 760)
        self.allowed = allowed
        self.file_path = file_path
        self.reason = reason
        self.defer_save = defer_save
        self._saving = False
        self.mark_resolved = False
        self._current = 0
        self._blocks = []
        self._marker_sizes = {7}

        self.base_editor = self._read_only_editor(base_text)
        self.ours_editor = self._read_only_editor(ours_text)
        self.theirs_editor = self._read_only_editor(theirs_text)
        self.result_editor = QPlainTextEdit(result_text)
        self.result_editor.setReadOnly(not allowed)

        self.comparison_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.base_panel = self._editor_panel("共同版本 · stage 1", self.base_editor)
        self.base_panel.hide()
        self.comparison_splitter.addWidget(
            self._editor_panel("当前侧 · stage 2 (ours)", self.ours_editor)
        )
        self.comparison_splitter.addWidget(self._editor_panel("最终结果（可编辑）", self.result_editor))
        self.comparison_splitter.addWidget(
            self._editor_panel("对方侧 · stage 3 (theirs)", self.theirs_editor)
        )
        self.comparison_splitter.setSizes([350, 500, 350])
        self.comparison_splitter.setChildrenCollapsible(False)

        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.addWidget(self.comparison_splitter)
        self.vertical_splitter.addWidget(self.base_panel)
        self.vertical_splitter.setCollapsible(0, False)
        self.vertical_splitter.setSizes([600, 0])

        self.ours_button = QPushButton("本块采用当前侧")
        self.ours_button.clicked.connect(self.choose_ours)
        self.theirs_button = QPushButton("本块采用对方侧")
        self.theirs_button.clicked.connect(self.choose_theirs)
        self.both_button = QPushButton("本块采用双方")
        self.both_button.clicked.connect(self.choose_both)
        self.both_button.setToolTip("仅取当前冲突块的内容，按 stage 2 → stage 3 排列；不会拼接两份全文。")
        self.previous_button = QPushButton("上一块")
        self.previous_button.clicked.connect(self.previous_conflict)
        self.next_button = QPushButton("下一块")
        self.next_button.clicked.connect(self.next_conflict)
        self.count_label = QLabel()
        self.base_toggle = QCheckBox("显示共同版本")
        self.base_toggle.setChecked(False)
        self.base_toggle.toggled.connect(self._toggle_base)

        actions = QHBoxLayout()
        for widget in (self.previous_button, self.next_button, self.count_label,
                       self.ours_button, self.theirs_button, self.both_button):
            actions.addWidget(widget)
        actions.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancel_button.setText("取消")
        self.draft_button = QPushButton("保存草稿（不暂存）")
        self.resolve_button = QPushButton("标记解决并暂存")
        for button in (self.draft_button, self.resolve_button):
            button.setAutoDefault(False)
            buttons.addButton(button, QDialogButtonBox.ButtonRole.ActionRole)
        self.draft_button.clicked.connect(self.save_draft)
        self.resolve_button.clicked.connect(self.save_resolved)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        help_label = QLabel("逐块取舍后保存；不会自动提交")
        help_label.setToolTip(
            "来源是索引 stage 2 / stage 3，不等同于本地 / 远程；rebase 时尤其如此。\n"
            "双方仅合并当前块，按 stage 2 → stage 3 排列。高亮区域是当前操作的冲突块。"
        )
        help_label.setWordWrap(True)
        header = QHBoxLayout()
        header.addWidget(help_label, 1)
        header.addWidget(self.base_toggle)
        self.html_review_button = QPushButton("检查 HTML 结果")
        self.html_review_button.setVisible(is_html_path(file_path))
        self.html_review_button.clicked.connect(self._review_html)
        header.addWidget(self.html_review_button)
        if is_html_path(file_path):
            self.both_button.setToolTip(
                "仅文本拼接，可能产生重复 ID、表格结构或脚本问题；采用后请检查 HTML 结果。")
        layout.addLayout(header)
        self.reason_label = QLabel(f"无法保存：{reason or '此冲突只读'}")
        self.reason_label.setTextFormat(Qt.TextFormat.PlainText)
        self.reason_label.setWordWrap(True)
        font = self.reason_label.font()
        font.setBold(True)
        self.reason_label.setFont(font)
        self.reason_label.setVisible(not allowed)
        layout.addWidget(self.reason_label)
        layout.addLayout(actions)
        layout.addWidget(self.vertical_splitter, 1)
        layout.addWidget(buttons)
        self.result_editor.textChanged.connect(self._refresh_blocks)
        self.result_editor.cursorPositionChanged.connect(self._cursor_changed)
        self._refresh_blocks()
        self._select_current()
        self.result_editor.setFocus()

    def _review_html(self) -> None:
        if self._saving or not is_html_path(self.file_path):
            return
        baselines = (
            ("当前侧 · stage 2", self.ours_editor.toPlainText()),
            ("对方侧 · stage 3", self.theirs_editor.toPlainText()),
            ("共同基准 · stage 1", self.base_editor.toPlainText()),
        )
        pair = TextComparison(
            self.file_path, baselines[0][1], self.result_text(),
            baselines[0][0], "结果副本 · 未保存",
            "只检查打开窗口时的编辑副本；不保存、不暂存。")
        open_html_review(pair, self, baselines=baselines)

    def _toggle_base(self, visible: bool) -> None:
        self.base_panel.setVisible(visible)
        height = max(self.vertical_splitter.height(), 400)
        self.vertical_splitter.setSizes(
            [height * 3 // 4, height // 4] if visible else [height, 0]
        )

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "result_editor"):
            self._highlight_current()

    def _highlight_current(self) -> None:
        if not self._blocks:
            self.result_editor.setExtraSelections([])
            return
        block = self._blocks[self._current]
        text = self.result_text()
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(self.result_editor.document())
        selection.cursor.setPosition(self._qt_position(text, block.start))
        selection.cursor.setPosition(
            self._qt_position(text, max(block.start, block.end - 1)),
            QTextCursor.MoveMode.KeepAnchor,
        )
        color = self.palette().color(QPalette.ColorRole.Highlight)
        color.setAlpha(65)
        selection.format.setBackground(color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        # ExtraSelection keeps a visible target without selecting editable text:
        # typing must not accidentally replace an entire conflict block.
        self.result_editor.setExtraSelections([selection])

    def choose_ours(self) -> None:
        self._choose("ours")

    def choose_theirs(self) -> None:
        self._choose("theirs")

    def choose_both(self) -> None:
        self._choose("both")

    @property
    def conflict_count(self) -> int:
        return len(self._blocks)

    @staticmethod
    def _qt_position(text: str, position: int) -> int:
        return len(text[:position].encode("utf-16-le")) // 2

    def _choose(self, side: str) -> None:
        if not self.allowed or self._saving or not self._blocks:
            return
        block = self._blocks[self._current]
        replacement = (block.ours + block.theirs if side == "both"
                       else getattr(block, side))
        text = self.result_text()
        cursor = self.result_editor.textCursor()
        cursor.setPosition(self._qt_position(text, block.start))
        cursor.setPosition(self._qt_position(text, block.end), QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        cursor.insertText(replacement)
        cursor.endEditBlock()
        self.result_editor.setTextCursor(cursor)
        self._select_current()

    def _refresh_blocks(self) -> None:
        text = self.result_text()
        self._blocks = parse_conflict_blocks(text)
        self._marker_sizes.update(block.marker_size for block in self._blocks)
        self._current = min(self._current, max(0, self.conflict_count - 1))
        self._update_actions()

    def _update_actions(self) -> None:
        self._highlight_current()
        has_blocks = bool(self._blocks)
        editable = self.allowed and not self._saving
        self.count_label.setText(
            f"冲突块 {self._current + 1} / {self.conflict_count}" if has_blocks else "冲突块 0 / 0"
        )
        for button in (self.ours_button, self.theirs_button, self.both_button):
            button.setEnabled(editable and has_blocks)
        self.previous_button.setEnabled(has_blocks and not self._saving)
        self.next_button.setEnabled(has_blocks and not self._saving)
        self.draft_button.setEnabled(editable)
        self.cancel_button.setEnabled(not self._saving)
        self.html_review_button.setEnabled(not self._saving and is_html_path(self.file_path))
        unresolved = contains_conflict_markers(self.result_text(), tuple(self._marker_sizes))
        self.resolve_button.setEnabled(editable and not unresolved)
        self.resolve_button.setToolTip(
            "仍有冲突标记（包括不完整标记），可先保存草稿" if unresolved
            else "保存文件并显式暂存；不自动提交"
        )

    def _cursor_changed(self) -> None:
        position = self.result_editor.textCursor().position()
        text = self.result_text()
        for index, block in enumerate(self._blocks):
            if self._qt_position(text, block.start) <= position < self._qt_position(text, block.end):
                self._current = index
                self._update_actions()
                break

    def _select_current(self) -> None:
        if not self._blocks:
            return
        block = self._blocks[self._current]
        cursor = self.result_editor.textCursor()
        cursor.setPosition(self._qt_position(self.result_text(), block.start))
        self.result_editor.setTextCursor(cursor)
        self.result_editor.ensureCursorVisible()
        self._update_actions()

    def next_conflict(self) -> None:
        if self._blocks:
            self._current = (self._current + 1) % self.conflict_count
            self._select_current()

    def previous_conflict(self) -> None:
        if self._blocks:
            self._current = (self._current - 1) % self.conflict_count
            self._select_current()

    def save_draft(self) -> None:
        self._request_save(False)

    def save_resolved(self) -> None:
        self._request_save(True)

    def _request_save(self, mark_resolved: bool) -> None:
        if not self.allowed or self._saving:
            return
        if mark_resolved and contains_conflict_markers(self.result_text(), tuple(self._marker_sizes)):
            return
        self.mark_resolved = mark_resolved
        if self.defer_save:
            # Enter the pending state before emitting: direct/queued slots must
            # not allow reentrant or double-click saves of the same snapshot.
            self.set_saving(True)
            self.save_requested.emit(mark_resolved)
        else:
            super().accept()

    def set_saving(self, saving: bool) -> None:
        """Main resets this on failure; text stays available for selection/copy.

        This never reloads/rebases a stale snapshot. A stale service session must
        be reopened by Main, not silently overwritten from this retained buffer.
        """
        self._saving = bool(saving)
        self.result_editor.setReadOnly(not self.allowed or self._saving)
        self._update_actions()

    def accept(self) -> None:
        if not self.allowed:
            return
        if self.defer_save:
            # Explicit acceptance in deferred mode is Main's success callback.
            self.set_saving(False)
            super().accept()
        else:
            self.save_draft()

    def reject(self) -> None:
        if not self._saving:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._saving:
            event.ignore()
        else:
            super().closeEvent(event)

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
