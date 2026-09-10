from __future__ import annotations

import threading
import difflib
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from clickgit.defaults import MAX_RECENT_PROJECTS
from clickgit.document_workflow import DocumentWorkflow, DocumentError, ComparisonList, MergePlan
from clickgit.git_runner import GitRunner
from clickgit.models import Branch, FileChange
from clickgit.recovery import RecoveryManager, RecoveryPoint
from clickgit.repository import OperationConflict, Repository
from clickgit.settings import (
    AppSettings,
    ProjectsSaveError,
    SettingsStore,
    SettingsValidationError,
)
from clickgit.tasks import RepositoryTaskQueue


@dataclass(slots=True, frozen=True)
class RepositorySnapshot:
    path: Path
    branch: str
    changes: tuple[FileChange, ...]
    branches: tuple[Branch, ...]
    merge_active: bool = False


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
    conflict_save_finished = Signal(object, bool, str)
    diagnostic_ready = Signal(str, str)
    diff_ready = Signal(str, str, bool)
    document_ready = Signal(object, str)
    document_failed = Signal(str)
    comparison_ready = Signal(object)
    comparison_file_ready = Signal(object, object, int)
    comparison_file_failed = Signal(object, str, int, str)
    merge_plan_ready = Signal(object)
    merge_review_ready = Signal(object)
    busy_changed = Signal(bool)
    operation_started = Signal(str)
    operation_finished = Signal(str)
    operation_failed = Signal(str, str)
    conflict_detected = Signal(str, object)
    settings_notice_changed = Signal(str)
    settings_changed = Signal(object)

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
        self._settings_save_notice = ""
        self._projects_save_notice = ""
        self._settings_validation_notice = ""
        self.recovery_root = settings_store.path.parent / "recovery"
        self.runner = GitRunner(git_executable=git_executable)
        self.task_queue = RepositoryTaskQueue()
        self.repository: Repository | None = None
        self._pending = 0
        self._pending_lock = threading.Lock()
        self._shutting_down = False
        self._document_generation = 0
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
        self.invalidate_document()
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
                merge_active=DocumentWorkflow(repository).merge_active(),
            )

        self._submit(
            repository.path,
            load,
            write=False,
            label="正在刷新仓库",
            on_success=lambda snapshot: self.snapshot_ready.emit(snapshot)
            if self.repository is repository else None,
        )

    def invalidate_document(self) -> None:
        self._document_generation += 1

    def load_document(self, path: str, *, staged: bool = False,
                      original_path: str | None = None) -> None:
        repository = self.repository
        if repository is None:
            return
        self.invalidate_document()
        generation = self._document_generation
        def load():
            try:
                pair = DocumentWorkflow(repository).workspace(path, staged=staged, original_path=original_path)
            except Exception as exc:
                return None, str(exc) or type(exc).__name__
            left, right = pair.left.splitlines(keepends=True), pair.right.splitlines(keepends=True)
            if not pair.supported:
                raw = pair.notice
            elif (max(len(left), len(right)) > 2000
                  or len(left) * len(right) > 250000
                  or any(len(line) > 8192 for lines in (left, right) for line in lines)
                  or len(pair.left.encode("utf-8")) + len(pair.right.encode("utf-8")) > 1024 * 1024):
                raw = "文本大小或复杂度超过原始差异安全预算，请使用左右对比或外部工具。"
            else:
                raw = "".join(difflib.unified_diff(left, right, fromfile=pair.left_title,
                                                  tofile=pair.right_title))
            return pair, raw
        def finished(result):
            if self.repository is not repository or generation != self._document_generation:
                return
            if result[0] is None:
                self.document_failed.emit(result[1])
            else:
                self.document_ready.emit(*result)
        self._submit(repository.path, load, write=False, label="正在读取文件内容对比",
                     on_success=finished)

    def load_comparison(self, left: str, right: str) -> None:
        self._document_task("正在读取版本变化", lambda flow: flow.compare_revisions(left, right),
                            self.comparison_ready.emit)

    def load_comparison_file(self, listing: ComparisonList, path: str, request_id: int = 0) -> None:
        repository = self.repository
        if repository is None:
            self.comparison_file_failed.emit(listing, path, request_id, "仓库已关闭，请重新打开比较。")
            return
        def load():
            try:
                return DocumentWorkflow(repository).comparison_file(listing, path), ""
            except Exception as exc:
                return None, str(exc) or type(exc).__name__
        def finished(result):
            if self.repository is not repository:
                return
            pair, error = result
            if pair is None:
                self.comparison_file_failed.emit(listing, path, request_id, error)
            else:
                self.comparison_file_ready.emit(listing, pair, request_id)
        self._submit(repository.path, load, write=False, label="正在读取版本文件", on_success=finished)

    def preview_merge(self, source: str) -> None:
        self._document_task("正在比较合并来源", lambda flow: flow.plan_merge(source),
                            self.merge_plan_ready.emit)

    def start_reviewed_merge(self, plan: MergePlan) -> None:
        self._document_task("正在准备合并（不自动提交）", lambda flow: flow.start_merge(plan),
                            lambda _: self.refresh(), write=True,
                            success="合并命令已结束；请在工作区检查状态、处理冲突或确认结果。")

    def review_merge(self) -> None:
        self._document_task("正在读取实际合并结果", lambda flow: flow.merge_result(),
                            self.merge_review_ready.emit)

    def finish_reviewed_merge(self, listing: ComparisonList) -> None:
        def finished(oid):
            self.refresh()
            self.load_comparison(listing.left_oid, oid)
        self._document_task("正在完成已检查的合并", lambda flow: flow.finish_merge(listing),
                            finished, write=True, success="合并已完成，未自动推送。")

    def _document_task(self, label, function, callback, *, write=False, success=""):
        repository = self.repository
        if repository is None:
            return
        def execute():
            if write and self.repository is not repository:
                raise DocumentError("当前仓库已切换，未执行旧页面的操作。")
            return function(DocumentWorkflow(repository))
        self._submit(repository.path, execute,
                     write=write, label=label, success_message=success,
                     on_success=lambda result: callback(result) if self.repository is repository else None)

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
            lambda: self._load_safe_conflict(repository, path),
            write=False,
            label="正在读取冲突版本",
            on_success=lambda session: self.conflict_versions_ready.emit(session)
            if self.repository is repository else None,
        )

    @staticmethod
    def _load_safe_conflict(repository, path):
        from clickgit.conflict_workflow import load_conflict
        return load_conflict(repository, path)

    def save_conflict_session(self, session, text: str, *, mark_resolved: bool):
        from clickgit.conflict_workflow import save_conflict
        repository = self.repository
        if repository is None:
            self.conflict_save_finished.emit(session, False, "当前仓库已关闭，编辑内容仍保留在窗口中。")
            return
        def execute():
            try:
                if self.repository is not repository:
                    raise DocumentError("当前仓库已切换，未执行旧窗口的保存。")
                save_conflict(repository, session, text, mark_resolved=mark_resolved)
            except Exception as exc:
                return False, str(exc) or "保存失败；请先复制保留编辑内容。"
            return True, ""
        def finished(result):
            success, message = result
            self.conflict_save_finished.emit(session, success, message)
            if success:
                self.operation_finished.emit("已保存并暂存，尚未完成合并。" if mark_resolved
                                             else "草稿已保存，尚未标记冲突解决。")
                if self.repository is repository:
                    self.refresh()
        self._submit(repository.path, execute, write=True,
                     label="正在保存冲突结果" if mark_resolved else "正在保存冲突草稿",
                     on_success=finished)

    def stage(self, paths: list[str]) -> None:
        self._run_write("正在暂存文件", lambda repo: repo.stage(paths))

    def unstage(self, paths: list[str]) -> None:
        self._run_write("正在取消暂存", lambda repo: repo.unstage(paths))

    def restore(self, paths: list[str]) -> None:
        self._run_write("正在丢弃文件修改", lambda repo: repo.restore(paths))

    def commit(self, message: str, *, amend: bool = False) -> None:
        def commit_checked(repo):
            if DocumentWorkflow(repo).merge_active():
                raise DocumentError("合并进行中，请使用“检查结果并完成合并”，不能绕过结果确认直接提交。")
            return repo.commit(message, amend=amend)
        self._run_write(
            "正在提交",
            commit_checked,
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
        self._run_write("正在放弃合并", lambda repo: DocumentWorkflow(repo).abort_merge())

    def abort_rebase(self) -> None:
        self._run_write("正在放弃变基", lambda repo: repo.abort_rebase())

    def continue_merge(self) -> None:
        self.review_merge()

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
            if mode not in {"soft", "mixed", "hard"}:
                raise ValueError(f"不支持的回退模式：{mode}")
            if mode == "hard" and repository.status():
                raise RuntimeError(
                    "工作区存在未提交改动，不能执行硬回退。"
                    "请先提交、贮藏或处理这些改动。"
                )
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

        def restore() -> RecoveryPoint:
            if not point.restore():
                raise RuntimeError(
                    "恢复点未恢复任何内容，目标文件可能已经存在。"
                )
            return point

        self._submit(
            repository.path,
            restore,
            write=True,
            label="正在恢复内容",
            success_message="恢复完成",
            on_success=lambda _point: self._after_recovery_change(),
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
        try:
            self.settings_store.validate(settings)
        except SettingsValidationError as error:
            self._settings_validation_notice = str(error) + "；本次未应用，请修正后重试。"
            self.settings_notice_changed.emit(self.settings_notice)
            return
        self._settings_validation_notice = ""
        self.settings = settings
        self.settings_changed.emit(settings)
        try:
            self.settings_store.save(settings)
        except ProjectsSaveError:
            self._settings_save_notice = ""
            self._projects_save_notice = (
                "设置已保存，但项目记录未保存；"
                "请检查数据目录权限和磁盘空间，或查看上方只读保护原因。"
            )
        except (OSError, ValueError):
            self._settings_save_notice = (
                "本次设置已保留在当前会话，但未保存设置；"
                "请检查数据目录权限和磁盘空间后，在设置中再次保存。"
            )
        else:
            self._settings_save_notice = ""
            self._projects_save_notice = ""
        self.settings_notice_changed.emit(self.settings_notice)

    @property
    def settings_notice(self) -> str:
        return "\n".join(item for item in (
            *self.settings_store.warnings,
            self._settings_save_notice,
            self._projects_save_notice,
            self._settings_validation_notice,
        ) if item)

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
        self.settings.recent_repositories = [normalized, *recent][:MAX_RECENT_PROJECTS]
        try:
            self.settings_store.save_projects(self.settings)
        except (OSError, ValueError):
            self._projects_save_notice = (
                "最近项目记录未保存，但项目已打开，可以继续操作；"
                "请检查数据目录权限和磁盘空间。"
            )
        else:
            self._projects_save_notice = ""
        self.settings_notice_changed.emit(self.settings_notice)
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
            from clickgit.diagnostics import log_exception
            log_exception(type(exc), exc, exc.__traceback__, event="operation_failed")
            self.conflict_detected.emit(exc.operation, exc.result)
            self.operation_failed.emit(
                "操作产生冲突",
                "请在“工作区”中处理冲突文件，然后继续或放弃当前操作。",
            )
        except Exception as exc:
            from clickgit.diagnostics import log_exception
            log_exception(type(exc), exc, exc.__traceback__, event="operation_failed")
            self.operation_failed.emit(
                "操作失败",
                str(exc) or exc.__class__.__name__,
            )
        finally:
            with self._pending_lock:
                self._pending = max(0, self._pending - 1)
                still_busy = self._pending > 0
            self.busy_changed.emit(still_busy)
