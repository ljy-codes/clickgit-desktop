import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ApplicationFeatureTests(unittest.TestCase):
    def test_windows_build_does_not_copy_ai_runtime(self):
        script = (ROOT / "scripts/build.ps1").read_text("utf-8-sig")
        self.assertNotIn("local-ai", script)
        self.assertNotIn("verify_local_ai_runtime.py", script)

    def test_both_entry_points_apply_branding(self):
        tree = ast.parse((ROOT / "src/clickgit/__main__.py").read_text("utf-8"))
        for name in ("main", "write_diagnostic"):
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            self.assertTrue(any(isinstance(call.func, ast.Name) and call.func.id == "apply_branding" for call in calls),
                            f"{name} must set Qt icon and Windows identity before creating windows")

    def test_main_window_stops_controller_on_close(self):
        tree = ast.parse((ROOT / "src/clickgit/ui/main_window.py").read_text("utf-8"))
        close = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "closeEvent")
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                            node.func.attr == "shutdown" for node in ast.walk(close)))
        calls = [node.value.func for node in close.body
                 if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
        names = [call.id if isinstance(call, ast.Name) else getattr(call, "attr", "") for call in calls]
        self.assertIn("stop_all_previews", names)
        self.assertLess(names.index("stop_all_previews"), names.index("shutdown"))

    def test_diagnostic_records_current_increment_and_navigation(self):
        source = (ROOT / "src/clickgit/__main__.py").read_text("utf-8")
        self.assertIn('"navigation"', source)
        self.assertIn("2026-09-10-source-inline-highlight", source)
        self.assertIn("source_inline_highlight_verified", source)

    def test_diagnostic_has_no_ai_lifecycle_or_model_imports(self):
        source = (ROOT / "src/clickgit/__main__.py").read_text("utf-8")
        self.assertNotIn("window.ai_panel", source)
        self.assertNotIn("clickgit.ai", source)

    def test_diagnostic_keeps_theme_and_html_checks(self):
        source = (ROOT / "src/clickgit/__main__.py").read_text("utf-8")
        for marker in ('"verified_themes"', '"html_review_available"',
                       '"document_compare_available"', '"reviewed_merge_available"'):
            self.assertIn(marker, source)
