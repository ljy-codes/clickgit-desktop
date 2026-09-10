"""Visual review UI, constructed only inside the owned preview child."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from clickgit.html_preview_policy import NOTICE
from clickgit.html_visual_diff import compare_html_text
from clickgit.ui.html_preview import HtmlPreview


def _label(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class HtmlPreviewWindow(QDialog):
    def __init__(self, request):
        super().__init__()
        self.setWindowTitle("ClickGit · HTML 页面对比（独立进程）")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1440, area.width() - 40), min(960, area.height() - 60))
        self.setMinimumSize(800, 580)
        self.comparison = compare_html_text(request["left"], request["right"])
        self._ready = False
        self._selection = 0
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(_label("HTML 页面对比"), 1)
        self.view_combo = QComboBox()
        self.view_combo.addItems(["左右并排", "仅看左侧", "仅看右侧"])
        self.view_combo.setAccessibleName("页面布局")
        toolbar.addWidget(self.view_combo)
        toolbar.addWidget(_label("缩放"))
        self.zoom_combo = QComboBox()
        for percent in (50, 67, 80, 100, 125, 150):
            self.zoom_combo.addItem(f"{percent}%", percent / 100)
        self.zoom_combo.setCurrentIndex(1)
        self.zoom_combo.setAccessibleName("左右页面同步缩放")
        toolbar.addWidget(self.zoom_combo)
        help_button = QPushButton("？")
        help_button.setFixedWidth(30)
        help_button.setStyleSheet("QPushButton { border-radius: 14px; }")
        help_button.setAccessibleName("页面对比说明")
        help_button.clicked.connect(self._show_help)
        toolbar.addWidget(help_button)
        close_button = QPushButton("关闭预览")
        close_button.clicked.connect(self.reject)
        toolbar.addWidget(close_button)
        layout.addLayout(toolbar)
        self.summary_label = _label(self.comparison.notice)
        layout.addWidget(self.summary_label)
        navigation = QHBoxLayout()
        self.change_combo = QComboBox()
        self.change_combo.setMinimumContentsLength(15)
        self.change_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.change_combo.setAccessibleName("正文改动列表")
        for index, change in enumerate(self.comparison.changes, 1):
            sample = " ".join((change.right or change.left).split())[:65]
            self.change_combo.addItem(f"{index}. {change.kind} · {sample}")
        navigation.addWidget(self.change_combo, 1)
        self.previous_button = QPushButton("上一改动")
        self.next_button = QPushButton("下一改动")
        self.locate_button = QPushButton("定位到页面")
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        navigation.addWidget(self.locate_button)
        layout.addLayout(navigation)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.panels, self.version_labels, self.previews, self.location_labels = [], [], [], []
        for side, name, source in (
                ("左", request["left_title"], self.comparison.left),
                ("右", request["right_title"], self.comparison.right)):
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(2, 2, 2, 2)
            version = _label(f"{side}侧版本：{name}")
            version.setStyleSheet("font-weight: bold; padding: 5px;")
            column.addWidget(version)
            preview = HtmlPreview(compact=True)
            preview.set_zoom_factor(self.zoom_combo.currentData())
            column.addWidget(preview, 1)
            location = _label("页面加载中…")
            # Search callbacks alternate short/long status text. Reserve two
            # lines so they never repeatedly resize an active Chromium surface.
            location.setFixedHeight(location.fontMetrics().lineSpacing() * 2 + 4)
            column.addWidget(location)
            self.splitter.addWidget(panel)
            self.panels.append(panel)
            self.version_labels.append(version)
            self.previews.append(preview)
            self.location_labels.append(location)
        self.splitter.setSizes([700, 700])
        layout.addWidget(self.splitter, 1)
        self.detail_title = _label("正文改动详情（包括隐藏正文；只读）")
        layout.addWidget(self.detail_title)
        details = QSplitter(Qt.Orientation.Horizontal)
        self.detail_left, self.detail_right = QPlainTextEdit(), QPlainTextEdit()
        for editor in (self.detail_left, self.detail_right):
            editor.setReadOnly(True)
            editor.setMaximumHeight(115)
            details.addWidget(editor)
        details.setSizes([700, 700])
        layout.addWidget(details)
        self.change_combo.currentIndexChanged.connect(self._select)
        self.previous_button.clicked.connect(
            lambda: self.change_combo.setCurrentIndex(self.change_combo.currentIndex() - 1))
        self.next_button.clicked.connect(
            lambda: self.change_combo.setCurrentIndex(self.change_combo.currentIndex() + 1))
        self.locate_button.clicked.connect(self.locate_current)
        self.zoom_combo.currentIndexChanged.connect(self._zoom)
        self.view_combo.currentIndexChanged.connect(self._view)
        self._select(self.change_combo.currentIndex())

    def load(self):
        for preview, source in zip(self.previews, (self.comparison.left, self.comparison.right)):
            preview.set_source(source)

    def mark_ready(self):
        self._ready = True
        self.locate_button.setEnabled(bool(self.comparison.changes))
        self.locate_current()

    def _select(self, index):
        self._selection += 1
        count = len(self.comparison.changes)
        valid = 0 <= index < count
        self.change_combo.setEnabled(count > 0)
        self.previous_button.setEnabled(valid and index > 0)
        self.next_button.setEnabled(valid and index < count - 1)
        self.locate_button.setEnabled(valid and self._ready)
        if valid:
            change = self.comparison.changes[index]
            self.detail_title.setText(
                f"正文改动 {index + 1}/{count} · {change.kind}（左＝原内容，右＝新内容；隐藏正文也在此显示）")
            # Bound Qt text layout too: pathological single-line HTML text must
            # not monopolize the worker event loop after the pure diff succeeds.
            for editor, text in ((self.detail_left, change.left), (self.detail_right, change.right)):
                excerpt = text[:8000]
                editor.setPlainText(excerpt + ("\n…详情过长已截断，请查看源码。" if len(text) > 8000 else "")
                                    if text else "（本侧无对应正文）")
            self.locate_current()
        else:
            self.detail_left.setPlainText("没有可列出的正文改动；请结合上方提示和源码判断。")
            self.detail_right.setPlainText(self.comparison.notice)

    def locate_current(self):
        if not self._ready:
            return
        index = self.change_combo.currentIndex()
        if not 0 <= index < len(self.comparison.changes):
            for label in self.location_labels:
                label.setText("无正文定位项；可自由查看页面。")
            return
        self._selection += 1
        generation = self._selection
        change = self.comparison.changes[index]
        for preview, label, text, marked in zip(
                self.previews, self.location_labels, (change.left, change.right),
                (change.left_marked, change.right_marked)):
            if not text:
                label.setText("本侧无对应正文。")
            elif not marked:
                label.setText("控件内正文无法标记定位，请看下方详情。")
            else:
                label.setText("正在定位…")

                def located(found, target=label, version=generation):
                    if version == self._selection:
                        target.setText("已找到改动标记；若页面正文仍不可见，请看下方详情。" if found else
                                       "正文可能隐藏或被布局遮挡，未找到可见标记；请看下方详情。")

                preview.find_marker(change.marker, located)

    def _zoom(self):
        for preview in self.previews:
            preview.set_zoom_factor(self.zoom_combo.currentData())

    def _view(self, index):
        for side, panel in enumerate(self.panels, 1):
            panel.setVisible(index == 0 or index == side)
        if index == 0:
            self.splitter.setSizes([700, 700])

    def done(self, result):
        self._selection += 1  # Ignore callbacks arriving during renderer shutdown.
        super().done(result)

    def _show_help(self):
        box = QMessageBox(self)
        box.setWindowTitle("页面对比说明")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            "绿＝新增，红＝删除，橙＝修改。选择改动可查看左右原文，并定位可见页面标记。\n"
            "隐藏正文和下拉控件文字可能无法定位，请看下方详情或主界面的需求对比。\n"
            "正文高亮不是像素/结构比较；样式、属性、脚本变化必须查看源码。\n"
            "标记仅存在于预览副本，可能轻微改变排版，不修改、不保存原文件。\n"
            "页面挤压时可降低缩放比例，或切换“仅看左侧／右侧”。")
        box.setDetailedText(NOTICE + "\n所有预览仍在独立进程中运行。")
        box.exec()
        box.deleteLater()
