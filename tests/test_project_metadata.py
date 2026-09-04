from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_user_delivery_documents_contract(self) -> None:
        install_guide_path = (
            PROJECT_ROOT / "docs" / "user" / "安装说明.html"
        )
        product_intro_path = (
            PROJECT_ROOT / "docs" / "user" / "产品介绍.html"
        )

        self.assertTrue(install_guide_path.is_file())
        self.assertTrue(product_intro_path.is_file())

        install_guide = install_guide_path.read_text(encoding="utf-8")
        product_intro = product_intro_path.read_text(encoding="utf-8")

        self.assertIn("<title>ClickGit 安装说明</title>", install_guide)
        self.assertIn("Windows 安装版", install_guide)
        self.assertIn("Windows 便携版", install_guide)
        self.assertIn("macOS", install_guide)
        self.assertIn("<title>ClickGit 产品介绍</title>", product_intro)
        self.assertIn("完全点击操作", product_intro)

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
        for release_section in (
            "## SHA-256",
            "## 测试结果",
            "## 签名状态",
            "## 已知问题",
            "## 回滚方式",
        ):
            with self.subTest(release_section=release_section):
                self.assertIn(release_section, release)
        self.assertIn(
            "v0.1.0 发布时的三个 GitHub Release 附件 SHA-256 未保存在",
            release,
        )
        self.assertIn(
            "v0.1.0 发布时的完整测试命令、数量和日志未保存在",
            release,
        )
        self.assertIn("Windows：未代码签名", release)
        self.assertIn("macOS：未签名、未公证", release)
        self.assertIn(
            "仅在重新核验附件存在、架构和 SHA-256 后",
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
        normalized_notice = " ".join(notice.split())
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
                "docs/licenses is established as the project's "
                "license-governance entry point"
            ),
            "must be populated and maintained there before the next release",
            (
                "The directory's presence does not prove that the current "
                "release archives contain all required materials"
            ),
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, normalized_notice)
        self.assertNotIn(
            "docs/licenses must be created",
            normalized_notice,
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

    def test_readme_contains_product_sections(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        required_sections = (
            "## 下载",
            "## 快速开始",
            "## 功能矩阵",
            "## 安全与恢复",
            "## 数据与隐私",
            "## 开发与测试",
            "## 项目结构",
            "## 发布",
            "## 许可证",
        )

        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, readme)

        self.assertIn("windows-v0.1.0", readme)
        self.assertIn("mac-v0.1.0", readme)
        self.assertIn("MIT", readme)
        for download_url in (
            (
                "https://github.com/ljy-codes/clickgit-desktop/releases/"
                "tag/windows-v0.1.0"
            ),
            (
                "https://github.com/ljy-codes/clickgit-desktop/releases/"
                "download/windows-v0.1.0/ClickGit-Windows-x64.zip"
            ),
            (
                "https://github.com/ljy-codes/clickgit-desktop/releases/"
                "tag/mac-v0.1.0"
            ),
            (
                "https://github.com/ljy-codes/clickgit-desktop/releases/"
                "download/mac-v0.1.0/ClickGit-macOS-arm64.zip"
            ),
            (
                "https://github.com/ljy-codes/clickgit-desktop/releases/"
                "download/mac-v0.1.0/ClickGit-macOS-x64.zip"
            ),
        ):
            with self.subTest(download_url=download_url):
                self.assertIn(download_url, readme)

        self.assertIn(
            "使用 Git LFS 功能时还需安装 Git LFS",
            readme,
        )
        self.assertIn(
            "当前发布工作流尚未自动检查第三方许可证材料",
            readme,
        )
        self.assertIn("检查未完成不得发布", readme)
        self.assertIn(
            "目前是待完善的许可证治理入口",
            readme,
        )
        self.assertIn(
            "不代表现有发布包的许可证材料已经齐全",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
