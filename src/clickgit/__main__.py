from __future__ import annotations

import json
import os
import subprocess
import sys
import ctypes
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from clickgit.app import AppController
from clickgit.settings import SettingsStore
from clickgit.ui.main_window import MainWindow
from clickgit.ui.styles import APP_STYLE


def application_data_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / "ClickGit"
    return Path.home() / ".clickgit"


def application_executable_dir() -> Path:
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetModuleFileNameW(
            None,
            buffer,
            len(buffer),
        )
        if length:
            return Path(buffer.value).resolve().parent
    return Path(sys.executable).resolve().parent


def bundled_git_executable() -> Path | str:
    executable_root = application_executable_dir()
    candidates = [
        executable_root / "runtime" / "git" / "cmd" / "git.exe",
        Path(__file__).resolve().parents[2]
        / "runtime"
        / "git"
        / "cmd"
        / "git.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return "git"


def write_diagnostic(report_path: Path, *, include_gui: bool = False) -> int:
    git_executable = bundled_git_executable()
    completed = subprocess.run(
        [str(git_executable), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
        creationflags=(
            subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        ),
    )
    payload = {
        "git_executable": str(Path(git_executable).resolve()),
        "git_version": completed.stdout.decode(
            "utf-8",
            errors="replace",
        ).strip(),
        "git_returncode": completed.returncode,
        "gui_started": False,
    }
    if include_gui and completed.returncode == 0:
        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        app.setFont(QFont("Microsoft YaHei UI", 9))
        app.setStyleSheet(APP_STYLE)
        controller = AppController(
            settings_store=SettingsStore(
                report_path.parent / "smoke-settings.json"
            ),
            git_executable=git_executable,
        )
        window = MainWindow(controller)
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        QTimer.singleShot(150, app.quit)
        app.exec()
        controller.shutdown()
        window.close()
        payload["gui_started"] = True
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if completed.returncode == 0 else 1


def main() -> int:
    arguments = sys.argv[1:]
    if arguments and arguments[0] in {
        "--diagnose-bundled-git",
        "--smoke-test",
    }:
        if len(arguments) != 2:
            return 2
        return write_diagnostic(
            Path(arguments[1]).resolve(),
            include_gui=arguments[0] == "--smoke-test",
        )
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ClickGit")
    app.setOrganizationName("ClickGit")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(APP_STYLE)
    data_dir = application_data_dir()
    controller = AppController(
        settings_store=SettingsStore(data_dir / "settings.json"),
        git_executable=bundled_git_executable(),
    )
    app.aboutToQuit.connect(controller.shutdown)
    window = MainWindow(controller)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
