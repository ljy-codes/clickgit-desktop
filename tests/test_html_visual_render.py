import unittest
import sys

from tests import test_html_preview


class HtmlVisualRenderTests(unittest.TestCase):
    def run_child(self, code, **kwargs):
        if sys.platform == "win32":
            # Rapid native find/scroll under Qt's offscreen Windows backend
            # reproducibly loses its D3D context. Exercise the actual product
            # backend instead, without showing test windows to the user.
            # Keep sandbox/GPU flags unchanged; existing policy tests continue
            # to cover offscreen rendering separately.
            code = code.replace(
                "app = QApplication([])",
                'import os; os.environ["QT_QPA_PLATFORM"] = "windows"; app = QApplication([])')
            code = code.replace(
                "window.show()",
                "window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True); window.show()")
        return test_html_preview.HtmlPreviewTests.run_child(self, code, **kwargs)

    def extra_window_case(self, left, right, expectation):
        prefix = f"LEFT = {left!r}\nRIGHT = {right!r}\nEXPECTATION = {expectation!r}\n"
        self.run_child(prefix + r'''
import time
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from clickgit.ui.html_preview_window import HtmlPreviewWindow
app = QApplication([])
def spin(predicate):
    start = time.monotonic()
    while not predicate():
        app.processEvents()
        time.sleep(.01)
        assert time.monotonic() - start < 10, "search verification timeout"
window = HtmlPreviewWindow(dict(left=LEFT, right=RIGHT, left_title="Before", right_title="After"))
window.show()
window.load()
spin(lambda: all(p.status_label.text() == "已加载" for p in window.previews))
window.mark_ready()
spin(lambda: all("正在定位" not in l.text() for l in window.location_labels))
assert all(EXPECTATION in l.text() for l in window.location_labels), [l.text() for l in window.location_labels]
window.close()
for p in window.previews:
    p.dispose()
window.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
''', timeout=60)

    def test_search_hit_does_not_claim_opacity_or_clipping_is_visible(self):
        for style in ("opacity:0", "height:0;overflow:hidden"):
            with self.subTest(style=style):
                old = f'<p>Visible heading</p><div style="{style}">Hidden old</div>'
                self.extra_window_case(old, old.replace("old", "new"), "仍不可见")

    def test_lowercase_similar_marker_cannot_redirect_search(self):
        old = '<p>[cg改动1] same</p><div style="display:none">Hidden old</div>'
        self.extra_window_case(old, old.replace("old", "new"), "未找到可见标记")

    def test_hidden_first_group_node_still_finds_visible_changed_node(self):
        old = '<div style="display:none">Hidden old</div><p>Visible old</p>'
        self.extra_window_case(old, old.replace("old", "new"), "已找到改动标记")

    def test_real_renderer_markers_navigation_zoom_and_hidden_details(self):
        self.run_child(r'''
            import time
            from PySide6.QtCore import QCoreApplication, QEvent, Qt
            from PySide6.QtWidgets import QApplication
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
            from clickgit.ui.html_preview_window import HtmlPreviewWindow
            app = QApplication([])
            def spin(predicate):
                start = time.monotonic()
                while not predicate():
                    app.processEvents()
                    time.sleep(.01)
                    assert time.monotonic() - start < 14, "visual comparison timeout"
            left = ('<style>body{font:18px sans-serif}.hidden{display:none}</style>'
                    '<h1>Work configuration</h1><p>Hours: 3</p>'
                    '<p>Shared separator</p><div class="hidden">Limit: 10</div>')
            right = left.replace("Hours: 3", "Hours: 5").replace("Limit: 10", "Limit: 20")
            window = HtmlPreviewWindow(dict(left=left,right=right,left_title="Before",right_title="After"))
            window.show()
            window.load()
            spin(lambda: all(p.status_label.text() == "已加载" for p in window.previews))
            print("TRACE loaded", flush=True)
            assert len(window.comparison.changes) == 2
            assert window.detail_left.toPlainText() == "Hours: 3"
            window.mark_ready()
            spin(lambda: all("已找到改动标记" in label.text() for label in window.location_labels))
            print("TRACE first marker", flush=True)
            for preview in window.previews:
                assert abs(preview._host.view.zoomFactor() - .67) < .001
                settings = preview._host.page.settings()
                assert not settings.testAttribute(settings.WebAttribute.JavascriptEnabled)
            # Selecting the same change repeatedly must not exhaust browser search.
            window.locate_current()
            spin(lambda: all("已找到改动标记" in label.text() for label in window.location_labels))
            print("TRACE repeat marker", flush=True)
            window.next_button.click()
            spin(lambda: all("隐藏" in label.text() for label in window.location_labels))
            print("TRACE hidden", flush=True)
            assert window.detail_right.toPlainText() == "Limit: 20"
            window.previous_button.click()
            spin(lambda: all("已找到改动标记" in label.text() for label in window.location_labels))
            print("TRACE previous", flush=True)
            window.zoom_combo.setCurrentIndex(window.zoom_combo.findData(1.0))
            print("TRACE zoom set", flush=True)
            assert all(p._host.view.zoomFactor() == 1.0 for p in window.previews)
            contents = []
            window.previews[0]._host.page.toHtml(contents.append)
            spin(lambda: bool(contents))
            print("TRACE read markup", flush=True)
            assert "background-color:" in contents[0]
            assert window.comparison.changes[0].marker in contents[0]
            # Visible marker contents are only in the private child, not IPC/logs.
            assert left.endswith('Limit: 10</div>')
            window.close()
            print("TRACE close", flush=True)
            for p in window.previews:
                p.dispose()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            print("VISUAL_DIFF_RENDER_OK")
        ''', timeout=70)


if __name__ == "__main__":
    unittest.main()
