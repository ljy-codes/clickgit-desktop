from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
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
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clickgit.app import AppController, RepositorySnapshot
from clickgit.document_workflow import TextComparison
from clickgit.models import (
    Branch,
    ChangeKind,
    Commit,
    ConflictVersions,
    FileChange,
    ReflogEntry,
    Remote,
    StashEntry,
    SubmoduleInfo,
    WorktreeInfo,
)
from clickgit.recovery import RecoveryPoint
from clickgit.ui.conflict_editor import ConflictEditorDialog
from clickgit.ui.diff_viewer import DiffViewer
from clickgit.ui.html_review import is_html_path, open_html_review
from clickgit.ui.document_dialogs import DocumentComparisonDialog, ExpandedDiffDialog
from clickgit.ui.themes import ThemeManager, theme_values
from clickgit.ui.dialogs import (
    BranchDialog,
    CleanPreviewDialog,
    CloneDialog,
    ConfirmDialog,
    RemoteDialog,
    ResetDialog,
    SettingsDialog,
    TagDialog,
    WorktreeDialog,
)


FILE_ROLE = Qt.ItemDataRole.UserRole
STAGED_ROLE = Qt.ItemDataRole.UserRole + 1
CONFLICT_ROLE = Qt.ItemDataRole.UserRole + 2
ORIGINAL_PATH_ROLE = Qt.ItemDataRole.UserRole + 3


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.theme_manager = ThemeManager(QApplication.instance())
        self.theme_manager.apply(self.controller.settings)
        self.repository_path: Path | None = None
        self._busy = False
        self._merge_active = False
        self._current_document = None
        self._build_window()
        self._connect_controller()
        self._show_empty_state()
        self._show_settings_notice(self.controller.settings_notice)

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
        self.settings_notice_label = QLabel()
        self.settings_notice_label.setObjectName("settingsNotice")
        self.settings_notice_label.setTextFormat(Qt.TextFormat.PlainText)
        self.settings_notice_label.setWordWrap(True)
        self.settings_notice_label.setContentsMargins(16, 8, 16, 8)
        self.settings_notice_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.settings_notice_label)

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
        self.conflict_label.setObjectName("dangerLabel")
        title_row.addWidget(title)
        title_row.addWidget(self.workspace_summary)
        title_row.addWidget(self.conflict_label)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        self.merge_bar = QWidget()
        merge_row = QHBoxLayout(self.merge_bar)
        merge_row.setContentsMargins(0, 0, 0, 0)
        self.merge_status = QLabel("合并尚未完成")
        self.merge_status.setWordWrap(True)
        self.merge_review_button = QPushButton("检查结果并完成合并")
        self.merge_review_button.clicked.connect(self.controller.review_merge)
        self.merge_abort_button = QPushButton("取消本次合并")
        self.merge_abort_button.clicked.connect(self._abort_merge)
        merge_row.addWidget(self.merge_status, 1)
        merge_row.addWidget(self.merge_review_button)
        merge_row.addWidget(self.merge_abort_button)
        self.merge_bar.hide()
        layout.addWidget(self.merge_bar)

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
        self.change_tree.itemDoubleClicked.connect(
            self._open_conflict_editor_for_item
        )
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
        self.resolve_button = QPushButton("解决所选文件冲突…")
        self.resolve_button.setEnabled(False)
        self.resolve_button.clicked.connect(self._resolve_selected_conflict)
        file_layout.addWidget(self.resolve_button)
        workspace_splitter.addWidget(file_panel)

        diff_panel = QWidget()
        diff_layout = QVBoxLayout(diff_panel)
        diff_layout.setContentsMargins(0, 0, 0, 0)
        self.diff_title = QLabel("选择文件查看差异")
        self.diff_title.setTextFormat(Qt.TextFormat.PlainText)
        self.diff_title.setObjectName("mutedLabel")
        self.diff_editor = QPlainTextEdit()
        self.diff_editor.setReadOnly(True)
        self.diff_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        fixed_font = QFont("Cascadia Mono")
        fixed_font.setStyleHint(QFont.StyleHint.Monospace)
        self.diff_editor.setFont(fixed_font)
        diff_layout.addWidget(self.diff_title)
        self.document_viewer = DiffViewer()
        self.diff_tabs = QTabWidget()
        self.diff_tabs.addTab(self.document_viewer, "左右对比")
        self.diff_tabs.addTab(self.diff_editor, "原始差异")
        self.zoom_diff_button = QPushButton("放大对比")
        self.zoom_diff_button.setEnabled(False)
        self.zoom_diff_button.clicked.connect(self._expand_document)
        self.diff_tabs.setCornerWidget(self.zoom_diff_button)
        diff_layout.addWidget(self.diff_tabs, 1)
        self.html_review_button = QPushButton("HTML 需求对比 / 页面预览")
        self.html_review_button.setEnabled(False)
        self.html_review_button.setVisible(False)
        self.html_review_button.clicked.connect(self._review_html)
        diff_layout.addWidget(self.html_review_button)
        workspace_splitter.addWidget(diff_panel)
        workspace_splitter.setSizes([300, 900])
        layout.addWidget(workspace_splitter, 1)

        self.commit_form = QWidget()
        commit_row = QHBoxLayout(self.commit_form)
        commit_row.setContentsMargins(0, 0, 0, 0)
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
        layout.addWidget(self.commit_form)
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
        self.history_compare_button = QPushButton("查看内容变化")
        self.history_compare_button.clicked.connect(self._compare_history_commit)
        top.addWidget(self.history_compare_button)
        compare_two = QPushButton("比较两个版本…")
        compare_two.clicked.connect(self._compare_two_revisions)
        top.addWidget(compare_two)
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
        merge = QPushButton("比较并合并到当前分支")
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
        top = QHBoxLayout()
        title = QLabel("恢复中心")
        title.setObjectName("pageTitle")
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.controller.load_recovery_points)
        restore = QPushButton("恢复所选")
        restore.clicked.connect(self._restore_recovery_point)
        delete = QPushButton("删除记录")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_recovery_point)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(refresh)
        top.addWidget(restore)
        top.addWidget(delete)
        subtitle = QLabel(
            "危险操作创建的恢复点和隔离文件将在这里集中管理。"
        )
        subtitle.setObjectName("mutedLabel")
        self.recovery_list = QTableWidget(0, 4)
        self.recovery_list.setHorizontalHeaderLabels(
            ["时间", "仓库", "操作", "可恢复内容"]
        )
        self.recovery_list.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.recovery_list.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.recovery_list.horizontalHeader().setStretchLastSection(True)
        layout.addLayout(top)
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
        warning.setObjectName("warningLabel")
        layout.addWidget(title)
        layout.addWidget(warning)

        tabs = QTabWidget()
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(8, 8, 8, 8)
        row = QHBoxLayout()
        force_push = QPushButton("安全强制推送")
        force_push.clicked.connect(self._force_push)
        reset = QPushButton("回退到提交")
        reset.clicked.connect(self._reset_repository)
        clean = QPushButton("清理未跟踪文件")
        clean.clicked.connect(self.controller.load_clean_preview)
        export_patch = QPushButton("导出补丁")
        export_patch.clicked.connect(self._export_patch)
        apply_patch = QPushButton("应用补丁")
        apply_patch.clicked.connect(self._apply_patch)
        fsck = QPushButton("完整性检查")
        fsck.clicked.connect(self.controller.run_fsck)
        gc = QPushButton("优化仓库")
        gc.clicked.connect(self.controller.run_gc)
        for button in (
            reset,
            clean,
            export_patch,
            apply_patch,
            fsck,
            gc,
            force_push,
        ):
            row.addWidget(button)
        row.addStretch(1)
        history_layout.addLayout(row)

        operation_row = QHBoxLayout()
        continue_merge = QPushButton("继续合并")
        continue_merge.clicked.connect(self.controller.continue_merge)
        abort_merge = QPushButton("放弃合并")
        abort_merge.clicked.connect(self._abort_merge)
        continue_rebase = QPushButton("继续变基")
        continue_rebase.clicked.connect(self.controller.continue_rebase)
        abort_rebase = QPushButton("放弃变基")
        abort_rebase.clicked.connect(self._abort_rebase)
        for button in (
            continue_merge,
            abort_merge,
            continue_rebase,
            abort_rebase,
        ):
            operation_row.addWidget(button)
        operation_row.addStretch(1)
        history_layout.addLayout(operation_row)

        reflog_title = QHBoxLayout()
        reflog_title.addWidget(QLabel("Reflog"))
        reflog_title.addStretch(1)
        load_reflog = QPushButton("刷新 Reflog")
        load_reflog.clicked.connect(self.controller.load_reflog)
        reflog_title.addWidget(load_reflog)
        history_layout.addLayout(reflog_title)
        self.reflog_table = QTableWidget(0, 4)
        self.reflog_table.setHorizontalHeaderLabels(
            ["位置", "提交", "时间", "操作"]
        )
        self.reflog_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.reflog_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.reflog_table.horizontalHeader().setStretchLastSection(True)
        history_layout.addWidget(self.reflog_table, 1)
        tabs.addTab(history_tab, "安全与历史")

        extensions_tab = QWidget()
        extensions_layout = QVBoxLayout(extensions_tab)
        extensions_layout.setContentsMargins(8, 8, 8, 8)
        worktree_row = QHBoxLayout()
        worktree_row.addWidget(QLabel("Worktree"))
        worktree_row.addStretch(1)
        add_worktree = QPushButton("创建 Worktree")
        add_worktree.clicked.connect(self._add_worktree)
        remove_worktree = QPushButton("移除 Worktree")
        remove_worktree.clicked.connect(self._remove_worktree)
        refresh_worktree = QPushButton("刷新")
        refresh_worktree.clicked.connect(self.controller.load_worktrees)
        worktree_row.addWidget(add_worktree)
        worktree_row.addWidget(remove_worktree)
        worktree_row.addWidget(refresh_worktree)
        extensions_layout.addLayout(worktree_row)
        self.worktree_table = QTableWidget(0, 4)
        self.worktree_table.setHorizontalHeaderLabels(
            ["目录", "分支", "提交", "状态"]
        )
        self.worktree_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.worktree_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.worktree_table.horizontalHeader().setStretchLastSection(True)
        extensions_layout.addWidget(self.worktree_table, 1)

        submodule_row = QHBoxLayout()
        submodule_row.addWidget(QLabel("子模块"))
        submodule_row.addStretch(1)
        update_submodules = QPushButton("初始化并更新")
        update_submodules.clicked.connect(self.controller.submodule_update)
        refresh_submodules = QPushButton("刷新")
        refresh_submodules.clicked.connect(self.controller.load_submodules)
        submodule_row.addWidget(update_submodules)
        submodule_row.addWidget(refresh_submodules)
        extensions_layout.addLayout(submodule_row)
        self.submodule_table = QTableWidget(0, 4)
        self.submodule_table.setHorizontalHeaderLabels(
            ["路径", "提交", "状态", "说明"]
        )
        self.submodule_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.submodule_table.horizontalHeader().setStretchLastSection(True)
        extensions_layout.addWidget(self.submodule_table, 1)

        lfs_row = QHBoxLayout()
        lfs_row.addWidget(QLabel("Git LFS"))
        lfs_pattern = QLineEdit()
        lfs_pattern.setPlaceholderText("例如 *.psd")
        lfs_pattern.setMaximumWidth(260)
        track_lfs = QPushButton("添加跟踪规则")
        track_lfs.clicked.connect(
            lambda: self._track_lfs_pattern(lfs_pattern)
        )
        pull_lfs = QPushButton("拉取 LFS 对象")
        pull_lfs.clicked.connect(self.controller.lfs_pull)
        lfs_row.addWidget(lfs_pattern)
        lfs_row.addWidget(track_lfs)
        lfs_row.addWidget(pull_lfs)
        lfs_row.addStretch(1)
        extensions_layout.addLayout(lfs_row)
        tabs.addTab(extensions_tab, "Worktree / 子模块 / LFS")

        layout.addWidget(tabs, 1)
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
        self.diagnostics_button = QPushButton("查看 / 复制诊断信息")
        self.diagnostics_button.setMaximumWidth(200)
        self.diagnostics_button.clicked.connect(self._show_diagnostics)
        layout.addWidget(title)
        layout.addWidget(self.settings_summary)
        layout.addWidget(edit)
        layout.addWidget(self.diagnostics_button)
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
        self.controller.reflog_ready.connect(self._apply_reflog)
        self.controller.recovery_ready.connect(self._apply_recovery_points)
        self.controller.clean_preview_ready.connect(self._show_clean_preview)
        self.controller.worktrees_ready.connect(self._apply_worktrees)
        self.controller.submodules_ready.connect(self._apply_submodules)
        self.controller.conflict_versions_ready.connect(
            self._show_conflict_editor
        )
        self.controller.diagnostic_ready.connect(self._show_diagnostic)
        self.controller.diff_ready.connect(self._apply_diff)
        self.controller.document_ready.connect(self._apply_document)
        self.controller.document_failed.connect(self._document_failed)
        self.controller.comparison_ready.connect(self._show_comparison)
        self.controller.merge_plan_ready.connect(self._show_merge_plan)
        self.controller.merge_review_ready.connect(self._show_merge_review)
        self.controller.busy_changed.connect(self._set_busy)
        self.controller.operation_started.connect(self.task_label.setText)
        self.controller.operation_finished.connect(self._operation_finished)
        self.controller.operation_failed.connect(self._show_error)
        self.controller.conflict_detected.connect(self._show_conflict_notice)
        self.controller.settings_notice_changed.connect(self._show_settings_notice)
        self.controller.settings_changed.connect(self._apply_settings)
        self.theme_manager.changed.connect(self._refresh_theme_colors)

    @Slot(object)
    def _apply_settings(self, settings) -> None:
        self.theme_manager.apply(settings)
        self._refresh_settings_summary()

    @Slot(str)
    def _refresh_theme_colors(self, theme: str) -> None:
        color = QColor(theme_values(theme)["danger"])
        for root_index in range(self.change_tree.topLevelItemCount()):
            root = self.change_tree.topLevelItem(root_index)
            for index in range(root.childCount()):
                item = root.child(index)
                if item.data(0, CONFLICT_ROLE):
                    item.setForeground(0, color)
                    item.setForeground(1, color)

    @Slot(str)
    def _show_settings_notice(self, message: str) -> None:
        self.settings_notice_label.setText(message)
        self.settings_notice_label.setVisible(bool(message))

    @Slot(object)
    def _repository_changed(self, path: Path | None) -> None:
        self._populate_changes(())
        self.merge_bar.hide()
        self._merge_active = False
        self.commit_form.show()
        self.commit_message.clear()
        self.branch_badge.setText("读取中…")
        self.status_branch.clear()
        if path is None:
            self._show_empty_state()
            return
        self.repository_path = Path(path)
        self.repository_name.setText(self.repository_path.name)
        self.repository_path_label.setText(str(self.repository_path))
        self.content_host.setCurrentIndex(1)
        self.navigation.setEnabled(True)
        for index in range(1, 8):
            item = self.navigation.item(index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
        self.navigation.setCurrentRow(0)
        self._set_repository_actions_enabled(True)

    @Slot(object)
    def _apply_snapshot(self, snapshot: RepositorySnapshot) -> None:
        self.repository_path = snapshot.path
        self.branch_badge.setText(snapshot.branch)
        self.status_branch.setText(f"分支：{snapshot.branch}")
        self.workspace_summary.setText(f"{len(snapshot.changes)} 个文件有变化")
        conflicts = sum(1 for change in snapshot.changes if change.conflicted)
        self.merge_bar.setVisible(snapshot.merge_active)
        self.merge_status.setText(
            f"合并待完成 · {conflicts} 个冲突文件。先解决冲突，再检查最终结果。"
            if conflicts else "合并待完成 · 请检查实际结果，再确认提交。")
        self.merge_review_button.setEnabled(not conflicts and not self._busy)
        self._merge_active = snapshot.merge_active
        self.commit_form.setVisible(not snapshot.merge_active)
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

    @Slot(object)
    def _apply_reflog(self, entries: list[ReflogEntry]) -> None:
        self.reflog_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = (
                entry.selector,
                entry.oid[:10],
                entry.created_at.astimezone().strftime("%Y-%m-%d %H:%M"),
                entry.subject,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(FILE_ROLE, entry)
                self.reflog_table.setItem(row, column, item)
        self.reflog_table.resizeColumnsToContents()
        self.reflog_table.horizontalHeader().setStretchLastSection(True)

    @Slot(object)
    def _apply_recovery_points(self, points: list[RecoveryPoint]) -> None:
        self.recovery_list.setRowCount(len(points))
        reason_labels = {
            "hard-reset": "硬回退",
            "mixed-reset": "混合回退",
            "soft-reset": "软回退",
            "clean": "清理未跟踪文件",
        }
        for row, point in enumerate(points):
            content = (
                f"{len(point.files)} 个文件"
                if point.files
                else point.ref_name
            )
            values = (
                point.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                str(point.repository_path),
                reason_labels.get(point.reason, point.reason),
                content,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(FILE_ROLE, point)
                self.recovery_list.setItem(row, column, item)
        self.recovery_list.resizeColumnsToContents()
        self.recovery_list.horizontalHeader().setStretchLastSection(True)

    @Slot(object)
    def _show_clean_preview(self, paths: list[str]) -> None:
        if not paths:
            QMessageBox.information(
                self,
                "无需清理",
                "当前没有未跟踪文件。",
            )
            return
        dialog = CleanPreviewDialog(paths, self)
        if dialog.exec() and dialog.selected_paths:
            self.controller.quarantine_untracked(dialog.selected_paths)

    @Slot(object)
    def _apply_worktrees(self, worktrees: list[WorktreeInfo]) -> None:
        self.worktree_table.setRowCount(len(worktrees))
        for row, worktree in enumerate(worktrees):
            if worktree.bare:
                state = "裸仓库"
            elif worktree.detached:
                state = "分离头指针"
            elif worktree.locked:
                state = f"已锁定：{worktree.locked}"
            elif worktree.prunable:
                state = f"可清理：{worktree.prunable}"
            else:
                state = "正常"
            values = (
                str(worktree.path),
                worktree.branch,
                worktree.head[:10],
                state,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(FILE_ROLE, worktree)
                self.worktree_table.setItem(row, column, item)
        self.worktree_table.resizeColumnsToContents()
        self.worktree_table.horizontalHeader().setStretchLastSection(True)

    @Slot(object)
    def _apply_submodules(self, submodules: list[SubmoduleInfo]) -> None:
        self.submodule_table.setRowCount(len(submodules))
        state_labels = {
            " ": "正常",
            "-": "未初始化",
            "+": "提交不一致",
            "U": "冲突",
        }
        for row, submodule in enumerate(submodules):
            values = (
                submodule.path,
                submodule.oid[:10],
                state_labels.get(submodule.state, submodule.state),
                submodule.description,
            )
            for column, value in enumerate(values):
                self.submodule_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self.submodule_table.resizeColumnsToContents()
        self.submodule_table.horizontalHeader().setStretchLastSection(True)

    @Slot(object)
    def _show_conflict_editor(self, versions: ConflictVersions) -> None:
        dialog = ConflictEditorDialog(
            file_path=versions.path,
            base_text=versions.base,
            ours_text=versions.ours,
            theirs_text=versions.theirs,
            result_text=versions.result,
            allowed=versions.allowed,
            reason=versions.reason,
            defer_save=True,
            parent=self,
        )
        def save(mark_resolved):
            dialog.set_saving(True)
            self.controller.save_conflict_session(versions, dialog.result_text(), mark_resolved=mark_resolved)
        def finished(session, success, message):
            if session is not versions:
                return
            dialog.set_saving(False)
            if success:
                dialog.accept()
            else:
                QMessageBox.warning(dialog, "未保存成功，编辑内容仍保留", message)
        dialog.save_requested.connect(save)
        self.controller.conflict_save_finished.connect(finished)
        try:
            dialog.exec()
        finally:
            self.controller.conflict_save_finished.disconnect(finished)
        dialog.deleteLater()

    @Slot(object, str)
    def _apply_document(self, pair: TextComparison, raw: str) -> None:
        self._current_document = pair
        self.html_review_button.setVisible(is_html_path(pair.path))
        self.html_review_button.setEnabled(pair.supported and is_html_path(pair.path))
        self.zoom_diff_button.setEnabled(pair.supported)
        self.diff_title.setText(pair.path)
        self.diff_editor.setPlainText(raw)
        self.document_viewer.set_comparison(pair.left, pair.right, pair.left_title, pair.right_title, pair.notice)
        if not pair.supported:
            self.document_viewer.clear(pair.notice or "此文件不支持文本对比。")

    @Slot(str)
    def _document_failed(self, message: str) -> None:
        self._current_document = None
        self.html_review_button.setEnabled(False)
        self.zoom_diff_button.setEnabled(False)
        self.diff_editor.clear()
        self.document_viewer.clear(f"读取失败：{message}。可重新选择文件重试。")

    def _review_html(self) -> None:
        if self._current_document is not None:
            open_html_review(self._current_document, self)

    def _expand_document(self) -> None:
        if self._current_document is None or not self._current_document.supported:
            return
        dialog = ExpandedDiffDialog(self._current_document, self)
        dialog.exec()
        dialog.deleteLater()

    @Slot(object)
    def _show_comparison(self, listing) -> None:
        dialog = DocumentComparisonDialog(self.controller, listing, parent=self)
        dialog.exec()
        dialog.deleteLater()

    @Slot(object)
    def _show_merge_plan(self, plan) -> None:
        dialog = DocumentComparisonDialog(
            self.controller, plan.comparison, parent=self, action_text="开始合并（先不提交）",
            notice=f"当前分支 {plan.current_branch} ← 合入 {plan.source_name}。"
            "这里是两个分支的内容差异，不是预测合并结果。"
            "开始后将修改工作文件；即使可快进也停在确认阶段，完成时生成合并提交。"
            "有未提交文件或不支持的文本/二进制变化时拒绝开始，不自动丢弃或贮藏。")
        if dialog.exec():
            self.navigation.setCurrentRow(0)
            self.controller.start_reviewed_merge(plan)
        dialog.deleteLater()

    @Slot(object)
    def _show_merge_review(self, listing) -> None:
        dialog = DocumentComparisonDialog(self.controller, listing, parent=self,
                                          action_text="确认完成合并")
        if dialog.exec():
            self.controller.finish_reviewed_merge(listing)
        dialog.deleteLater()

    @Slot(str, str)
    def _show_diagnostic(self, title: str, text: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(title)
        box.setDetailedText(text)
        box.setInformativeText(text if len(text) < 240 else "检查已完成。")
        box.exec()

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
        self.merge_abort_button.setEnabled(not busy)
        conflicts = any(bool(item.data(0, CONFLICT_ROLE))
                        for root_index in range(self.change_tree.topLevelItemCount())
                        for item in (self.change_tree.topLevelItem(root_index).child(i)
                                     for i in range(self.change_tree.topLevelItem(root_index).childCount())))
        self.merge_review_button.setEnabled(not busy and not conflicts)
        selected = self._selected_change_items()
        self.resolve_button.setEnabled(not busy and bool(selected)
                                       and bool(selected[0].data(0, CONFLICT_ROLE)))
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
        self.controller.invalidate_document()
        self.html_review_button.setEnabled(False)
        self.document_viewer.clear()
        self.diff_editor.clear()
        self.merge_bar.hide()
        self._merge_active = False
        self._current_document = None
        self.zoom_diff_button.setEnabled(False)
        self.commit_form.show()
        self.repository_path = None
        self.repository_name.setText("未打开仓库")
        self.repository_path_label.setText("请选择本地仓库或克隆远程仓库")
        self.branch_badge.setText("无分支")
        self.status_branch.setText("")
        self.navigation.setEnabled(True)
        for index in range(1, 8):
            item = self.navigation.item(index)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        self.navigation.setCurrentRow(0)
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
        if row < 0:
            return
        if self.repository_path is None and row != 8:
            self.content_host.setCurrentIndex(0)
            return
        self.content_host.setCurrentIndex(1)
        self.pages.setCurrentIndex(row)
        if row == 1:
            self.controller.load_history()
        elif row == 3:
            self.controller.load_tags()
        elif row == 4:
            self.controller.load_stashes()
        elif row == 5:
            self.controller.load_remotes()
        elif row == 6:
            self.controller.load_recovery_points()
        elif row == 7:
            self.controller.load_reflog()
            self.controller.load_worktrees()
            self.controller.load_submodules()

    def _populate_changes(self, changes: tuple[FileChange, ...]) -> None:
        self._current_document = None
        self.html_review_button.setEnabled(False)
        self.html_review_button.hide()
        self.zoom_diff_button.setEnabled(False)
        self.controller.invalidate_document()
        self.diff_title.setText("选择文件查看内容对比；冲突文件可双击编辑")
        self.diff_editor.clear()
        self.document_viewer.clear()
        self.resolve_button.setEnabled(False)
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
            item.setData(0, CONFLICT_ROLE, change.conflicted)
            item.setData(0, ORIGINAL_PATH_ROLE, change.original_path)
            item.setToolTip(1, change.path)
            if change.conflicted:
                color = QColor(theme_values(self.theme_manager.effective_theme)["danger"])
                item.setForeground(0, color)
                item.setForeground(1, color)
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
        self._current_document = None
        self.zoom_diff_button.setEnabled(False)
        self.controller.invalidate_document()
        selected = self._selected_change_items()
        self.resolve_button.setEnabled(
            bool(selected) and bool(selected[0].data(0, CONFLICT_ROLE)) and not self._busy)
        if not selected:
            self.document_viewer.clear()
            self.diff_editor.clear()
            return
        item = selected[0]
        self.document_viewer.clear("正在读取内容…")
        self.diff_editor.clear()
        if item.data(0, CONFLICT_ROLE):
            self.document_viewer.clear("该文件存在冲突。双击文件或点击“解决所选文件冲突”逐块编辑。")
            return
        self.controller.load_document(
            str(item.data(0, FILE_ROLE)),
            staged=bool(item.data(0, STAGED_ROLE)),
            original_path=item.data(0, ORIGINAL_PATH_ROLE),
        )

    def _resolve_selected_conflict(self) -> None:
        selected = self._selected_change_items()
        if selected:
            self._open_conflict_editor_for_item(selected[0], 0)

    def _open_conflict_editor_for_item(
        self,
        item: QTreeWidgetItem,
        _column: int,
    ) -> None:
        if item.parent() is None or not item.data(0, CONFLICT_ROLE):
            return
        self.controller.load_conflict_versions(str(item.data(0, FILE_ROLE)))

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
            and not self._merge_active
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

    def _compare_history_commit(self) -> None:
        row = self.history_table.currentRow()
        item = self.history_table.item(row, 0) if row >= 0 else None
        commit = item.data(FILE_ROLE) if item else None
        if not isinstance(commit, Commit):
            self.statusBar().showMessage("请先选择一条提交记录。", 4000)
            return
        parent = commit.parents[0] if commit.parents else ""
        if len(commit.parents) > 1:
            options = [f"{index + 1} · {oid}" for index, oid in enumerate(commit.parents)]
            selected, ok = QInputDialog.getItem(
                self, "选择合并前的基线", "第一个父版本通常是接收合并的原分支：", options, 0, False)
            if not ok:
                return
            parent = commit.parents[options.index(selected)]
        self.controller.load_comparison(parent, commit.oid)

    def _compare_two_revisions(self) -> None:
        left, ok = QInputDialog.getText(self, "比较两个版本", "原版本（分支名或提交哈希）：")
        if not ok or not left.strip():
            return
        right, ok = QInputDialog.getText(self, "比较两个版本", "目标版本（分支名或提交哈希）：")
        if ok and right.strip():
            self.controller.load_comparison(left.strip(), right.strip())

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
        if branch and not branch.current:
            self.controller.preview_merge(branch.name)

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

    def _selected_recovery_point(self) -> RecoveryPoint | None:
        row = self.recovery_list.currentRow()
        item = self.recovery_list.item(row, 0) if row >= 0 else None
        point = item.data(FILE_ROLE) if item else None
        return point if isinstance(point, RecoveryPoint) else None

    def _restore_recovery_point(self) -> None:
        point = self._selected_recovery_point()
        if point and ConfirmDialog.ask(
            self,
            title="恢复内容",
            text="确认恢复所选记录？",
            detail=(
                "提交恢复点会创建一个新分支；隔离文件会移回原目录。"
            ),
        ):
            self.controller.restore_recovery_point(point)

    def _delete_recovery_point(self) -> None:
        point = self._selected_recovery_point()
        if point and ConfirmDialog.ask(
            self,
            title="删除恢复记录",
            text="确认永久删除所选恢复记录？",
            detail="删除后将无法再通过 ClickGit 恢复这些内容。",
            danger=True,
        ):
            self.controller.delete_recovery_point(point)

    def _reset_repository(self) -> None:
        dialog = ResetDialog(self)
        if not dialog.exec():
            return
        target, mode = dialog.values
        descriptions = {
            "soft": "保留暂存区和工作区文件",
            "mixed": "重置暂存区，保留工作区文件",
            "hard": "覆盖暂存区和工作区文件",
        }
        if ConfirmDialog.ask(
            self,
            title="确认回退",
            text=f"确认以“{mode}”方式回退到 {target}？",
            detail=(
                f"{descriptions[mode]}。执行前会创建 ClickGit 恢复点。"
            ),
            danger=mode == "hard",
        ):
            self.controller.reset(target, mode=mode)

    def _export_patch(self) -> None:
        revisions, accepted = QInputDialog.getText(
            self,
            "导出补丁",
            "提交范围：",
            text="HEAD~1..HEAD",
        )
        if not accepted or not revisions.strip():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存补丁",
            "clickgit-change.patch",
            "Git 补丁 (*.patch);;所有文件 (*.*)",
        )
        if path:
            self.controller.create_patch(revisions.strip(), Path(path))

    def _apply_patch(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择补丁文件",
            filter="Git 补丁 (*.patch *.mbox);;所有文件 (*.*)",
        )
        if path and ConfirmDialog.ask(
            self,
            title="应用补丁",
            text=f"确认应用补丁“{Path(path).name}”？",
        ):
            self.controller.apply_patch(Path(path))

    def _add_worktree(self) -> None:
        dialog = WorktreeDialog(self)
        if dialog.exec():
            path, branch, create_branch = dialog.values
            self.controller.worktree_add(
                path,
                branch,
                create_branch=create_branch,
            )

    def _selected_worktree(self) -> WorktreeInfo | None:
        row = self.worktree_table.currentRow()
        item = self.worktree_table.item(row, 0) if row >= 0 else None
        worktree = item.data(FILE_ROLE) if item else None
        return worktree if isinstance(worktree, WorktreeInfo) else None

    def _remove_worktree(self) -> None:
        worktree = self._selected_worktree()
        if not worktree or worktree.path == self.repository_path:
            return
        if ConfirmDialog.ask(
            self,
            title="移除 Worktree",
            text=f"确认移除“{worktree.path}”？",
            detail="存在未提交修改时 Git 会拒绝移除。",
            danger=True,
        ):
            self.controller.worktree_remove(worktree.path)

    def _track_lfs_pattern(self, pattern_edit: QLineEdit) -> None:
        pattern = pattern_edit.text().strip()
        if pattern:
            self.controller.lfs_track(pattern)
            pattern_edit.clear()

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

    def _show_diagnostics(self) -> None:
        from clickgit.ui.diagnostics_dialog import show_diagnostics
        show_diagnostics(self)

    def _refresh_settings_summary(self) -> None:
        settings = self.controller.settings
        theme_names = {
            "system": "跟随系统",
            "light": "明亮白色",
            "dark": "经典深色",
            "tech": "极光科技",
        }
        editor = settings.external_editor or "未设置"
        self.settings_summary.setText(
            f"界面主题：{theme_names.get(settings.theme, '跟随系统')}（已应用）\n"
            f"字号：{settings.font_size_px} px · 密度：{'舒适' if settings.density == 'comfortable' else '紧凑'}\n"
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
        from clickgit.ui.preview_session import stop_all_previews
        stop_all_previews()
        self.controller.shutdown()
        self.theme_manager.deleteLater()
        super().closeEvent(event)
