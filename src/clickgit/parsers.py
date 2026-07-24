from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from clickgit.models import (
    Branch,
    ChangeKind,
    Commit,
    FileChange,
    ReflogEntry,
    Remote,
    StashEntry,
)


def parse_status_v2(raw: bytes) -> list[FileChange]:
    records = raw.split(b"\0")
    changes: list[FileChange] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue

        text = record.decode("utf-8", errors="surrogateescape")
        prefix = text[:1]
        if prefix == "1":
            parts = text.split(" ", 8)
            if len(parts) != 9:
                continue
            xy = parts[1]
            changes.append(_file_change(parts[8], xy))
        elif prefix == "2":
            parts = text.split(" ", 9)
            if len(parts) != 10:
                continue
            original = None
            if index < len(records):
                original = records[index].decode(
                    "utf-8", errors="surrogateescape"
                )
                index += 1
            changes.append(
                _file_change(parts[9], parts[1], original_path=original)
            )
        elif prefix == "u":
            parts = text.split(" ", 10)
            if len(parts) != 11:
                continue
            changes.append(
                FileChange(
                    path=parts[10],
                    kind=ChangeKind.CONFLICTED,
                    staged=False,
                    index_status=parts[1][0],
                    worktree_status=parts[1][1],
                    conflicted=True,
                )
            )
        elif prefix == "?":
            changes.append(
                FileChange(
                    path=text[2:],
                    kind=ChangeKind.UNTRACKED,
                    worktree_status="?",
                )
            )
        elif prefix == "!":
            changes.append(
                FileChange(
                    path=text[2:],
                    kind=ChangeKind.IGNORED,
                    worktree_status="!",
                )
            )
    return changes


def _file_change(
    path: str,
    xy: str,
    *,
    original_path: str | None = None,
) -> FileChange:
    index_status, worktree_status = xy[0], xy[1]
    conflicted = "U" in xy or xy in {"AA", "DD"}
    if conflicted:
        kind = ChangeKind.CONFLICTED
    else:
        significant = index_status if index_status != "." else worktree_status
        kind = {
            "A": ChangeKind.ADDED,
            "D": ChangeKind.DELETED,
            "R": ChangeKind.RENAMED,
            "C": ChangeKind.COPIED,
            "T": ChangeKind.TYPE_CHANGED,
        }.get(significant, ChangeKind.MODIFIED)
    return FileChange(
        path=path,
        kind=kind,
        staged=index_status != ".",
        index_status=index_status,
        worktree_status=worktree_status,
        original_path=original_path,
        conflicted=conflicted,
    )


def parse_branches(raw: str) -> list[Branch]:
    branches: list[Branch] = []
    for line in raw.splitlines():
        fields = line.split("\0")
        if len(fields) < 5:
            continue
        upstream = fields[1]
        if upstream.startswith("refs/remotes/"):
            upstream = upstream.removeprefix("refs/remotes/")
        branches.append(
            Branch(
                name=fields[0],
                upstream=upstream or None,
                ahead=_parse_int(fields[2]),
                behind=_parse_int(fields[3]),
                current=fields[4].strip() == "*",
            )
        )
    return branches


def parse_log_records(raw: bytes) -> list[Commit]:
    commits: list[Commit] = []
    for record in raw.decode("utf-8", errors="replace").split("\x1e"):
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) < 7:
            continue
        commits.append(
            Commit(
                oid=fields[0],
                parents=tuple(filter(None, fields[1].split())),
                author_name=fields[2],
                author_email=fields[3],
                authored_at=datetime.fromisoformat(fields[4]),
                subject=fields[5],
                decorations=tuple(
                    item.strip()
                    for item in fields[6].split(",")
                    if item.strip()
                ),
            )
        )
    return commits


def parse_remotes(raw: str) -> list[Remote]:
    grouped: dict[str, dict[str, str]] = defaultdict(dict)
    for line in raw.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        name, operation, url = fields
        grouped[name][operation] = url
    return [
        Remote(
            name=name,
            fetch_url=urls.get("fetch", ""),
            push_url=urls.get("push", ""),
        )
        for name, urls in sorted(grouped.items())
    ]


def parse_stashes(raw: str) -> list[StashEntry]:
    return [
        StashEntry(
            reference=fields[0],
            oid=fields[1],
            created_at=datetime.fromisoformat(fields[2]),
            subject=fields[3],
        )
        for fields in _parse_delimited_records(raw, 4)
    ]


def parse_reflog(raw: str) -> list[ReflogEntry]:
    return [
        ReflogEntry(
            selector=fields[0],
            oid=fields[1],
            created_at=datetime.fromisoformat(fields[2]),
            subject=fields[3],
        )
        for fields in _parse_delimited_records(raw, 4)
    ]


def _parse_delimited_records(raw: str, field_count: int) -> list[list[str]]:
    records: list[list[str]] = []
    for record in raw.split("\x1e"):
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) >= field_count:
            records.append(fields)
    return records


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0
