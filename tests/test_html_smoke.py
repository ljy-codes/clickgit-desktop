"""A real renderer in a separate process; no private source or internet."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class HtmlSmokeTests(unittest.TestCase):
    def test_ready_then_failed_is_not_a_successful_smoke(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "failed-smoke.json"
            # Synthetic session only: no WebEngine, files or business repository.
            code = """
import sys
from pathlib import Path
from unittest.mock import patch
from clickgit.ui.preview_session import PreviewSession
from clickgit.html_smoke import write_html_diagnostic
def fail_after_ready(self, pair):
    self.ready_details = dict(previews_loaded=2, javascript_disabled=True,
        profiles_off_record=True, local_access_disabled=True, visible_text_verified=True)
    self.state = 'failed'
    self.failure_reason = 'render_failed'
with patch.object(PreviewSession, 'start', fail_after_ready):
    raise SystemExit(write_html_diagnostic(Path(sys.argv[1])))
"""
            env = dict(os.environ, PYTHONPATH=str(root / "src"), QT_QPA_PLATFORM="offscreen")
            completed = subprocess.run([sys.executable, "-B", "-c", code, str(report)],
                                       env=env, cwd=root, capture_output=True, timeout=20)
            self.assertEqual(completed.returncode, 1)
            payload = json.loads(report.read_text("utf-8"))
            self.assertFalse(payload["success"])
            self.assertEqual(payload["failure_reason"], "render_failed")

    def test_source_cli_loads_restricted_preview_and_checks_policy(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn('"--smoke-html"', (root / "src/clickgit/__main__.py").read_text("utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "html-smoke.json"
            env = dict(os.environ, PYTHONPATH=str(root / "src"), QT_QPA_PLATFORM="offscreen",
                       PYTHONIOENCODING="utf-8")
            result = subprocess.run([sys.executable, "-B", "-m", "clickgit", "--smoke-html", str(report)],
                                    cwd=root, env=env, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace") +
                             (report.read_text("utf-8") if report.exists() else "No smoke report"))
            payload = json.loads(report.read_text("utf-8"))
            self.assertTrue(payload["success"])
            self.assertEqual(payload["previews_loaded"], 2)
            self.assertTrue(payload["javascript_disabled"])
            self.assertTrue(payload["profiles_off_record"])
            self.assertTrue(payload["source_unchanged"])
            self.assertTrue(payload["visible_text_verified"])
            self.assertFalse(payload["interactive_preview_enabled"])
            self.assertTrue(payload["isolated_preview"])
            self.assertFalse(payload["main_process_webengine_loaded"])


if __name__ == "__main__":
    unittest.main()
