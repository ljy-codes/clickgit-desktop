"""Read-only HTML review; extracted text and previews never become saved source."""
from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QListWidget, QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from clickgit.html_document import analyze_html
from clickgit.conflict_workflow import contains_conflict_markers
from clickgit.ui.diff_viewer import DiffViewer
from clickgit.ui.preview_session import PreviewSession


def is_html_path(path: str) -> bool:
    return PurePosixPath(path.replace("\\", "/")).suffix.lower() in (".html", ".htm")


def _label(text: str) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class HtmlReviewDialog(QDialog):
    def __init__(self, pair, parent=None, *, baselines=()):
        super().__init__(parent)
        self.pair = pair
        self._baselines = baselines
        self._sections = []
        # Kept as an empty compatibility attribute for callers checking lazy
        # construction; render widgets now exist exclusively in the child.
        self.preview_widgets = []
        self.preview_session = PreviewSession(self)
        self.setWindowTitle(f"HTML 审阅 · {pair.path}")
        self.resize(1280, 820)
        self.setMinimumSize(860, 580)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(_label(pair.path), 1)
        self.baseline_combo = QComboBox()
        for title, _source in baselines:
            self.baseline_combo.addItem(title)
        self.baseline_combo.setVisible(bool(baselines))
        self.baseline_combo.setToolTip("选择比较基准；右侧始终为打开检查时的结果副本。")
        header.addWidget(self.baseline_combo)
        help_button = QPushButton("?")
        help_button.setMaximumWidth(36)
        help_button.setStyleSheet("QPushButton { border-radius: 12px; }")
        help_button.setAccessibleName("HTML 审阅说明")
        help_button.clicked.connect(self._show_help)
        header.addWidget(help_button)
        layout.addLayout(header)
        self.warning_label = _label("")
        layout.addWidget(self.warning_label)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        requirements = QWidget()
        requirement_layout = QVBoxLayout(requirements)
        row = QHBoxLayout()
        self.section_status = _label("")
        row.addWidget(self.section_status, 1)
        self.locate_button = QPushButton("定位原源码")
        self.locate_button.clicked.connect(self._locate_source)
        row.addWidget(self.locate_button)
        requirement_layout.addLayout(row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.section_list = QListWidget()
        self.section_list.setMinimumWidth(130)
        self.requirements_viewer = DiffViewer()
        splitter.addWidget(self.section_list)
        splitter.addWidget(self.requirements_viewer)
        splitter.setSizes([230, 1000])
        requirement_layout.addWidget(splitter, 1)
        self.tabs.addTab(requirements, "需求对比")
        self.source_viewer = DiffViewer()
        self.tabs.addTab(self.source_viewer, "源码对比")

        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_row = QHBoxLayout()
        self.source_location = _label("原文件逐字只读展示，不格式化、不写回。")
        source_row.addWidget(self.source_location, 1)
        self.wrap_toggle = QCheckBox("自动换行")
        self.wrap_toggle.setChecked(True)
        self.wrap_toggle.toggled.connect(self._set_wrap)
        source_row.addWidget(self.wrap_toggle)
        source_layout.addLayout(source_row)
        original_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_left = QPlainTextEdit()
        self.source_right = QPlainTextEdit()
        self.source_titles = []
        for editor in (self.source_left, self.source_right):
            editor.setReadOnly(True)
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            label = _label("")
            self.source_titles.append(label)
            panel_layout.addWidget(label)
            panel_layout.addWidget(editor, 1)
            original_splitter.addWidget(panel)
        source_layout.addWidget(original_splitter, 1)
        self.source_page_index = self.tabs.addTab(source_page, "原文定位")
        preview_page = QWidget()
        self.preview_layout = QVBoxLayout(preview_page)
        self.preview_layout.addWidget(_label(
            "左右页面将在独立窗口中打开；保留内嵌样式，不执行脚本、不加载外部资源。"))
        self.preview_status = _label("尚未打开页面对比。支持正文高亮、改动定位和缩放；隐藏正文也可在详情中查看。")
        self.preview_layout.addWidget(self.preview_status)
        self.preview_button = QPushButton("打开 HTML 页面对比（独立窗口）")
        self.preview_button.clicked.connect(self._load_preview)
        self.preview_layout.addWidget(self.preview_button)
        self.preview_close_button = QPushButton("关闭本次预览")
        self.preview_close_button.setEnabled(False)
        self.preview_close_button.clicked.connect(self.preview_session.stop)
        self.preview_layout.addWidget(self.preview_close_button)
        self.preview_diagnostics_button = QPushButton("查看诊断信息")
        self.preview_diagnostics_button.clicked.connect(self._show_diagnostics)
        self.preview_layout.addWidget(self.preview_diagnostics_button)
        self.preview_layout.addStretch()
        self.preview_session.status_changed.connect(self._preview_status_changed)
        self.tabs.addTab(preview_page, "静态预览")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.section_list.currentRowChanged.connect(self._select_section)
        self.baseline_combo.currentIndexChanged.connect(self._baseline_changed)
        self._populate()

    def _populate(self):
        self._dispose_previews()
        self.source_viewer.set_comparison(
            self.pair.left, self.pair.right, self.pair.left_title,
            self.pair.right_title, self.pair.notice)
        # Keep Qt layout bounded even when the source diff refuses pathological input.
        for editor, title, source in zip(
                (self.source_left, self.source_right), self.source_titles,
                (self.pair.left, self.pair.right)):
            editor.clear()
            title.setText(self.pair.left_title if editor is self.source_left else self.pair.right_title)
            # HTML extraction normalizes physical CR/LF lines. Qt also treats
            # Unicode paragraph separators as blocks, unlike HTMLParser; refuse
            # that uncommon locator case rather than jumping to the wrong line.
            physical = source.replace("\r\n", "\n").replace("\r", "\n")
            separators = "\u2028" in source or "\u2029" in source
            if (len(source) <= 2 * 1024 * 1024
                    and len(source.encode("utf-8", errors="surrogatepass")) <= 2 * 1024 * 1024
                    and physical.count("\n") < 20000 and not separators
                    and all(len(line) <= 8192 for line in physical.split("\n"))):
                editor.setPlainText(physical)
                editor.setProperty("sourceLoaded", True)
            else:
                editor.setProperty("sourceLoaded", False)
                title.setText(title.text() + (
                    " · 含特殊段落分隔符，原文定位不可用，请看源码对比" if separators else
                    " · 超出原文显示预算，未加载"))
        self._sections = []
        self.section_list.clear()
        self.requirements_viewer.clear("正在提取正文…")
        self.locate_button.setEnabled(False)
        self.section_status.setText("")
        scope = "仅正文对比；样式、属性、脚本变化请检查源码。"
        if contains_conflict_markers(self.pair.left) or contains_conflict_markers(self.pair.right):
            scope = "检测到疑似冲突标记，请回源码处理；预览不代表已解决。 " + scope
        try:
            left = analyze_html(self.pair.left) if self.pair.left else None
            right = analyze_html(self.pair.right) if self.pair.right else None
            warnings = []
            for name, result in ((self.pair.left_title, left), (self.pair.right_title, right)):
                if result:
                    warnings.extend(f"{name}：{warning}" for warning in result.warnings)
                    if result.has_scripts:
                        warnings.append(f"{name}：含脚本，动态内容未执行。")
            self.warning_label.setText(scope + (" 有提取提示，点击 ? 查看。" if warnings else ""))
            self.warning_label.setToolTip("\n".join(warnings))
            left_sections = {section.key: section for section in left.sections} if left else {}
            right_sections = {section.key: section for section in right.sections} if right else {}
            keys = list(dict.fromkeys([*left_sections, *right_sections]))
            first_changed = None
            for key in keys:
                old, new = left_sections.get(key), right_sections.get(key)
                self._sections.append((old, new))
                status = "新增" if old is None else "删除" if new is None else (
                    "修改" if old.text != new.text else "相同")
                if status != "相同" and first_changed is None:
                    first_changed = len(self._sections) - 1
                self.section_list.addItem(f"[{status}] {(new or old).title}")
            if keys:
                self.section_list.setCurrentRow(first_changed if first_changed is not None else 0)
            else:
                self.requirements_viewer.clear("未提取到正文；请查看源码，不代表文件没有变化。")
        except ValueError as exc:
            self.warning_label.setText(f"{scope} 提取失败：{exc}")
            self.warning_label.setToolTip("")
            self.requirements_viewer.clear("正文提取不可用，请查看源码。")

    def _select_section(self, index):
        if index < 0 or index >= len(self._sections):
            self.locate_button.setEnabled(False)
            return
        old, new = self._sections[index]
        self.requirements_viewer.set_comparison(
            old.text if old else "", new.text if new else "",
            self.pair.left_title, self.pair.right_title, "提取视图只读，不用于写回文件。")
        self.section_status.setText(
            f"原源码行：左 {old.line if old else '—'} / 右 {new.line if new else '—'}")
        self.locate_button.setEnabled(any(
            section and editor.property("sourceLoaded")
            for section, editor in ((old, self.source_left), (new, self.source_right))))

    def _locate_source(self):
        index = self.section_list.currentRow()
        if index < 0 or index >= len(self._sections):
            return
        for section, editor in zip(self._sections[index], (self.source_left, self.source_right)):
            if section and editor.property("sourceLoaded"):
                block = editor.document().findBlockByNumber(section.line - 1)
                if block.isValid():
                    editor.setTextCursor(QTextCursor(block))
                    editor.centerCursor()
        self.source_location.setText(self.section_status.text() + " · 只读，显示换行不改变源文件")
        self.tabs.setCurrentIndex(self.source_page_index)

    def _set_wrap(self, checked):
        for editor in (self.source_left, self.source_right):
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if checked
                                   else QPlainTextEdit.LineWrapMode.NoWrap)

    def _baseline_changed(self, index):
        if 0 <= index < len(self._baselines):
            title, text = self._baselines[index]
            self.pair = replace(self.pair, left=text, left_title=title)
            self._populate()

    def _show_help(self):
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("HTML 审阅说明")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText("需求视图提取隐藏正文，不执行脚本；正文相同不等于整份文件相同。\n"
                    "源码为唯一写回依据。本窗口不保存、不暂存、不提交。\n"
                    "静态预览禁用交互和外部资源；解析成功不等于结构、脚本或业务检查通过。")
        box.setDetailedText(self.warning_label.toolTip() or "本次提取没有额外提示。")
        box.exec()
        box.deleteLater()

    def _load_preview(self):
        self.preview_session.start(self.pair)
        self._preview_status_changed()

    def _preview_status_changed(self, message=None):
        if message:
            self.preview_status.setText(message)
        self.preview_button.setEnabled(not self.preview_session.running)
        self.preview_close_button.setEnabled(self.preview_session.running)
        self.preview_button.setText("重新打开 HTML 页面对比" if self.preview_session.state in (
            "failed", "closed") else "打开 HTML 页面对比（独立窗口）")

    def _show_diagnostics(self):
        from clickgit.ui.diagnostics_dialog import show_diagnostics
        show_diagnostics(self)

    def _dispose_previews(self):
        self.preview_session.stop()
        self.preview_button.setEnabled(True)

    def done(self, result):
        self._dispose_previews()
        super().done(result)


def open_html_review(pair, parent=None, *, baselines=()):
    if not pair.supported or not is_html_path(pair.path):
        return
    dialog = HtmlReviewDialog(pair, parent, baselines=baselines)
    try:
        dialog.exec()
    finally:
        dialog._dispose_previews()
        dialog.deleteLater()
