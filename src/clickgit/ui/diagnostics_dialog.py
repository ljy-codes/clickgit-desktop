"""Explicit, local-only diagnostic viewer. No external file opening or export."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)

from clickgit.diagnostics import get_diagnostics

__all__ = ["DiagnosticsDialog", "show_diagnostics"]


class DiagnosticsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("本机诊断日志")
        self.resize(880, 580)
        layout = QVBoxLayout(self)
        self.privacy_notice = QLabel(
            "诊断日志仅保存在本机，可能包含本机程序 / 配置路径及用户名；"
            "复制前请检查隐私信息。不会自动上传或导出。\n"
            "显示最多 64 KiB 内存快照，包含后台加载的历史日志；新记录不保证已落盘。"
            "不读取配置损坏隔离件。"
        )
        self.privacy_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.privacy_notice.setWordWrap(True)
        layout.addWidget(self.privacy_notice)
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.viewer.setAccessibleName("本机诊断日志只读快照")
        layout.addWidget(self.viewer, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.refresh_button = buttons.addButton("刷新", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button = buttons.addButton("复制当前快照", QDialogButtonBox.ButtonRole.ActionRole)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        self.refresh_button.clicked.connect(self.refresh)
        self.copy_button.clicked.connect(self.copy_snapshot)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        log = get_diagnostics()
        if log is None:
            self.viewer.setPlainText("本机诊断日志未启用；当前没有已配置的日志实例。")
            self.status_label.setText("未启用")
            self.copy_button.setEnabled(False)
            return
        self.viewer.setPlainText(log.snapshot())
        # No I/O here: worker status can change independently of the GUI.
        status = {"pending": "初始化中", "available": "可用",
                  "unavailable": "不可用", "closed": "不可用（已关闭）"}[log.status]
        self.status_label.setText(f"本机日志{status} · {log.path}")
        # A read-only/slow company drive must not prevent copying safe memory.
        self.copy_button.setEnabled(True)

    def copy_snapshot(self):
        if self.copy_button.isEnabled():
            QApplication.clipboard().setText(self.viewer.toPlainText())


def show_diagnostics(parent=None):
    """GUI-thread, modal viewer; the application retains ownership of its log."""
    dialog = DiagnosticsDialog(parent)
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()
