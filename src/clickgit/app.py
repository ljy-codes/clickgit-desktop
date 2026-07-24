from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from clickgit.git_runner import GitRunner
from clickgit.models import Branch, FileChange
from clickgit.recovery import RecoveryManager, RecoveryPoint
from clickgit.repository import OperationConflict, Repository
from clickgit.settings import AppSettings, SettingsStore
from clickgit.tasks import RepositoryTaskQueue


@dataclass(slots=True, frozen=True)
class RepositorySnapshot:
    path: Path
    branch: str
    changes: tuple[FileChange, ...]
    branches: tuple[Branch, ...]


class AppController(QObject):
    repository_changed = Signal(object)
    snapshot_ready = Signal(object)
    history_ready = Signal(object)
    tags_ready = Signal(object)
    stashes_ready = Signal(object)
    remotes_ready = Signal(object)
    reflog_ready = Signal(object)
    recovery_ready = Signal(object)
    clean_preview_ready = Signal(object)
    worktrees_ready = Signal(object)
    submodules_ready = Signal(object)
    conflict_versions_ready = Signal(object)
    diagnostic_ready = Signal(str, str)
    diff_ready = Signal(str, str, bool)
    busy_changed = Signal(bool)
    operation_started = Signal(str)
    operation_finished = Signal(str)
    operation_failed = Signal(str, str)
    conflict_detected = Signal(str, object)

    _future_ready = Signal(object, object, str)

    def __init__(
        self,
        *,
        settings_store: SettingsStore,
        git_executable: str | Path = "git",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_store = settings_store
        self.settings = settings_store.load()
        self.recovery_root = settings_store.path.parent / "recovery"
        self.runner = GitRunner(git_executable=git_executable)
        self.task_queue = RepositoryTaskQueue()
        self.repository: Repository | None = None
        self._pending = 0
        self._pending_lock = threading.Lock()
        self._shutting_down = False
        self._future_ready.connect(self._finish_future)

    @property
    def repository_path(self) -> Path | None:
        return self.repository.path if self.repository else None

    def open_repository(self, path: str | Path) -> None:
        requested = Path(path).resolve()
        self._submit(
            requested,
            lambda: Repository(requested, self.runner),
            write=False,
            label="正在打开仓库",
            on_success=self._accept_repository,
        )

    def init_repository(self, path: str | Path, *, bare: bool = False) -> None:
        requested = Path(path).resolve()
        self._submit(
            requested,
            lambda: Repository.init(requested, self.runner, bare=bare),
            write=True,
            label="正在创建仓库",
            success_message="仓库创建完成",
            on_success=self._accept_repository,
        )

    def clone_repository(self, url: str, path: str | Path) -> None:
        requested = Path(path).resolve()
        self._submit(
            requested,
            lambda: Repository.clone(url, requested, self.runner),
            write=True,
            label="正在克隆仓库",
            success_message="仓库克隆完成",
            on_success=self._accept_repository,
        )

    def close_repository(self) -> None:
        self.repository = None
        self.repository_changed.emit(None)

    def refresh(self) -> None:
        repository = self.repository
        if repository is None:
            return

        def load() -> RepositorySnapshot:
            return RepositorySnapshot(
                path=repository.path,
                branch=repository.current_branch(),
                changes=tuple(repository.status()),
                branches=tuple(repository.branches()),
            )

        self._submit(
            repository.path,
            load,
            write=False,
            label="正在刷新仓库",
            on_success=self.snapshot_ready.emit,
        )

    def load_diff(self, path: str, *, staged: bool = False) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: repository.diff(path, staged=staged),
            write=False,
            label="正在读取差异",
            on_success=lambda text: self.diff_ready.emit(text, path, staged),
        )

    def load_history(self, *, query: str | None = None) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: repository.history(query=query),
            write=False,
            label="正在读取提交历史",
            on_success=self.history_ready.emit,
        )

    def load_tags(self) -> None:
        self._load_collection("正在读取标签", "tags", self.tags_ready.emit)

    def load_stashes(self) -> None:
        self._load_collection(
            "正在读取贮藏记录",
            "stashes",
            self.stashes_ready.emit,
        )

    def load_remotes(self) -> None:
        self._load_collection(
            "正在读取远程仓库",
            "remotes",
            self.remotes_ready.emit,
        )

    def load_reflog(self) -> None:
        self._load_collection(
            "正在读取 Reflog",
            "reflog",
            self.reflog_ready.emit,
        )

    def load_worktrees(self) -> None:
        self._load_collection(
            "正在读取 Worktree",
            "worktrees",
            self.worktrees_ready.emit,
        )

    def load_submodules(self) -> None:
        self._load_collection(
            "正在读取子模块",
            "submodules",
            self.submodules_ready.emit,
        )

    def load_recovery_points(self) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: self._recovery_manager(repository).list_points(),
            write=False,
            label="正在读取恢复记录",
            on_success=self.recovery_ready.emit,
        )

    def load_clean_preview(self, *, include_ignored: bool = False) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: repository.clean_preview(
                include_ignored=include_ignored
            ),
            write=False,
            label="正在扫描未跟踪文件",
            on_success=self.clean_preview_ready.emit,
        )

    def load_conflict_versions(self, path: str) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: repository.conflict_versions(path),
            write=False,
            label="正在读取冲突版本",
            on_success=self.conflict_versions_ready.emit,
        )

    def stage(self, paths: list[str]) -> None:
        self._run_write("正在暂存文件", lambda repo: repo.stage(paths))

    def unstage(self, paths: list[str]) -> None:
        self._run_write("正在取消暂存", lambda repo: repo.unstage(paths))

    def restore(self, paths: list[str]) -> None:
        self._run_write("正在丢弃文件修改", lambda repo: repo.restore(paths))

    def commit(self, message: str, *, amend: bool = False) -> None:
        self._run_write(
            "正在提交",
            lambda repo: repo.commit(message, amend=amend),
            success_message="提交完成",
        )

    def fetch(self) -> None:
        self._run_write("正在获取远程更新", lambda repo: repo.fetch())

    def pull(self, *, rebase: bool | None = None) -> None:
        self._run_write(
            "正在拉取远程更新",
            lambda repo: repo.pull(rebase=rebase),
        )

    def push(self, *, force_with_lease: bool = False) -> None:
        self._run_write(
            "正在推送本地提交",
            lambda repo: repo.push(force_with_lease=force_with_lease),
        )

    def create_branch(self, name: str, start_point: str | None = None) -> None:
        self._run_write(
            "正在创建分支",
            lambda repo: repo.create_branch(name, start_point),
        )

    def checkout_branch(self, name: str) -> None:
        self._run_write("正在切换分支", lambda repo: repo.checkout(name))

    def merge_branch(self, name: str) -> None:
        self._run_write("正在合并分支", lambda repo: repo.merge(name))

    def rebase_branch(self, name: str) -> None:
        self._run_write("正在变基", lambda repo: repo.rebase(name))

    def delete_branch(self, name: str, *, force: bool = False) -> None:
        self._run_write(
            "正在删除分支",
            lambda repo: repo.delete_branch(name, force=force),
        )

    def create_tag(
        self,
        name: str,
        *,
        target: str | None = None,
        message: str | None = None,
    ) -> None:
        self._run_write(
            "正在创建标签",
            lambda repo: repo.create_tag(name, target, message),
        )

    def delete_tag(self, name: str) -> None:
        self._run_write("正在删除标签", lambda repo: repo.delete_tag(name))

    def create_stash(
        self,
        message: str,
        *,
        include_untracked: bool = True,
    ) -> None:
        self._run_write(
            "正在贮藏修改",
            lambda repo: repo.stash_create(
                message,
                include_untracked=include_untracked,
            ),
        )

    def apply_stash(self, reference: str, *, pop: bool = False) -> None:
        self._run_write(
            "正在应用贮藏记录",
            lambda repo: repo.stash_apply(reference, pop=pop),
        )

    def drop_stash(self, reference: str) -> None:
        self._run_write(
            "正在删除贮藏记录",
            lambda repo: repo.stash_drop(reference),
        )

    def add_remote(self, name: str, url: str) -> None:
        self._run_write(
            "正在添加远程仓库",
            lambda repo: repo.add_remote(name, url),
        )

    def set_remote_url(self, name: str, url: str) -> None:
        self._run_write(
            "正在更新远程地址",
            lambda repo: repo.set_remote_url(name, url),
        )

    def remove_remote(self, name: str) -> None:
        self._run_write(
            "正在删除远程仓库",
            lambda repo: repo.remove_remote(name),
        )

    def abort_merge(self) -> None:
        self._run_write("正在放弃合并", lambda repo: repo.abort_merge())

    def abort_rebase(self) -> None:
        self._run_write("正在放弃变基", lambda repo: repo.abort_rebase())

    def continue_merge(self) -> None:
        self._run_write("正在继续合并", lambda repo: repo.continue_merge())

    def continue_rebase(self) -> None:
        self._run_write("正在继续变基", lambda repo: repo.continue_rebase())

    def resolve_conflict(self, path: str, result_text: str) -> None:
        self._run_write(
            "正在保存冲突结果",
            lambda repo: repo.resolve_conflict(path, result_text),
        )

    def reset(self, target: str, *, mode: str) -> None:
        repository = self.repository
        if repository is None:
            return

        def protected_reset() -> RecoveryPoint:
            manager = self._recovery_manager(repository)
            point = manager.protect_commit_graph(f"{mode}-reset")
            repository.reset(target, mode=mode)
            return point

        self._submit(
            repository.path,
            protected_reset,
            write=True,
            label="正在回退提交",
            success_message="回退完成，已创建恢复点",
            on_success=lambda _point: self._after_recovery_change(),
        )

    def quarantine_untracked(self, paths: list[str]) -> None:
        repository = self.repository
        if repository is None or not paths:
            return

        def quarantine() -> RecoveryPoint:
            return self._recovery_manager(repository).quarantine(
                repository.path / path for path in paths
            )

        self._submit(
            repository.path,
            quarantine,
            write=True,
            label="正在隔离未跟踪文件",
            success_message="文件已移入恢复中心",
            on_success=lambda _point: self._after_recovery_change(),
        )

    def restore_recovery_point(self, point: RecoveryPoint) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            point.restore,
            write=True,
            label="正在恢复内容",
            success_message="恢复完成",
            on_success=lambda _restored: self._after_recovery_change(),
        )

    def delete_recovery_point(self, point: RecoveryPoint) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: self._recovery_manager(repository).delete(point),
            write=True,
            label="正在删除恢复记录",
            success_message="恢复记录已删除",
            on_success=lambda _result: self.load_recovery_points(),
        )

    def run_fsck(self) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            repository.fsck,
            write=False,
            label="正在检查仓库完整性",
            success_message="完整性检查完成",
            on_success=lambda text: self.diagnostic_ready.emit(
                "仓库完整性检查",
                text or "未发现问题。",
            ),
        )

    def run_gc(self) -> None:
        self._run_write("正在优化仓库", lambda repo: repo.gc())

    def worktree_add(
        self,
        path: Path,
        branch: str,
        *,
        create_branch: bool,
    ) -> None:
        self._run_write(
            "正在创建 Worktree",
            lambda repo: repo.worktree_add(
                path,
                branch,
                create_branch=create_branch,
            ),
        )

    def worktree_remove(self, path: Path, *, force: bool = False) -> None:
        self._run_write(
            "正在移除 Worktree",
            lambda repo: repo.worktree_remove(path, force=force),
        )

    def submodule_update(self) -> None:
        self._run_write(
            "正在更新子模块",
            lambda repo: repo.submodule_update(),
        )

    def lfs_track(self, pattern: str) -> None:
        self._run_write(
            "正在添加 LFS 规则",
            lambda repo: repo.lfs_track(pattern),
        )

    def lfs_pull(self) -> None:
        self._run_write("正在拉取 LFS 对象", lambda repo: repo.lfs_pull())

    def create_patch(self, revisions: str, destination: Path) -> None:
        self._run_write(
            "正在导出补丁",
            lambda repo: repo.create_patch(revisions, destination),
        )

    def apply_patch(self, patch_path: Path) -> None:
        self._run_write(
            "正在应用补丁",
            lambda repo: repo.apply_patch(patch_path),
        )

    def update_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.settings_store.save(settings)

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.task_queue.shutdown(wait=True)

    def _accept_repository(self, repository: Repository) -> None:
        self.repository = repository
        normalized = str(repository.path)
        recent = [
            item
            for item in self.settings.recent_repositories
            if item != normalized
        ]
        self.settings.recent_repositories = [normalized, *recent][:12]
        self.settings_store.save(self.settings)
        self.repository_changed.emit(repository.path)
        self.refresh()

    def _load_collection(
        self,
        label: str,
        method_name: str,
        receiver: Callable[[Any], None],
    ) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: getattr(repository, method_name)(),
            write=False,
            label=label,
            on_success=receiver,
        )

    def _recovery_manager(self, repository: Repository) -> RecoveryManager:
        return RecoveryManager(repository, self.recovery_root)

    def _after_recovery_change(self) -> None:
        self.refresh()
        self.load_recovery_points()

    def _run_write(
        self,
        label: str,
        operation: Callable[[Repository], Any],
        *,
        success_message: str | None = None,
    ) -> None:
        repository = self.repository
        if repository is None:
            return
        self._submit(
            repository.path,
            lambda: operation(repository),
            write=True,
            label=label,
            success_message=success_message or label.replace("正在", "") + "完成",
            on_success=lambda _result: self.refresh(),
        )

    def _submit(
        self,
        repository_path: Path,
        function: Callable[[], Any],
        *,
        write: bool,
        label: str,
        on_success: Callable[[Any], None] | None = None,
        success_message: str = "",
    ) -> None:
        if self._shutting_down:
            return
        with self._pending_lock:
            self._pending += 1
            became_busy = self._pending == 1
        if became_busy:
            self.busy_changed.emit(True)
        self.operation_started.emit(label)
        future = self.task_queue.submit(
            repository_path,
            function,
            write=write,
        )
        future.add_done_callback(
            lambda completed: self._future_ready.emit(
                completed,
                on_success,
                success_message,
            )
        )

    @Slot(object, object, str)
    def _finish_future(
        self,
        future: Future[Any],
        on_success: Callable[[Any], None] | None,
        success_message: str,
    ) -> None:
        try:
            result = future.result()
            if on_success is not None:
                on_success(result)
            if success_message:
                self.operation_finished.emit(success_message)
        except OperationConflict as exc:
            self.conflict_detected.emit(exc.operation, exc.result)
            self.operation_failed.emit(
                "操作产生冲突",
                "请在“工作区”中处理冲突文件，然后继续或放弃当前操作。",
            )
        except Exception as exc:
            self.operation_failed.emit(
                "操作失败",
                str(exc) or exc.__class__.__name__,
            )
        finally:
            with self._pending_lock:
                self._pending = max(0, self._pending - 1)
                still_busy = self._pending > 0
            self.busy_changed.emit(still_busy)
