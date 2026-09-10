"""Explicit, synthetic-only HTML diagnostic for source and frozen builds."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication

from clickgit.document_workflow import TextComparison
from clickgit.ui.html_review import HtmlReviewDialog


def write_html_diagnostic(report_path: Path) -> int:
    if QApplication.instance() is None:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    source = ('<!doctype html><html><head><style>body{font:16px sans-serif}'
              '.prd-body{display:none}button{color:blue}</style></head><body>'
              '<h1>Static prototype</h1><button onclick="document.title=\'unsafe\'">Disabled</button>'
              '<div class="prd-body"><h2>Requirements</h2><p>Limit 3</p></div>'
              '<script>document.title="unsafe"</script></body></html>')
    result = source.replace("Limit 3", "Limit 5")
    dialog = HtmlReviewDialog(TextComparison("synthetic.html", source, result, "Before", "After"))
    dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    dialog.show()
    lazy = not dialog.preview_widgets
    dialog.tabs.setCurrentIndex(3)
    dialog.preview_button.click()
    timer = QTimer()
    timer.setInterval(50)
    ticks = 0
    payload = {
        "success": False, "synthetic_material_only": True,
        "interactive_preview_enabled": False, "ai_used": False,
        "preview_lazy_before_click": lazy,
    }
    def finish(timed_out=False):
        timer.stop()
        session = dialog.preview_session
        checks = session.ready_details
        javascript_disabled = checks.get("javascript_disabled", False)
        profiles_off_record = checks.get("profiles_off_record", False)
        local_access_disabled = checks.get("local_access_disabled", False)
        loaded = checks.get("previews_loaded", 0)
        unchanged = dialog.pair.left == source and dialog.pair.right == result
        text_verified = checks.get("visible_text_verified", False)
        engine_in_parent = any(name.startswith("PySide6.QtWebEngine") for name in sys.modules)
        payload.update(
            success=not timed_out and session.state == "ready" and loaded == 2 and javascript_disabled and
                    profiles_off_record and local_access_disabled and unchanged and lazy and
                    text_verified and not engine_in_parent,
            previews_loaded=loaded, state=session.state, javascript_disabled=javascript_disabled,
            profiles_off_record=profiles_off_record, local_access_disabled=local_access_disabled,
            source_unchanged=unchanged, timed_out=timed_out,
            visible_text_verified=text_verified,
            main_process_webengine_loaded=engine_in_parent,
            isolated_preview=True, failure_reason=session.failure_reason,
            complete_security_audit=False, real_install_uninstall_tested=False,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        dialog.reject()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QTimer.singleShot(50, app.quit)

    def poll():
        nonlocal ticks
        ticks += 1
        if dialog.preview_session.state in ("ready", "failed", "closed"):
            finish()
        elif ticks >= 600:
            finish(True)

    timer.timeout.connect(poll)
    timer.start()
    app.exec()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return 0 if payload["success"] else 1
