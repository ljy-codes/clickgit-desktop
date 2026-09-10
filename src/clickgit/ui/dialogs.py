from __future__ import annotations

from dataclasses import replace
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
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from clickgit.models import AppSettings
from clickgit.defaults import UI_FONT_SIZES_PX
from clickgit.settings import SettingsStore, SettingsValidationError


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
        self._original_settings = settings
        self.setWindowTitle("ClickGit 设置")
        self.setMinimumWidth(500)
        layout = QFormLayout(self)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("明亮白色", "light")
        self.theme_combo.addItem("经典深色", "dark")
        self.theme_combo.addItem("极光科技", "tech")
        self.theme_combo.setToolTip(
            "保存后立即应用到整个界面，无需重启；跟随系统会自动响应系统深浅色变化。"
        )
        index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(max(index, 0))
        self.font_size_combo = QComboBox()
        for size in UI_FONT_SIZES_PX:
            self.font_size_combo.addItem(f"{size} px", size)
        self.font_size_combo.setCurrentIndex(self.font_size_combo.findData(settings.font_size_px))
        self.density_combo = QComboBox()
        self.density_combo.addItem("舒适 · 更宽松的操作空间", "comfortable")
        self.density_combo.addItem("紧凑 · 显示更多内容", "compact")
        self.density_combo.setCurrentIndex(self.density_combo.findData(settings.density))
        self.editor_edit = QLineEdit(settings.external_editor)
        browse = QPushButton("浏览...")
        browse.clicked.connect(self._browse_editor)
        row = QHBoxLayout()
        row.addWidget(self.editor_edit, 1)
        row.addWidget(browse)
        layout.addRow("界面主题", self.theme_combo)
        layout.addRow("界面字号", self.font_size_combo)
        layout.addRow("显示密度", self.density_combo)
        layout.addRow("外部编辑器", row)
        self.validation_label = QLabel()
        self.validation_label.setTextFormat(Qt.TextFormat.PlainText)
        self.validation_label.setWordWrap(True)
        layout.addRow(self.validation_label)
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
        return replace(
            original,
            recent_repositories=list(original.recent_repositories),
            favorite_repositories=list(original.favorite_repositories),
            theme=str(self.theme_combo.currentData()),
            font_size_px=int(self.font_size_combo.currentData()),
            density=str(self.density_combo.currentData()),
            external_editor=self.editor_edit.text().strip(),
        )

    def accept(self) -> None:
        try:
            SettingsStore.validate(self.build_settings(self._original_settings))
        except SettingsValidationError as error:
            self.validation_label.setText(str(error))
            return
        self.validation_label.clear()
        super().accept()

    def _browse_editor(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择外部编辑器",
            filter="可执行程序 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.editor_edit.setText(path)


class ResetDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("回退到指定提交")
        layout = QFormLayout(self)
        self.target_edit = QLineEdit("HEAD~1")
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("软回退（保留暂存区和文件）", "soft")
        self.mode_combo.addItem("混合回退（保留文件）", "mixed")
        self.mode_combo.addItem("硬回退（覆盖文件）", "hard")
        layout.addRow("目标提交", self.target_edit)
        layout.addRow("回退方式", self.mode_combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("下一步")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def values(self) -> tuple[str, str]:
        return (
            self.target_edit.text().strip(),
            str(self.mode_combo.currentData()),
        )

    def _validate(self) -> None:
        if not self.target_edit.text().strip():
            QMessageBox.warning(self, "目标为空", "请输入提交哈希或引用。")
            return
        self.accept()


class CleanPreviewDialog(QDialog):
    def __init__(self, paths: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("清理未跟踪文件")
        self.resize(680, 480)
        layout = QVBoxLayout(self)
        warning = QLabel(
            "选中的文件不会直接删除，而是移入 ClickGit 恢复中心。"
        )
        warning.setObjectName("warningLabel")
        self.path_list = QListWidget()
        for path in paths:
            item = QListWidgetItem(path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.path_list.addItem(item)
        layout.addWidget(warning)
        layout.addWidget(self.path_list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "移入恢复中心"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_paths(self) -> list[str]:
        return [
            self.path_list.item(index).text()
            for index in range(self.path_list.count())
            if self.path_list.item(index).checkState() == Qt.CheckState.Checked
        ]


class WorktreeDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("创建 Worktree")
        self.setMinimumWidth(560)
        layout = QFormLayout(self)
        self.path_edit = QLineEdit()
        browse = QPushButton("浏览...")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        self.branch_edit = QLineEdit()
        self.create_branch = QCheckBox("同时创建新分支")
        self.create_branch.setChecked(True)
        layout.addRow("Worktree 目录", path_row)
        layout.addRow("分支名称", self.branch_edit)
        layout.addRow("", self.create_branch)
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
    def values(self) -> tuple[Path, str, bool]:
        return (
            Path(self.path_edit.text()).resolve(),
            self.branch_edit.text().strip(),
            self.create_branch.isChecked(),
        )

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 Worktree 目录")
        if path:
            self.path_edit.setText(path)

    def _validate(self) -> None:
        if not self.path_edit.text().strip() or not self.branch_edit.text().strip():
            QMessageBox.warning(self, "信息不完整", "请填写目录和分支名称。")
            return
        self.accept()


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
