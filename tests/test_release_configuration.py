from __future__ import annotations

import ast
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _find_single_call(tree: ast.AST, function_name: str) -> ast.Call:
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == function_name
    ]
    if len(calls) != 1:
        raise AssertionError(
            f"Expected one {function_name} call, found {len(calls)}."
        )
    return calls[0]


def _required_keyword(call: ast.Call, keyword_name: str) -> ast.AST:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return keyword.value
    raise AssertionError(f"Missing keyword argument: {keyword_name}")


def _find_iscc() -> str | None:
    candidates = [
        shutil.which("ISCC.exe"),
        (
            Path(os.environ["LOCALAPPDATA"])
            / "Programs"
            / "Inno Setup 6"
            / "ISCC.exe"
            if os.environ.get("LOCALAPPDATA")
            else None
        ),
        (
            Path(os.environ["ProgramFiles(x86)"])
            / "Inno Setup 6"
            / "ISCC.exe"
            if os.environ.get("ProgramFiles(x86)")
            else None
        ),
        (
            Path(os.environ["ProgramFiles"])
            / "Inno Setup 6"
            / "ISCC.exe"
            if os.environ.get("ProgramFiles")
            else None
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


class ReleaseConfigurationTests(unittest.TestCase):
    def test_windows_packaging_contract(self) -> None:
        windows_spec_path = (
            PROJECT_ROOT / "installer" / "clickgit.spec"
        )
        windows_spec = windows_spec_path.read_text(encoding="utf-8")
        spec_tree = ast.parse(windows_spec, filename=str(windows_spec_path))
        analysis_call = _find_single_call(spec_tree, "Analysis")
        analysis_datas = _required_keyword(analysis_call, "datas")
        with self.subTest(contract="Analysis.datas is empty"):
            self.assertIsInstance(analysis_datas, ast.List)
            self.assertEqual(analysis_datas.elts, [])

        exe_call = _find_single_call(spec_tree, "EXE")
        contents_directory = _required_keyword(
            exe_call,
            "contents_directory",
        )
        with self.subTest(contract="EXE contents directory"):
            self.assertIsInstance(contents_directory, ast.Constant)
            self.assertEqual(contents_directory.value, "_internal")

        self.assertTrue(
            (PROJECT_ROOT / "installer" / "ClickGit.iss").is_file()
        )
        self.assertTrue(
            (PROJECT_ROOT / "scripts" / "package.ps1").is_file()
        )
        self.assertTrue(
            (PROJECT_ROOT / "scripts" / "publish.ps1").is_file()
        )

    def test_installer_and_publishing_contract(self) -> None:
        installer_path = PROJECT_ROOT / "installer" / "ClickGit.iss"
        package_script_path = PROJECT_ROOT / "scripts" / "package.ps1"
        publish_script_path = PROJECT_ROOT / "scripts" / "publish.ps1"

        self.assertTrue(installer_path.is_file())
        self.assertTrue(package_script_path.is_file())
        self.assertTrue(publish_script_path.is_file())

        installer = installer_path.read_text(encoding="utf-8")
        package_script = package_script_path.read_text(encoding="utf-8")
        publish_script = publish_script_path.read_text(encoding="utf-8")

        self.assertIn("PrivilegesRequired=lowest", installer)
        self.assertIn("ClickGit-Windows-x64-Setup", installer)
        self.assertIn("recursesubdirs createallsubdirs", installer)
        self.assertIn(
            "ClickGit-Windows-x64-Portable.zip",
            package_script,
        )
        self.assertIn("scripts\\verify-package.ps1", package_script)
        self.assertIn("SHA256SUMS.txt", publish_script)
        self.assertIn("ClickGit-安装包.exe", publish_script)
        self.assertIn("Assert-ChildPath", publish_script)

    def test_installer_uses_complete_simplified_chinese_translation(
        self,
    ) -> None:
        installer_path = PROJECT_ROOT / "installer" / "ClickGit.iss"
        package_script_path = PROJECT_ROOT / "scripts" / "package.ps1"
        installer_language_path = (
            PROJECT_ROOT
            / "installer"
            / "Languages"
            / "ChineseSimplified.isl"
        )
        installer_language_license_path = (
            PROJECT_ROOT / "installer" / "Languages" / "LICENSE"
        )

        self.assertTrue(installer_path.is_file())
        self.assertTrue(package_script_path.is_file())
        self.assertTrue(installer_language_path.is_file())
        self.assertTrue(installer_language_license_path.is_file())

        installer = installer_path.read_text(encoding="utf-8")
        package_script = package_script_path.read_text(encoding="utf-8")
        installer_language = installer_language_path.read_text(
            encoding="utf-8"
        )
        installer_language_license = (
            installer_language_license_path.read_text(encoding="utf-8")
        )

        self.assertIn(
            'MessagesFile: "Languages\\ChineseSimplified.isl"',
            installer,
        )
        self.assertIn(
            'Source: "{#SourceRoot}\\installer\\Languages\\LICENSE"',
            installer,
        )
        self.assertIn(
            'DestName: "Inno-Setup-Chinese-Translation-LICENSE.txt"',
            installer,
        )
        self.assertIn('DestDir: "{app}\\licenses"', installer)
        self.assertIn('"/DSourceRoot=$ProjectRoot"', package_script)
        self.assertNotIn("[Messages]", installer)
        self.assertIn("LanguageName=简体中文", installer_language)
        self.assertIn("LanguageID=$0804", installer_language)
        self.assertTrue(installer_language_license.startswith("MIT License"))

    @unittest.skipUnless(os.name == "nt", "Windows publishing only")
    def test_windows_publish_script_integrates_safe_outer_layout(self) -> None:
        source_publish_script = PROJECT_ROOT / "scripts" / "publish.ps1"
        self.assertTrue(source_publish_script.is_file())
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        self.assertIsNotNone(powershell)

        with tempfile.TemporaryDirectory(
            prefix="clickgit-publish-contract-"
        ) as temporary_directory:
            temporary_root = Path(temporary_directory)
            outer_root = temporary_root / "git工具"
            project_root = outer_root / "开发空间"
            scripts_root = project_root / "scripts"
            installer_root = project_root / "artifacts" / "installer"
            package_root = project_root / "artifacts" / "package"
            docs_root = project_root / "docs" / "user"
            delivery_root = outer_root / "交付产品"
            scripts_root.mkdir(parents=True)
            installer_root.mkdir(parents=True)
            package_root.mkdir(parents=True)
            docs_root.mkdir(parents=True)
            delivery_root.mkdir(parents=True)
            publish_script = scripts_root / "publish.ps1"
            shutil.copy2(source_publish_script, publish_script)

            installer_name = "ClickGit-Windows-x64-Setup.exe"
            installer_content = b"fake-installer"
            (installer_root / installer_name).write_bytes(installer_content)
            existing_macos_name = "ClickGit-macOS-x64.zip"
            existing_macos_content = b"existing-macos-x64"
            (delivery_root / existing_macos_name).write_bytes(
                existing_macos_content
            )
            package_files = {
                "ClickGit-Windows-x64-Portable.zip": b"fake-portable",
                "ClickGit-macOS-arm64.zip": b"fake-macos-arm64",
            }
            for file_name, content in package_files.items():
                (package_root / file_name).write_bytes(content)
            fixture_files = {
                installer_name: installer_content,
                **package_files,
                existing_macos_name: existing_macos_content,
            }

            install_guide = "<html><body>安装说明</body></html>"
            product_intro = "<html><body>产品介绍</body></html>"
            (docs_root / "安装说明.html").write_text(
                install_guide,
                encoding="utf-8",
            )
            (docs_root / "产品介绍.html").write_text(
                product_intro,
                encoding="utf-8",
            )

            obsolete_directory = delivery_root / "ClickGit"
            obsolete_directory.mkdir()
            (obsolete_directory / "stale.dll").write_bytes(b"obsolete")
            (delivery_root / "ClickGit.zip").write_bytes(b"obsolete")
            unexpected_notes = delivery_root / "unexpected-notes.txt"
            unexpected_notes.write_text("must be removed", encoding="utf-8")
            unexpected_directory = delivery_root / "unexpected-directory"
            unexpected_directory.mkdir()
            (unexpected_directory / "stale.txt").write_bytes(b"obsolete")

            result = self._run_publish_script(
                powershell,
                publish_script,
                project_root,
                outer_root,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )

            self.assertFalse(obsolete_directory.exists())
            self.assertFalse((delivery_root / "ClickGit.zip").exists())
            self.assertFalse(unexpected_notes.exists())
            self.assertFalse(unexpected_directory.exists())
            allowed_delivery_files = {
                "ClickGit-Windows-x64-Setup.exe",
                "ClickGit-Windows-x64-Portable.zip",
                "ClickGit-macOS-arm64.zip",
                "ClickGit-macOS-x64.zip",
                "SHA256SUMS.txt",
            }
            delivery_entries = list(delivery_root.iterdir())
            self.assertTrue(
                all(path.is_file() for path in delivery_entries),
                msg="Delivery directory must not contain subdirectories.",
            )
            self.assertEqual(
                {path.name for path in delivery_entries},
                allowed_delivery_files,
            )
            self.assertNotIn(
                "unexpected-notes.txt",
                (delivery_root / "SHA256SUMS.txt").read_text(
                    encoding="utf-8-sig"
                ),
            )
            for path in delivery_entries:
                with self.subTest(clean_delivery_entry=path.name):
                    self.assertNotIn(
                        path.suffix.casefold(),
                        {".dll", ".pyd"},
                    )
                    self.assertNotEqual(path.name.casefold(), "pyside6")
                    self.assertNotEqual(path.name.casefold(), "clickgit")
            for file_name, content in fixture_files.items():
                with self.subTest(delivery_file=file_name):
                    self.assertEqual(
                        (delivery_root / file_name).read_bytes(),
                        content,
                    )
            self.assertEqual(
                (outer_root / "ClickGit-安装包.exe").read_bytes(),
                fixture_files["ClickGit-Windows-x64-Setup.exe"],
            )
            self.assertEqual(
                (outer_root / "安装说明.html").read_text(encoding="utf-8"),
                install_guide,
            )
            self.assertEqual(
                (outer_root / "产品介绍.html").read_text(encoding="utf-8"),
                product_intro,
            )
            self._assert_sha256_manifest_matches(delivery_root)

            mismatched_outer = temporary_root / "不匹配外层"
            mismatched_outer.mkdir()
            mismatched_result = self._run_publish_script(
                powershell,
                publish_script,
                project_root,
                mismatched_outer,
            )
            self.assertNotEqual(mismatched_result.returncode, 0)
            self.assertFalse(
                (mismatched_outer / "ClickGit-安装包.exe").exists()
            )

            child_outer = project_root / "artifacts"
            boundary_result = self._run_publish_script(
                powershell,
                publish_script,
                project_root,
                child_outer,
            )
            self.assertNotEqual(boundary_result.returncode, 0)
            self.assertFalse(
                (child_outer / "ClickGit-安装包.exe").exists()
            )

            delivery_snapshot = {
                path.name: path.read_bytes()
                for path in delivery_root.iterdir()
            }
            outer_installer = outer_root / "ClickGit-安装包.exe"
            outside_outer_target = temporary_root / "outside-outer-target"
            outside_outer_target.mkdir()
            outside_outer_marker = outside_outer_target / "marker.txt"
            outside_outer_marker.write_bytes(b"outer-must-survive")
            outer_installer.unlink()
            outer_junction_result = self._create_directory_junction(
                outer_installer,
                outside_outer_target,
            )
            if outer_junction_result is None:
                outer_installer.write_bytes(installer_content)
            else:
                try:
                    rollback_result = self._run_publish_script(
                        powershell,
                        publish_script,
                        project_root,
                        outer_root,
                    )
                    self.assertNotEqual(
                        rollback_result.returncode,
                        0,
                        msg=(
                            "Publishing must reject an outer-file junction.\n"
                            f"stdout:\n{rollback_result.stdout}\n"
                            f"stderr:\n{rollback_result.stderr}"
                        ),
                    )
                    restored_snapshot = {
                        path.name: path.read_bytes()
                        for path in delivery_root.iterdir()
                    }
                    self.assertEqual(restored_snapshot, delivery_snapshot)
                    self.assertEqual(
                        outside_outer_marker.read_bytes(),
                        b"outer-must-survive",
                    )
                finally:
                    is_junction = getattr(
                        os.path,
                        "isjunction",
                        lambda path: False,
                    )
                    if is_junction(outer_installer):
                        os.rmdir(outer_installer)
                    outer_installer.write_bytes(installer_content)

            shutil.rmtree(delivery_root)
            outside_delivery = temporary_root / "outside-delivery"
            outside_delivery.mkdir()
            outside_marker = outside_delivery / "marker.txt"
            outside_marker.write_bytes(b"outside-must-survive")
            junction_result = self._create_directory_junction(
                delivery_root,
                outside_delivery,
            )
            if junction_result is not None:
                try:
                    junction_publish_result = self._run_publish_script(
                        powershell,
                        publish_script,
                        project_root,
                        outer_root,
                    )
                    self.assertNotEqual(
                        junction_publish_result.returncode,
                        0,
                        msg=(
                            "Publishing must reject a delivery junction.\n"
                            f"stdout:\n{junction_publish_result.stdout}\n"
                            f"stderr:\n{junction_publish_result.stderr}"
                        ),
                    )
                    self.assertEqual(
                        outside_marker.read_bytes(),
                        b"outside-must-survive",
                    )
                finally:
                    is_junction = getattr(
                        os.path,
                        "isjunction",
                        lambda path: False,
                    )
                    if is_junction(delivery_root):
                        os.rmdir(delivery_root)

    @unittest.skipUnless(os.name == "nt", "Windows packaging only")
    def test_windows_package_script_builds_verified_products(self) -> None:
        source_package_script = PROJECT_ROOT / "scripts" / "package.ps1"
        source_installer = PROJECT_ROOT / "installer" / "ClickGit.iss"
        self.assertTrue(source_package_script.is_file())
        self.assertTrue(source_installer.is_file())
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        self.assertIsNotNone(powershell)
        iscc_path = _find_iscc()
        if iscc_path is None:
            self.skipTest("Inno Setup ISCC.exe is not installed.")

        with tempfile.TemporaryDirectory(
            prefix="clickgit-package-contract-"
        ) as temporary_directory:
            project_root = Path(temporary_directory) / "开发空间"
            package_script, verify_script, marker = (
                self._create_package_fixture(
                    project_root,
                    source_package_script,
                    source_installer,
                    verify_exit_code=0,
                )
            )

            result = self._run_package_script(
                powershell,
                package_script,
                project_root,
                verify_script,
                iscc_path,
                marker,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertTrue(marker.is_file())

            installer = (
                project_root
                / "artifacts"
                / "installer"
                / "ClickGit-Windows-x64-Setup.exe"
            )
            portable = (
                project_root
                / "artifacts"
                / "package"
                / "ClickGit-Windows-x64-Portable.zip"
            )
            self.assertTrue(installer.is_file())
            self.assertGreater(installer.stat().st_size, 0)
            self.assertTrue(portable.is_file())

            with zipfile.ZipFile(portable) as archive:
                archive_files = {
                    name.replace("\\", "/").rstrip("/")
                    for name in archive.namelist()
                    if not name.endswith(("/", "\\"))
                }
            expected_archive_files = {
                "ClickGit/ClickGit.exe",
                "ClickGit/runtime/git/cmd/git.exe",
                "ClickGit/LICENSE",
                "ClickGit/THIRD-PARTY-NOTICES.txt",
            }
            self.assertTrue(
                expected_archive_files.issubset(archive_files),
                msg=f"ZIP entries: {sorted(archive_files)}",
            )

    @unittest.skipUnless(os.name == "nt", "Windows packaging only")
    def test_windows_package_script_stops_when_verification_fails(
        self,
    ) -> None:
        source_package_script = PROJECT_ROOT / "scripts" / "package.ps1"
        source_installer = PROJECT_ROOT / "installer" / "ClickGit.iss"
        self.assertTrue(source_package_script.is_file())
        self.assertTrue(source_installer.is_file())
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        self.assertIsNotNone(powershell)

        with tempfile.TemporaryDirectory(
            prefix="clickgit-package-failure-"
        ) as temporary_directory:
            project_root = Path(temporary_directory) / "开发空间"
            package_script, verify_script, marker = (
                self._create_package_fixture(
                    project_root,
                    source_package_script,
                    source_installer,
                    verify_exit_code=19,
                )
            )
            iscc_marker = project_root / "iscc.marker"
            fake_iscc = project_root / "scripts" / "fake-iscc.cmd"
            fake_iscc.write_text(
                (
                    '@echo invoked>"%CLICKGIT_ISCC_MARKER%"\n'
                    "@exit /b 0\n"
                ),
                encoding="utf-8",
            )
            stale_installer = (
                project_root
                / "artifacts"
                / "installer"
                / "ClickGit-Windows-x64-Setup.exe"
            )
            stale_portable = (
                project_root
                / "artifacts"
                / "package"
                / "ClickGit-Windows-x64-Portable.zip"
            )
            stale_installer.parent.mkdir(parents=True)
            stale_portable.parent.mkdir(parents=True)
            stale_installer.write_bytes(b"stale-installer")
            stale_portable.write_bytes(b"stale-portable")

            result = self._run_package_script(
                powershell,
                package_script,
                project_root,
                verify_script,
                str(fake_iscc),
                marker,
                iscc_marker=iscc_marker,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(marker.is_file())
            self.assertFalse(iscc_marker.exists())
            self.assertFalse(stale_installer.exists())
            self.assertFalse(stale_portable.exists())

    def _create_package_fixture(
        self,
        project_root: Path,
        source_package_script: Path,
        source_installer: Path,
        *,
        verify_exit_code: int,
    ) -> tuple[Path, Path, Path]:
        scripts_root = project_root / "scripts"
        installer_root = project_root / "installer"
        application_root = (
            project_root
            / "artifacts"
            / "publish"
            / "windows-x64"
            / "ClickGit"
        )
        git_root = application_root / "runtime" / "git" / "cmd"
        scripts_root.mkdir(parents=True)
        installer_root.mkdir(parents=True)
        git_root.mkdir(parents=True)

        package_script = scripts_root / "package.ps1"
        shutil.copy2(source_package_script, package_script)
        shutil.copy2(source_installer, installer_root / "ClickGit.iss")
        shutil.copytree(
            source_installer.parent / "Languages",
            installer_root / "Languages",
        )

        (application_root / "ClickGit.exe").write_bytes(b"fake-clickgit")
        (git_root / "git.exe").write_bytes(b"fake-git")
        (application_root / "LICENSE").write_text(
            "MIT License",
            encoding="utf-8",
        )
        (application_root / "THIRD-PARTY-NOTICES.txt").write_text(
            "Third-party notices",
            encoding="utf-8",
        )

        marker = project_root / "verify.marker"
        verify_script = scripts_root / "fake-verify.ps1"
        verify_script.write_text(
            "\n".join(
                (
                    "param(",
                    "    [string]$ProjectRoot,",
                    "    [string]$PackageRoot",
                    ")",
                    '$ErrorActionPreference = "Stop"',
                    (
                        "Set-Content -LiteralPath "
                        "$env:CLICKGIT_VERIFY_MARKER "
                        '-Value "verified" -Encoding UTF8'
                    ),
                    f"exit {verify_exit_code}",
                )
            ),
            encoding="utf-8",
        )
        return package_script, verify_script, marker

    def _run_package_script(
        self,
        powershell: str,
        package_script: Path,
        project_root: Path,
        verify_script: Path,
        iscc_path: str,
        marker: Path,
        *,
        iscc_marker: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["CLICKGIT_VERIFY_MARKER"] = str(marker)
        if iscc_marker is not None:
            environment["CLICKGIT_ISCC_MARKER"] = str(iscc_marker)
        return subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(package_script),
                "-Version",
                "0.1.0",
                "-ProjectRoot",
                str(project_root),
                "-SkipBuild",
                "-VerifyScript",
                str(verify_script),
                "-IsccPath",
                iscc_path,
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            env=environment,
        )

    def _run_publish_script(
        self,
        powershell: str,
        publish_script: Path,
        project_root: Path,
        outer_root: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(publish_script),
                "-Version",
                "0.1.0",
                "-ProjectRoot",
                str(project_root),
                "-OuterRoot",
                str(outer_root),
                "-SkipPackage",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )

    def _create_directory_junction(
        self,
        junction_path: Path,
        target_path: Path,
    ) -> subprocess.CompletedProcess[str] | None:
        command_prompt = shutil.which("cmd.exe")
        if command_prompt is None:
            return None
        result = subprocess.run(
            [
                command_prompt,
                "/d",
                "/c",
                "mklink",
                "/J",
                str(junction_path),
                str(target_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result

    def _assert_sha256_manifest_matches(self, delivery_root: Path) -> None:
        manifest_path = delivery_root / "SHA256SUMS.txt"
        self.assertTrue(manifest_path.is_file())
        manifest_entries: dict[str, str] = {}
        for line in manifest_path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            digest, file_name = line.split(maxsplit=1)
            normalized_name = file_name.lstrip("*")
            self.assertNotIn(
                normalized_name,
                manifest_entries,
                msg=f"Duplicate SHA-256 entry: {normalized_name}",
            )
            manifest_entries[normalized_name] = digest.casefold()

        delivery_files = {
            path.name: path
            for path in delivery_root.iterdir()
            if path.is_file() and path.name != manifest_path.name
        }
        self.assertEqual(set(manifest_entries), set(delivery_files))
        for file_name, file_path in delivery_files.items():
            with self.subTest(sha256=file_name):
                actual_digest = hashlib.sha256(
                    file_path.read_bytes()
                ).hexdigest()
                self.assertEqual(
                    manifest_entries[file_name],
                    actual_digest,
                )

    def test_sha256_manifest_rejects_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="clickgit-sha-contract-"
        ) as temporary_directory:
            delivery_root = Path(temporary_directory)
            artifact = delivery_root / "ClickGit-Windows-x64-Setup.exe"
            artifact.write_bytes(b"installer")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            (delivery_root / "SHA256SUMS.txt").write_text(
                (
                    f"{digest}  {artifact.name}\n"
                    f"{digest} *{artifact.name}\n"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                AssertionError,
                "Duplicate SHA-256 entry",
            ):
                self._assert_sha256_manifest_matches(delivery_root)

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
        normalized_workflow = workflow.replace("\\", "/")

        self.assertIn('tags:\n      - "release-v*"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("version:", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn("runner: macos-15\n", workflow)
        self.assertIn("macos-15-intel", workflow)
        self.assertNotIn("macos-15-arm64", workflow)
        self.assertIn(
            "choco install innosetup --no-progress -y",
            workflow,
        )
        self.assertEqual(workflow.count("scripts/package.ps1"), 1)
        self.assertIn(
            "scripts/package.ps1 -Version $env:RELEASE_VERSION",
            workflow,
        )
        self.assertIn("RELEASE_VERSION=", workflow)
        input_expression_lines = [
            line.strip()
            for line in workflow.splitlines()
            if "${{ inputs.version }}" in line
        ]
        self.assertEqual(
            input_expression_lines,
            ["RELEASE_INPUT: ${{ inputs.version }}"] * 2,
        )
        self.assertIn("$ReleaseVersion = $env:RELEASE_INPUT", workflow)
        self.assertIn("$env:GITHUB_REF_NAME", workflow)
        self.assertNotIn(
            '$ReleaseVersion = "${{ inputs.version }}"',
            workflow,
        )
        self.assertNotIn('VERSION="${{ inputs.version }}"', workflow)
        self.assertNotIn("scripts/build.ps1", workflow)
        self.assertNotIn("scripts/verify-package.ps1", workflow)
        self.assertNotIn("Compress-Archive", workflow)
        self.assertIn("ClickGit-Windows-x64-Setup.exe", workflow)
        self.assertIn("ClickGit-Windows-x64-Portable.zip", workflow)
        self.assertNotIn("ClickGit-Windows-x64.zip", workflow)
        self.assertIn("ClickGit-macOS-arm64.zip", workflow)
        self.assertIn("ClickGit-macOS-x64.zip", workflow)
        self.assertIn(
            (
                '$ReleaseDirectory = "artifacts\\release\\windows-x64"'
            ),
            workflow,
        )
        self.assertIn(
            "if (Test-Path -LiteralPath $ReleaseDirectory) {",
            workflow,
        )
        self.assertNotIn("-ErrorAction SilentlyContinue", workflow)
        self.assertIn(
            (
                'Copy-Item -LiteralPath "artifacts\\installer\\'
                'ClickGit-Windows-x64-Setup.exe" '
                "-Destination $ReleaseDirectory"
            ),
            workflow,
        )
        self.assertIn(
            (
                'Copy-Item -LiteralPath "artifacts\\package\\'
                'ClickGit-Windows-x64-Portable.zip" '
                "-Destination $ReleaseDirectory"
            ),
            workflow,
        )
        self.assertIn(
            "path: artifacts/release/windows-x64",
            normalized_workflow,
        )
        self.assertNotIn(
            (
                "path: |\n"
                "            artifacts/installer/"
                "ClickGit-Windows-x64-Setup.exe"
            ),
            normalized_workflow,
        )
        self.assertIn(
            "artifacts/package/${{ matrix.archive }}",
            workflow,
        )
        package_index = workflow.index("scripts/package.ps1")
        staging_index = workflow.index("$ReleaseDirectory")
        upload_index = workflow.index("uses: actions/upload-artifact@v4")
        self.assertLess(package_index, staging_index)
        self.assertLess(staging_index, upload_index)

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
        self.assertIn('VERSION="$RELEASE_INPUT"', workflow)
        self.assertIn('VERSION="${VERSION%%-retry*}"', workflow)
        self.assertIn(
            (
                'WINDOWS_SETUP="release-assets/windows-x64/'
                'ClickGit-Windows-x64-Setup.exe"'
            ),
            workflow,
        )
        self.assertIn(
            (
                'WINDOWS_PORTABLE="release-assets/windows-x64/'
                'ClickGit-Windows-x64-Portable.zip"'
            ),
            workflow,
        )
        self.assertIn(
            (
                'gh release upload "$WINDOWS_TAG" \\\n'
                '            "$WINDOWS_SETUP" \\\n'
                '            "$WINDOWS_PORTABLE" \\\n'
                "            --clobber"
            ),
            workflow,
        )
        required_asset_checks = (
            'test -f "$WINDOWS_SETUP"',
            'test -f "$WINDOWS_PORTABLE"',
            'test -f "$MAC_ARM_ASSET"',
            'test -f "$MAC_X64_ASSET"',
        )
        self.assertEqual(workflow.count("test -f "), 4)
        for asset_check in required_asset_checks:
            with self.subTest(asset_check=asset_check):
                self.assertIn(asset_check, workflow)
        self.assertIn("resolve_tag_commit() {", workflow)
        self.assertIn(
            'gh api "repos/${GH_REPO}/git/ref/tags/${tag}"',
            workflow,
        )
        self.assertIn(
            'gh api "repos/${GH_REPO}/git/tags/${object_sha}"',
            workflow,
        )
        self.assertIn(
            'while [[ "$object_type" == "tag" ]]; do',
            workflow,
        )
        self.assertIn(
            'if [[ "$object_type" != "commit" ]]; then',
            workflow,
        )
        self.assertIn("assert_release_tag_target() {", workflow)
        self.assertIn(
            'if [[ "$resolved_sha" != "$GITHUB_SHA" ]]; then',
            workflow,
        )
        self.assertIn(
            'assert_release_tag_target "$WINDOWS_TAG"',
            workflow,
        )
        self.assertIn(
            'assert_release_tag_target "$MAC_TAG"',
            workflow,
        )
        self.assertIn(
            (
                'if gh api "repos/${GH_REPO}/git/ref/tags/'
                '${WINDOWS_TAG}" >/dev/null 2>&1; then'
            ),
            workflow,
        )
        self.assertIn(
            (
                'if gh api "repos/${GH_REPO}/git/ref/tags/'
                '${MAC_TAG}" >/dev/null 2>&1; then'
            ),
            workflow,
        )
        self.assertEqual(workflow.count('--target "$GITHUB_SHA"'), 2)
        asset_check_index = workflow.index(
            'test -f "$MAC_X64_ASSET"'
        )
        windows_tag_check_index = workflow.index(
            (
                'if gh api "repos/${GH_REPO}/git/ref/tags/'
                '${WINDOWS_TAG}"'
            )
        )
        self.assertIn(
            'if gh release view "$WINDOWS_TAG"',
            workflow,
        )
        windows_release_check_index = workflow.index(
            'if gh release view "$WINDOWS_TAG"'
        )
        windows_upload_index = workflow.index(
            'gh release upload "$WINDOWS_TAG"'
        )
        mac_upload_index = workflow.index('gh release upload "$MAC_TAG"')
        self.assertLess(asset_check_index, windows_tag_check_index)
        self.assertLess(
            windows_release_check_index,
            workflow.index(
                'assert_release_tag_target "$WINDOWS_TAG"'
            ),
        )
        self.assertLess(
            windows_release_check_index,
            windows_upload_index,
        )
        self.assertLess(
            workflow.index('assert_release_tag_target "$MAC_TAG"'),
            mac_upload_index,
        )
        self.assertIn("安装版", workflow)
        self.assertIn("便携版", workflow)
        self.assertIn("备用", workflow)


if __name__ == "__main__":
    unittest.main()
