from __future__ import annotations

import ctypes
import importlib
import importlib.util
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import QApplication, QWidget


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src" / "clickgit" / "resources"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


class BrandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("clickgit.branding"),
            "Runtime branding API has not been implemented",
        )
        return importlib.import_module("clickgit.branding")

    def test_resource_path_is_absolute_and_independent_of_working_directory(self):
        branding = self.api()
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                path = branding.resource_path("clickgit.ico")
                self.assertEqual(path, RESOURCES / "clickgit.ico")
                self.assertTrue(path.is_absolute())
                self.assertTrue(path.is_file())
            finally:
                os.chdir(previous)

    def test_resource_path_uses_package_location_in_frozen_layout(self):
        branding = self.api()
        with tempfile.TemporaryDirectory() as directory:
            # Windows TEMP can use an 8.3 user directory alias.
            package = Path(directory).resolve() / "_internal" / "clickgit"
            with patch.object(branding, "__file__", str(package / "branding.py")):
                self.assertEqual(
                    branding.resource_path("clickgit.ico"),
                    package / "resources" / "clickgit.ico",
                )

    def test_resource_path_rejects_outside_asset_names(self):
        branding = self.api()
        for name in ("../LICENSE", "..\\LICENSE", "/clickgit.ico", "C:\\icon.ico"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                branding.resource_path(name)

    def test_app_icon_propagates_to_windows_without_changing_theme(self):
        branding = self.api()
        old_icon = QIcon(self.app.windowIcon())
        old_style = self.app.styleSheet()
        self.addCleanup(self.app.setWindowIcon, old_icon)
        with patch.object(branding.sys, "platform", "linux"):
            branding.apply_branding(self.app)
        self.assertFalse(self.app.windowIcon().isNull())
        self.assertEqual(self.app.styleSheet(), old_style)
        window = QWidget()
        try:
            self.assertFalse(window.windowIcon().pixmap(16, 16).isNull())
        finally:
            window.close()
            window.deleteLater()
        self.assertEqual(
            {size.width() for size in self.app.windowIcon().availableSizes()},
            set(SIZES),
        )

    def test_windows_app_id_is_stable_and_shared_with_shortcuts(self):
        branding = self.api()
        self.assertEqual(branding.APP_USER_MODEL_ID, "ljy-codes.ClickGit")
        setter = Mock(return_value=0)
        shell32 = SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter)
        with patch.object(branding.sys, "platform", "win32"), patch.object(
            ctypes, "windll", SimpleNamespace(shell32=shell32), create=True
        ):
            self.assertTrue(branding.set_windows_app_user_model_id())
        setter.assert_called_once_with(branding.APP_USER_MODEL_ID)

    def test_windows_shell_api_failure_does_not_abort_startup(self):
        branding = self.api()
        for error in (OSError("shell unavailable"), AttributeError("not exposed")):
            shell32 = Mock()
            shell32.SetCurrentProcessExplicitAppUserModelID.side_effect = error
            with self.subTest(error=error), patch.object(
                branding.sys, "platform", "win32"
            ), patch.object(ctypes, "windll", SimpleNamespace(shell32=shell32), create=True):
                with self.assertLogs("clickgit.branding", level="WARNING"):
                    self.assertFalse(branding.set_windows_app_user_model_id())

    def test_failed_hresult_is_reported_without_aborting_startup(self):
        branding = self.api()
        shell32 = Mock()
        shell32.SetCurrentProcessExplicitAppUserModelID.return_value = -2147467259
        with patch.object(branding.sys, "platform", "win32"), patch.object(
            ctypes, "windll", SimpleNamespace(shell32=shell32), create=True
        ), self.assertLogs("clickgit.branding", level="WARNING"):
            self.assertFalse(branding.set_windows_app_user_model_id())

    def test_non_windows_does_not_load_shell_api(self):
        branding = self.api()
        with patch.object(branding.sys, "platform", "darwin"), patch.object(
            ctypes, "windll", new=Mock(), create=True
        ) as windll:
            self.assertFalse(branding.set_windows_app_user_model_id())
        self.assertEqual(windll.mock_calls, [])

    def test_apply_branding_sets_process_identity_before_icon(self):
        branding = self.api()
        events = []
        app = SimpleNamespace(setWindowIcon=lambda icon: events.append("icon"))
        with patch.object(
            branding, "set_windows_app_user_model_id",
            side_effect=lambda: events.append("identity"),
        ):
            branding.apply_branding(app)
        self.assertEqual(events, ["identity", "icon"])

    def test_ico_contains_all_sizes_with_real_alpha_and_legible_cyan_pixels(self):
        icon_path = RESOURCES / "clickgit.ico"
        self.assertTrue(icon_path.is_file(), "Multi-resolution app icon is missing")
        data = icon_path.read_bytes()
        self.assertEqual(struct.unpack_from("<HHH", data), (0, 1, len(SIZES)))
        for index, size in enumerate(SIZES):
            width, height, colors, reserved, planes, depth, length, offset = (
                struct.unpack_from("<BBBBHHII", data, 6 + index * 16)
            )
            self.assertEqual((width or 256, height or 256), (size, size))
            self.assertEqual((colors, reserved, planes, depth), (0, 0, 1, 32))
            frame = QImage.fromData(data[offset:offset + length], "PNG")
            self.assertEqual(frame.size(), QSize(size, size))
            self.assertTrue(frame.hasAlphaChannel())
            self.assertEqual(frame.pixelColor(0, 0).alpha(), 0)
            cyan_pixels = sum(
                1 for y in range(size) for x in range(size)
                if (color := frame.pixelColor(x, y)).alpha() > 200
                and color.green() > 160 and color.blue() > 160 and color.red() < 140
            )
            self.assertGreater(cyan_pixels, size * size * 0.08)
            self.assertEqual(frame, QImage(str(RESOURCES / f"clickgit-{size}.png")))

    def test_wizard_images_are_high_dpi_dark_blue_assets(self):
        for name, dimensions in (
            ("wizard-panel.png", QSize(492, 942)),
            ("wizard-small.png", QSize(192, 192)),
        ):
            with self.subTest(name=name):
                image = QImage(str(RESOURCES / name))
                self.assertEqual(image.size(), dimensions)
                corner = image.pixelColor(0, 0)
                self.assertEqual(corner.alpha(), 255)
                self.assertLess(corner.lightness(), 35)
                self.assertGreater(corner.blue(), corner.red())

    def test_generator_is_byte_reproducible_and_matches_committed_assets(self):
        script = ROOT / "scripts" / "generate_brand_assets.py"
        self.assertTrue(script.is_file(), "Deterministic brand asset generator is missing")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "品牌资源"
            command = [sys.executable, str(script), "--output-dir", str(output)]
            for _ in range(2):
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                generated = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
                self.assertIn("clickgit.svg", generated)
                self.assertIn("clickgit.ico", generated)
                for name, content in generated.items():
                    reference = RESOURCES / name
                    # Git's Windows checkout may convert vector-source LF to
                    # CRLF. Raster/ICO output still must match byte for byte.
                    expected = (
                        reference.read_text(encoding="utf-8").encode("utf-8")
                        if reference.suffix == ".svg" else reference.read_bytes()
                    )
                    self.assertEqual(content, expected, name)

    def test_pyinstaller_embeds_icon_and_only_explicit_brand_resources(self):
        calls = {}

        def analysis(*args, **kwargs):
            calls["analysis"] = kwargs
            return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=kwargs["datas"])

        def exe(*args, **kwargs):
            calls["exe"] = kwargs
            return object()

        runpy.run_path(
            str(ROOT / "installer" / "clickgit.spec"),
            init_globals={
                "SPECPATH": str(ROOT / "installer"),
                "Analysis": analysis, "PYZ": lambda *a: object(),
                "EXE": exe, "COLLECT": lambda *a, **kw: object(),
            },
        )
        self.assertEqual(Path(calls["exe"].get("icon", "")), RESOURCES / "clickgit.ico")
        datas = calls["analysis"]["datas"]
        self.assertTrue(datas, "Brand resources are not bundled")
        self.assertEqual(
            {Path(source).name for source, _ in datas},
            {"clickgit.ico"} | {f"clickgit-{size}.png" for size in SIZES},
        )
        for source, destination in datas:
            self.assertTrue(Path(source).is_file())
            self.assertTrue(Path(source).is_absolute())
            self.assertEqual(destination, "clickgit/resources")
        self.assertEqual(calls["exe"]["contents_directory"], "_internal")

    def test_installer_native_dark_branding_keeps_safety_and_license(self):
        script = (ROOT / "installer" / "ClickGit.iss").read_text(encoding="utf-8")
        required = (
            "WizardStyle=modern dark polar",
            "WizardBackColor=#080F20",
            "WizardImageFile={#SourceRoot}\\src\\clickgit\\resources\\wizard-panel.png",
            "WizardSmallImageFile={#SourceRoot}\\src\\clickgit\\resources\\wizard-small.png",
            "SetupIconFile={#SourceRoot}\\src\\clickgit\\resources\\clickgit.ico",
            "UninstallDisplayIcon={app}\\ClickGit.exe",
            'LicenseFile={#SourceRoot}\\LICENSE',
            "PrivilegesRequired=lowest",
            "DefaultDirName={localappdata}\\Programs\\ClickGit",
            'DestName: "Inno-Setup-Chinese-Translation-LICENSE.txt"',
            '#if Ver < EncodeVer(6, 7, 0)',
        )
        for value in required:
            self.assertIn(value, script)
        icons = script.split("[Icons]", 1)[1].split("[", 1)[0]
        for line in icons.strip().splitlines():
            if line.startswith("Name:"):
                self.assertIn('IconFilename: "{app}\\ClickGit.exe"', line)
                if "{uninstallexe}" not in line:
                    self.assertIn('AppUserModelID: "ljy-codes.ClickGit"', line)
        self.assertNotIn("[UninstallDelete]", script)
        self.assertNotIn("external ", script.lower())

    def test_inno_compiler_validates_script_without_installer_output(self):
        compiler = shutil.which("ISCC.exe")
        if compiler is None and os.environ.get("LOCALAPPDATA"):
            candidate = Path(os.environ["LOCALAPPDATA"]) / "Programs/Inno Setup 6/ISCC.exe"
            if candidate.is_file():
                compiler = str(candidate)
        if compiler is None:
            self.skipTest("Inno Setup compiler is not installed")
        with tempfile.TemporaryDirectory(prefix="clickgit-branding-") as directory:
            temporary = Path(directory)
            payload = temporary / "payload"
            payload.mkdir()
            (payload / "ClickGit.exe").write_bytes(b"syntax-check-only")
            result = subprocess.run(
                [compiler, "/O-", f"/DSourceDir={payload}", f"/DSourceRoot={ROOT}",
                 str(ROOT / "installer" / "ClickGit.iss")],
                capture_output=True, text=True, errors="replace", check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(temporary.iterdir()), [payload])


if __name__ == "__main__":
    unittest.main()
