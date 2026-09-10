"""Opt-in static HTML preview, never a browser or a local application bridge.

GUI-thread API: HtmlPreview(parent=None), set_source(source, title=""), clear(),
dispose(). Create only on an explicit user click. Even construction/clear do
not import WebEngine; only a valid set_source does. There is no automatic
refresh. clear releases the render session; dispose is idempotent and terminal.

The whitelist policy deliberately simplifies HTML; inline CSS still renders.
No application file/network I/O, HTTP server, borrowed browser profile or JS.
QtWebEngineProcess and Chromium may themselves use OS temporary/runtime files;
off-the-record means no persistent browsing data, not a diskless Chromium.

Packaging: retain PySide6.QtWebEngineCore/Widgets and their PyInstaller hooks,
QtWebEngineProcess, resources (including ICU) and locales. Missing components
show an explicit unavailable message. Never turn off the Chromium sandbox.
Test frozen bundles on the target OS; a fatal native initialization failure
cannot be caught by Python. GUI event processing is required for deleteLater.
"""

from __future__ import annotations

import os
from urllib.parse import quote

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from clickgit.html_preview_policy import (
    DATA_URL_PREFIX, NOTICE, PreviewPolicyError, prepare_html,
)

__all__ = ["HtmlPreview"]


def _load_webengine():
    """Late imports also let PyInstaller discover the optional Qt hooks."""
    from PySide6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
        QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView

    class StaticPage(QWebEnginePage):
        def __init__(self, profile, parent, document_url):
            super().__init__(profile, parent)
            self._document_url = QUrl(document_url)
            self.pending_document = True

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            allowed = (
                self.pending_document and is_main_frame
                and navigation_type in (
                    self.NavigationType.NavigationTypeTyped,
                    self.NavigationType.NavigationTypeOther,
                )
                and url == self._document_url
            )
            if allowed:
                self.pending_document = False
            return bool(allowed)

        def createWindow(self, window_type):
            return None

        def chooseFiles(self, mode, old_files, accepted_mime_types):
            return []

        def javaScriptAlert(self, security_origin, msg):
            pass

        def javaScriptConfirm(self, security_origin, msg):
            return False

        def javaScriptPrompt(self, security_origin, msg, default_value):
            return False, ""

        def javaScriptConsoleMessage(self, level, message, line_number, source_id):
            # Do not leak supplied text, URLs or source paths to application logs.
            pass

    class StaticInterceptor(QWebEngineUrlRequestInterceptor):
        def __init__(self, parent, document_url):
            super().__init__(parent)
            self._document_url = QUrl(document_url)
            self.pending_document = True

        def interceptRequest(self, info):
            # One exact, generated top-level data URL. ALL subresources, even
            # data:/blob:/qrc:/file: or the same URL as an iframe, are blocked.
            allowed = (
                self.pending_document
                and info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame
                and info.requestUrl() == self._document_url
            )
            if allowed:
                self.pending_document = False
            info.block(not allowed)

    return QWebEngineView, QWebEngineProfile, StaticPage, StaticInterceptor, QWebEngineSettings


