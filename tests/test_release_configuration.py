from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseConfigurationTests(unittest.TestCase):
    def test_macos_spec_builds_app_without_windows_git_runtime(self) -> None:
        spec = (
            PROJECT_ROOT / "packaging" / "clickgit-macos.spec"
        ).read_text(encoding="utf-8")

        self.assertIn("BUNDLE(", spec)
        self.assertIn('name="ClickGit.app"', spec)
        self.assertIn(
            'bundle_identifier="io.github.ljy-codes.clickgit"',
            spec,
        )
        self.assertNotIn("runtime/git", spec)

    def test_macos_build_archives_native_app_bundle(self) -> None:
        script = (
            PROJECT_ROOT / "scripts" / "build-macos.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("packaging/clickgit-macos.spec", script)
        self.assertIn("scripts/verify-macos.sh", script)
        self.assertIn("ditto -c -k --sequesterRsrc --keepParent", script)
        self.assertIn("ClickGit-macOS-arm64.zip", script)
        self.assertIn("ClickGit-macOS-x64.zip", script)

    def test_macos_verification_uses_packaged_smoke_mode(self) -> None:
        script = (
            PROJECT_ROOT / "scripts" / "verify-macos.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("Contents/MacOS/ClickGit", script)
        self.assertIn("--smoke-test", script)
        self.assertIn("gui_started", script)
        self.assertIn("git_returncode", script)

    def test_release_workflow_builds_three_native_artifacts(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('tags:\n      - "release-v*"', workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn("macos-15-arm64", workflow)
        self.assertIn("runner: macos-15\n", workflow)
        self.assertNotIn("macos-15-intel", workflow)
        self.assertIn("ClickGit-Windows-x64.zip", workflow)
        self.assertIn("ClickGit-macOS-arm64.zip", workflow)
        self.assertIn("ClickGit-macOS-x64.zip", workflow)

    def test_release_workflow_creates_windows_and_mac_releases(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('WINDOWS_TAG="windows-v${VERSION}"', workflow)
        self.assertIn('MAC_TAG="mac-v${VERSION}"', workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("gh release edit", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("--clobber", workflow)


if __name__ == "__main__":
    unittest.main()
