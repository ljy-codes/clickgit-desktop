from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QListWidget,
    QSplitter, QVBoxLayout, QPushButton,
)

from clickgit.ui.diff_viewer import DiffViewer
from clickgit.ui.html_review import is_html_path, open_html_review


class ExpandedDiffDialog(QDialog):
    def __init__(self, pair, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"内容对比 · {pair.path}")
        self.resize(1200, 760)
        layout = QVBoxLayout(self)
        self.viewer = DiffViewer()
        self.viewer.set_comparison(pair.left, pair.right, pair.left_title, pair.right_title, pair.notice)
        layout.addWidget(self.viewer, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.html_review_button = buttons.addButton("HTML 需求 / 预览", QDialogButtonBox.ButtonRole.ActionRole)
        self.html_review_button.setVisible(is_html_path(pair.path))
        self.html_review_button.setEnabled(pair.supported)
        self.html_review_button.clicked.connect(lambda: open_html_review(pair, self))
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class DocumentComparisonDialog(QDialog):
    """File selection loads immutable blob pairs through the controller's queue."""
    def __init__(self, controller, listing, *, action_text="", notice="", parent=None):
        super().__init__(parent)
        self.controller = controller
        self.listing = listing
        self._request_id = 0
        self._viewed = set()
        self._loading = False
        self._current_ready = not listing.files
        self._html_pair = None
        self.setWindowTitle(listing.title)
        self.resize(1220, 760)
        self.setMinimumSize(850, 560)
        layout = QVBoxLayout(self)
        title = QLabel(f"{listing.title} · {len(listing.files)} 个变化文件")
        title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title)
        hint = QLabel(notice or listing.notice or "只读查看，不改变工作文件或提交。")
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(hint)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.files = QListWidget()
        self.files.addItems(listing.files)
        self.viewer = DiffViewer()
        splitter.addWidget(self.files)
        splitter.addWidget(self.viewer)
        splitter.setSizes([230, 950])
        layout.addWidget(splitter, 1)
        self.progress_label = QLabel()
        layout.addWidget(self.progress_label)
        self.retry_button = QPushButton("重新读取当前文件")
        self.retry_button.hide()
        self.retry_button.clicked.connect(lambda: self._load(self.files.currentItem().text())
                                          if self.files.currentItem() else None)
        layout.addWidget(self.retry_button)
        self.acknowledge = QCheckBox(
            "我已检查比较范围，理解此操作将写入工作文件或生成本机提交，不会自动推送。")
        self.acknowledge.setVisible(bool(action_text))
        layout.addWidget(self.acknowledge)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.html_review_button = self.buttons.addButton("HTML 需求 / 预览", QDialogButtonBox.ButtonRole.ActionRole)
        self.html_review_button.setEnabled(False)
        self.html_review_button.clicked.connect(self._review_html)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        self.buttons.rejected.connect(self.reject)
        if action_text:
            self.action_button = self.buttons.addButton(action_text, QDialogButtonBox.ButtonRole.AcceptRole)
            self.action_button.setEnabled(False)
            self.acknowledge.toggled.connect(self._update_action)
            self.action_button.clicked.connect(self.accept)
        layout.addWidget(self.buttons)
        self.files.currentTextChanged.connect(self._load)
        self.controller.comparison_file_ready.connect(self._apply)
        self.controller.comparison_file_failed.connect(self._failed)
        self.controller.repository_changed.connect(self.reject)
        # Disconnect before returning from exec; no accumulation of hidden dialogs.
        self.finished.connect(self._disconnect)
        if listing.files:
            self.files.setCurrentRow(0)
        else:
            self.viewer.clear("两个快照没有文件内容差异。")
        self._update_action()

    def _load(self, path):
        self._html_pair = None
        self.html_review_button.setEnabled(False)
        self._request_id += 1
        self._loading = True
        self._current_ready = False
        self.acknowledge.setChecked(False)
        self.retry_button.hide()
        self.viewer.clear("正在读取，请稍候…")
        self._update_action()
        self.controller.load_comparison_file(self.listing, path, self._request_id)

    def _matches(self, listing, path, request_id):
        item = self.files.currentItem()
        return (listing is self.listing and item is not None and item.text() == path
                and request_id == self._request_id)

    def _apply(self, listing, pair, request_id):
        if not self._matches(listing, pair.path, request_id):
            return
        self._loading = False
        self._html_pair = pair if pair.supported and is_html_path(pair.path) else None
        self.html_review_button.setEnabled(self._html_pair is not None)
        if pair.supported:
            self.viewer.set_comparison(pair.left, pair.right, pair.left_title, pair.right_title, pair.notice)
            self._current_ready = self.viewer.comparison_loaded
        else:
            self.viewer.clear(pair.notice or "此文件不支持文本对比。")
            self._current_ready = False
        if self._current_ready:
            self._viewed.add(pair.path)
        else:
            self._viewed.discard(pair.path)
        self._update_action()

    def _failed(self, listing, path, request_id, error):
        if not self._matches(listing, path, request_id):
            return
        self._loading = False
        self._html_pair = None
        self.html_review_button.setEnabled(False)
        self._current_ready = False
        self._viewed.discard(path)
        self.acknowledge.setChecked(False)
        self.viewer.clear(f"读取失败：{error}")
        self.retry_button.show()
        self._update_action()

    def _review_html(self):
        if self._html_pair is not None:
            open_html_review(self._html_pair, self)

    def _update_action(self):
        self.progress_label.setText(f"已查看 {len(self._viewed)}/{len(self.listing.files)} 个文件"
                                    "；需逐个加载并人工检查，再勾选确认。"
                                    if hasattr(self, "action_button") else
                                    f"已查看 {len(self._viewed)}/{len(self.listing.files)} 个文件")
        if hasattr(self, "action_button"):
            self.action_button.setEnabled(not self._loading and self._current_ready
                                          and len(self._viewed) == len(self.listing.files)
                                          and self.acknowledge.isChecked())

    def _disconnect(self, _result):
        self.controller.comparison_file_ready.disconnect(self._apply)
        self.controller.comparison_file_failed.disconnect(self._failed)
        self.controller.repository_changed.disconnect(self.reject)
