from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from clickgit.models import GitResult


class GitRunnerError(RuntimeError):
    pass


class GitCommandError(GitRunnerError):
    def __init__(self, result: GitResult) -> None:
        safe_result = redact_git_result(result)
        message = (
            safe_result.stderr_text.strip()
            or safe_result.stdout_text.strip()
        )
        super().__init__(message or "Git command failed")
        self.result = safe_result


class GitTimeoutError(GitRunnerError):
    def __init__(self, command: tuple[str, ...], timeout: float) -> None:
        super().__init__(f"Git operation timed out after {timeout:g} seconds")
        self.command = command
        self.timeout = timeout


def locate_git(application_root: Path | None = None) -> Path:
    configured = os.environ.get("CLICKGIT_GIT")
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate

    if application_root is not None:
        bundled = application_root / "runtime" / "git" / "cmd" / "git.exe"
        if bundled.is_file():
            return bundled

    discovered = shutil.which("git")
    if discovered:
        return Path(discovered)
    raise FileNotFoundError("Git executable was not found")


class GitRunner:
    def __init__(self, git_executable: Path | None = None) -> None:
        self.git_executable = Path(git_executable or locate_git())

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        input_bytes: bytes | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> GitResult:
        command = (str(self.git_executable), *(str(arg) for arg in args))
        process_env = os.environ.copy()
        process_env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C.UTF-8",
                "LANG": "C.UTF-8",
            }
        )
        if env:
            process_env.update({str(key): str(value) for key, value in env.items()})

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd) if cwd is not None else None,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=process_env,
                timeout=timeout,
                shell=False,
                check=False,
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitTimeoutError(command, timeout or 0) from exc

        return GitResult(
            command=command,
            cwd=Path(cwd) if cwd is not None else None,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.monotonic() - started,
        )


_URL_CREDENTIALS = re.compile(r"(://[^:/\s]+:)([^@\s]+)(@)")
_ASSIGNMENT_SECRET = re.compile(
    r"(?i)\b(token|password|passwd|secret|access_token)=([^\s&]+)"
)
_AUTHORIZATION = re.compile(
    r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)([^\s]+)"
)


def redact_secrets(text: str) -> str:
    redacted = _URL_CREDENTIALS.sub(r"\1***\3", text)
    redacted = _ASSIGNMENT_SECRET.sub(r"\1=***", redacted)
    return _AUTHORIZATION.sub(r"\1***", redacted)


def redact_git_result(result: GitResult) -> GitResult:
    return GitResult(
        command=tuple(redact_secrets(argument) for argument in result.command),
        cwd=result.cwd,
        returncode=result.returncode,
        stdout=redact_secrets(result.stdout_text).encode("utf-8"),
        stderr=redact_secrets(result.stderr_text).encode("utf-8"),
        duration_seconds=result.duration_seconds,
    )
