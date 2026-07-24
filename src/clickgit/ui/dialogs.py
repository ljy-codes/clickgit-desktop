from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from clickgit.models import AppSettings


class CloneDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("克隆远程仓库")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://、ssh:// 或 git@server:group/repo.git"
        )
        self.path_edit = QLineEdit()
        browse = QPushButton("浏览...")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        form.addRow("远程地址", self.url_edit)
        form.addRow("保存位置", path_row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("开始克隆")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def values(self) -> tuple[str, Path]:
        return self.url_edit.text().strip(), Path(self.path_edit.text()).resolve()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择父目录")
        if path:
            self.path_edit.setText(path)

    def _validate(self) -> None:
        url = self.url_edit.text().strip()
        path_text = self.path_edit.text().strip()
        if not url or not path_text:
            QMessageBox.warning(self, "信息不完整", "请填写远程地址和保存位置。")
            return
        path = Path(path_text)
        if path.exists() and any(path.iterdir()):
            QMessageBox.warning(
                self,
                "目录非空",
                "克隆目标目录必须不存在或为空目录。",
            )
            return
        self.accept()


class BranchDialog(QDialog):
    def __init__(self, parent=None, *, title: str = "新建分支") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("留空表示当前提交")
        layout.addRow("分支名称", self.name_edit)
        layout.addRow("起始提交", self.start_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def values(self) -> tuple[str, str | None]:
        return (
            self.name_edit.text().strip(),
            self.start_edit.text().strip() or None,
        )

    def _validate(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "分支名称为空", "请输入分支名称。")
            return
        self.accept()


class TagDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建标签")
        self.setMinimumWidth(440)
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("留空表示当前提交")
        self.message_edit = QLineEdit()
        self.message_edit.setPlaceholderText("填写后创建附注标签")
        layout.addRow("标签名称", self.name_edit)
        layout.addRow("目标提交", self.target_edit)
        layout.addRow("标签说明", self.message_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def values(self) -> tuple[str, str | None, str | None]:
        return (
            self.name_edit.text().strip(),
            self.target_edit.text().strip() or None,
            self.message_edit.text().strip() or None,
        )

    def _validate(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "标签名称为空", "请输入标签名称。")
            return
        self.accept()


class RemoteDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        title: str = "添加远程仓库",
        name: str = "",
        url: str = "",
        lock_name: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        layout = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        self.name_edit.setReadOnly(lock_name)
        self.url_edit = QLineEdit(url)
        layout.addRow("远程名称", self.name_edit)
        layout.addRow("远程地址", self.url_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.url_edit.text().strip()

    def _validate(self) -> None:
        if not all(self.values):
            QMessageBox.warning(self, "信息不完整", "请填写远程名称和地址。")
            return
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ClickGit 设置")
        self.setMinimumWidth(500)
        layout = QFormLayout(self)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(index, 0))
        self.editor_edit = QLineEdit(settings.external_editor)
        browse = QPushButton("浏览...")
        browse.clicked.connect(self._browse_editor)
        row = QHBoxLayout()
        row.addWidget(self.editor_edit, 1)
        row.addWidget(browse)
        layout.addRow("界面主题", self.theme_combo)
        layout.addRow("外部编辑器", row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def build_settings(self, original: AppSettings) -> AppSettings:
        return AppSettings(
            recent_repositories=list(original.recent_repositories),
            favorite_repositories=list(original.favorite_repositories),
            theme=str(self.theme_combo.currentData()),
            external_editor=self.editor_edit.text().strip(),
        )

    def _browse_editor(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择外部编辑器",
            filter="可执行程序 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.editor_edit.setText(path)


class ConfirmDialog(QMessageBox):
    @classmethod
    def ask(
        cls,
        parent,
        *,
        title: str,
        text: str,
        detail: str = "",
        danger: bool = False,
    ) -> bool:
        box = cls(parent)
        box.setWindowTitle(title)
        box.setText(text)
        if detail:
            box.setInformativeText(detail)
        box.setIcon(
            QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        box.button(QMessageBox.StandardButton.Yes).setText("确认")
        box.button(QMessageBox.StandardButton.Cancel).setText("取消")
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Yes
