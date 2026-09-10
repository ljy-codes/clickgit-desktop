"""Bounded text conflict editing with optimistic, fail-closed save checks.

This is NOT a cross-process transaction: another process can still write between
the final check and os.replace / Git's index lock acquisition. Never roll back a
user's worktree file after staging fails. Reload a session after every save.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from clickgit.repository import RepositoryError

if TYPE_CHECKING:
    from clickgit.repository import Repository


MAX_TEXT_BYTES = 2 * 1024 * 1024
_OPERATIONS = (
    "HEAD", "ORIG_HEAD", "MERGE_HEAD", "MERGE_MSG", "MERGE_MODE", "AUTO_MERGE",
    "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "rebase-merge",
    "rebase-apply", "sequencer", "BISECT_LOG", "BISECT_START",
)
_MARKER = re.compile(r"^(<{1,}|>{1,}|\|{1,})(?:[ \t].*)?$|^(={1,})[ \t]*$")


class ConflictWorkflowError(RepositoryError):
    """A stale, unsupported or unsuccessful conflict operation."""


@dataclass(frozen=True)
class ConflictBlock:
    # Python string offsets, NOT Qt UTF-16 cursor positions.
    start: int
    end: int
    ours: str
    theirs: str
    base: str | None = None
    marker_size: int = 7


def _marker(line: str) -> tuple[str, int] | None:
    match = _MARKER.fullmatch(line.rstrip("\r\n"))
    if not match:
        return None
    run = match.group(1) or match.group(2)
    return run[0], len(run)


def parse_conflict_blocks(text: str) -> list[ConflictBlock]:
    """Parse complete merge/diff3/zdiff3 blocks, keeping untouched text intact."""
    blocks: list[ConflictBlock] = []
    start = offset = 0
    size = 0
    phase = ""
    ours: list[str] = []
    base: list[str] | None = None
    theirs: list[str] = []
    for line in text.splitlines(keepends=True):
        token = _marker(line)
        if token and token[0] == "<":
            # Nested/malformed markers invalidate the outer block.
            start, size, phase = offset, token[1], "ours"
            ours, base, theirs = [], None, []
        elif phase and token:
            kind, length = token
            if length != size:
                phase = ""
            elif kind == "|" and phase == "ours":
                phase, base = "base", []
            elif kind == "=" and phase in ("ours", "base"):
                phase = "theirs"
            elif kind == ">" and phase == "theirs":
                blocks.append(ConflictBlock(
                    start, offset + len(line), "".join(ours), "".join(theirs),
                    None if base is None else "".join(base), size,
                ))
                phase = ""
            else:
                phase = ""
        elif phase == "ours":
            ours.append(line)
        elif phase == "base" and base is not None:
            base.append(line)
        elif phase == "theirs":
            theirs.append(line)
        offset += len(line)
    return blocks


def contains_conflict_markers(text: str, marker_sizes: tuple[int, ...] = (7,)) -> bool:
    """Reject real/residual markers, but permit ordinary Markdown Setext titles.

    An isolated equals underline immediately after a nonempty, non-marker title
    is intentionally treated as document text; this ambiguous case is not proof
    of an unresolved merge. Complete conflict blocks always take precedence.
    """
    if parse_conflict_blocks(text):
        return True
    lines = text.splitlines()
    for index, line in enumerate(lines):
        token = _marker(line)
        if (token and token[0] == "=" and index > 0 and lines[index - 1].strip()
                and _marker(lines[index - 1]) is None):
            continue
        if token and (token[1] >= 3 or token[1] in marker_sizes):
            return True
        # A user may have removed the separator space but not the marker run.
        prefix = re.match(r"^(<+|>+|\|+|=+)", line)
        if prefix and (len(prefix[0]) >= 3 or len(prefix[0]) in marker_sizes):
            return True
    return False


@dataclass(frozen=True)
class _Snapshot:
    root: Path
    relative: str
    identity: tuple
    state: tuple
    index: tuple
    stages: bytes
    file: tuple
    attributes: bytes


@dataclass(frozen=True)
class ConflictSession:
    path: str
    base: str = ""
    ours: str = ""
    theirs: str = ""
    result: str = ""
    allowed: bool = False
    reason: str = ""
    _snapshot: _Snapshot | None = field(default=None, repr=False)
    _bom: bool = field(default=False, repr=False)
    _newline: str = field(default="\n", repr=False)
    _final_newline: bool = field(default=False, repr=False)
    _marker_size: int = field(default=7, repr=False)


def _git(repository: Repository, *args: str, data: bytes | None = None) -> bytes:
    result = repository.runner.run(
        ["--literal-pathspecs", *args], cwd=repository.path, input_bytes=data,
        timeout=30, env={"GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode:
        raise ConflictWorkflowError(f"Git 检查失败：{result.stderr_text.strip()}")
    return result.stdout


def _stat_key(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, "st_file_attributes", 0))


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _handle_matches(info: os.stat_result, expected: os.stat_result) -> bool:
    actual, wanted = _stat_key(info), _stat_key(expected)
    # Windows Python/CRT fstat and lstat may expose different ctime semantics.
    # Compare ctime only between like APIs; keep it in the pathname snapshot.
    if os.name == "nt":
        return actual[:6] + actual[7:] == wanted[:6] + wanted[7:]
    return actual == wanted


def _checked_chain(path: Path) -> tuple:
    """lstat every ancestor, including ancestors above the repository root."""
    identities = []
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if _is_link(info):
            raise ConflictWorkflowError("不允许符号链接或父路径 reparse point")
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise ConflictWorkflowError("父路径不是普通目录")
        identities.append((str(item), info.st_dev, info.st_ino, info.st_mode))
    return tuple(identities)


def _target(repository: Repository, path: str) -> tuple[Path, str]:
    if not isinstance(path, str) or not path or "\0" in path:
        raise ConflictWorkflowError("无效文件路径")
    if Path(path).is_absolute() or PureWindowsPath(path).drive or "\\" in path:
        raise ConflictWorkflowError("必须使用仓库内的普通相对路径")
    parts = path.split("/")
    if any(part in ("", ".", "..") or part.rstrip(" .").casefold() == ".git"
           or ":" in part or part.endswith((" ", ".")) for part in parts):
        raise ConflictWorkflowError("不允许 .git、父路径或特殊路径")
    root = Path(repository.path).absolute()
    target = root.joinpath(*parts)
    _checked_chain(target)
    return target, "/".join(parts)


def _read_file(path: Path, *, bounded: bool = True) -> tuple[bytes, tuple]:
    _checked_chain(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ConflictWorkflowError("仅允许普通文件，不允许硬链接或特殊文件")
    if bounded and before.st_size > MAX_TEXT_BYTES:
        raise ConflictWorkflowError("文本超过 2 MiB，只读")
    digest = hashlib.sha256()
    content = bytearray()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not _handle_matches(opened, before):
            raise ConflictWorkflowError("文件在读取前发生变化，请重新加载")
        while True:
            chunk = stream.read(min(65536, MAX_TEXT_BYTES + 1 - len(content))
                                if bounded else 65536)
            if not chunk:
                break
            digest.update(chunk)
            if bounded:
                content.extend(chunk)
                if len(content) > MAX_TEXT_BYTES:
                    raise ConflictWorkflowError("文本超过 2 MiB，只读")
        if _stat_key(os.fstat(stream.fileno())) != _stat_key(opened):
            raise ConflictWorkflowError("文件在读取中发生变化，请重新加载")
    _checked_chain(path)
    if _stat_key(path.lstat()) != _stat_key(before):
        raise ConflictWorkflowError("文件在读取中发生变化，请重新加载")
    return bytes(content), (_stat_key(before), digest.digest())


def _optional_state(path: Path) -> tuple:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return ()
    if _is_link(info):
        raise ConflictWorkflowError("仓库操作状态含链接，禁止保存")
    if stat.S_ISDIR(info.st_mode):
        entries = sorted(path.iterdir())
        if len(entries) > 4096:
            raise ConflictWorkflowError("仓库操作状态过大，禁止保存")
        return (_checked_chain(path), tuple((p.name, _optional_state(p)) for p in entries))
    return _read_file(path)[1]


def _snapshot(repository: Repository, relative: str) -> _Snapshot:
    target, relative = _target(repository, relative)
    root = Path(repository.path).absolute()
    lines = _git(repository, "rev-parse", "--show-toplevel", "--absolute-git-dir",
                 "--git-common-dir", "--git-path", "index").decode("utf-8").splitlines()
    if len(lines) != 4:
        raise ConflictWorkflowError("无法确认仓库身份")
    top, gitdir, common, index = [
        Path(value) if Path(value).is_absolute() else root / value for value in lines
    ]
    if top.resolve() != root or repository.is_bare:
        raise ConflictWorkflowError("仓库身份发生变化，请重新加载")
    # Git's actual index can be redirected by its environment; capture that exact path.
    identity = (_checked_chain(root), _checked_chain(gitdir), _checked_chain(common),
                _checked_chain(target.parent), str(index.absolute()),
                _optional_state(root / ".git") if (root / ".git").is_file() else ())
    if index.with_name(index.name + ".lock").exists():
        raise ConflictWorkflowError("Git 索引被锁定，请等待后重新加载")
    state = (
        _git(repository, "rev-parse", "--verify", "HEAD"),
        tuple((name, _optional_state(gitdir / name)) for name in _OPERATIONS),
        _optional_state(common / "config"), _optional_state(gitdir / "config.worktree"),
    )
    index_state = _read_file(index, bounded=False)[1]
    stages = _git(repository, "ls-files", "--stage", "-z", "--", relative)
    attrs = _git(repository, "check-attr", "-z", "filter", "working-tree-encoding",
                 "text", "conflict-marker-size", "--", relative)
    file_state = _read_file(target)[1]
    return _Snapshot(root, relative, identity, state, index_state, stages, file_state, attrs)


def _stages(raw: bytes, path: str) -> dict[int, tuple[str, str]]:
    stages = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        if name.decode("utf-8") != path or int(stage) in stages:
            raise ConflictWorkflowError("索引路径不明确，禁止文本覆盖")
        stages[int(stage)] = (mode, oid)
    return stages


def _decode(raw: bytes) -> tuple[str, bool, str, bool]:
    if b"\0" in raw or any(byte < 32 and byte not in (9, 10, 13) for byte in raw):
        raise ConflictWorkflowError("二进制或非普通文本不允许覆盖")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ConflictWorkflowError("未知编码：仅支持 UTF-8 / UTF-8 BOM") from error
    newlines = set(re.findall(r"\r\n|\r|\n", text))
    if len(newlines) > 1:
        raise ConflictWorkflowError("混合换行文本只读，避免保存时改变格式")
    newline = next(iter(newlines), "\n")
    return text, raw.startswith(b"\xef\xbb\xbf"), newline, text.endswith(("\r", "\n"))


def _blob(repository: Repository, oid: str) -> str:
    # Immutable object id: size first prevents unbounded text/blob capture.
    size = int(_git(repository, "cat-file", "-s", oid))
    if size > MAX_TEXT_BYTES:
        raise ConflictWorkflowError("索引版本超过 2 MiB，只读")
    raw = _git(repository, "cat-file", "blob", oid)
    if len(raw) != size:
        raise ConflictWorkflowError("索引对象读取不完整")
    return _decode(raw)[0]


def _validate_simple_conflict(repository: Repository, snapshot: _Snapshot) -> int:
    stages = _stages(snapshot.stages, snapshot.relative)
    if set(stages) not in ({1, 2, 3}, {2, 3}):
        raise ConflictWorkflowError("文件已非普通冲突；删除/重命名冲突请使用专用 Git 操作")
    modes = {mode for mode, _ in stages.values()}
    if len(modes) != 1 or not modes.issubset({"100644", "100755"}):
        raise ConflictWorkflowError("链接、子模块或类型变化冲突不允许文本覆盖")
    values = snapshot.attributes.split(b"\0")
    attrs = dict(zip(values[1::3], values[2::3]))
    if (attrs.get(b"filter") not in (b"unspecified", b"unset")
            or attrs.get(b"working-tree-encoding") not in (b"unspecified", b"unset")
            or attrs.get(b"text") == b"unset"):
        raise ConflictWorkflowError("过滤器、特殊编码或二进制属性不允许文本覆盖")
    # Rename conflicts can have all three stages under a new/reused pathname.
    # Confirm each stage against that exact name in the operation's source trees.
    gitdir = Path(_git(repository, "rev-parse", "--absolute-git-dir").decode().strip())
    merge_head = gitdir / "MERGE_HEAD"
    if merge_head.exists():
        tips = _read_file(merge_head)[0].decode("ascii").split()
        if len(tips) != 1:
            raise ConflictWorkflowError("多头复杂合并不允许文本覆盖")
        refs = {2: "HEAD", 3: tips[0]}
        if 1 in stages:
            bases = _git(repository, "merge-base", "--all", "HEAD", tips[0]).decode().split()
            if len(bases) != 1:
                raise ConflictWorkflowError("多个共同祖先的复杂冲突只读")
            refs[1] = bases[0]
    else:
        source = next((name for name in ("REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")
                       if (gitdir / name).exists()), None)
        if source is None:
            raise ConflictWorkflowError("无法确认冲突来源；复杂或无操作状态的冲突只读")
        oid = _read_file(gitdir / source)[0].decode("ascii").strip()
        parents = _git(repository, "rev-list", "--parents", "-n", "1", oid).decode().split()
        if len(parents) != 2:
            raise ConflictWorkflowError("根提交或多父提交的复杂冲突只读")
        refs = {2: "HEAD", 3: oid, 1: parents[1]}
        if source == "REVERT_HEAD":
            refs[1], refs[3] = refs[3], refs[1]
    for stage, (mode, oid) in stages.items():
        record = _git(repository, "ls-tree", "-z", refs[stage], "--", snapshot.relative)
        expected = f"{mode} blob {oid}\t".encode() + snapshot.relative.encode() + b"\0"
        if record != expected:
            raise ConflictWorkflowError("复杂删除/重命名或非标准索引冲突不允许文本覆盖")
    marker = attrs.get(b"conflict-marker-size", b"7")
    return int(marker) if marker.isdigit() and int(marker) > 0 else 7


def load_conflict(repository: Repository, path: str) -> ConflictSession:
    """Load a guarded UTF-8 conflict, or a read-only session with a reason."""
    try:
        _, relative = _target(repository, path)
        before = _snapshot(repository, relative)
        marker_size = _validate_simple_conflict(repository, before)
        stages = _stages(before.stages, relative)
        sources = {stage: _blob(repository, oid) for stage, (_, oid) in stages.items()}
        raw, file_state = _read_file(before.root / relative)
        result, bom, newline, final_newline = _decode(raw)
        if file_state != before.file or _snapshot(repository, relative) != before:
            raise ConflictWorkflowError("读取期间文件、索引或仓库操作发生变化，请重新加载")
        return ConflictSession(
            relative, sources.get(1, ""), sources[2], sources[3], result, True, "",
            before, bom, newline, final_newline, marker_size,
        )
    except (OSError, ValueError, RuntimeError) as error:
        return ConflictSession(path=path, reason=str(error) or "无法安全读取冲突")


def _verify(repository: Repository, session: ConflictSession,
            *, file_state: tuple | None = None, staged: bool = False) -> _Snapshot:
    expected = session._snapshot
    if expected is None or Path(repository.path).absolute() != expected.root:
        raise ConflictWorkflowError("仓库身份发生变化，请重新加载")
    current = _snapshot(repository, session.path)
    same = (current.identity == expected.identity and current.state == expected.state
            and current.attributes == expected.attributes
            and current.file == (expected.file if file_state is None else file_state))
    if not staged:
        same = same and current.index == expected.index and current.stages == expected.stages
    if not same:
        raise ConflictWorkflowError("文件、索引或仓库操作发生变化，请重新加载；不会覆盖外部修改")
    return current


def _encode_result(session: ConflictSession, text: str) -> bytes:
    if len(text) > MAX_TEXT_BYTES:
        raise ConflictWorkflowError("结果超过 2 MiB")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Preserve the original EOF convention, while leaving intentional blank lines.
    if normalized and session._final_newline and not normalized.endswith("\n"):
        normalized += "\n"
    elif not session._final_newline:
        normalized = normalized.rstrip("\n")
    raw = normalized.replace("\n", session._newline).encode("utf-8")
    if session._bom:
        raw = b"\xef\xbb\xbf" + raw
    if len(raw) > MAX_TEXT_BYTES:
        raise ConflictWorkflowError("结果超过 2 MiB")
    _decode(raw)
    return raw


def _file_owner(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def _cleanup_temporary(path: Path, owner: tuple | None, parents: tuple | None) -> None:
    """Remove only our original single-link object through unchanged parents."""
    try:
        if owner is None or parents is None or _checked_chain(path.parent) != parents:
            raise ConflictWorkflowError("临时文件父路径或归属无法确认")
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        if (_is_link(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not info.st_ino or _file_owner(info) != owner):
            raise ConflictWorkflowError("临时路径已替换、成为链接或不再属于本次保存")
        # Like replacement, this final check/unlink pair is optimistic, not a
        # cross-process transaction. Never chmod or follow an unexpected object.
        path.unlink()
    except (OSError, RuntimeError) as error:
        raise ConflictWorkflowError(
            f"未能安全清理临时路径，已停止删除，请人工检查：{path}（{error}）"
        ) from error


def save_conflict(repository: Repository, session: ConflictSession, result_text: str,
                  *, mark_resolved: bool) -> None:
    """Atomically replace the text; optionally stage, never auto-commit.

    Sessions are single-save snapshots. Staging failure leaves the new user file
    in place, raises an error and does not claim the conflict was resolved.
    """
    if not session.allowed or session._snapshot is None:
        raise ConflictWorkflowError(session.reason or "此冲突不允许保存")
    marker_sizes = (session._marker_size, *(
        block.marker_size for block in parse_conflict_blocks(session.result)
    ))
    if mark_resolved and contains_conflict_markers(result_text, marker_sizes):
        raise ConflictWorkflowError("仍有未解决的冲突标记；可以保存草稿")
    temporary: Path | None = None
    temporary_owner: tuple | None = None
    temporary_parents: tuple | None = None
    written = False
    try:
        raw = _encode_result(session, result_text)
        _verify(repository, session)
        target, _ = _target(repository, session.path)
        temporary_parents = _checked_chain(target.parent)
        fd, name = tempfile.mkstemp(prefix=".clickgit-conflict-", dir=target.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            temporary_owner = _file_owner(os.fstat(stream.fileno()))
            stream.write(raw)
            stream.flush()
            mode = stat.S_IMODE(session._snapshot.file[0][2])
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), mode)
            elif stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != mode:
                # Fail closed on runtimes without a no-follow permission API.
                os.chmod(temporary, mode, follow_symlinks=False)
            os.fsync(stream.fileno())
        prepared, prepared_state = _read_file(temporary)
        if (prepared != raw or _file_owner(temporary.lstat()) != temporary_owner
                or _checked_chain(temporary.parent) != temporary_parents):
            raise ConflictWorkflowError("临时结果内容或归属校验失败")
        _verify(repository, session)  # Last check immediately before replacement.
        if _read_file(temporary) != (prepared, prepared_state):
            raise ConflictWorkflowError("临时结果在最后校验期间发生变化，未覆盖原文件")
        if _read_file(target)[1] != session._snapshot.file:
            raise ConflictWorkflowError("目标文件在最后校验期间发生变化，未覆盖原文件")
        os.replace(temporary, target)
        temporary = None
        written = True
        saved, saved_state = _read_file(target)
        if saved != raw or saved_state[0][:2] != prepared_state[0][:2]:
            raise ConflictWorkflowError("写后文件发生变化，请检查；不自动回滚用户文件")
        _verify(repository, session, file_state=saved_state)
        if mark_resolved:
            try:
                expected_oid = _git(repository, "hash-object", "--path", session.path,
                                    "--stdin", data=raw).strip().decode("ascii")
                _verify(repository, session, file_state=saved_state)
                _git(repository, "add", "--", session.path)
                current = _verify(repository, session, file_state=saved_state, staged=True)
                entries = _stages(current.stages, session.path)
                if set(entries) != {0} or entries[0][1] != expected_oid:
                    raise ConflictWorkflowError("暂存内容不符或文件仍处于冲突状态")
            except (OSError, ValueError, RuntimeError) as error:
                raise ConflictWorkflowError(
                    f"用户结果已保存，但暂存失败或校验未通过；请重新检查，不能视为已解决：{error}"
                ) from error
    except (OSError, ValueError) as error:
        suffix = "；用户结果已写入，未自动回滚" if written else "；未覆盖原文件"
        raise ConflictWorkflowError(f"冲突保存失败：{error}{suffix}") from error
    finally:
        if temporary is not None:
            pending_error = sys.exc_info()[1]
            try:
                _cleanup_temporary(temporary, temporary_owner, temporary_parents)
            except ConflictWorkflowError as cleanup_error:
                detail = f"{pending_error}；" if pending_error is not None else ""
                raise ConflictWorkflowError(detail + str(cleanup_error)) from cleanup_error
