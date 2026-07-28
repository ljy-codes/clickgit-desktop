from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = PROJECT_ROOT / "scripts" / "verify_macos_report.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_macos_report",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the macOS report verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MacOSReportVerifierTests(unittest.TestCase):
    def test_accepts_successful_report(self) -> None:
        verifier = load_verifier()

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "git_returncode": 0,
                        "gui_started": True,
                        "git_executable": "/usr/bin/git",
                        "git_version": "git version 2.50.0",
                    }
                ),
                encoding="utf-8",
            )

            message = verifier.verify_report(report_path)

        self.assertEqual(
            message,
            "macOS package verified with git version 2.50.0",
        )

    def test_rejects_relative_git_path(self) -> None:
        verifier = load_verifier()

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "git_returncode": 0,
                        "gui_started": True,
                        "git_executable": "git",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "absolute Git path",
            ):
                verifier.verify_report(report_path)


if __name__ == "__main__":
    unittest.main()
