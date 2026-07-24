from __future__ import annotations

import os
import sys
from pathlib import Path

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


def bundled_git_executable() -> Path | str:
    executable_root = Path(sys.executable).resolve().parent
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


def main() -> int:
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
