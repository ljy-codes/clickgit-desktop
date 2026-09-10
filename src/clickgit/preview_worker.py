"""Private child entry point. No Git, settings, disk HTML or network bridge."""
from __future__ import annotations

import json
import os
import sys

from clickgit.preview_process import initialize_worker, read_request, write_status


def _emit(event, **fields):
    write_status(json.dumps({"event": event, **fields}, ensure_ascii=True).encode("ascii") + b"\n")


def run_preview_worker() -> int:
    try:
        initialize_worker()
        if sys.platform != "win32":
            # Windows job handles also cover abrupt parent death. POSIX needs
            # its own orphan watcher in addition to parent's normal killpg().
            import signal
            import threading
            import time
            owner = os.getppid()

            def watch_parent():
                while os.getppid() == owner and owner != 1:
                    time.sleep(.5)
                os.killpg(os.getpid(), signal.SIGKILL)

            threading.Thread(target=watch_parent, daemon=True).start()
        request = json.loads(read_request())
        if (type(request) is not dict or set(request) != {
                "left", "right", "left_title", "right_title"}
                or any(type(value) is not str for value in request.values())):
            raise ValueError
        if any(len(request[key]) > 512 for key in ("left_title", "right_title")):
            raise ValueError
    except Exception:
        try:
            _emit("failed")
        except OSError:
            pass
        return 2

    from PySide6.QtCore import QCoreApplication, Qt, QTimer
    from PySide6.QtWidgets import QApplication
    from clickgit.branding import apply_branding
    from clickgit.ui.html_preview_window import HtmlPreviewWindow

    if QApplication.instance() is None:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    apply_branding(app)
    app.setStyle("Fusion")
    try:
        window = HtmlPreviewWindow(request)
    except Exception:
        _emit("failed")
        return 2
    previews = window.previews
    seen_text = {}
    requested_text = ready = failed = False

    def send(event, **fields):
        try:
            _emit(event, **fields)
        except OSError:
            app.quit()

    def poll():
        nonlocal requested_text, ready, failed
        if failed:
            return
        states = [preview.status_label.text().split("\n", 1)[0] for preview in previews]
        if any(state not in ("已加载", "加载中", "未加载") for state in states):
            failed = True
            send("failed")
            app.quit()
            return
        if all(state == "已加载" for state in states) and not ready:
            if not requested_text:
                requested_text = True
                for index, preview in enumerate(previews):
                    # Only boolean presence crosses IPC, never extracted text.
                    preview._host.page.toPlainText(
                        lambda text, i=index: seen_text.__setitem__(i, bool(text.strip())))
            elif len(seen_text) == 2:
                hosts = [preview._host for preview in previews]
                checks = {
                    "previews_loaded": 2,
                    "javascript_disabled": all(
                        not host.page.settings().testAttribute(
                            host.page.settings().WebAttribute.JavascriptEnabled) for host in hosts),
                    "profiles_off_record": all(host.profile.isOffTheRecord() for host in hosts),
                    "local_access_disabled": all(
                        not host.page.settings().testAttribute(
                            getattr(host.page.settings().WebAttribute, name))
                        for host in hosts for name in ("LocalContentCanAccessFileUrls",
                                                      "LocalContentCanAccessRemoteUrls",
                                                      "LocalStorageEnabled")),
                    "visible_text_verified": all(seen_text.values()),
                }
                ready = True
                window.mark_ready()
                send("ready", checks=checks)
        send("tick")

    def load():
        try:
            window.load()
        except Exception:
            send("failed")
            app.quit()

    timer = QTimer(window)
    timer.setInterval(500)
    timer.timeout.connect(poll)
    timer.start()
    app.aboutToQuit.connect(lambda: send("closed"))
    window.finished.connect(app.quit)
    window.show()
    QTimer.singleShot(0, load)
    app.exec()
    return 0 if not failed else 1
