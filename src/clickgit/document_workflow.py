"""Bounded, read-only document comparisons and explicitly reviewed Git merges."""
from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from clickgit.git_runner import GitCommandError
from clickgit.repository import Repository

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_FILES = 3000


class DocumentError(ValueError):
    pass


@dataclass(frozen=True)
class TextComparison:
    path: str
    left: str
    right: str
    left_title: str
    right_title: str
    notice: str = ""
    supported: bool = True


@dataclass(frozen=True)
class ComparisonList:
    repository: str
    title: str
    left_oid: str
    right_oid: str
    files: tuple[str, ...]
    left_title: str
    right_title: str
    notice: str = ""
    merge_head: str = ""
    index_digest: str = ""
    branch: str = ""


@dataclass(frozen=True)
class MergePlan:
    repository: str
    current_branch: str
    before_oid: str
    source_name: str
    source_oid: str
    comparison: ComparisonList


class DocumentWorkflow:
    def __init__(self, repository: Repository):
        self.repo = repository

    def _run(self, args):
        return self.repo._run(args)

    def _path(self, path: str) -> Path:
        # Reject metadata, traversal and special paths before resolving anything.
        normalized = path.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        if (not parts or normalized.startswith("/") or ":" in normalized
                or any(p in (".", "..") or p.casefold() == ".git" for p in parts)
                or any(c in normalized for c in ("\0", "\n", "\r"))):
            raise DocumentError("只能查看仓库内普通文件，不能访问仓库元数据或外部路径。")
        current = self.repo.path
        for part in parts:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise DocumentError("链接或重解析路径不使用文本对比。")
        return current

    def _tree_blob(self, tree: str, path: str) -> tuple[str, str] | None:
        self._path(path)
        if not tree:
            return None
        data = self._run(["ls-tree", "-z", "--full-tree", tree, "--",
                          f":(literal){path}"]).stdout
        if not data:
            return None
        records = data.rstrip(b"\0").split(b"\0")
        if len(records) != 1:
            raise DocumentError("文件路径没有唯一对应的版本。")
        metadata = records[0].split(b"\t", 1)[0].decode("ascii").split()
        return metadata[0], metadata[2]

    def _index_blob(self, path: str) -> tuple[str, str] | None:
        self._path(path)
        data = self._run(["ls-files", "--stage", "-z", "--", f":(literal){path}"]).stdout
        if not data:
            return None
        records = data.rstrip(b"\0").split(b"\0")
        if len(records) != 1:
            raise DocumentError("该文件存在冲突，请双击打开冲突编辑器。")
        mode, oid, stage = records[0].split(b"\t", 1)[0].decode("ascii").split()
        if stage != "0":
            raise DocumentError("该文件存在冲突，请双击打开冲突编辑器。")
        return mode, oid

    def _blob(self, record: tuple[str, str] | None) -> bytes:
        if record is None:
            return b""
        mode, oid = record
        if mode not in ("100644", "100755"):
            raise DocumentError("链接、子模块或特殊文件不支持文本对比。")
        size = int(self._run(["cat-file", "-s", oid]).stdout_text.strip())
        if size > MAX_TEXT_BYTES:
            raise DocumentError("文件超过 2 MiB，请使用外部工具查看，未读取完整内容。")
        return self._run(["cat-file", "blob", oid]).stdout

    def _working_bytes(self, path: str) -> bytes:
        target = self._path(path)
        try:
            info = target.stat()
        except FileNotFoundError:
            return b""
        if not stat.S_ISREG(info.st_mode):
            raise DocumentError("该路径不是普通文本文件。")
        if info.st_size > MAX_TEXT_BYTES:
            raise DocumentError("文件超过 2 MiB，请使用外部工具查看，未读取完整内容。")
        with target.open("rb") as stream:
            data = stream.read(MAX_TEXT_BYTES + 1)
        if len(data) > MAX_TEXT_BYTES:
            raise DocumentError("文件读取时变大，请刷新后重试。")
        return data

    @staticmethod
    def _decode(data: bytes) -> str:
        if b"\0" in data:
            raise DocumentError("二进制文件不支持文本对比，未进行有损解码。")
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("不是受支持的 UTF-8 文本，请使用外部工具确认编码。") from exc

    def _head_optional(self) -> str:
        result = self.repo.runner.run(["rev-parse", "--verify", "HEAD"], cwd=self.repo.path)
        if result.returncode == 0:
            return result.stdout_text.strip()
        branch = self.repo.runner.run(["symbolic-ref", "-q", "HEAD"], cwd=self.repo.path)
        if branch.returncode == 0:
            exists = self.repo.runner.run(
                ["show-ref", "--verify", "--quiet", branch.stdout_text.strip()], cwd=self.repo.path)
            if exists.returncode == 1:
                return ""
        raise GitCommandError(result)

    def workspace(self, path: str, *, staged: bool = False,
                  original_path: str | None = None) -> TextComparison:
        self._path(path)
        old = original_path or path
        self._path(old)
        head = self._head_optional() if staged else ""
        left_title = (f"上次提交 {head[:10]} · {old}" if head else "首次提交前（空）") if staged else "暂存版本"
        right_title = "本次暂存内容" if staged else "当前工作文件（未暂存）"
        try:
            left = self._blob(self._tree_blob(head, old) if staged else self._index_blob(path))
            right = self._blob(self._index_blob(path)) if staged else self._working_bytes(path)
            return self._text_pair(path, left, right, left_title, right_title)
        except DocumentError as exc:
            return TextComparison(path, "", "", left_title, right_title, str(exc), False)

    def _text_pair(self, path, left, right, left_title, right_title, notice=""):
        left_text, right_text = self._decode(left), self._decode(right)
        def description(data):
            endings = "CRLF" if b"\r\n" in data else ("CR" if b"\r" in data else "LF")
            return f"{'UTF-8 BOM' if data.startswith(bytes.fromhex('efbbbf')) else 'UTF-8'} / {endings}"
        details = f"左：{description(left)}；右：{description(right)}。只读对比，不修改文件。"
        return TextComparison(path, left_text, right_text, left_title, right_title,
                              f"{notice}\n{details}".strip())

    def _comparison(self, left: str, right: str, *, title: str,
                    left_title: str, right_title: str, notice="",
                    merge_head="", index_digest="", branch="") -> ComparisonList:
        args = ["diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z"]
        # Root commits are compared against an empty tree without writing an object.
        if not left:
            args = ["ls-tree", "-r", "--name-only", "-z", right, "--"]
        else:
            args += [left, right, "--"]
        raw = self._run(args).stdout
        names = tuple(n.decode("utf-8", "strict") for n in raw.split(b"\0") if n)
        if len(names) > MAX_FILES:
            raise DocumentError("变化文件超过 3000 个，请缩小比较范围或使用外部工具。")
        return ComparisonList(str(self.repo.path), title, left, right, names,
                              left_title, right_title, notice, merge_head, index_digest, branch)

    def compare_revisions(self, left: str, right: str) -> ComparisonList:
        before = self.repo.rev_parse(left + "^{commit}") if left else ""
        after = self.repo.rev_parse(right + "^{commit}")
        return self._comparison(before, after, title="版本内容对比",
                                left_title=f"原版本 {before[:10]}" if before else "首次提交前（空）",
                                right_title=f"目标版本 {after[:10]}",
                                notice="新增与删除分别列出；重命名按旧路径删除、新路径新增展示。")

    def comparison_file(self, listing: ComparisonList, path: str) -> TextComparison:
        if listing.repository != str(self.repo.path) or path not in listing.files:
            raise DocumentError("比较快照与当前仓库或文件不匹配，请重新打开。")
        try:
            left = self._blob(self._tree_blob(listing.left_oid, path))
            right = self._blob(self._tree_blob(listing.right_oid, path))
            return self._text_pair(path, left, right, listing.left_title, listing.right_title, listing.notice)
        except DocumentError as exc:
            return TextComparison(path, "", "", listing.left_title, listing.right_title, str(exc), False)

    def _git_path(self, name: str) -> Path:
        path = Path(self._run(["rev-parse", "--git-path", name]).stdout_text.strip())
        return path if path.is_absolute() else self.repo.path / path

    def merge_active(self) -> bool:
        return self._git_path("MERGE_HEAD").is_file()

    def _merge_head(self) -> str:
        value = self._git_path("MERGE_HEAD").read_text(encoding="ascii").strip()
        if len(value.splitlines()) != 1:
            raise DocumentError("多来源合并请使用外部 Git 工具完成。")
        return self.repo.rev_parse(value + "^{commit}")

    def _other_operation(self) -> bool:
        return any(self._git_path(name).exists() for name in (
            "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD"))

    def plan_merge(self, source: str) -> MergePlan:
        if self.merge_active() or self._other_operation():
            raise DocumentError("当前有尚未完成的合并或其他操作，请先完成或取消。")
        before = self.repo.head_oid()
        target = self.repo.rev_parse(source + "^{commit}")
        branch = self.repo.current_branch()
        if branch == "(detached HEAD)":
            raise DocumentError("请先切换到接收内容的分支，再合并。")
        comparison = self.compare_revisions(before, target)
        return MergePlan(str(self.repo.path), branch, before, source, target, comparison)

    def start_merge(self, plan: MergePlan) -> None:
        if (plan.repository != str(self.repo.path) or self.repo.head_oid() != plan.before_oid
                or self.repo.current_branch() != plan.current_branch
                or self.repo.rev_parse(plan.source_name + "^{commit}") != plan.source_oid):
            raise DocumentError("分支或来源已变化，旧预览失效，请重新比较并确认。")
        if self.merge_active() or self._other_operation() or self.repo.status():
            raise DocumentError("合并前请先提交或妥善贮藏全部修改（含未跟踪文件）；不会自动丢弃。")
        # Do not lead users into a merge they cannot review/finish in this text-only increment.
        for path in plan.comparison.files:
            pair = self.comparison_file(plan.comparison, path)
            if not pair.supported:
                raise DocumentError(f"{path} 无法安全文本预览：{pair.notice} 本次未开始合并，请使用外部 Git 工具。")
            # status() excludes ignored files; some Git strategies still overwrite
            # them despite --no-overwrite-ignore. Guard incoming paths ourselves.
            if self._tree_blob(plan.before_oid, path) is None and self._path(path).exists():
                raise DocumentError(f"合入路径 {path} 已有本机文件或目录（可能被 Git 忽略），请先另存，未开始合并。")
        if (self.repo.head_oid() != plan.before_oid
                or self.repo.current_branch() != plan.current_branch
                or self.repo.rev_parse(plan.source_name + "^{commit}") != plan.source_oid
                or self.merge_active() or self._other_operation() or self.repo.status()):
            raise DocumentError("预检期间分支或文件已变化，请重新比较，未开始合并。")
        # --no-ff is deliberate: even a fast-forward must stop before committing.
        result = self.repo.runner.run(
            ["merge", "--no-commit", "--no-ff", "--no-edit", "--no-overwrite-ignore",
             plan.source_oid], cwd=self.repo.path)
        if result.returncode and not (self.merge_active() and self.repo.conflicted_files()):
            raise GitCommandError(result)

    def _index_digest(self) -> str:
        return hashlib.sha256(self._run(["ls-files", "--stage", "-z"]).stdout).hexdigest()

    def merge_result(self) -> ComparisonList:
        if not self.merge_active() or self._other_operation():
            raise DocumentError("当前没有可完成的普通分支合并。")
        if self.repo.conflicted_files():
            raise DocumentError("仍有冲突文件，请先逐项处理并标记已解决。")
        before = self.repo.head_oid()
        if before != self.repo.rev_parse("ORIG_HEAD"):
            raise DocumentError("合并开始后当前版本已被外部改变，请使用 Git 工具检查，不使用错误基线完成合并。")
        branch = self.repo.current_branch()
        source = self._merge_head()
        digest = self._index_digest()
        tree = self._run(["write-tree"]).stdout_text.strip()
        if digest != self._index_digest() or before != self.repo.head_oid():
            raise DocumentError("暂存内容发生变化，请重新检查合并结果。")
        return self._comparison(before, tree, title="检查实际合并结果",
                                left_title=f"合并前 {before[:10]}", right_title="实际暂存结果（尚未提交）",
                                notice="仅这些暂存内容将进入合并提交；查看后仍需点击“确认完成合并”。",
                                merge_head=source, index_digest=digest, branch=branch)

    def finish_merge(self, reviewed: ComparisonList) -> str:
        self._validate_review_state(reviewed)
        # Text presentation limits remain fail-closed for merges started by external tools.
        from clickgit.conflict_workflow import parse_conflict_blocks
        import re
        for path in reviewed.files:
            record = self._tree_blob(reviewed.right_oid, path)
            if record is None or record[0] not in ("100644", "100755"):
                continue
            data = self._blob(record)
            if b"\0" not in data:
                text = data.decode("utf-8", errors="replace")
                # A standalone ======= line can be a legitimate Markdown title.
                # Complete blocks and orphaned start/end/base delimiters still block.
                if parse_conflict_blocks(text) or re.search(
                        r"(?m)^(?:<{7,}|>{7,}|\|{7,})(?:[ \t].*)?\r?$", text):
                    raise DocumentError(f"文件 {path} 仍有疑似冲突标记，请人工检查后重新暂存。")
        # Scanning can be slow. Recheck immediately before Git acquires its locks.
        # This is optimistic validation, not an atomic transaction with external tools.
        self._validate_review_state(reviewed)
        self.repo.continue_merge()
        return self.repo.head_oid()

    def _validate_review_state(self, reviewed: ComparisonList) -> None:
        if (reviewed.repository != str(self.repo.path) or not reviewed.merge_head
                or not self.merge_active() or self._other_operation()):
            raise DocumentError("合并状态已改变，请重新检查。")
        if (self.repo.head_oid() != reviewed.left_oid or self._merge_head() != reviewed.merge_head
                or self._index_digest() != reviewed.index_digest
                or self.repo.current_branch() != reviewed.branch
                or self.repo.rev_parse("ORIG_HEAD") != reviewed.left_oid):
            raise DocumentError("检查后合并来源或暂存内容已变化，请重新检查。")
        changes = self.repo.status()
        if any(c.conflicted or not c.staged for c in changes):
            raise DocumentError("仍有冲突、未暂存或未跟踪文件，请先处理后重新检查。")
        if self._run(["write-tree"]).stdout_text.strip() != reviewed.right_oid:
            raise DocumentError("合并结果已变化，请重新检查。")

    def abort_merge(self) -> None:
        if not self.merge_active() or self._other_operation():
            raise DocumentError("当前没有可取消的普通合并。")
        self.repo.abort_merge()