class HtmlPreview(QWidget):
    def __init__(self, parent: QWidget | None = None, *, compact=False) -> None:
        super().__init__(parent)
        self._compact = compact
        self._zoom_factor = 1.0
        self._search_generation = 0
        self._host = None
        self._disposed = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel(self)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setOpenExternalLinks(False)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._layout.addWidget(self.status_label)
        self._set_status("未加载")
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.dispose)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message if self._compact else f"{message}\n{NOTICE}")
        self.status_label.setToolTip(NOTICE)

    def set_zoom_factor(self, value: float) -> None:
        if type(value) not in (int, float) or not 0.5 <= value <= 1.5:
            raise ValueError("Preview zoom must be between 0.5 and 1.5")
        self._zoom_factor = float(value)
        if self._host is not None:
            self._host.view.setZoomFactor(self._zoom_factor)

    def find_marker(self, text: str, callback) -> None:
        """Native browser search only; never execute scripts for navigation."""
        self._search_generation += 1
        generation, host = self._search_generation, self._host
        if host is None or self._disposed or len(text) > 128:
            callback(False)
            return

        def found(result):
            if self._host is host and generation == self._search_generation and not self._disposed:
                callback(result.numberOfMatches() > 0)

        # Reset first so selecting the same item locates its first marker again.
        host.page.findText("")
        host.page.findText(text, host.page.FindFlag.FindCaseSensitively, found)

    def _retire(self) -> None:
        self._search_generation += 1
        host, self._host = self._host, None  # Invalidate callbacks before stop().
        if host is None:
            return
        host.hide()
        host.setEnabled(False)
        self._layout.removeWidget(host)
        if hasattr(host, "timer"):
            host.timer.stop()
        if hasattr(host, "interceptor"):
            host.interceptor.pending_document = False
        if hasattr(host, "page"):
            host.page.pending_document = False
            # Calling view.stop() before setPage() would lazily create an
            # unintended default page/profile on an early setup failure.
            host.page.triggerAction(host.page.WebAction.Stop)
        # Do NOT delete profile first. QObject child order is intentional:
        # host -> view -> page, then host -> profile -> interceptor.
        host.deleteLater()

    def clear(self) -> None:
        self._retire()
        self._set_status("已释放" if self._disposed else "未加载")

    def dispose(self) -> None:
        self._disposed = True
        self.clear()

    def set_source(self, source: str, title: str = "") -> None:
        if self._disposed:
            self._set_status("已释放；请重新创建预览组件")
            return
        self._retire()
        try:
            document = prepare_html(source, title)
        except PreviewPolicyError as exc:
            self._set_status(str(exc))
            return
        # Refuse unsafe host configuration; never rewrite global Chromium flags.
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").lower()
        if (os.environ.get("QTWEBENGINE_DISABLE_SANDBOX", "")
                or os.environ.get("QTWEBENGINE_REMOTE_DEBUGGING", "")
                or any(flag in flags for flag in (
                    "--no-sandbox", "--disable-web-security", "--remote-debugging",
                    "--disable-site-isolation", "--single-process",
                ))):
            self._set_status("预览不可用：检测到不安全的 Chromium 沙箱或调试配置")
            return
        self._set_status("加载中")
        try:
            self._create_session(document)
        except Exception:
            # Optional DLL/API/setup errors must fail closed, without echoing
            # source, local install paths or native error details into the UI.
            self._retire()
            self._set_status("QtWebEngine 不可用或安全设置失败；请使用 HTML 源码视图")

    def _create_session(self, document: str) -> None:
        View, Profile, Page, Interceptor, Settings = _load_webengine()
        host = QWidget(self)
        self._host = host  # Also ensures partially initialized sessions retire.
        host.hide()
        self._layout.addWidget(host, 1)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        # view MUST be the first engine child; page is owned by view.
        host.view = View(host)
        host.profile = Profile(host)  # No storage name => off-the-record.
        if not host.profile.isOffTheRecord():
            raise RuntimeError("An off-the-record profile is required")
        host.profile.setHttpCacheType(Profile.HttpCacheType.NoCache)
        host.profile.setPersistentCookiesPolicy(Profile.PersistentCookiesPolicy.NoPersistentCookies)
        host.profile.setPersistentPermissionsPolicy(Profile.PersistentPermissionsPolicy.AskEveryTime)
        host.profile.setSpellCheckEnabled(False)
        # Qt's cookie filter also denies IndexedDB, DOM storage, service workers,
        # filesystem API and other third-party storage accesses.
        host.profile.cookieStore().setCookieFilter(lambda request: False)
        host.profile.downloadRequested.connect(lambda download: download.cancel())
        host.document_url = DATA_URL_PREFIX + quote(document, safe="-._~")
        host.interceptor = Interceptor(host.profile, host.document_url)
        host.profile.setUrlRequestInterceptor(host.interceptor)
        host.page = Page(host.profile, host.view, host.document_url)
        settings = host.page.settings()
        # Missing security attributes are an error, not a silently weaker mode.
        for name in (
            "AutoLoadImages", "JavascriptEnabled", "JavascriptCanOpenWindows",
            "JavascriptCanAccessClipboard", "JavascriptCanPaste", "LocalStorageEnabled",
            "LocalContentCanAccessRemoteUrls", "LocalContentCanAccessFileUrls",
            "HyperlinkAuditingEnabled", "PluginsEnabled", "FullScreenSupportEnabled",
            "ScreenCaptureEnabled", "WebGLEnabled", "Accelerated2dCanvasEnabled",
            "AutoLoadIconsForPage", "TouchIconsEnabled", "AllowRunningInsecureContent",
            "AllowGeolocationOnInsecureOrigins", "AllowWindowActivationFromJavaScript",
            "DnsPrefetchEnabled", "PdfViewerEnabled", "NavigateOnDropEnabled",
            "ReadingFromCanvasEnabled", "LinksIncludedInFocusChain",
            "BackForwardCacheEnabled", "TouchEventsApiEnabled",
        ):
            settings.setAttribute(getattr(Settings.WebAttribute, name), False)
        settings.setAttribute(Settings.WebAttribute.PlaybackRequiresUserGesture, True)
        settings.setUnknownUrlSchemePolicy(Settings.UnknownUrlSchemePolicy.DisallowUnknownUrlSchemes)
        host.page.permissionRequested.connect(lambda permission: permission.deny())
        host.page.fileSystemAccessRequested.connect(lambda request: request.reject())
        host.page.quotaRequested.connect(lambda request: request.reject())
        host.page.registerProtocolHandlerRequested.connect(lambda request: request.reject())
        host.page.fullScreenRequested.connect(lambda request: request.reject())
        host.page.desktopMediaRequested.connect(lambda request: request.cancel())
        host.page.certificateError.connect(lambda error: error.rejectCertificate())
        host.page.selectClientCertificate.connect(lambda selection: selection.selectNone())
        host.page.authenticationRequired.connect(lambda url, auth: self._deny_auth(auth))
        host.page.proxyAuthenticationRequired.connect(
            lambda url, auth, proxy: self._deny_auth(auth))
        host.page.webAuthUxRequested.connect(lambda request: request.cancel())
        # Unaccepted newWindowRequested creates no page. No print/dialog handlers.
        host.view.setPage(host.page)
        host.view.setZoomFactor(self._zoom_factor)
        host.view.setAcceptDrops(False)
        host.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        host.view.installEventFilter(self)
        if host.view.focusProxy() is not None:
            host.view.focusProxy().installEventFilter(self)
        layout.addWidget(host.view)
        # Remove built-in copy/save/download/reload actions as well as shortcuts.
        for action in host.page.WebAction:
            if action not in (host.page.WebAction.NoWebAction, host.page.WebAction.WebActionCount):
                host.page.action(action).setEnabled(False)
        host.page.loadFinished.connect(lambda ok: self._loaded(host, ok))
        host.page.renderProcessTerminated.connect(
            lambda status, code: self._failed(host, "渲染进程已终止；请重新显式加载"))
        host.timer = QTimer(host)
        host.timer.setSingleShot(True)
        host.timer.setInterval(15000)
        host.timer.timeout.connect(lambda: self._failed(host, "静态预览加载超时，未显示内容"))
        host.timer.start()
        host.view.setHtml(document, QUrl())

    @staticmethod
    def _deny_auth(auth) -> None:
        auth.setUser("")
        auth.setPassword("")

    def _loaded(self, host, ok: bool) -> None:
        if self._host is not host or self._disposed:
            return
        host.timer.stop()
        host.interceptor.pending_document = False
        host.page.pending_document = False
        if not ok:
            self._failed(host, "静态预览加载失败，未显示内容")
            return
        host.page.history().clear()
        # Qt can re-enable actions when a load/selection changes.
        for action in host.page.WebAction:
            if action not in (host.page.WebAction.NoWebAction, host.page.WebAction.WebActionCount):
                host.page.action(action).setEnabled(False)
        host.show()
        self._set_status("已加载")

    def _failed(self, host, message: str) -> None:
        if self._host is host and not self._disposed:
            self._retire()
            self._set_status(message)

    def eventFilter(self, watched, event) -> bool:
        # Chromium's inner render widget receives keyboard/clipboard shortcuts.
        # Keep scrolling, but never copy/paste, reload, print, save or open links.
        if event.type() in (
            QEvent.Type.ContextMenu, QEvent.Type.DragEnter, QEvent.Type.DragMove,
            QEvent.Type.Drop, QEvent.Type.Shortcut, QEvent.Type.ShortcutOverride,
        ):
            event.accept()
            return True
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if (event.modifiers() != Qt.KeyboardModifier.NoModifier
                    or event.key() not in (
                        Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                        Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home,
                        Qt.Key.Key_End, Qt.Key.Key_Space,
                    )):
                event.accept()
                return True
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            if event.button() != Qt.MouseButton.LeftButton:
                event.accept()
                return True
        return super().eventFilter(watched, event)
