from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from clickgit.defaults import (
    DEFAULT_DENSITY,
    DEFAULT_FONT_SIZE_PX,
    DEFAULT_MODE,
    DEFAULT_THEME,
)


@dataclass(slots=True)
class AppSettings:
    recent_repositories: list[str] = field(default_factory=list)
    favorite_repositories: list[str] = field(default_factory=list)
    theme: str = DEFAULT_THEME
    external_editor: str = ""
    mode: str = DEFAULT_MODE
    font_size_px: int = DEFAULT_FONT_SIZE_PX
    density: str = DEFAULT_DENSITY
    onboarding_completed: bool = False


class ChangeKind(str, Enum):
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    TYPE_CHANGED = "type_changed"
    UNTRACKED = "untracked"
    IGNORED = "ignored"
    CONFLICTED = "conflicted"


@dataclass(slots=True, frozen=True)
class FileChange:
    path: str
    kind: ChangeKind
    staged: bool = False
    index_status: str = "."
    worktree_status: str = "."
    original_path: str | None = None
    conflicted: bool = False


@dataclass(slots=True, frozen=True)
class Branch:
    name: str
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    current: bool = False


@dataclass(slots=True, frozen=True)
class Commit:
    oid: str
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    authored_at: datetime
    subject: str
    decorations: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class Remote:
    name: str
    fetch_url: str = ""
    push_url: str = ""


@dataclass(slots=True, frozen=True)
class StashEntry:
    reference: str
    oid: str
    created_at: datetime
    subject: str


@dataclass(slots=True, frozen=True)
class ReflogEntry:
    selector: str
    oid: str
    created_at: datetime
    subject: str


@dataclass(slots=True, frozen=True)
class GitResult:
    command: tuple[str, ...]
    cwd: Path | None
    returncode: int
    stdout: bytes
    stderr: bytes
    duration_seconds: float

    @property
    def stdout_text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    @property
    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", errors="replace")


@dataclass(slots=True, frozen=True)
class WorktreeInfo:
    path: Path
    head: str = ""
    branch: str = ""
    bare: bool = False
    detached: bool = False
    locked: str = ""
    prunable: str = ""


@dataclass(slots=True, frozen=True)
class SubmoduleInfo:
    path: str
    oid: str
    state: str
    description: str = ""


@dataclass(slots=True, frozen=True)
class ConflictVersions:
    path: str
    base: str
    ours: str
    theirs: str
    result: str
