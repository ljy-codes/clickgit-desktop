"""WebEngine runs only in isolated child processes, with the sandbox unchanged.

Run with PYTHONPATH=src: python -B -m unittest tests.test_html_preview -v
Synthetic documents/URLs only. No HTTP server or temporary HTML files.
"""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HtmlPreviewTests(unittest.TestCase):
    def run_child(self, code, *, timeout=75):
        from clickgit.preview_process import ProcessTree
        self.assertIsNotNone(importlib.util.find_spec("clickgit.ui.html_preview"),
                             "HtmlPreview component is missing")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1",
                   PYTHONIOENCODING="utf-8")
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        # Own the synthetic renderer tree, not just its Python parent. Otherwise
        # a timeout may leave descendants holding stdout/stderr pipes open.
        # Suppress native fault dialogs only inside this disposable test helper.
        prefix = ("import sys,faulthandler\n"
                  "from clickgit.preview_process import initialize_worker\n"
                  "initialize_worker()\nsys.stdin.buffer.read()\n"
                  "faulthandler.dump_traceback_later(20)\n")
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", prefix + textwrap.dedent(code)], cwd=ROOT,
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        tree = None
        try:
            tree = ProcessTree(process.pid)
            try:
                stdout, stderr = process.communicate("", timeout=timeout)
            except subprocess.TimeoutExpired:
                tree.close()
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
                self.fail("Synthetic HTML helper timeout:\n" + stdout[-4000:] + stderr[-4000:])
        finally:
            if tree is not None:
                tree.close()
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stdout + "\n" + stderr)
        self.assertNotIn("Release of profile requested but WebEnginePage still not deleted",
                         stderr)
        return stdout

    def test_import_and_empty_widget_do_not_load_webengine(self):
        self.run_child("""
            import sys
            from clickgit.ui.html_preview import HtmlPreview
            assert not any(k.startswith("PySide6.QtWebEngine") for k in sys.modules)
            from PySide6.QtWidgets import QApplication
            app = QApplication([])
            widget = HtmlPreview()
            widget.clear()
            widget.dispose()
            widget.dispose()
            widget.set_source("<p>after dispose</p>")
            assert not any(k.startswith("PySide6.QtWebEngine") for k in sys.modules)
            assert widget._host is None
            assert "已释放" in widget.status_label.text()
        """)

    def test_missing_webengine_and_invalid_input_fail_closed(self):
        self.run_child("""
            from unittest.mock import patch
            from PySide6.QtWidgets import QApplication
            from clickgit.ui.html_preview import HtmlPreview
            app = QApplication([])
            widget = HtmlPreview()
            with patch("clickgit.ui.html_preview._load_webengine",
                       side_effect=ImportError("synthetic dependency unavailable")) as loader:
                widget.set_source("<p>safe</p>", "<b>not markup</b>")
                assert "不可用" in widget.status_label.text(), widget.status_label.text()
                assert widget._host is None
                widget.set_source("中" * 240000)
                assert "setHtml" in widget.status_label.text()
                assert loader.call_count == 1
                widget.set_source("\\ud800")
                assert "UTF-8" in widget.status_label.text()
                widget.clear()
                assert widget._host is None
                assert "未加载" in widget.status_label.text()
            widget.dispose()
        """)

    def test_source_has_no_eager_engine_import_or_escape_hatches(self):
        self.assertIsNotNone(importlib.util.find_spec("clickgit.ui.html_preview"),
                             "HtmlPreview component is missing")
        import ast
        path = ROOT / "src/clickgit/ui/html_preview.py"
        source = path.read_text("utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("QtWebEngine", node.module or "")
        for token in ("runJavaScript(", "setWebChannel(", "QWebChannel(",
                      "defaultProfile(", "QDesktopServices", "write_text(",
                      "write_bytes(", "TemporaryDirectory(", "HTTPServer("):
            self.assertNotIn(token, source)

    def test_unsafe_host_flags_refuse_initialization_without_mutating_environment(self):
        self.run_child("""
            import os
            import sys
            from unittest.mock import patch
            from PySide6.QtWidgets import QApplication
            from clickgit.ui.html_preview import HtmlPreview
            app = QApplication([])
            widget = HtmlPreview()
            for key, value in (
                ("QTWEBENGINE_DISABLE_SANDBOX", "1"),
                ("QTWEBENGINE_REMOTE_DEBUGGING", "9222"),
                ("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox"),
                ("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-web-security"),
            ):
                with patch.dict(os.environ, {key: value}):
                    widget.set_source("<p>synthetic</p>")
                    assert widget._host is None
                    assert "不安全" in widget.status_label.text()
                    assert os.environ[key] == value
            assert not any(k.startswith("PySide6.QtWebEngine") for k in sys.modules)
            widget.dispose()
        """)

    def test_real_load_failure_stale_callbacks_and_partial_setup_cleanup(self):
        self.run_child(r'''
            import time
            from unittest.mock import patch
            from PySide6.QtCore import QCoreApplication, QEvent
            from PySide6.QtWidgets import QApplication
            import clickgit.ui.html_preview as module
            app = QApplication([])
            widget = module.HtmlPreview()
            widget.show()
            def spin(predicate):
                end = time.monotonic() + 20
                while time.monotonic() < end:
                    app.processEvents()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    if predicate(): return
                    time.sleep(.01)
                raise AssertionError("Timed out: " + widget.status_label.text())
            widget.set_source("<p>OLD_SYNTHETIC</p>")
            spin(lambda: "已加载" in widget.status_label.text())
            old = widget._host
            V, R, P, I, S = module._load_webengine()
            class RejectDocument(I):
                def interceptRequest(self, info):
                    info.block(True)
            # A real Chromium load failure, not a direct call to _loaded(False).
            with patch.object(module, "_load_webengine", return_value=(V,R,P,RejectDocument,S)):
                widget.set_source("<p>REJECTED_SYNTHETIC</p>")
            rejected = widget._host
            spin(lambda: "加载失败" in widget.status_label.text())
            assert widget._host is None
            failed_status = widget.status_label.text()
            widget._loaded(old, True)
            widget._loaded(rejected, True)
            widget._failed(old, "stale error")
            assert widget.status_label.text() == failed_status
            widget.set_source("<p>NEW_SYNTHETIC</p>")
            current = widget._host
            widget._loaded(old, False)
            widget._failed(rejected, "stale error")
            assert widget._host is current
            spin(lambda: "已加载" in widget.status_label.text())
            widget._loaded(old, True)
            assert widget._host is current
            # Two sides must never share a profile or storage instance.
            other = module.HtmlPreview()
            other.set_source("<p>SECOND_SIDE</p>")
            assert other._host.profile is not current.profile
            other.dispose()
            other.deleteLater()
            # Exceptions after allocating a profile/page must retire the session.
            destroyed = []
            class BrokenView(V):
                def setHtml(self, *args):
                    self.page().destroyed.connect(lambda: destroyed.append("page"))
                    self.page().profile().destroyed.connect(lambda: destroyed.append("profile"))
                    raise RuntimeError("synthetic setHtml setup failure")
            with patch.object(module, "_load_webengine", return_value=(BrokenView,R,P,I,S)):
                widget.set_source("<p>PARTIAL_SETUP</p>")
            assert widget._host is None
            assert "不可用" in widget.status_label.text()
            spin(lambda: "profile" in destroyed)
            assert destroyed == ["page", "profile"], destroyed
            # Failure before attaching a page must not call view.stop(): that
            # convenience method can lazily create an unintended default page.
            unattached_stops = []
            class UnattachedView(V):
                def stop(self):
                    unattached_stops.append(True)
            class BrokenProfile(R):
                def setHttpCacheType(self, value):
                    raise RuntimeError("synthetic profile configuration failure")
            with patch.object(module, "_load_webengine",
                              return_value=(UnattachedView,BrokenProfile,P,I,S)):
                widget.set_source("<p>EARLY_SETUP</p>")
            assert widget._host is None
            assert not unattached_stops, "unattached view must not create a default page"
            # Timeout and renderer failure branches use the same fail-closed path.
            widget.set_source("<p>TIMEOUT_SYNTHETIC</p>")
            timed = widget._host
            timed.timer.timeout.emit()
            assert widget._host is None
            assert "超时" in widget.status_label.text()
            widget._loaded(timed, True)
            assert "超时" in widget.status_label.text()
            widget.set_source("<p>CRASH_SYNTHETIC</p>")
            crashed = widget._host
            # PySide cannot emit this native enum signal from Python without
            # registering its metatype; exercise the connected failure handler.
            widget._failed(crashed, "渲染进程已终止；请重新显式加载")
            assert widget._host is None
            assert "终止" in widget.status_label.text()
            widget.dispose()
            for _ in range(10):
                widget.dispose()
                widget._loaded(crashed, True)
                widget._loaded(old, False)
                widget._failed(current, "late")
                widget.clear()
            assert widget._host is None
            assert "已释放" in widget.status_label.text()
            widget.deleteLater()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        ''')

    def test_real_offscreen_static_load_security_and_lifecycle(self):
        self.run_child(r'''
            import gc
            import time
            from PySide6.QtCore import QCoreApplication, QEvent, QUrl, Qt
            from PySide6.QtWidgets import QApplication, QWidget
            import clickgit.ui.html_preview as module
            from clickgit.ui.html_preview import HtmlPreview
            assert not QCoreApplication.testAttribute(
                Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
            app = QApplication([])
            # Audit the real engine boundary; CSP should reject CSS URLs before
            # network. The interceptor still handles every request it receives.
            loader = module._load_webengine
            requests, console = [], []
            def audited_loader():
                V,R,P,I,S = loader()
                class AuditPage(P):
                    def javaScriptConsoleMessage(self, level, message, line, source):
                        console.append(message)
                class AuditInterceptor(I):
                    def interceptRequest(self, info):
                        requests.append((info.requestUrl().scheme(), info.resourceType()))
                        super().interceptRequest(info)
                return V,R,AuditPage,AuditInterceptor,S
            module._load_webengine = audited_loader

            def spin(predicate, seconds=20):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    app.processEvents()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    if predicate():
                        return
                    time.sleep(.01)
                raise AssertionError("Timed out")

            def load(widget, source, title="Synthetic"):
                widget.set_source(source, title)
                assert widget._host is not None, widget.status_label.text()
                spin(lambda: "加载中" not in widget.status_label.text())
                assert "已加载" in widget.status_label.text(), widget.status_label.text()
                return widget._host

            def text(page):
                out = []
                page.toPlainText(out.append)
                spin(lambda: bool(out))
                return out[0]

            widget = HtmlPreview()
            widget.resize(640, 480)
            widget.show()
            source = """<html><head><style>body {background: red; color: white}</style></head>
                <body style="background:rgb(18,52,86)">
                <h1 id="synthetic">STATIC_SENTINEL</h1>
                <script>document.body.textContent='EXECUTED_SENTINEL'</script>
                <p onclick="document.body.textContent='EVENT_EXECUTED'">static body</p>
                <a href="https://synthetic.invalid/path">inert link</a>
                <form class="filters"><label for="q">Filter</label>
                <input id="q" type="text" placeholder="Query" value="Synthetic">
                <input type="number" value="42"><select><option selected>All</option></select>
                <textarea rows="2">Synthetic note</textarea>
                <table><tr><td><button onclick="bad()">Inspect row</button></td></tr></table></form>
                <img src="file:///C:/synthetic-nonexistent.png">
                <style>@import url('https://synthetic.invalid/never.css');
                p {background-image:url(file:///C:/synthetic-nonexistent.png)}</style></body></html>"""
            host = load(widget, source)
            page, profile = host.page, host.profile
            assert "STATIC_SENTINEL" in text(page)
            assert "EXECUTED_SENTINEL" not in text(page)
            assert "Inspect row" in text(page)
            assert "静态不交互" in page.title()
            html = []
            page.toHtml(html.append)
            spin(lambda: bool(html))
            from html.parser import HTMLParser
            class Tags(HTMLParser):
                controls = []
                def handle_starttag(self, tag, attrs):
                    if tag in {"button", "input", "select", "textarea"}:
                        self.controls.append((tag, dict(attrs)))
            tags = Tags()
            tags.feed(html[0])
            assert len(tags.controls) == 5, tags.controls
            assert all("disabled" in attrs for _,attrs in tags.controls)
            assert "安全静态简化" in widget.status_label.text()
            assert "图片" in widget.status_label.text()
            assert profile.isOffTheRecord()
            assert profile.storageName() == ""
            from PySide6.QtWebEngineCore import (
                QWebEngineSettings as S, QWebEnginePage as P,
                QWebEngineProfile as R, QWebEngineUrlRequestInfo as I)
            for name in ("JavascriptEnabled", "JavascriptCanOpenWindows",
                         "JavascriptCanAccessClipboard", "JavascriptCanPaste",
                         "LocalStorageEnabled", "LocalContentCanAccessFileUrls",
                         "LocalContentCanAccessRemoteUrls", "PluginsEnabled",
                         "DnsPrefetchEnabled", "AutoLoadImages", "NavigateOnDropEnabled",
                         "WebGLEnabled", "FullScreenSupportEnabled", "ScreenCaptureEnabled"):
                assert not page.settings().testAttribute(getattr(S.WebAttribute, name)), name
            assert profile.httpCacheType() == R.HttpCacheType.NoCache
            assert profile.persistentCookiesPolicy() == R.PersistentCookiesPolicy.NoPersistentCookies
            assert profile.persistentPermissionsPolicy() == R.PersistentPermissionsPolicy.AskEveryTime
            assert page.webChannel() is None
            assert not host.view.acceptDrops()
            assert host.view.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu
            assert page.createWindow(P.WebWindowType.WebBrowserTab) is None
            assert page.chooseFiles(P.FileSelectionMode.FileSelectOpen, [], []) == []
            from PySide6.QtGui import QKeyEvent
            for key, modifiers in ((Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier),
                                   (Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier),
                                   (Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier)):
                event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
                assert widget.eventFilter(host.view.focusProxy(), event)
            assert any("Content Security Policy" in message for message in console), console
            assert all(scheme == "data" and kind == I.ResourceType.ResourceTypeMainFrame
                       for scheme, kind in requests), requests

            # Exact initial data document only, never a generic data: exception.
            for url in ("https://synthetic.invalid/", "http://127.0.0.1:9/",
                        "file:///C:/synthetic.txt", "qrc:/synthetic", "ftp://synthetic.invalid/",
                        "data:text/html,<script>bad()</script>", "javascript:bad()",
                        "blob:synthetic", "about:blank"):
                assert not page.acceptNavigationRequest(
                    QUrl(url), P.NavigationType.NavigationTypeOther, True), url
                class Request:
                    blocked = None
                    def requestUrl(self): return QUrl(url)
                    def resourceType(self): return I.ResourceType.ResourceTypeMainFrame
                    def block(self, value): self.blocked = value
                request = Request()
                host.interceptor.interceptRequest(request)
                assert request.blocked is True, url
            # Child frames and reload cannot reuse even the admitted document.
            assert not page.acceptNavigationRequest(
                QUrl(host.document_url), P.NavigationType.NavigationTypeReload, True)
            assert not page.acceptNavigationRequest(
                QUrl(host.document_url), P.NavigationType.NavigationTypeOther, False)

            # No diagnostic JS is used: inspect CSS output through a real widget grab.
            spin(lambda: host.view.grab().toImage().pixelColor(600, 350).name() == "#123456")
            baseline = text(page)
            app.processEvents()
            assert text(page) == baseline

            order = []
            page.destroyed.connect(lambda: order.append("page"))
            profile.destroyed.connect(lambda: order.append("profile"))
            widget.set_source("中" * 240000)
            assert widget._host is None
            assert "setHtml" in widget.status_label.text()
            spin(lambda: "profile" in order)
            assert order.index("page") < order.index("profile"), order
            new_host = load(widget, "<p>NEW_SENTINEL</p>")
            assert "NEW_SENTINEL" in text(new_host.page)
            widget.clear()
            assert widget._host is None
            assert "未加载" in widget.status_label.text()
            # Parent destruction also must preserve page-before-profile order.
            parent = QWidget()
            child = HtmlPreview(parent)
            h = load(child, "<p>parent owned</p>")
            order2 = []
            h.page.destroyed.connect(lambda: order2.append("page"))
            h.profile.destroyed.connect(lambda: order2.append("profile"))
            parent.deleteLater()
            spin(lambda: "profile" in order2)
            assert order2 == ["page", "profile"], order2
            # Rapid explicit refresh / clear / dispose during a pending load.
            for i in range(6):
                widget.set_source("<p>rapid synthetic %d</p>" % i)
                widget.clear()
            widget.set_source("<p>pending</p>")
            widget.dispose()
            widget.dispose()
            widget.set_source("<p>must not revive</p>")
            assert widget._host is None
            assert "已释放" in widget.status_label.text()
            widget.deleteLater()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            gc.collect()
            print("REAL_WEBENGINE_SMOKE_OK")
        ''', timeout=120)


if __name__ == "__main__":
    unittest.main()
