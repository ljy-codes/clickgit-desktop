"""Bounded, read-only side-by-side text comparison; no repository/file I/O.

Call set_comparison/clear on the GUI thread. Editor documents contain alignment
rows and display-normalized separators; use normal Copy for original text, not
toPlainText() for persistence. No folding, editing or merge-result calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from PySide6.QtCore import QEvent, QMimeData, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSizePolicy, QSplitter,
    QScrollBar, QTextEdit, QVBoxLayout, QWidget,
)

__all__ = ["DiffViewer"]

_MAX_BYTES = 2 * 1024 * 1024  # Per input, measured as UTF-8 (not Python characters).
_MAX_LINES = 20000
_MAX_LINE_LENGTH = 8192  # Qt can otherwise spend seconds laying out one long line.
_MAX_LINE_WORK = 250000
_MAX_CHAR_LENGTH = 2048
_MAX_CHAR_PAIR_WORK = 16384
_MAX_CHAR_TOTAL_WORK = 100000
# Preserve code-point/UTF-16 lengths while preventing Qt from making extra blocks.
_DISPLAY_TRANSLATION = str.maketrans({"\r": "␍", "\u2028": "↵", "\u2029": "¶"})


@dataclass(frozen=True)
class _Line:
    content: str
    ending: str


@dataclass(frozen=True)
class _Row:
    line: int | None
    kind: str = "equal"
    spans: tuple[tuple[int, int], ...] = ()


def _lines(text: str) -> list[_Line]:
    parts = text.split("\n")
    result = []
    for index, part in enumerate(parts):
        ending = "\n" if index < len(parts) - 1 else ""
        if ending and part.endswith("\r"):
            part, ending = part[:-1], "\r\n"
        result.append(_Line(part, ending))
    return result


def _blend(base: QColor, tint: QColor, weight: float) -> QColor:
    return QColor(*(round(a * (1 - weight) + b * weight) for a, b in zip(
        (base.red(), base.green(), base.blue()),
        (tint.red(), tint.green(), tint.blue()),
    )))


class _Gutter(QWidget):
    def __init__(self, editor: _DiffEditor) -> None:
        super().__init__(editor)
        self.editor = editor
        self.setAccessibleName("原文行号与增删标记")

    def paintEvent(self, event) -> None:
        editor = self.editor
        painter = QPainter(self)
        palette = editor.palette()
        painter.fillRect(event.rect(), palette.color(QPalette.AlternateBase))
        painter.setFont(editor.font())
        block = editor.firstVisibleBlock()
        while block.isValid():
            geometry = editor.blockBoundingGeometry(block).translated(editor.contentOffset())
            top = round(geometry.top())
            if top > event.rect().bottom():
                break
            row_index = block.blockNumber()
            if block.isVisible() and row_index < len(editor._rows):
                row = editor._rows[row_index]
                number = str(row.line + 1) if row.line is not None else ""
                marker = {"delete": "−", "insert": "+", "replace": "~",
                          "placeholder": "·"}.get(row.kind, "")
                painter.setPen(palette.color(QPalette.Text))
                painter.drawText(
                    QRect(0, top, self.width() - 6, round(geometry.height())),
                    Qt.AlignRight | Qt.AlignVCenter, f"{number} {marker}",
                )
            block = block.next()


class _DiffEditor(QPlainTextEdit):
    def __init__(self, parent: QWidget, *, removed: bool = False) -> None:
        super().__init__(parent)
        self._removed = removed
        self._source: list[_Line] = []
        self._rows: list[_Row] = []
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        # Equal viewport heights are necessary for synchronized last-page scrolling.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.gutter = _Gutter(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self._update_gutter_width()

    @property
    def line_numbers(self) -> list[int | None]:
        """Original 1-based line numbers; None denotes an alignment-only row."""
        return [row.line + 1 if row.line is not None else None for row in self._rows]

    def _update_gutter_width(self, *_args) -> None:
        digits = len(str(max(1, len(self._source))))
        width = self.fontMetrics().horizontalAdvance("9") * (digits + 2) + 16
        self.setViewportMargins(width, 0, 0, 0)
        rect = self.contentsRect()
        self.gutter.setGeometry(rect.left(), rect.top(), width, rect.height())
        self.gutter.update()

    def _update_gutter(self, rect: QRect, dy: int) -> None:
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_gutter_width()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "gutter"):
            if event.type() in (QEvent.FontChange, QEvent.StyleChange):
                self._update_gutter_width()
            if event.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
                self.refresh_highlights()
                self.gutter.update()

    def set_rows(self, source: list[_Line], rows: list[_Row]) -> None:
        self._source, self._rows = source, rows
        self.setPlainText("\n".join(
            source[row.line].content.translate(_DISPLAY_TRANSLATION)
            if row.line is not None else "" for row in rows
        ))
        self._update_gutter_width()
        self.refresh_highlights()

    def createMimeDataFromSelection(self) -> QMimeData:
        """Exclude synthetic rows/numbers, retaining original CRLF and Unicode."""
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        block = self.document().findBlock(start)
        pieces = []
        while start < end and block.isValid() and block.position() <= end:
            index = block.blockNumber()
            if index < len(self._rows) and self._rows[index].line is not None:
                line = self._source[self._rows[index].line]
                encoded = line.content.encode("utf-16-le", errors="surrogatepass")
                lo = max(0, start - block.position()) * 2
                hi = max(0, end - block.position()) * 2
                pieces.append(encoded[lo:hi].decode("utf-16-le", errors="surrogatepass"))
                if end > block.position() + len(encoded) // 2:
                    pieces.append(line.ending)
            block = block.next()
        mime = QMimeData()
        mime.setText("".join(pieces))
        return mime

    def refresh_highlights(self) -> None:
        palette = self.palette()
        base = palette.color(QPalette.Base)
        text = palette.color(QPalette.Text)
        # Semantic colors must not inherit link/selection colors (blue/grey in
        # our themes). Keep the theme text color readable over both strengths.
        light = base.lightnessF() > 0.5
        tints = {
            "insert": QColor("#a8e1b3" if light else "#27804c"),
            "delete": QColor("#f6b6bd" if light else "#a34558"),
            "replace": QColor("#edca80" if light else "#795c2c"),
            "placeholder": palette.color(QPalette.AlternateBase),
        }
        inline_tint = tints["delete" if self._removed else "insert"]
        selections = []
        # Traverse blocks once, rather than repeatedly resolving block numbers.
        block = self.document().firstBlock()
        for row in self._rows:
            if not block.isValid():
                break
            if row.kind != "equal":
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(block)
                selection.format.setProperty(QTextFormat.FullWidthSelection, True)
                selection.format.setBackground(_blend(base, tints[row.kind], 0.22))
                selection.format.setForeground(text)
                selections.append(selection)
                for start, end in row.spans:
                    inline = QTextEdit.ExtraSelection()
                    inline.cursor = QTextCursor(block)
                    inline.cursor.setPosition(block.position() + start)
                    inline.cursor.setPosition(block.position() + end, QTextCursor.KeepAnchor)
                    inline.format.setBackground(_blend(base, inline_tint, 0.85))
                    inline.format.setForeground(text)
                    selections.append(inline)
            block = block.next()
        self.setExtraSelections(selections)


class DiffViewer(QWidget):
    """Independent Qt text diff. Inputs are never written to disk.

    Both inputs are capped at 2 MiB UTF-8 / 20,000 LF-delimited display lines
    (a terminal LF includes its trailing empty line). A single display line is
    capped at 8,192 code points. Expensive comparisons are rejected, not silently
    truncated. Character-level work has a separate budget and falls back to rows.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hunks: list[int] = []
        self._current = -1
        self._summary = ""
        self._syncing = False
        self.left_editor = _DiffEditor(self, removed=True)
        self.right_editor = _DiffEditor(self)
        self.left_editor.setAccessibleName("原版本文本（只读）")
        self.right_editor.setAccessibleName("修改后版本文本（只读）")
        self.left_title_label = self._label("原版本")
        self.right_title_label = self._label("修改后版本")
        self.notice_label = self._label("")
        self.notice_label.setWordWrap(True)
        self.status_label = self._label("")
        self.status_label.setWordWrap(True)
        self.previous_button = QPushButton("上一差异", self)
        self.next_button = QPushButton("下一差异", self)
        self.previous_button.clicked.connect(self.previous_difference)
        self.next_button.clicked.connect(self.next_difference)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self._label("全文 · 红色 − 删除 / 绿色 + 新增 / 浅底 ~ 修改行"))
        toolbar.addStretch()
        toolbar.addWidget(self.previous_button)
        toolbar.addWidget(self.next_button)
        layout.addLayout(toolbar)
        layout.addWidget(self.notice_label)
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        for title, editor in (
            (self.left_title_label, self.left_editor),
            (self.right_title_label, self.right_editor),
        ):
            pane = QWidget(self.splitter)
            pane.setMinimumWidth(80)
            column = QVBoxLayout(pane)
            column.setContentsMargins(0, 0, 0, 0)
            title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            column.addWidget(title)
            column.addWidget(editor)
            self.splitter.addWidget(pane)
        self.splitter.setSizes([1, 1])
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.status_label)
        for source, target in (
            (self.left_editor, self.right_editor),
            (self.right_editor, self.left_editor),
        ):
            source.verticalScrollBar().valueChanged.connect(
                lambda value, bar=target.verticalScrollBar(): self._sync_scroll(bar, value)
            )
            source.horizontalScrollBar().valueChanged.connect(
                lambda value, bar=target.horizontalScrollBar(): self._sync_scroll(bar, value)
            )
        self.clear()

    def _label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setTextFormat(Qt.PlainText)
        return label

    @property
    def difference_count(self) -> int:
        return len(self._hunks)

    @property
    def current_difference(self) -> int:
        """Zero-based selected hunk, or -1 before navigation/after clearing."""
        return self._current

    @property
    def comparison_loaded(self) -> bool:
        """Both editor documents loaded successfully, including equal/empty text."""
        return self._comparison_loaded

    def clear(self, message: str = "请选择文件查看内容对比") -> None:
        self._comparison_loaded = False
        self._hunks = []
        self._current = -1
        self._summary = ""
        self._syncing = True
        try:
            self.left_editor.set_rows([], [])
            self.right_editor.set_rows([], [])
        finally:
            self._syncing = False
        self.left_title_label.setText("原版本")
        self.right_title_label.setText("修改后版本")
        self.left_title_label.setToolTip("")
        self.right_title_label.setToolTip("")
        self.notice_label.clear()
        self.notice_label.hide()
        self.status_label.setText(message)
        self.status_label.setToolTip("")
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)

    def set_comparison(
        self, left_text: str, right_text: str, left_title: str = "原版本",
        right_title: str = "修改后版本", notice: str = "",
    ) -> None:
        self.clear()
        self.left_title_label.setText(left_title)
        self.right_title_label.setText(right_title)
        self.left_title_label.setToolTip(left_title)
        self.right_title_label.setToolTip(right_title)
        self.notice_label.setText(notice)
        self.notice_label.setVisible(bool(notice))
        for text in (left_text, right_text):
            # Check character count first: do not allocate an encoding of huge input.
            if len(text) > _MAX_BYTES or len(text.encode("utf-8", errors="surrogatepass")) > _MAX_BYTES:
                self.status_label.setText("文本超过 2 MiB 上限，未加载对比。")
                return
            if text.count("\n") + 1 > _MAX_LINES:
                self.status_label.setText("文本超过 20000 行上限，未加载对比。")
                return
        left, right = _lines(left_text), _lines(right_text)
        if any(len(line.content) > _MAX_LINE_LENGTH for lines in (left, right) for line in lines):
            self.status_label.setText("单行超过 8192 字符安全上限，未加载对比。")
            return

        # Trim common edges in O(bytes). difflib is only allowed a small matrix;
        # autojunk alone is not a worst-case complexity guard for repeated input.
        prefix = 0
        while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
            prefix += 1
        a_end, b_end = len(left), len(right)
        while a_end > prefix and b_end > prefix and left[a_end - 1] == right[b_end - 1]:
            a_end -= 1
            b_end -= 1
        if (a_end - prefix) * (b_end - prefix) > _MAX_LINE_WORK:
            self.status_label.setText("差异复杂度超过安全预算，未加载；请缩小比较范围。")
            return
        opcodes = [("equal", 0, prefix, 0, prefix)] if prefix else []
        if prefix < a_end or prefix < b_end:
            # Intern into small integers before matching, avoiding repeated long
            # string equality/hashing inside SequenceMatcher's nested loops.
            identifiers: dict[_Line, int] = {}

            def tokens(lines: list[_Line]) -> list[int]:
                return [identifiers.setdefault(line, len(identifiers)) for line in lines]

            a_tokens, b_tokens = tokens(left[prefix:a_end]), tokens(right[prefix:b_end])
            matcher = SequenceMatcher(None, a_tokens, b_tokens, autojunk=False)
            opcodes.extend((tag, i + prefix, j + prefix, k + prefix, m + prefix)
                           for tag, i, j, k, m in matcher.get_opcodes())
        if a_end < len(left):
            opcodes.append(("equal", a_end, len(left), b_end, len(right)))

        left_rows: list[_Row] = []
        right_rows: list[_Row] = []
        char_budget = _MAX_CHAR_TOTAL_WORK
        simplified = False
        for tag, a, b, c, d in opcodes:
            if tag != "equal":
                self._hunks.append(len(left_rows))
            for offset in range(max(b - a, d - c)):
                li = a + offset if a + offset < b else None
                ri = c + offset if c + offset < d else None
                left_spans: tuple[tuple[int, int], ...] = ()
                right_spans: tuple[tuple[int, int], ...] = ()
                if tag == "replace" and li is not None and ri is not None:
                    old, new = left[li].content, right[ri].content
                    if old != new:
                        # Long HTML rows often differ by only a couple of digits.
                        # Trim equal edges linearly before charging the bounded
                        # matcher; do not relax limits for repetitive middles.
                        start, old_end, new_end = self._changed_region(old, new)
                        old_middle, new_middle = old[start:old_end], new[start:new_end]
                        work = max(1, len(old_middle)) * max(1, len(new_middle))
                        if (max(len(old_middle), len(new_middle)) <= _MAX_CHAR_LENGTH
                                and work <= min(_MAX_CHAR_PAIR_WORK, char_budget)):
                            char_budget -= work
                            left_spans, right_spans = self._character_spans(old_middle, new_middle)
                            # Qt cursors use UTF-16, not Python code-point offsets.
                            shift = len(old[:start].encode("utf-16-le", errors="surrogatepass")) // 2
                            left_spans = tuple((a + shift, b + shift) for a, b in left_spans)
                            right_spans = tuple((a + shift, b + shift) for a, b in right_spans)
                        else:
                            simplified = True
                left_kind = ("placeholder" if li is None else
                             "delete" if ri is None else tag)
                right_kind = ("placeholder" if ri is None else
                              "insert" if li is None else tag)
                left_rows.append(_Row(li, left_kind, left_spans))
                right_rows.append(_Row(ri, right_kind, right_spans))
        self._syncing = True
        try:
            self.left_editor.set_rows(left, left_rows)
            self.right_editor.set_rows(right, right_rows)
            self.left_editor.verticalScrollBar().setValue(0)
            self.right_editor.verticalScrollBar().setValue(0)
        finally:
            self._syncing = False
        self._summary = (
            f"末尾换行：左{'有' if left_text.endswith(chr(10)) else '无'} / "
            f"右{'有' if right_text.endswith(chr(10)) else '无'}"
        )
        details = (
            "全文、不折叠；CRLF/LF 按行显示，特殊分隔符显示为 ␍/↵/¶，复制保留原文。"
        )
        if simplified:
            self._summary += " · 部分仅行级"
            details += " 部分行内比较超预算，仅行级高亮。"
        self.status_label.setToolTip(details)
        self.previous_button.setEnabled(bool(self._hunks))
        self.next_button.setEnabled(bool(self._hunks))
        self._update_status()
        self._comparison_loaded = True

    @staticmethod
    def _changed_region(old: str, new: str) -> tuple[int, int, int]:
        start = 0
        while start < min(len(old), len(new)) and old[start] == new[start]:
            start += 1
        old_end, new_end = len(old), len(new)
        while old_end > start and new_end > start and old[old_end - 1] == new[new_end - 1]:
            old_end -= 1
            new_end -= 1
        return start, old_end, new_end

    @staticmethod
    def _character_spans(old: str, new: str):
        spans: list[list[tuple[int, int]]] = [[], []]
        offsets = []
        for text in (old, new):
            positions = [0]
            for char in text:
                positions.append(positions[-1] + (2 if ord(char) > 0xFFFF else 1))
            offsets.append(positions)
        for tag, a, b, c, d in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag != "equal":
                if a < b:
                    spans[0].append((offsets[0][a], offsets[0][b]))
                if c < d:
                    spans[1].append((offsets[1][c], offsets[1][d]))
        return tuple(spans[0]), tuple(spans[1])

    def _sync_scroll(self, target: QScrollBar, value: int) -> None:
        if not self._syncing:
            self._syncing = True
            try:
                target.setValue(value)
            finally:
                self._syncing = False

    def next_difference(self) -> None:
        self._navigate(1)

    def previous_difference(self) -> None:
        self._navigate(-1)

    def _navigate(self, direction: int) -> None:
        if not self._hunks:
            return
        self._current = ((0 if direction > 0 else len(self._hunks) - 1)
                         if self._current < 0 else (self._current + direction) % len(self._hunks))
        row = self._hunks[self._current]
        self._syncing = True
        try:
            for editor in (self.left_editor, self.right_editor):
                editor.setTextCursor(QTextCursor(editor.document().findBlockByNumber(row)))
            # Cursor movement can scroll differently; align explicitly afterwards.
            value = min(row, self.left_editor.verticalScrollBar().maximum(),
                        self.right_editor.verticalScrollBar().maximum())
            self.left_editor.verticalScrollBar().setValue(value)
            self.right_editor.verticalScrollBar().setValue(value)
        finally:
            self._syncing = False
        self._update_status()

    def _update_status(self) -> None:
        position = f"{self._current + 1}/{len(self._hunks)}"
        result = f"差异 {position}" if self._hunks else "内容相同（0 处差异）"
        self.status_label.setText(f"{result} · {self._summary}")
