from __future__ import annotations

import tomllib
import unittest
from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class VisibleHTMLParser(HTMLParser):
    _HIDDEN_TAGS = {"head", "script", "style", "template", "noscript"}
    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._frames: list[tuple[str, bool, int | None]] = []
        self._text_parts: list[str] = []
        self._heading_parts: list[list[str]] = []

    @property
    def visible_text(self) -> str:
        return " ".join("".join(self._text_parts).split())

    @property
    def visible_headings(self) -> list[str]:
        return [
            " ".join("".join(parts).split())
            for parts in self._heading_parts
        ]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        attributes = {
            name.casefold(): value
            for name, value in attrs
        }
        parent_hidden = bool(self._frames and self._frames[-1][1])
        style = (attributes.get("style") or "").replace(" ", "").casefold()
        hidden = (
            parent_hidden
            or normalized_tag in self._HIDDEN_TAGS
            or "hidden" in attributes
            or (attributes.get("aria-hidden") or "").casefold() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        parent_heading = self._frames[-1][2] if self._frames else None
        heading_index = parent_heading
        if normalized_tag in self._HEADING_TAGS and not hidden:
            self._heading_parts.append([])
            heading_index = len(self._heading_parts) - 1
        if normalized_tag not in self._VOID_TAGS:
            self._frames.append((normalized_tag, hidden, heading_index))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        for index in range(len(self._frames) - 1, -1, -1):
            if self._frames[index][0] == normalized_tag:
                del self._frames[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._frames and self._frames[-1][1]:
            return
        if not data.strip():
            return
        self._text_parts.append(data)
        if self._frames and self._frames[-1][2] is not None:
            heading_index = self._frames[-1][2]
            self._heading_parts[heading_index].append(data)


class PreviewStructureParser(HTMLParser):
    _INTERACTIVE_TAGS = {
        "a",
        "button",
        "input",
        "select",
        "textarea",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._frames: list[tuple[str, bool]] = []
        self.preview_attributes: list[dict[str, str | None]] = []
        self.interactive_tags: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        attributes = {
            name.casefold(): value
            for name, value in attrs
        }
        classes = set((attributes.get("class") or "").split())
        parent_is_preview = bool(
            self._frames and self._frames[-1][1]
        )
        starts_preview = "preview-shell" in classes
        is_preview = parent_is_preview or starts_preview
        if starts_preview:
            self.preview_attributes.append(attributes)
        if is_preview and normalized_tag in self._INTERACTIVE_TAGS:
            self.interactive_tags.append(normalized_tag)
        if normalized_tag not in VisibleHTMLParser._VOID_TAGS:
            self._frames.append((normalized_tag, is_preview))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        for index in range(len(self._frames) - 1, -1, -1):
            if self._frames[index][0] == normalized_tag:
                del self._frames[index:]
                break


def _parse_visible_html(path: Path) -> VisibleHTMLParser:
    parser = VisibleHTMLParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


class ProjectMetadataTests(unittest.TestCase):
    def test_visible_html_parser_ignores_non_visible_content(self) -> None:
        parser = VisibleHTMLParser()
        parser.feed(
            """
            <html>
              <head><title>隐藏标题</title></head>
              <body>
                <!-- 完全点击操作 -->
                <script>Windows 安装版</script>
                <style>.hidden { display: none; }</style>
                <h2 hidden>Windows 便携版</h2>
                <h2 aria-hidden="true">macOS</h2>
                <h2 style="display: none">首次使用</h2>
                <h2>卸载与<span>数据</span></h2>
                <p>ClickGit <strong>完全点击操作</strong></p>
              </body>
            </html>
            """
        )
        parser.close()

        self.assertEqual(parser.visible_headings, ["卸载与数据"])
        self.assertNotIn("Windows 安装版", parser.visible_text)
        self.assertNotIn("Windows 便携版", parser.visible_text)
        self.assertNotIn("macOS", parser.visible_text)
        self.assertNotIn("首次使用", parser.visible_text)
        self.assertIn("ClickGit", parser.visible_text)
        self.assertIn("完全点击操作", parser.visible_text)

    def test_user_delivery_documents_contract(self) -> None:
        install_guide_path = (
            PROJECT_ROOT / "docs" / "user" / "安装说明.html"
        )
        product_intro_path = (
            PROJECT_ROOT / "docs" / "user" / "产品介绍.html"
        )

        self.assertTrue(install_guide_path.is_file())
        self.assertTrue(product_intro_path.is_file())

        install_guide = _parse_visible_html(install_guide_path)
        product_intro = _parse_visible_html(product_intro_path)
        preview_structure = PreviewStructureParser()
        preview_structure.feed(
            product_intro_path.read_text(encoding="utf-8")
        )
        preview_structure.close()

        for section in (
            "Windows 安装版",
            "Windows 便携版",
            "macOS",
            "首次使用",
            "卸载与数据",
            "常见问题",
        ):
            with self.subTest(document="安装说明", section=section):
                self.assertIn(section, install_guide.visible_headings)
        for required_text in (
            "SmartScreen",
            "未知发布者",
            "完整解压",
            "Gatekeeper",
            "Git LFS",
            "额外安装",
        ):
            with self.subTest(
                document="安装说明",
                required_text=required_text,
            ):
                self.assertIn(required_text, install_guide.visible_text)
        self.assertIn("ClickGit", product_intro.visible_headings)
        self.assertIn("界面预览", product_intro.visible_headings)
        self.assertIn("完全点击操作", product_intro.visible_text)
        for required_text in (
            "仓库 / 分支侧栏",
            "文件变更列表",
            "提交与同步操作区",
        ):
            with self.subTest(
                document="产品介绍",
                required_text=required_text,
            ):
                self.assertIn(required_text, product_intro.visible_text)
        for forbidden_text in ("占位图", "待补充"):
            with self.subTest(
                document="产品介绍",
                forbidden_text=forbidden_text,
            ):
                self.assertNotIn(
                    forbidden_text,
                    product_intro.visible_text,
                )
        self.assertEqual(len(preview_structure.preview_attributes), 1)
        preview_attributes = preview_structure.preview_attributes[0]
        self.assertEqual(preview_attributes.get("role"), "img")
        self.assertEqual(
            preview_attributes.get("aria-label"),
            "ClickGit 三栏工作台界面预览",
        )
        self.assertEqual(preview_structure.interactive_tags, [])

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
        for delivery_change in (
            "_internal",
            "ClickGit-Windows-x64-Setup.exe",
            "ClickGit-Windows-x64-Portable.zip",
            "干净交付目录",
            "SHA-256",
        ):
            with self.subTest(delivery_change=delivery_change):
                self.assertIn(delivery_change, changelog)

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
            "### 当前稳定版 v0.1.0",
            "### 下一版本交付格式与本地构建产物",
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
                "tag/mac-v0.1.0"
            ),
            (
                "https://github.com/ljy-codes/clickgit-desktop/releases/"
                "download/windows-v0.1.0/ClickGit-Windows-x64.zip"
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

        current_release = readme.split(
            "### 当前稳定版 v0.1.0",
            maxsplit=1,
        )[1].split(
            "### 下一版本交付格式与本地构建产物",
            maxsplit=1,
        )[0]
        next_release_format = readme.split(
            "### 下一版本交付格式与本地构建产物",
            maxsplit=1,
        )[1].split("## 快速开始", maxsplit=1)[0]
        windows_quick_start = readme.split(
            "### Windows",
            maxsplit=1,
        )[1].split("### macOS", maxsplit=1)[0]

        current_windows_url = (
            "https://github.com/ljy-codes/clickgit-desktop/releases/"
            "download/windows-v0.1.0/ClickGit-Windows-x64.zip"
        )
        self.assertIn(current_windows_url, current_release)
        self.assertIn("ClickGit-Windows-x64.zip", current_release)
        self.assertIn("历史便携包", current_release)
        self.assertNotIn(
            "ClickGit-Windows-x64-Setup.exe",
            current_release,
        )
        self.assertNotIn(
            "ClickGit-Windows-x64-Portable.zip",
            current_release,
        )

        self.assertIn(
            "ClickGit-Windows-x64-Setup.exe",
            next_release_format,
        )
        self.assertIn(
            "ClickGit-Windows-x64-Portable.zip",
            next_release_format,
        )
        self.assertIn("本地构建产物", next_release_format)
        self.assertIn("尚未作为当前稳定版附件发布", next_release_format)

        self.assertIn(current_windows_url, windows_quick_start)
        self.assertIn("ClickGit-Windows-x64.zip", windows_quick_start)
        self.assertIn("新版本发布后", windows_quick_start)
        self.assertIn("优先安装版", windows_quick_start)

        for required_text in (
            "ClickGit-Windows-x64-Setup.exe",
            "ClickGit-Windows-x64-Portable.zip",
            r"scripts\package.ps1",
            r"scripts\publish.ps1",
            "安装版优先",
            "便携版备用",
            "macOS Apple Silicon",
            "macOS Intel",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, readme)
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
