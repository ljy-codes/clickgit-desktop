from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from clickgit.git_runner import (
    GitCommandError,
    GitRunner,
    GitTimeoutError,
    redact_secrets,
)
from clickgit.models import GitResult


class GitRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cwd = Path(self.temp_dir.name)
        self.runner = GitRunner(git_executable=Path(sys.executable))

    def test_runner_passes_arguments_without_shell(self) -> None:
        result = self.runner.run(
            [
                "-c",
                "import sys;sys.stdout.buffer.write(sys.argv[1].encode())",
                "中文 path & echo unsafe",
            ],
            cwd=self.cwd,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout_text, "中文 path & echo unsafe")
        self.assertEqual(
            result.command[-1],
            "中文 path & echo unsafe",
        )

    def test_runner_passes_binary_stdin_and_captures_stderr(self) -> None:
        result = self.runner.run(
            [
                "-c",
                (
                    "import sys;"
                    "data=sys.stdin.buffer.read();"
                    "sys.stdout.buffer.write(data.upper());"
                    "sys.stderr.write('warning')"
                ),
            ],
            cwd=self.cwd,
            input_bytes=b"abc",
        )

        self.assertEqual(result.stdout, b"ABC")
        self.assertEqual(result.stderr_text, "warning")

    def test_runner_raises_typed_timeout(self) -> None:
        with self.assertRaises(GitTimeoutError):
            self.runner.run(
                ["-c", "import time; time.sleep(1)"],
                cwd=self.cwd,
                timeout=0.01,
            )

    def test_redacts_urls_tokens_passwords_and_authorization_headers(self) -> None:
        text = (
            "https://user:secret@example.com/repo.git "
            "token=abc123 password=hunter2 "
            "Authorization: Bearer bearer-secret"
        )

        redacted = redact_secrets(text)

        for secret in ("secret", "abc123", "hunter2", "bearer-secret"):
            self.assertNotIn(secret, redacted)
        self.assertIn("***", redacted)

    def test_command_error_does_not_expose_raw_secrets_in_result(self) -> None:
        result = GitResult(
            command=(
                "git",
                "clone",
                "https://user:secret@example.com/repo.git",
            ),
            cwd=self.cwd,
            returncode=1,
            stdout=b"token=abc123",
            stderr=b"Authorization: Bearer bearer-secret",
            duration_seconds=0.1,
        )

        error = GitCommandError(result)
        exposed = " ".join(error.result.command)
        exposed += error.result.stdout_text
        exposed += error.result.stderr_text

        for secret in ("secret", "abc123", "bearer-secret"):
            self.assertNotIn(secret, exposed)


if __name__ == "__main__":
    unittest.main()
