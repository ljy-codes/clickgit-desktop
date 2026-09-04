from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_project_uses_mit_license_and_repository_urls(self) -> None:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
            pyproject = tomllib.load(pyproject_file)

        project = pyproject["project"]
        with self.subTest(metadata="build-system"):
            self.assertIn(
                "setuptools>=77",
                pyproject["build-system"]["requires"],
            )
        with self.subTest(metadata="license-files"):
            self.assertEqual(project.get("license-files"), ["LICENSE"])
        self.assertEqual(project["license"], "MIT")
        self.assertEqual(project["authors"], [{"name": "ljy-codes"}])
        self.assertCountEqual(
            project["keywords"],
            ["git", "desktop", "gui", "pyside6"],
        )
        self.assertEqual(
            project["urls"]["Repository"],
            "https://github.com/ljy-codes/clickgit-desktop",
        )
        self.assertEqual(
            project["urls"]["Issues"],
            "https://github.com/ljy-codes/clickgit-desktop/issues",
        )

        license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 ljy-codes", license_text)

    def test_change_log_and_release_record_describe_v010(self) -> None:
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(
            encoding="utf-8"
        )
        release = (
            PROJECT_ROOT / "docs" / "releases" / "2026-07-28-v0.1.0.md"
        ).read_text(encoding="utf-8")

        self.assertIn("## [Unreleased]", changelog)
        self.assertIn("### Changed", changelog)
        self.assertIn(
            "将工程治理、产品文档和交付清单纳入发布门禁",
            changelog,
        )
        self.assertIn("## [0.1.0] - 2026-07-28", changelog)
        self.assertIn(
            (
                "https://github.com/ljy-codes/clickgit-desktop/"
                "compare/windows-v0.1.0...HEAD"
            ),
            changelog,
        )
        self.assertIn("windows-v0.1.0", release)
        self.assertIn("mac-v0.1.0", release)
        self.assertIn("ClickGit-Windows-x64.zip", release)
        self.assertIn("ClickGit-macOS-arm64.zip", release)
        self.assertIn("ClickGit-macOS-x64.zip", release)
        for feature in (
            "Worktree",
            "子模块",
            "Git LFS",
            "未跟踪文件隔离",
            "敏感信息脱敏",
        ):
            with self.subTest(document="changelog", feature=feature):
                self.assertIn(feature, changelog)
        for feature in (
            "Worktree",
            "子模块",
            "Git LFS",
            "仓库维护",
        ):
            with self.subTest(document="release", feature=feature):
                self.assertIn(feature, release)
        self.assertIn(
            "大型仓库的历史记录默认最多加载 200 条",
            release,
        )

    def test_third_party_notice_lists_distributed_components(self) -> None:
        notice = (PROJECT_ROOT / "THIRD-PARTY-NOTICES.txt").read_text(
            encoding="utf-8"
        )

        for component in (
            "Python",
            "PySide6",
            "Qt 6.10.3",
            "PySide6_Essentials 6.10.3",
            "PySide6_Addons 6.10.3",
            "Shiboken6",
            "PyInstaller",
            "Git for Windows",
            "Git Credential Manager",
            "runtime/git/mingw64/doc/git-credential-manager/LICENSE",
            "runtime/git/mingw64/doc/git-credential-manager/NOTICE",
        ):
            with self.subTest(component=component):
                self.assertIn(component, notice)
        self.assertNotIn(
            "Copyright (c) Microsoft Corporation and contributors.",
            notice,
        )
        for requirement in (
            "ClickGit does not declare that it holds a commercial Qt license.",
            (
                "Open-source distribution must retain the applicable LGPL "
                "or GPL license texts"
            ),
            (
                "This baseline does not prove that the required Qt and "
                "PySide6 license materials"
            ),
            "the release must be blocked",
            (
                "docs/licenses must be created and maintained before the "
                "next release"
            ),
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, notice)
        self.assertNotIn(
            "The maintained license inventory is stored under docs/licenses",
            notice,
        )

    def test_documentation_directories_are_tracked(self) -> None:
        expected_files = (
            "docs/images/README.md",
            "docs/development/README.md",
            "docs/releases/README.md",
            "docs/licenses/README.md",
        )

        for relative_path in expected_files:
            with self.subTest(path=relative_path):
                path = PROJECT_ROOT / relative_path
                self.assertTrue(path.is_file())
                self.assertGreater(len(path.read_text(encoding="utf-8")), 80)


if __name__ == "__main__":
    unittest.main()
