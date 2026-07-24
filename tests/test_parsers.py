from __future__ import annotations

import unittest

from clickgit.models import ChangeKind
from clickgit.parsers import (
    parse_branches,
    parse_log_records,
    parse_reflog,
    parse_remotes,
    parse_stashes,
    parse_status_v2,
)


class StatusParserTests(unittest.TestCase):
    def test_parse_modified_staged_untracked_and_renamed_files(self) -> None:
        raw = (
            b"1 .M N... 100644 100644 100644 abcdef0 abcdef1 src/app.py\0"
            b"1 A. N... 000000 100644 100644 0000000 abcdef2 "
            b"\xe4\xb8\xad\xe6\x96\x87.txt\0"
            b"? notes.txt\0"
            b"2 R. N... 100644 100644 100644 abcdef3 abcdef4 R100 "
            b"new-name.txt\0old-name.txt\0"
        )

        changes = parse_status_v2(raw)

        self.assertEqual(
            [(item.path, item.kind, item.staged) for item in changes],
            [
                ("src/app.py", ChangeKind.MODIFIED, False),
                ("中文.txt", ChangeKind.ADDED, True),
                ("notes.txt", ChangeKind.UNTRACKED, False),
                ("new-name.txt", ChangeKind.RENAMED, True),
            ],
        )
        self.assertEqual(changes[-1].original_path, "old-name.txt")

    def test_parse_conflicted_file(self) -> None:
        raw = (
            b"u UU N... 100644 100644 100644 100644 "
            b"aaaaaaa bbbbbbb ccccccc ddddddd conflict.txt\0"
        )

        changes = parse_status_v2(raw)

        self.assertEqual(changes[0].kind, ChangeKind.CONFLICTED)
        self.assertTrue(changes[0].conflicted)


class ReferenceParserTests(unittest.TestCase):
    def test_parse_branches_keeps_upstream_and_ahead_behind(self) -> None:
        raw = (
            "main\0refs/remotes/origin/main\0"
            "2\0"
            "1\0*\n"
            "feature/login\0\0"
            "0\0"
            "3\0 \n"
        )

        branches = parse_branches(raw)

        self.assertEqual(branches[0].name, "main")
        self.assertEqual(branches[0].upstream, "origin/main")
        self.assertEqual(branches[0].ahead, 2)
        self.assertEqual(branches[0].behind, 1)
        self.assertTrue(branches[0].current)
        self.assertEqual(branches[1].behind, 3)

    def test_parse_log_records(self) -> None:
        raw = (
            "abc123\x1fparent1 parent2\x1fAda\x1fada@example.com\x1f"
            "2026-07-24T10:00:00+08:00\x1fAdd feature\x1fmain, tag: v1\x1e"
        ).encode()

        commits = parse_log_records(raw)

        self.assertEqual(commits[0].oid, "abc123")
        self.assertEqual(commits[0].parents, ("parent1", "parent2"))
        self.assertEqual(commits[0].subject, "Add feature")
        self.assertEqual(commits[0].decorations, ("main", "tag: v1"))

    def test_parse_remote_stash_and_reflog_records(self) -> None:
        remotes = parse_remotes(
            "origin\tfetch\thttps://example.com/repo.git\n"
            "origin\tpush\tssh://git@example.com/repo.git\n"
        )
        stashes = parse_stashes(
            "stash@{0}\x1fabc123\x1f2026-07-24T10:00:00+08:00\x1fWIP\x1e"
        )
        reflog = parse_reflog(
            "HEAD@{0}\x1fabc123\x1f2026-07-24T10:00:00+08:00\x1fcommit: WIP\x1e"
        )

        self.assertEqual(remotes[0].fetch_url, "https://example.com/repo.git")
        self.assertEqual(remotes[0].push_url, "ssh://git@example.com/repo.git")
        self.assertEqual(stashes[0].reference, "stash@{0}")
        self.assertEqual(reflog[0].selector, "HEAD@{0}")


if __name__ == "__main__":
    unittest.main()
