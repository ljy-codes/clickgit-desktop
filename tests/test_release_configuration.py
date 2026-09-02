from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseConfigurationTests(unittest.TestCase):
    def test_pyinstaller_specs_live_under_installer(self) -> None:
        self.assertTrue(
            (PROJECT_ROOT / "installer" / "clickgit.spec").is_file()
        )
        self.assertTrue(
            (
                PROJECT_ROOT
                / "installer"
                / "clickgit-macos.spec"
            ).is_file()
        )
        self.assertFalse((PROJECT_ROOT / "packaging").exists())

    def test_macos_spec_builds_app_without_windows_git_runtime(self) -> None:
        spec = (
            PROJECT_ROOT / "installer" / "clickgit-macos.spec"
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

        self.assertIn("installer/clickgit-macos.spec", script)
        self.assertIn("--workpath artifacts/build/macos", script)
        self.assertIn("--distpath artifacts/publish/macos", script)
        self.assertIn("scripts/verify-macos.sh", script)
        self.assertIn("ditto -c -k --sequesterRsrc --keepParent", script)
        self.assertIn("artifacts/publish/macos/ClickGit.app", script)
        self.assertIn("artifacts/package/$ARCHIVE_NAME", script)
        self.assertIn("ClickGit-macOS-arm64.zip", script)
        self.assertIn("ClickGit-macOS-x64.zip", script)

    def test_windows_build_and_verification_use_artifacts(self) -> None:
        build_script = (
            PROJECT_ROOT / "scripts" / "build.ps1"
        ).read_text(encoding="utf-8")
        verify_script = (
            PROJECT_ROOT / "scripts" / "verify-package.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("installer\\clickgit.spec", build_script)
        self.assertIn("--workpath artifacts\\build\\windows", build_script)
        self.assertIn(
            "--distpath artifacts\\publish\\windows-x64",
            build_script,
        )
        self.assertIn(
            "artifacts\\publish\\windows-x64\\ClickGit\\ClickGit.exe",
            build_script,
        )
        self.assertIn(
            "artifacts\\publish\\windows-x64\\ClickGit",
            verify_script,
        )
        self.assertIn(
            "artifacts\\build\\windows\\package-smoke.json",
            verify_script,
        )
        self.assertIn("$OriginalPath = $env:PATH", build_script)
        self.assertIn("codex-runtimes", build_script)
        self.assertIn("$env:PATH = $OriginalPath", build_script)

    def test_macos_verification_uses_packaged_smoke_mode(self) -> None:
        script = (
            PROJECT_ROOT / "scripts" / "verify-macos.sh"
        ).read_text(encoding="utf-8")
        verifier = (
            PROJECT_ROOT / "scripts" / "verify_macos_report.py"
        ).read_text(encoding="utf-8")

        self.assertIn("Contents/MacOS/ClickGit", script)
        self.assertIn("--smoke-test", script)
        self.assertIn("verify_macos_report.py", script)
        self.assertIn(
            "artifacts/publish/macos/ClickGit.app",
            script,
        )
        self.assertIn(
            "artifacts/build/macos/macos-package-smoke.json",
            script,
        )
        self.assertIn("gui_started", verifier)
        self.assertIn("git_returncode", verifier)

    def test_release_workflow_builds_three_native_artifacts(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('tags:\n      - "release-v*"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("version:", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn("runner: macos-15\n", workflow)
        self.assertIn("macos-15-intel", workflow)
        self.assertNotIn("macos-15-arm64", workflow)
        self.assertIn("ClickGit-Windows-x64.zip", workflow)
        self.assertIn("ClickGit-macOS-arm64.zip", workflow)
        self.assertIn("ClickGit-macOS-x64.zip", workflow)
        self.assertIn(
            "artifacts/package/ClickGit-Windows-x64.zip",
            workflow,
        )
        self.assertIn(
            "artifacts/package/${{ matrix.archive }}",
            workflow,
        )
        self.assertIn(
            "artifacts/publish/windows-x64/ClickGit",
            workflow.replace("\\", "/"),
        )

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
        self.assertIn("GH_REPO: ${{ github.repository }}", workflow)
        self.assertIn('VERSION="${{ inputs.version }}"', workflow)
        self.assertIn('VERSION="${VERSION%%-retry*}"', workflow)


if __name__ == "__main__":
    unittest.main()
