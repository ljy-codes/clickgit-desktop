from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, Qt
from PySide6.QtGui import QFont, QTextFormat
from PySide6.QtWidgets import QApplication

from clickgit.branding import apply_branding
from clickgit.git_runner import locate_git
from clickgit.platform_support import (
    application_data_dir,
    application_executable_dir,
    preferred_ui_font,
)


def bundled_git_executable() -> Path:
    executable_root = application_executable_dir()
    source_root = Path(__file__).resolve().parents[2]
    try:
        return locate_git(executable_root)
    except FileNotFoundError:
        return locate_git(source_root)


def write_diagnostic(report_path: Path, *, include_gui: bool = False) -> int:
    from clickgit.app import AppController
    from clickgit.settings import SettingsStore
    from clickgit.ui.main_window import MainWindow
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
        apply_branding(app)
        app.setStyle("Fusion")
        app.setFont(QFont(preferred_ui_font(), 9))
        controller = AppController(
            settings_store=SettingsStore(
                report_path.parent / "smoke-settings.json"
            ),
            git_executable=git_executable,
        )
        window = MainWindow(controller)
        verified_themes = []
        for theme in ("light", "dark", "tech"):
            window.theme_manager.apply(replace(controller.settings, theme=theme))
            if window.theme_manager.effective_theme == theme:
                verified_themes.append(theme)
        window.theme_manager.apply(controller.settings)
        # Synthetic only: verify frozen packaging includes bounded inline HTML diff.
        source = "<td>电池接插件" + "相同内容" * 800 + "更换</td>"
        window.document_viewer.set_comparison(source, source.replace("更换", "00更换"))
        inline = [
            item.cursor.selectedText()
            for item in window.document_viewer.right_editor.extraSelections()
            if not item.format.boolProperty(QTextFormat.FullWidthSelection)
        ]
        payload["features"] = {
            "increment": "2026-09-10-source-inline-highlight",
            "source_inline_highlight_verified": inline == ["00"],
            "navigation": [window.navigation.item(i).text()
                           for i in range(window.navigation.count())],
            "verified_themes": verified_themes,
            "document_compare_available": hasattr(window, "document_viewer"),
            "reviewed_merge_available": hasattr(window, "merge_review_button"),
            "document_workflow_tested_in_smoke": False,
            "html_review_available": hasattr(window, "html_review_button"),
            "html_interactive_preview_enabled": False,
            "html_preview_isolated": True,
            "diagnostics_available": hasattr(window, "diagnostics_button"),
            "application_icon_available": not app.windowIcon().isNull(),
        }
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
    if arguments and arguments[0] == "--html-preview-worker":
        if len(arguments) != 1:
            return 2
        from clickgit.preview_worker import run_preview_worker
        return run_preview_worker()
    if QApplication.instance() is None:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    if arguments and arguments[0] == "--smoke-html":
        if len(arguments) != 2:
            return 2
        from clickgit.html_smoke import write_html_diagnostic
        return write_html_diagnostic(Path(arguments[1]).resolve())
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
    apply_branding(app)
    app.setApplicationName("ClickGit")
    app.setOrganizationName("ClickGit")
    app.setStyle("Fusion")
    app.setFont(QFont(preferred_ui_font(), 9))
    data_dir = application_data_dir()
    from clickgit.diagnostics import DiagnosticLog, log_exception, record_event, set_diagnostics
    diagnostics = DiagnosticLog(data_dir)
    set_diagnostics(diagnostics)
    record_event("app_start", pid=os.getpid(), executable_path=str(
        application_executable_dir() / Path(sys.executable).name),
        config_path=str(data_dir / "settings.json"))
    old_hook, old_thread_hook = sys.excepthook, threading.excepthook
    sys.excepthook = lambda kind, value, tb: log_exception(kind, value, tb)
    threading.excepthook = lambda args: log_exception(args.exc_type, args.exc_value, args.exc_traceback)
    from clickgit.ui.preview_session import stop_all_previews
    # Preview teardown must precede the existing (possibly waiting) Git shutdown.
    app.aboutToQuit.connect(stop_all_previews)
    controller = None
    try:
        from clickgit.app import AppController
        from clickgit.settings import SettingsStore
        from clickgit.ui.main_window import MainWindow
        controller = AppController(
            settings_store=SettingsStore(data_dir / "settings.json"),
            git_executable=bundled_git_executable(),
        )
        app.aboutToQuit.connect(controller.shutdown)
        window = MainWindow(controller)
        window.show()
        return app.exec()
    except Exception:
        log_exception(*sys.exc_info())
        return 1
    finally:
        sys.excepthook, threading.excepthook = old_hook, old_thread_hook
        try:
            stop_all_previews()
            if controller is not None:
                controller.shutdown()
        finally:
            diagnostics.close()
            set_diagnostics(None)


if __name__ == "__main__":
    raise SystemExit(main())
