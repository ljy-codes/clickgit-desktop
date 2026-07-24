from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clickgit.app import AppController, RepositorySnapshot
from clickgit.models import Branch, ChangeKind, Commit, FileChange, Remote, StashEntry
from clickgit.ui.dialogs import (
    BranchDialog,
    CloneDialog,
    ConfirmDialog,
    RemoteDialog,
    SettingsDialog,
    TagDialog,
)


FILE_ROLE = Qt.ItemDataRole.UserRole
STAGED_ROLE = Qt.ItemDataRole.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.repository_path: Path | None = None
        self._busy = False
        self._build_window()
        self._connect_controller()
        self._show_empty_state()

    def _build_window(self) -> None:
        self.setWindowTitle("ClickGit")
        self.setMinimumSize(960, 650)
        self.resize(1360, 840)
        self._build_actions()
        self._build_toolbar()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_repository_bar())

        body = QSplitter(Qt.Orientation.Horizontal)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(176)
        self.navigation.setSpacing(0)
        for text in (
            "工作区",
            "提交历史",
            "分支",
            "标签",
            "贮藏记录",
            "远程仓库",
            "恢复中心",
            "高级操作",
            "设置",
        ):
            self.navigation.addItem(text)
        self.navigation.currentRowChanged.connect(self._change_page)
        body.addWidget(self.navigation)

        self.content_host = QStackedWidget()
        self.content_host.addWidget(self._build_empty_page())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_workspace_page())
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_branches_page())
        self.pages.addWidget(self._build_tags_page())
        self.pages.addWidget(self._build_stashes_page())
        self.pages.addWidget(self._build_remotes_page())
        self.pages.addWidget(self._build_recovery_page())
        self.pages.addWidget(self._build_advanced_page())
        self.pages.addWidget(self._build_settings_page())
        self.content_host.addWidget(self.pages)
        body.addWidget(self.content_host)
        body.setStretchFactor(1, 1)
        root.addWidget(body, 1)
        self.setCentralWidget(central)
        self._build_status_bar()

    def _build_actions(self) -> None:
        style = self.style()
        self.open_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
            "打开仓库",
            self,
        )
        self.open_action.setObjectName("openRepositoryAction")
        self.open_action.triggered.connect(self._open_repository)

        self.clone_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
            "克隆",
            self,
        )
        self.clone_action.triggered.connect(self._clone_repository)
        self.init_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder),
            "新建仓库",
            self,
        )
        self.init_action.triggered.connect(self._init_repository)
        self.refresh_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            "刷新",
            self,
        )
        self.refresh_action.triggered.connect(self.controller.refresh)
        self.fetch_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
            "获取",
            self,
        )
        self.fetch_action.triggered.connect(self.controller.fetch)
        self.pull_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
            "拉取",
            self,
        )
        self.pull_action.triggered.connect(self.controller.pull)
        self.push_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            "推送",
            self,
        )
        self.push_action.triggered.connect(self.controller.push)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("常用操作", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.clone_action)
        toolbar.addAction(self.init_action)
        toolbar.addSeparator()
        toolbar.addAction(self.refresh_action)
        toolbar.addAction(self.fetch_action)
        toolbar.addAction(self.pull_action)
        toolbar.addAction(self.push_action)
        self.addToolBar(toolbar)

    def _build_repository_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("repositoryBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        self.repository_name = QLabel("未打开仓库")
        self.repository_name.setObjectName("repositoryName")
        self.repository_path_label = QLabel("请选择本地仓库或克隆远程仓库")
        self.repository_path_label.setObjectName("mutedLabel")
        name_column = QVBoxLayout()
        name_column.setSpacing(1)
        name_column.addWidget(self.repository_name)
        name_column.addWidget(self.repository_path_label)
        self.branch_badge = QLabel("无分支")
        self.branch_badge.setObjectName("branchBadge")
        self.branch_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(name_column, 1)
        layout.addWidget(self.branch_badge)
        return bar

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 34, 28)
        title = QLabel("选择 Git 仓库")
        title.setObjectName("pageTitle")
        subtitle = QLabel("双击最近仓库，或使用下方按钮开始。")
        subtitle.setObjectName("mutedLabel")
        self.recent_repositories = QListWidget()
        self.recent_repositories.setObjectName("recentRepositories")
        self.recent_repositories.itemDoubleClicked.connect(
            lambda item: self.controller.open_repository(item.data(FILE_ROLE))
        )
        actions = QHBoxLayout()
        open_button = QPushButton("打开本地仓库")
        open_button.clicked.connect(self._open_repository)
        clone_button = QPushButton("克隆远程仓库")
        clone_button.clicked.connect(self._clone_repository)
        init_button = QPushButton("初始化新仓库")
        init_button.clicked.connect(self._init_repository)
        actions.addWidget(open_button)
        actions.addWidget(clone_button)
        actions.addWidget(init_button)
        actions.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(self.recent_repositories, 1)
        layout.addLayout(actions)
        return page

    def _build_workspace_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("工作区")
        title.setObjectName("pageTitle")
        self.workspace_summary = QLabel("0 个文件有变化")
        self.workspace_summary.setObjectName("mutedLabel")
        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet("color: #a32424; font-weight: 600;")
        title_row.addWidget(title)
        title_row.addWidget(self.workspace_summary)
        title_row.addWidget(self.conflict_label)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        file_panel = QWidget()
        file_layout = QVBoxLayout(file_panel)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.change_tree = QTreeWidget()
        self.change_tree.setHeaderLabels(["状态", "文件"])
        self.change_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.change_tree.setRootIsDecorated(True)
        self.change_tree.setAlternatingRowColors(True)
        self.change_tree.header().setStretchLastSection(True)
        self.change_tree.itemSelectionChanged.connect(self._preview_selected_file)
        file_actions = QHBoxLayout()
        self.stage_button = QPushButton("暂存")
        self.stage_button.clicked.connect(self._stage_selected)
        self.unstage_button = QPushButton("取消暂存")
        self.unstage_button.clicked.connect(self._unstage_selected)
        self.restore_button = QPushButton("丢弃修改")
        self.restore_button.setObjectName("dangerButton")
        self.restore_button.clicked.connect(self._restore_selected)
        file_actions.addWidget(self.stage_button)
        file_actions.addWidget(self.unstage_button)
        file_actions.addWidget(self.restore_button)
        file_actions.addStretch(1)
        file_layout.addWidget(self.change_tree, 1)
        file_layout.addLayout(file_actions)
        workspace_splitter.addWidget(file_panel)

        diff_panel = QWidget()
        diff_layout = QVBoxLayout(diff_panel)
        diff_layout.setContentsMargins(0, 0, 0, 0)
        self.diff_title = QLabel("选择文件查看差异")
        self.diff_title.setObjectName("mutedLabel")
        self.diff_editor = QPlainTextEdit()
        self.diff_editor.setReadOnly(True)
        self.diff_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        fixed_font = QFont("Cascadia Mono")
        fixed_font.setStyleHint(QFont.StyleHint.Monospace)
        self.diff_editor.setFont(fixed_font)
        diff_layout.addWidget(self.diff_title)
        diff_layout.addWidget(self.diff_editor, 1)
        workspace_splitter.addWidget(diff_panel)
        workspace_splitter.setSizes([440, 760])
        layout.addWidget(workspace_splitter, 1)

        commit_row = QHBoxLayout()
        self.commit_message = QPlainTextEdit()
        self.commit_message.setPlaceholderText("填写本次提交说明")
        self.commit_message.setMaximumHeight(88)
        self.commit_message.textChanged.connect(self._update_commit_enabled)
        options = QVBoxLayout()
        self.amend_checkbox = QCheckBox("修正上次提交")
        self.commit_button = QPushButton("提交暂存内容")
        self.commit_button.setObjectName("commitButton")
        self.commit_button.clicked.connect(self._commit)
        options.addWidget(self.amend_checkbox)
        options.addWidget(self.commit_button)
        options.addStretch(1)
        commit_row.addWidget(self.commit_message, 1)
        commit_row.addLayout(options)
        layout.addLayout(commit_row)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 10)
        top = QHBoxLayout()
        title = QLabel("提交历史")
        title.setObjectName("pageTitle")
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("按提交说明、作者或哈希筛选")
        self.history_search.setMaximumWidth(360)
        search_button = QPushButton("搜索")
        search_button.clicked.connect(
            lambda: self.controller.load_history(
                query=self.history_search.text().strip() or None
            )
        )
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.history_search)
        top.addWidget(search_button)
        layout.addLayout(top)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ["提交", "说明", "作者", "时间", "引用"]
        )
        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.history_table.setAlternatingRowColors(True)
        self.history_table.itemSelectionChanged.connect(
            self._show_commit_details
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.commit_details = QPlainTextEdit()
        self.commit_details.setReadOnly(True)
        splitter.addWidget(self.history_table)
        splitter.addWidget(self.commit_details)
        splitter.setSizes([520, 180])
        layout.addWidget(splitter, 1)
        return page

    def _build_branches_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 10)
        top = QHBoxLayout()
        title = QLabel("分支")
        title.setObjectName("pageTitle")
        create = QPushButton("新建分支")
        create.clicked.connect(self._create_branch)
        checkout = QPushButton("切换")
        checkout.clicked.connect(self._checkout_branch)
        merge = QPushButton("合并到当前分支")
        merge.clicked.connect(self._merge_branch)
        rebase = QPushButton("将当前分支变基到此")
        rebase.clicked.connect(self._rebase_branch)
        delete = QPushButton("删除")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_branch)
        top.addWidget(title)
        top.addStretch(1)
        for button in (create, checkout, merge, rebase, delete):
            top.addWidget(button)
        layout.addLayout(top)
        self.branch_table = QTableWidget(0, 5)
        self.branch_table.setHorizontalHeaderLabels(
            ["当前", "分支", "上游", "领先", "落后"]
        )
        self.branch_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.branch_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.branch_table.setAlternatingRowColors(True)
        self.branch_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.branch_table, 1)
        return page

    def _build_tags_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 10)
        top = QHBoxLayout()
        title = QLabel("标签")
        title.setObjectName("pageTitle")
        create = QPushButton("创建标签")
        create.clicked.connect(self._create_tag)
        delete = QPushButton("删除标签")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_tag)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(create)
        top.addWidget(delete)
        layout.addLayout(top)
        self.tag_list = QListWidget()
        layout.addWidget(self.tag_list, 1)
        return page

    def _build_stashes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 10)
        top = QHBoxLayout()
        title = QLabel("贮藏记录")
        title.setObjectName("pageTitle")
        create = QPushButton("贮藏当前修改")
        create.clicked.connect(self._create_stash)
        apply_button = QPushButton("应用")
        apply_button.clicked.connect(lambda: self._apply_stash(pop=False))
        pop_button = QPushButton("应用并删除")
        pop_button.clicked.connect(lambda: self._apply_stash(pop=True))
        delete = QPushButton("删除")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._drop_stash)
        top.addWidget(title)
        top.addStretch(1)
        for button in (create, apply_button, pop_button, delete):
            top.addWidget(button)
        layout.addLayout(top)
        self.stash_table = QTableWidget(0, 4)
        self.stash_table.setHorizontalHeaderLabels(
            ["引用", "说明", "创建时间", "提交"]
        )
        self.stash_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.stash_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.stash_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.stash_table, 1)
        return page

    def _build_remotes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 10)
        top = QHBoxLayout()
        title = QLabel("远程仓库")
        title.setObjectName("pageTitle")
        add = QPushButton("添加远程")
        add.clicked.connect(self._add_remote)
        edit = QPushButton("修改地址")
        edit.clicked.connect(self._edit_remote)
        delete = QPushButton("删除远程")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._remove_remote)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(add)
        top.addWidget(edit)
        top.addWidget(delete)
        layout.addLayout(top)
        self.remote_table = QTableWidget(0, 3)
        self.remote_table.setHorizontalHeaderLabels(
            ["名称", "获取地址", "推送地址"]
        )
        self.remote_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.remote_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.remote_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.remote_table, 1)
        return page

    def _build_recovery_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 12)
        title = QLabel("恢复中心")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "危险操作创建的恢复点和隔离文件将在这里集中管理。"
        )
        subtitle.setObjectName("mutedLabel")
        self.recovery_list = QTableWidget(0, 4)
        self.recovery_list.setHorizontalHeaderLabels(
            ["时间", "仓库", "操作", "可恢复内容"]
        )
        self.recovery_list.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.recovery_list, 1)
        return page

    def _build_advanced_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 12)
        title = QLabel("高级操作")
        title.setObjectName("pageTitle")
        warning = QLabel(
            "这些操作会重写提交历史或删除内容，执行前会再次确认并创建恢复点。"
        )
        warning.setStyleSheet("color: #8a4b16;")
        layout.addWidget(title)
        layout.addWidget(warning)
        line = QFrame()
        line.setObjectName("sectionLine")
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        sync_title = QLabel("远程与历史")
        sync_title.setStyleSheet("font-weight: 600;")
        row = QHBoxLayout()
        force_push = QPushButton("安全强制推送")
        force_push.clicked.connect(self._force_push)
        continue_merge = QPushButton("继续合并")
        continue_merge.clicked.connect(self.controller.continue_merge)
        abort_merge = QPushButton("放弃合并")
        abort_merge.clicked.connect(self._abort_merge)
        continue_rebase = QPushButton("继续变基")
        continue_rebase.clicked.connect(self.controller.continue_rebase)
        abort_rebase = QPushButton("放弃变基")
        abort_rebase.clicked.connect(self._abort_rebase)
        for button in (
            force_push,
            continue_merge,
            abort_merge,
            continue_rebase,
            abort_rebase,
        ):
            row.addWidget(button)
        row.addStretch(1)
        layout.addWidget(sync_title)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 12)
        title = QLabel("设置")
        title.setObjectName("pageTitle")
        self.settings_summary = QLabel()
        self.settings_summary.setObjectName("mutedLabel")
        edit = QPushButton("打开设置")
        edit.setMaximumWidth(140)
        edit.clicked.connect(self._edit_settings)
        layout.addWidget(title)
        layout.addWidget(self.settings_summary)
        layout.addWidget(edit)
        layout.addStretch(1)
        self._refresh_settings_summary()
        return page

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.task_label = QLabel("就绪")
        self.task_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(130)
        self.progress.hide()
        self.status_branch = QLabel("")
        status.addWidget(self.task_label, 1)
        status.addPermanentWidget(self.progress)
        status.addPermanentWidget(self.status_branch)
        self.setStatusBar(status)

    def _connect_controller(self) -> None:
        self.controller.repository_changed.connect(self._repository_changed)
        self.controller.snapshot_ready.connect(self._apply_snapshot)
        self.controller.history_ready.connect(self._apply_history)
        self.controller.tags_ready.connect(self._apply_tags)
        self.controller.stashes_ready.connect(self._apply_stashes)
        self.controller.remotes_ready.connect(self._apply_remotes)
        self.controller.diff_ready.connect(self._apply_diff)
        self.controller.busy_changed.connect(self._set_busy)
        self.controller.operation_started.connect(self.task_label.setText)
        self.controller.operation_finished.connect(self._operation_finished)
        self.controller.operation_failed.connect(self._show_error)
        self.controller.conflict_detected.connect(self._show_conflict_notice)

    @Slot(object)
    def _repository_changed(self, path: Path | None) -> None:
        if path is None:
            self._show_empty_state()
            return
        self.repository_path = Path(path)
        self.repository_name.setText(self.repository_path.name)
        self.repository_path_label.setText(str(self.repository_path))
        self.content_host.setCurrentIndex(1)
        self.navigation.setEnabled(True)
        self.navigation.setCurrentRow(0)
        self._set_repository_actions_enabled(True)

    @Slot(object)
    def _apply_snapshot(self, snapshot: RepositorySnapshot) -> None:
        self.repository_path = snapshot.path
        self.branch_badge.setText(snapshot.branch)
        self.status_branch.setText(f"分支：{snapshot.branch}")
        self.workspace_summary.setText(f"{len(snapshot.changes)} 个文件有变化")
        conflicts = sum(1 for change in snapshot.changes if change.conflicted)
        self.conflict_label.setText(
            f"{conflicts} 个冲突待解决" if conflicts else ""
        )
        self._populate_changes(snapshot.changes)
        self._populate_branches(snapshot.branches)
        self._update_commit_enabled()

    @Slot(object)
    def _apply_history(self, commits: list[Commit]) -> None:
        self.history_table.setRowCount(len(commits))
        for row, commit in enumerate(commits):
            values = (
                commit.oid[:10],
                commit.subject,
                commit.author_name,
                commit.authored_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                ", ".join(commit.decorations),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(FILE_ROLE, commit)
                self.history_table.setItem(row, column, item)
        self.history_table.resizeColumnsToContents()
        self.history_table.horizontalHeader().setStretchLastSection(True)

    @Slot(object)
    def _apply_tags(self, tags: list[str]) -> None:
        self.tag_list.clear()
        self.tag_list.addItems(tags)

    @Slot(object)
    def _apply_stashes(self, stashes: list[StashEntry]) -> None:
        self.stash_table.setRowCount(len(stashes))
        for row, stash in enumerate(stashes):
            values = (
                stash.reference,
                stash.subject,
                stash.created_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                stash.oid[:10],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(FILE_ROLE, stash.reference)
                self.stash_table.setItem(row, column, item)
        self.stash_table.resizeColumnsToContents()

    @Slot(object)
    def _apply_remotes(self, remotes: list[Remote]) -> None:
        self.remote_table.setRowCount(len(remotes))
        for row, remote in enumerate(remotes):
            for column, value in enumerate(
                (remote.name, remote.fetch_url, remote.push_url)
            ):
                item = QTableWidgetItem(value)
                item.setData(FILE_ROLE, remote)
                self.remote_table.setItem(row, column, item)
        self.remote_table.resizeColumnsToContents()

    @Slot(str, str, bool)
    def _apply_diff(self, text: str, path: str, staged: bool) -> None:
        area = "暂存区" if staged else "工作区"
        self.diff_title.setText(f"{path} · {area}")
        self.diff_editor.setPlainText(text or "此文件没有可显示的文本差异。")

    @Slot(bool)
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.setVisible(busy)
        self.refresh_action.setEnabled(
            not busy and self.repository_path is not None
        )
        self.fetch_action.setEnabled(
            not busy and self.repository_path is not None
        )
        self.pull_action.setEnabled(
            not busy and self.repository_path is not None
        )
        self.push_action.setEnabled(
            not busy and self.repository_path is not None
        )
        self._update_commit_enabled()

    @Slot(str)
    def _operation_finished(self, message: str) -> None:
        self.task_label.setText(message)
        self.statusBar().showMessage(message, 4500)

    @Slot(str, str)
    def _show_error(self, title: str, detail: str) -> None:
        self.task_label.setText(title)
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText(title)
        box.setInformativeText(self._friendly_error(detail))
        box.setDetailedText(detail)
        box.exec()

    @Slot(str, object)
    def _show_conflict_notice(self, _operation: str, _result: object) -> None:
        self.navigation.setCurrentRow(0)
        self.conflict_label.setText("操作产生冲突，请处理后继续")

    def _show_empty_state(self) -> None:
        self.repository_path = None
        self.repository_name.setText("未打开仓库")
        self.repository_path_label.setText("请选择本地仓库或克隆远程仓库")
        self.branch_badge.setText("无分支")
        self.status_branch.setText("")
        self.navigation.setEnabled(False)
        self.content_host.setCurrentIndex(0)
        self.recent_repositories.clear()
        for path in self.controller.settings.recent_repositories:
            item = QListWidgetItem(Path(path).name or path)
            item.setToolTip(path)
            item.setData(FILE_ROLE, path)
            self.recent_repositories.addItem(item)
        self._set_repository_actions_enabled(False)

    def _set_repository_actions_enabled(self, enabled: bool) -> None:
        for action in (
            self.refresh_action,
            self.fetch_action,
            self.pull_action,
            self.push_action,
        ):
            action.setEnabled(enabled and not self._busy)
        self.commit_button.setEnabled(False)

    def _change_page(self, row: int) -> None:
        if row < 0 or self.repository_path is None:
            return
        self.pages.setCurrentIndex(row)
        if row == 1:
            self.controller.load_history()
        elif row == 3:
            self.controller.load_tags()
        elif row == 4:
            self.controller.load_stashes()
        elif row == 5:
            self.controller.load_remotes()

    def _populate_changes(self, changes: tuple[FileChange, ...]) -> None:
        self.change_tree.clear()
        unstaged_root = QTreeWidgetItem(["工作区修改", ""])
        staged_root = QTreeWidgetItem(["已暂存", ""])
        unstaged_root.setFirstColumnSpanned(True)
        staged_root.setFirstColumnSpanned(True)
        self.change_tree.addTopLevelItems([unstaged_root, staged_root])
        for change in changes:
            parent = staged_root if change.staged else unstaged_root
            item = QTreeWidgetItem(
                [self._change_label(change), change.path]
            )
            item.setData(0, FILE_ROLE, change.path)
            item.setData(0, STAGED_ROLE, change.staged)
            item.setToolTip(1, change.path)
            if change.conflicted:
                item.setForeground(0, QColor("#a32424"))
                item.setForeground(1, QColor("#a32424"))
            parent.addChild(item)
        unstaged_root.setText(0, f"工作区修改（{unstaged_root.childCount()}）")
        staged_root.setText(0, f"已暂存（{staged_root.childCount()}）")
        unstaged_root.setExpanded(True)
        staged_root.setExpanded(True)
        self.change_tree.resizeColumnToContents(0)

    def _populate_branches(self, branches: tuple[Branch, ...]) -> None:
        self.branch_table.setRowCount(len(branches))
        for row, branch in enumerate(branches):
            values = (
                "●" if branch.current else "",
                branch.name,
                branch.upstream or "",
                str(branch.ahead),
                str(branch.behind),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(FILE_ROLE, branch)
                self.branch_table.setItem(row, column, item)
        self.branch_table.resizeColumnsToContents()
        self.branch_table.horizontalHeader().setStretchLastSection(True)

    def _preview_selected_file(self) -> None:
        selected = self._selected_change_items()
        if not selected:
            return
        item = selected[0]
        self.controller.load_diff(
            str(item.data(0, FILE_ROLE)),
            staged=bool(item.data(0, STAGED_ROLE)),
        )

    def _selected_change_items(self) -> list[QTreeWidgetItem]:
        return [
            item
            for item in self.change_tree.selectedItems()
            if item.parent() is not None and item.data(0, FILE_ROLE)
        ]

    def _selected_paths(self, *, staged: bool | None = None) -> list[str]:
        paths = []
        for item in self._selected_change_items():
            item_staged = bool(item.data(0, STAGED_ROLE))
            if staged is None or staged == item_staged:
                paths.append(str(item.data(0, FILE_ROLE)))
        return paths

    def _stage_selected(self) -> None:
        paths = self._selected_paths(staged=False)
        if paths:
            self.controller.stage(paths)

    def _unstage_selected(self) -> None:
        paths = self._selected_paths(staged=True)
        if paths:
            self.controller.unstage(paths)

    def _restore_selected(self) -> None:
        paths = self._selected_paths(staged=False)
        if not paths:
            return
        if ConfirmDialog.ask(
            self,
            title="丢弃文件修改",
            text=f"确认丢弃选中的 {len(paths)} 个文件修改？",
            detail="未提交的修改将被覆盖。",
            danger=True,
        ):
            self.controller.restore(paths)

    def _commit(self) -> None:
        message = self.commit_message.toPlainText().strip()
        if not message:
            return
        self.controller.commit(
            message,
            amend=self.amend_checkbox.isChecked(),
        )
        self.commit_message.clear()
        self.amend_checkbox.setChecked(False)

    def _update_commit_enabled(self) -> None:
        has_message = bool(self.commit_message.toPlainText().strip())
        has_staged = any(
            bool(item.data(0, STAGED_ROLE))
            for item in self._selected_change_items()
        ) or self._tree_has_staged_files()
        self.commit_button.setEnabled(
            self.repository_path is not None
            and not self._busy
            and has_message
            and has_staged
        )

    def _tree_has_staged_files(self) -> bool:
        if self.change_tree.topLevelItemCount() < 2:
            return False
        return self.change_tree.topLevelItem(1).childCount() > 0

    def _show_commit_details(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            return
        item = self.history_table.item(row, 0)
        commit = item.data(FILE_ROLE) if item else None
        if not isinstance(commit, Commit):
            return
        details = [
            f"提交：{commit.oid}",
            f"作者：{commit.author_name} <{commit.author_email}>",
            f"时间：{commit.authored_at.astimezone():%Y-%m-%d %H:%M:%S}",
            f"父提交：{' '.join(commit.parents) or '无'}",
            "",
            commit.subject,
        ]
        self.commit_details.setPlainText("\n".join(details))

    def _selected_branch(self) -> Branch | None:
        row = self.branch_table.currentRow()
        item = self.branch_table.item(row, 1) if row >= 0 else None
        branch = item.data(FILE_ROLE) if item else None
        return branch if isinstance(branch, Branch) else None

    def _create_branch(self) -> None:
        dialog = BranchDialog(self)
        if dialog.exec():
            name, start = dialog.values
            self.controller.create_branch(name, start)

    def _checkout_branch(self) -> None:
        branch = self._selected_branch()
        if branch and not branch.current:
            self.controller.checkout_branch(branch.name)

    def _merge_branch(self) -> None:
        branch = self._selected_branch()
        if branch and not branch.current and ConfirmDialog.ask(
            self,
            title="合并分支",
            text=f"将“{branch.name}”合并到当前分支？",
        ):
            self.controller.merge_branch(branch.name)

    def _rebase_branch(self) -> None:
        branch = self._selected_branch()
        if branch and not branch.current and ConfirmDialog.ask(
            self,
            title="变基",
            text=f"将当前分支变基到“{branch.name}”？",
            detail="该操作会重写当前分支尚未推送的提交。",
            danger=True,
        ):
            self.controller.rebase_branch(branch.name)

    def _delete_branch(self) -> None:
        branch = self._selected_branch()
        if not branch or branch.current:
            return
        if ConfirmDialog.ask(
            self,
            title="删除分支",
            text=f"确认删除分支“{branch.name}”？",
            detail="未合并分支不会被强制删除。",
            danger=True,
        ):
            self.controller.delete_branch(branch.name)

    def _create_tag(self) -> None:
        dialog = TagDialog(self)
        if dialog.exec():
            name, target, message = dialog.values
            self.controller.create_tag(name, target=target, message=message)

    def _delete_tag(self) -> None:
        item = self.tag_list.currentItem()
        if item and ConfirmDialog.ask(
            self,
            title="删除标签",
            text=f"确认删除本地标签“{item.text()}”？",
            danger=True,
        ):
            self.controller.delete_tag(item.text())

    def _create_stash(self) -> None:
        message, accepted = QInputDialog.getText(
            self,
            "贮藏当前修改",
            "说明（可留空）：",
        )
        if accepted:
            self.controller.create_stash(message.strip())

    def _selected_stash(self) -> str | None:
        row = self.stash_table.currentRow()
        item = self.stash_table.item(row, 0) if row >= 0 else None
        return str(item.data(FILE_ROLE)) if item else None

    def _apply_stash(self, *, pop: bool) -> None:
        reference = self._selected_stash()
        if reference:
            self.controller.apply_stash(reference, pop=pop)

    def _drop_stash(self) -> None:
        reference = self._selected_stash()
        if reference and ConfirmDialog.ask(
            self,
            title="删除贮藏记录",
            text=f"确认删除“{reference}”？",
            danger=True,
        ):
            self.controller.drop_stash(reference)

    def _selected_remote(self) -> Remote | None:
        row = self.remote_table.currentRow()
        item = self.remote_table.item(row, 0) if row >= 0 else None
        remote = item.data(FILE_ROLE) if item else None
        return remote if isinstance(remote, Remote) else None

    def _add_remote(self) -> None:
        dialog = RemoteDialog(self)
        if dialog.exec():
            name, url = dialog.values
            self.controller.add_remote(name, url)

    def _edit_remote(self) -> None:
        remote = self._selected_remote()
        if not remote:
            return
        dialog = RemoteDialog(
            self,
            title="修改远程地址",
            name=remote.name,
            url=remote.fetch_url,
            lock_name=True,
        )
        if dialog.exec():
            name, url = dialog.values
            self.controller.set_remote_url(name, url)

    def _remove_remote(self) -> None:
        remote = self._selected_remote()
        if remote and ConfirmDialog.ask(
            self,
            title="删除远程仓库",
            text=f"确认删除远程“{remote.name}”？",
            detail="不会删除服务器上的仓库。",
            danger=True,
        ):
            self.controller.remove_remote(remote.name)

    def _force_push(self) -> None:
        if ConfirmDialog.ask(
            self,
            title="安全强制推送",
            text="确认使用租约检查进行强制推送？",
            detail="远程分支发生未知变化时会自动中止。",
            danger=True,
        ):
            self.controller.push(force_with_lease=True)

    def _abort_merge(self) -> None:
        if ConfirmDialog.ask(
            self,
            title="放弃合并",
            text="确认放弃当前合并并恢复到合并前状态？",
            danger=True,
        ):
            self.controller.abort_merge()

    def _abort_rebase(self) -> None:
        if ConfirmDialog.ask(
            self,
            title="放弃变基",
            text="确认放弃当前变基并恢复到变基前状态？",
            danger=True,
        ):
            self.controller.abort_rebase()

    def _edit_settings(self) -> None:
        dialog = SettingsDialog(self.controller.settings, self)
        if dialog.exec():
            self.controller.update_settings(
                dialog.build_settings(self.controller.settings)
            )
            self._refresh_settings_summary()

    def _refresh_settings_summary(self) -> None:
        settings = self.controller.settings
        theme_names = {
            "system": "跟随系统",
            "light": "浅色",
            "dark": "深色",
        }
        editor = settings.external_editor or "未设置"
        self.settings_summary.setText(
            f"界面主题：{theme_names.get(settings.theme, '跟随系统')}\n"
            f"外部编辑器：{editor}\n"
            f"最近仓库：{len(settings.recent_repositories)} 个"
        )

    def _open_repository(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 Git 仓库")
        if path:
            self.controller.open_repository(path)

    def _clone_repository(self) -> None:
        dialog = CloneDialog(self)
        if dialog.exec():
            url, path = dialog.values
            self.controller.clone_repository(url, path)

    def _init_repository(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择新仓库目录")
        if path:
            self.controller.init_repository(path)

    @staticmethod
    def _change_label(change: FileChange) -> str:
        labels = {
            ChangeKind.MODIFIED: "修改",
            ChangeKind.ADDED: "新增",
            ChangeKind.DELETED: "删除",
            ChangeKind.RENAMED: "重命名",
            ChangeKind.COPIED: "复制",
            ChangeKind.TYPE_CHANGED: "类型",
            ChangeKind.UNTRACKED: "未跟踪",
            ChangeKind.IGNORED: "忽略",
            ChangeKind.CONFLICTED: "冲突",
        }
        return labels.get(change.kind, change.kind.value)

    @staticmethod
    def _friendly_error(detail: str) -> str:
        lowered = detail.lower()
        mappings = (
            (("authentication failed", "could not read username"), "认证失败，请检查账号、访问令牌或凭据设置。"),
            (("permission denied", "publickey"), "SSH 认证失败，请检查私钥和服务器公钥配置。"),
            (("non-fast-forward", "fetch first"), "远程包含新的提交，请先拉取并处理差异后再推送。"),
            (("not a git repository",), "所选目录不是有效的 Git 仓库。"),
            (("index.lock",), "仓库正在被其他 Git 程序使用，请关闭相关程序后重试。"),
            (("conflict",), "操作产生冲突，请返回工作区处理冲突文件。"),
        )
        for needles, message in mappings:
            if any(needle in lowered for needle in needles):
                return message
        return "操作未完成。可展开“详细信息”查看技术原因。"

    def closeEvent(self, event) -> None:
        self.controller.shutdown()
        super().closeEvent(event)
