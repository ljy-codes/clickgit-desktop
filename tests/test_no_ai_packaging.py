"""Source-level packaging guards; never build, install or touch user data."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import tomllib
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AI_MARKERS = re.compile(
    r"(?i)(?<![a-z])ai(?![a-z])|local[-_]ai|llama|qwen|gguf"
)


class NoAiPackagingTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def test_windows_build_has_no_ai_runtime_steps(self) -> None:
        script = self.read("scripts/build.ps1")
        self.assertIsNone(AI_MARKERS.search(script))
        self.assertNotIn("$LocalAi", script)

    def test_build_only_copies_git_runtime_and_release_licenses(self) -> None:
        script = self.read("scripts/build.ps1")
        runtime_paths = re.findall(r'"(runtime[^"]*)"', script)
        self.assertEqual(runtime_paths, [r"runtime\git", r"runtime\git"])
        copy_sources = re.findall(r"Copy-Item -LiteralPath (\$\w+)", script)
        self.assertEqual(
            copy_sources,
            ["$GitRuntime", "$LicenseSource", "$NoticesSource", "$LicenseBundleSource"],
        )
        self.assertIn("scripts\\verify_licenses.py", script)
        self.assertIn("Assert-NoReparseTree", script)
        self.assertIn("$ValidatedPackageRoot", script)

    def test_ai_provisioning_scripts_are_removed(self) -> None:
        for name in ("download-local-ai-runtime.py", "verify_local_ai_runtime.py"):
            with self.subTest(script=name):
                self.assertFalse((PROJECT_ROOT / "scripts" / name).exists())

    def test_spec_collects_only_brand_data_and_keeps_html_dependencies(self) -> None:
        source = self.read("installer/clickgit.spec")
        self.assertIsNone(AI_MARKERS.search(source))
        tree = ast.parse(source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Analysis"
        ]
        self.assertEqual(len(calls), 1)
        keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
        expected_data = ast.parse(
            '[(str(brand_resources / name), "clickgit/resources") '
            'for name in brand_names]', mode="eval",
        ).body
        self.assertEqual(ast.dump(keywords["datas"]), ast.dump(expected_data))
        self.assertEqual(ast.literal_eval(keywords["binaries"]), [])
        self.assertIn('brand_names = ["clickgit.ico"]', source)
        self.assertIn('brand_resources = project_root / "src" / "clickgit" / "resources"', source)
        self.assertNotIn("rglob", source)
        expected_imports = ast.parse('collect_submodules("clickgit")', mode="eval").body
        self.assertEqual(ast.dump(keywords["hiddenimports"]), ast.dump(expected_imports))
        excludes = ast.literal_eval(keywords["excludes"])
        for module in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"):
            with self.subTest(module=module):
                self.assertNotIn(module, excludes)

    def test_notices_cover_shipped_git_and_html_without_ai_inventory(self) -> None:
        notices = self.read("THIRD-PARTY-NOTICES.txt")
        self.assertIsNone(AI_MARKERS.search(notices))
        for component in (
            "Python 3.14", "Git for Windows", "Git Credential Manager",
            "Qt WebEngine Core/Widgets", "QtWebEngineProcess", "Chromium",
            "ICU", "LICENSE-MANIFEST.json",
        ):
            with self.subTest(component=component):
                self.assertIn(component, notices)

    def test_current_user_docs_do_not_advertise_removed_ai(self) -> None:
        paths = [PROJECT_ROOT / "README.md"]
        paths.extend(
            path for path in (PROJECT_ROOT / "docs" / "user").iterdir()
            if path.is_file() and path.suffix.lower() in {".md", ".html"}
        )
        for path in paths:
            with self.subTest(document=path.name):
                self.assertIsNone(AI_MARKERS.search(path.read_text(encoding="utf-8")))

    def test_theme_guide_is_renamed_and_keeps_all_theme_options(self) -> None:
        user_docs = PROJECT_ROOT / "docs" / "user"
        self.assertFalse((user_docs / "AI三种接入与本地模型.md").exists())
        self.assertFalse((user_docs / "三主题与AI使用说明.md").exists())
        guide = user_docs / "三主题使用说明.md"
        self.assertTrue(guide.is_file())
        content = guide.read_text(encoding="utf-8")
        for option in ("明亮白色", "经典深色", "极光科技", "跟随系统", "12 / 14 / 16 / 18", "未保存"):
            with self.subTest(option=option):
                self.assertIn(option, content)

    def test_release_version_remains_020(self) -> None:
        project = tomllib.loads(self.read("pyproject.toml"))
        self.assertEqual(project["project"]["version"], "0.2.0")
        self.assertIn('#define AppVersion "0.2.0"', self.read("installer/ClickGit.iss"))


if __name__ == "__main__":
    unittest.main()
