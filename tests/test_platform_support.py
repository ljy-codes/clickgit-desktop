from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clickgit.credentials import SshKeyService
from clickgit.git_runner import locate_git
from clickgit.platform_support import (
    application_data_dir,
    preferred_ui_font,
)


class PlatformSupportTests(unittest.TestCase):
    def test_windows_application_data_uses_appdata(self) -> None:
        result = application_data_dir(
            platform_name="win32",
            environ={"APPDATA": r"C:\Users\tester\AppData\Roaming"},
            home=Path(r"C:\Users\tester"),
        )

        self.assertEqual(
            result,
            Path(r"C:\Users\tester\AppData\Roaming") / "ClickGit",
        )

    def test_macos_application_data_uses_application_support(self) -> None:
        result = application_data_dir(
            platform_name="darwin",
            environ={},
            home=Path("/Users/tester"),
        )

        self.assertEqual(
            result,
            Path("/Users/tester/Library/Application Support/ClickGit"),
        )

    def test_platform_font_prefers_native_chinese_font(self) -> None:
        self.assertEqual(preferred_ui_font("win32"), "Microsoft YaHei UI")
        self.assertEqual(preferred_ui_font("darwin"), "PingFang SC")

    def test_locate_git_falls_back_to_path_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            system_git = Path(temp_dir) / "bin" / "git"
            system_git.parent.mkdir(parents=True)
            system_git.touch()

            result = locate_git(
                Path(temp_dir) / "ClickGit.app" / "Contents" / "MacOS",
                path_lookup=lambda _name: str(system_git),
            )

        self.assertEqual(result, system_git)

    def test_ssh_keygen_missing_error_is_platform_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            git_executable = Path(temp_dir) / "bin" / "git"
            git_executable.parent.mkdir(parents=True)
            git_executable.touch()
            with patch("clickgit.credentials.shutil.which", return_value=None):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    "^ssh-keygen was not found$",
                ):
                    SshKeyService.from_git(git_executable)


if __name__ == "__main__":
    unittest.main()
