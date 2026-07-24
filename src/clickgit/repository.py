from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from clickgit.git_runner import GitCommandError, GitRunner, redact_git_result
from clickgit.models import (
    Branch,
    Commit,
    FileChange,
    GitResult,
    Remote,
    StashEntry,
)
from clickgit.parsers import (
    parse_log_records,
    parse_stashes,
    parse_status_v2,
)


class RepositoryError(RuntimeError):
    pass


class InvalidRepositoryError(RepositoryError):
    pass


class UnsafeRepositoryPathError(RepositoryError):
    pass


class InvalidGitNameError(RepositoryError, ValueError):
    pass


class OperationConflict(RepositoryError):
    def __init__(self, operation: str, result: GitResult) -> None:
        super().__init__(f"{operation} produced conflicts")
        self.operation = operation
        self.result = redact_git_result(result)


class Repository:
    def __init__(self, path: Path, runner: GitRunner | None = None) -> None:
        self.runner = runner or GitRunner()
        requested_path = Path(path).resolve()
        probe = self.runner.run(
            ["rev-parse", "--is-bare-repository"],
            cwd=requested_path,
        )
        if probe.returncode != 0:
            raise InvalidRepositoryError(probe.stderr_text.strip())
        self.is_bare = probe.stdout_text.strip() == "true"
        root_argument = (
            "--absolute-git-dir" if self.is_bare else "--show-toplevel"
        )
        root_result = self.runner.run(
            ["rev-parse", root_argument],
            cwd=requested_path,
        )
        if root_result.returncode != 0:
            raise InvalidRepositoryError(root_result.stderr_text.strip())
        self.path = Path(root_result.stdout_text.strip()).resolve()

    @classmethod
    def init(
        cls,
        path: Path,
        runner: GitRunner | None = None,
        *,
        bare: bool = False,
    ) -> Repository:
        runner = runner or GitRunner()
        destination = Path(path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        args = ["init", "-b", "main"]
        if bare:
            args.append("--bare")
        args.append(str(destination))
        result = runner.run(args)
        if result.returncode != 0:
            raise GitCommandError(result)
        return cls(destination, runner)

    @classmethod
    def clone(
        cls,
        url: str,
        destination: Path,
        runner: GitRunner | None = None,
    ) -> Repository:
        runner = runner or GitRunner()
        destination = Path(destination).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = runner.run(["clone", "--", url, str(destination)])
        if result.returncode != 0:
            raise GitCommandError(result)
        return cls(destination, runner)

    def configure_identity(self, name: str, email: str) -> None:
        self._run(["config", "user.name", name])
        self._run(["config", "user.email", email])

    def status(self) -> list[FileChange]:
        if self.is_bare:
            return []
        result = self._run_bytes(
            ["status", "--porcelain=v2", "-z", "--untracked-files=all"]
        )
        return parse_status_v2(result.stdout)

    def current_branch(self) -> str:
        result = self.runner.run(
            ["symbolic-ref", "--quiet", "--short", "HEAD"],
            cwd=self.path,
        )
        if result.returncode == 0:
            return result.stdout_text.strip()
        head_result = self.runner.run(
            ["rev-parse", "--verify", "HEAD"],
            cwd=self.path,
        )
        if head_result.returncode != 0:
            raise GitCommandError(head_result)
        return "(detached HEAD)"

    def head_oid(self) -> str:
        return self.rev_parse("HEAD")

    def rev_parse(self, revision: str) -> str:
        revision = self._validated_revision(revision)
        return self._run(
            ["rev-parse", "--verify", "--end-of-options", revision]
        ).stdout_text.strip()

    def diff(self, path: str | None = None, *, staged: bool = False) -> str:
        args = ["diff", "--no-ext-diff", "--no-color"]
        if staged:
            args.append("--cached")
        if path is not None:
            args.extend(["--", self._validated_path(path)])
        return self._run(args).stdout_text

    def stage(self, paths: Iterable[str]) -> None:
        safe_paths = self._validated_paths(paths)
        if safe_paths:
            self._run(["add", "--", *safe_paths])

    def unstage(self, paths: Iterable[str]) -> None:
        safe_paths = self._validated_paths(paths)
        if not safe_paths:
            return
        result = self.runner.run(
            ["restore", "--staged", "--", *safe_paths],
            cwd=self.path,
        )
        if result.returncode != 0:
            self._run(["reset", "--", *safe_paths])

    def restore(self, paths: Iterable[str]) -> None:
        safe_paths = self._validated_paths(paths)
        if safe_paths:
            self._run(["restore", "--worktree", "--", *safe_paths])

    def commit(self, message: str, *, amend: bool = False) -> Commit:
        if not message.strip():
            raise ValueError("Commit message must not be empty")
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")
        self._run(args)
        commits = self.history(limit=1)
        if not commits:
            raise RepositoryError("Created commit could not be read")
        return commits[0]

    def commit_all(self, message: str) -> Commit:
        self._run(["add", "--all"])
        return self.commit(message)

    def fetch(self, remote: str | None = None) -> None:
        args = ["fetch", "--prune"]
        if remote:
            args.append(remote)
        self._run(args)

    def pull(
        self,
        remote: str | None = None,
        branch: str | None = None,
        *,
        rebase: bool | None = None,
    ) -> None:
        if branch is not None and remote is None:
            raise ValueError("A remote is required when a branch is specified")
        args = ["pull"]
        if rebase is not None:
            args.append("--rebase" if rebase else "--no-rebase")
        if remote:
            args.append(self._validated_remote_name(remote))
        if branch:
            args.append(self._validated_revision(branch))
        result = self.runner.run(args, cwd=self.path)
        self._raise_for_write_result("pull", result)

    def push(
        self,
        remote: str | None = None,
        branch: str | None = None,
        *,
        set_upstream: bool = False,
        force_with_lease: bool = False,
    ) -> None:
        args = ["push"]
        if force_with_lease:
            args.append("--force-with-lease")
        if set_upstream:
            args.append("--set-upstream")
            remote = remote or "origin"
            branch = branch or "HEAD"
        if branch is not None and remote is None:
            raise ValueError("A remote is required when a branch is specified")
        if remote is not None:
            args.append(self._validated_remote_name(remote))
        if branch is not None:
            args.append(self._validated_revision(branch))
        self._run(args)

    def branches(self) -> list[Branch]:
        result = self._run(
            [
                "for-each-ref",
                "--format=%(refname:short)%00%(upstream:short)%00%(HEAD)",
                "refs/heads",
            ]
        )
        branches: list[Branch] = []
        for line in result.stdout_text.splitlines():
            fields = line.split("\0")
            if len(fields) < 3:
                continue
            name, upstream, marker = fields[:3]
            ahead = 0
            behind = 0
            if upstream:
                counts = self.runner.run(
                    [
                        "rev-list",
                        "--left-right",
                        "--count",
                        f"{name}...{upstream}",
                    ],
                    cwd=self.path,
                )
                if counts.returncode == 0:
                    values = counts.stdout_text.strip().split()
                    if len(values) == 2:
                        ahead, behind = int(values[0]), int(values[1])
            branches.append(
                Branch(
                    name=name,
                    upstream=upstream or None,
                    ahead=ahead,
                    behind=behind,
                    current=marker.strip() == "*",
                )
            )
        return branches

    def create_branch(
        self,
        name: str,
        start_point: str | None = None,
    ) -> None:
        args = ["branch", self._validated_branch_name(name)]
        if start_point:
            args.append(self._validated_revision(start_point))
        self._run(args)

    def checkout(self, name: str) -> None:
        self._run(["switch", self._validated_branch_name(name)])

    def rename_branch(self, old: str, new: str) -> None:
        self._run(
            [
                "branch",
                "-m",
                self._validated_branch_name(old),
                self._validated_branch_name(new),
            ]
        )

    def delete_branch(self, name: str, *, force: bool = False) -> None:
        self._run(
            [
                "branch",
                "-D" if force else "-d",
                self._validated_branch_name(name),
            ]
        )

    def merge(self, name: str) -> None:
        result = self.runner.run(
            ["merge", "--no-edit", self._validated_revision(name)],
            cwd=self.path,
        )
        self._raise_for_write_result("merge", result)

    def rebase(self, name: str) -> None:
        result = self.runner.run(
            ["rebase", self._validated_revision(name)],
            cwd=self.path,
        )
        self._raise_for_write_result("rebase", result)

    def cherry_pick(self, oid: str) -> None:
        result = self.runner.run(
            ["cherry-pick", self._validated_revision(oid)],
            cwd=self.path,
        )
        self._raise_for_write_result("cherry-pick", result)

    def revert(self, oid: str) -> None:
        result = self.runner.run(
            ["revert", "--no-edit", self._validated_revision(oid)],
            cwd=self.path,
        )
        self._raise_for_write_result("revert", result)

    def continue_merge(self) -> None:
        self._run(["commit", "--no-edit"])

    def abort_merge(self) -> None:
        self._run(["merge", "--abort"])

    def continue_rebase(self) -> None:
        self._run(["-c", "core.editor=true", "rebase", "--continue"])

    def abort_rebase(self) -> None:
        self._run(["rebase", "--abort"])

    def conflicted_files(self) -> list[FileChange]:
        return [item for item in self.status() if item.conflicted]

    def history(
        self,
        *,
        limit: int = 200,
        skip: int = 0,
        query: str | None = None,
    ) -> list[Commit]:
        format_string = (
            "%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%D%x1e"
        )
        args = [
            "log",
            f"--max-count={max(1, limit)}",
            f"--skip={max(0, skip)}",
            f"--format={format_string}",
        ]
        if query:
            args.extend(["--regexp-ignore-case", f"--grep={query}"])
        result = self.runner.run(args, cwd=self.path)
        if result.returncode != 0:
            if "does not have any commits" in result.stderr_text:
                return []
            raise GitCommandError(result)
        return parse_log_records(result.stdout)

    def tags(self) -> list[str]:
        result = self._run(["tag", "--list", "--sort=-creatordate"])
        return [line for line in result.stdout_text.splitlines() if line]

    def create_tag(
        self,
        name: str,
        target: str | None = None,
        message: str | None = None,
    ) -> None:
        args = ["tag"]
        tag_name = self._validated_tag_name(name)
        if message:
            args.extend(["-a", tag_name, "-m", message])
        else:
            args.append(tag_name)
        if target:
            args.append(self._validated_revision(target))
        self._run(args)

    def delete_tag(self, name: str) -> None:
        self._run(["tag", "-d", self._validated_tag_name(name)])

    def stashes(self) -> list[StashEntry]:
        result = self._run(
            [
                "stash",
                "list",
                "--format=%gd%x1f%H%x1f%cI%x1f%gs%x1e",
            ]
        )
        entries = parse_stashes(result.stdout_text)
        normalized: list[StashEntry] = []
        for entry in entries:
            subject = entry.subject
            if subject.startswith("On ") and ": " in subject:
                subject = subject.split(": ", 1)[1]
            normalized.append(
                StashEntry(
                    reference=entry.reference,
                    oid=entry.oid,
                    created_at=entry.created_at,
                    subject=subject,
                )
            )
        return normalized

    def stash_create(
        self,
        message: str,
        *,
        include_untracked: bool = True,
    ) -> None:
        args = ["stash", "push"]
        if include_untracked:
            args.append("--include-untracked")
        if message:
            args.extend(["-m", message])
        self._run(args)

    def stash_apply(self, reference: str, *, pop: bool = False) -> None:
        result = self.runner.run(
            [
                "stash",
                "pop" if pop else "apply",
                self._validated_stash_reference(reference),
            ],
            cwd=self.path,
        )
        self._raise_for_write_result("stash-pop" if pop else "stash-apply", result)

    def stash_drop(self, reference: str) -> None:
        self._run(
            ["stash", "drop", self._validated_stash_reference(reference)]
        )

    def remotes(self) -> list[Remote]:
        names = [
            line
            for line in self._run(["remote"]).stdout_text.splitlines()
            if line
        ]
        remotes: list[Remote] = []
        for name in names:
            fetch_result = self._run(["remote", "get-url", name])
            push_result = self.runner.run(
                ["remote", "get-url", "--push", name],
                cwd=self.path,
            )
            fetch_url = fetch_result.stdout_text.rstrip("\r\n")
            push_url = (
                push_result.stdout_text.rstrip("\r\n")
                if push_result.returncode == 0
                else fetch_url
            )
            remotes.append(
                Remote(
                    name=name,
                    fetch_url=fetch_url,
                    push_url=push_url,
                )
            )
        return remotes

    def add_remote(self, name: str, url: str) -> None:
        self._run(
            [
                "remote",
                "add",
                self._validated_remote_name(name),
                self._validated_url(url),
            ]
        )

    def set_remote_url(self, name: str, url: str) -> None:
        self._run(
            [
                "remote",
                "set-url",
                self._validated_remote_name(name),
                self._validated_url(url),
            ]
        )

    def remove_remote(self, name: str) -> None:
        self._run(["remote", "remove", self._validated_remote_name(name)])

    def _raise_for_write_result(
        self,
        operation: str,
        result: GitResult,
    ) -> None:
        if result.returncode == 0:
            return
        if self.conflicted_files():
            raise OperationConflict(operation, result)
        raise GitCommandError(result)

    def _run(self, args: Sequence[str]) -> GitResult:
        result = self.runner.run(args, cwd=self.path)
        if result.returncode != 0:
            raise GitCommandError(result)
        return result

    def _run_bytes(self, args: Sequence[str]) -> GitResult:
        return self._run(args)

    def _validated_paths(self, paths: Iterable[str]) -> list[str]:
        return [self._validated_path(path) for path in paths]

    def _validated_path(self, path: str) -> str:
        candidate = Path(path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.path / candidate).resolve()
        try:
            relative = resolved.relative_to(self.path)
        except ValueError as exc:
            raise UnsafeRepositoryPathError(
                f"Path is outside repository: {path}"
            ) from exc
        return f":(literal){relative.as_posix()}"

    def _validated_branch_name(self, name: str) -> str:
        self._reject_option_or_control(name, "branch")
        result = self.runner.run(
            ["check-ref-format", "--branch", name],
            cwd=self.path,
        )
        if result.returncode != 0:
            raise InvalidGitNameError(f"Invalid branch name: {name}")
        return name

    def _validated_tag_name(self, name: str) -> str:
        self._reject_option_or_control(name, "tag")
        result = self.runner.run(
            ["check-ref-format", f"refs/tags/{name}"],
            cwd=self.path,
        )
        if result.returncode != 0:
            raise InvalidGitNameError(f"Invalid tag name: {name}")
        return name

    @staticmethod
    def _validated_remote_name(name: str) -> str:
        Repository._reject_option_or_control(name, "remote")
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", name)
            or ".." in name
            or "@{" in name
            or "//" in name
            or name.endswith(("/", "."))
        ):
            raise InvalidGitNameError(f"Invalid remote name: {name}")
        return name

    @staticmethod
    def _validated_revision(revision: str) -> str:
        Repository._reject_option_or_control(revision, "revision")
        return revision

    @staticmethod
    def _validated_stash_reference(reference: str) -> str:
        if not re.fullmatch(r"stash@\{\d+\}", reference):
            raise InvalidGitNameError(
                f"Invalid stash reference: {reference}"
            )
        return reference

    @staticmethod
    def _validated_url(url: str) -> str:
        Repository._reject_option_or_control(url, "remote URL")
        return url

    @staticmethod
    def _reject_option_or_control(value: str, label: str) -> None:
        if (
            not value
            or value.startswith("-")
            or any(character in value for character in ("\0", "\r", "\n"))
        ):
            raise InvalidGitNameError(f"Invalid {label}: {value!r}")
