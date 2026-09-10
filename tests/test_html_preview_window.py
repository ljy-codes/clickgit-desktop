import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from clickgit.ui.html_preview_window import HtmlPreviewWindow


class FakePreview(QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.status_label = QLabel("已加载", self)
        self.zoom = 1.0
        self.source = ""
        self.searches = []
        self.found = True

    def set_source(self, source, title=""):
        self.source = source

    def set_zoom_factor(self, value):
        self.zoom = value

    def find_marker(self, text, callback):
        self.searches.append(text)
        callback(self.found)


class HtmlPreviewWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def window(self, left="<p>旧</p>", right="<p>新</p>"):
        with patch("clickgit.ui.html_preview_window.HtmlPreview", FakePreview):
            window = HtmlPreviewWindow({
                "left": left, "right": right,
                "left_title": "<b>上次提交</b>", "right_title": "当前工作文件（未暂存）"})
        self.addCleanup(window.close)
        self.addCleanup(window.deleteLater)
        return window

    def test_titles_are_explicit_plain_text_and_detail_always_visible(self):
        window = self.window()
        self.assertEqual(window.version_labels[0].textFormat(), Qt.TextFormat.PlainText)
        self.assertIn("左", window.version_labels[0].text())
        self.assertIn("<b>上次提交</b>", window.version_labels[0].text())
        self.assertIn("旧", window.detail_left.toPlainText())
        self.assertIn("新", window.detail_right.toPlainText())
        self.assertTrue(window.detail_left.isReadOnly())
        self.assertEqual(window.change_combo.count(), 1)

    def test_navigation_initial_and_boundaries_and_no_stale_callbacks(self):
        window = self.window("<p>A</p><p>same</p><p>B</p>",
                             "<p>C</p><p>same</p><p>D</p>")
        self.assertFalse(window.previous_button.isEnabled())
        self.assertTrue(window.next_button.isEnabled())
        window.mark_ready()
        window.next_button.click()
        self.assertEqual(window.change_combo.currentIndex(), 1)
        self.assertFalse(window.next_button.isEnabled())
        self.assertTrue(window.previous_button.isEnabled())
        self.assertIn("B", window.detail_left.toPlainText())
        self.assertEqual(window.previews[0].searches[-1], window.comparison.changes[1].marker)

    def test_hidden_or_unmarkable_content_has_explicit_location_status(self):
        window = self.window()
        window.previews[0].found = False
        window.mark_ready()
        self.assertIn("隐藏", window.location_labels[0].text())
        self.assertIn("已找到改动标记", window.location_labels[1].text())
        self.assertIn("仍不可见", window.location_labels[1].text())
        window = self.window("", "<p>新增</p>")
        window.mark_ready()
        self.assertIn("无对应正文", window.location_labels[0].text())

    def test_both_pages_zoom_and_single_side_mode_preserve_other_content(self):
        window = self.window()
        window.zoom_combo.setCurrentIndex(window.zoom_combo.findData(1.0))
        self.assertEqual([p.zoom for p in window.previews], [1.0, 1.0])
        window.view_combo.setCurrentIndex(1)
        self.assertFalse(window.panels[0].isHidden())
        self.assertTrue(window.panels[1].isHidden())
        window.view_combo.setCurrentIndex(2)
        self.assertTrue(window.panels[0].isHidden())
        self.assertFalse(window.panels[1].isHidden())
        window.view_combo.setCurrentIndex(0)
        self.assertTrue(all(not p.isHidden() for p in window.panels))

    def test_no_text_change_does_not_claim_whole_file_equal(self):
        window = self.window('<p class="old">same</p>', '<p class="new">same</p>')
        self.assertEqual(window.change_combo.count(), 0)
        self.assertFalse(window.locate_button.isEnabled())
        self.assertIn("源码", window.summary_label.text())
        self.assertNotIn("完全相同", window.summary_label.text())

    def test_location_status_has_reserved_height_to_avoid_resizing_renderer(self):
        window = self.window()
        for label in window.location_labels:
            self.assertGreater(label.minimumHeight(), 0)
            self.assertEqual(label.minimumHeight(), label.maximumHeight())

    def test_delayed_search_results_cannot_replace_new_selection_status(self):
        window = self.window("<p>A</p><p>same</p><p>B</p>",
                             "<p>C</p><p>same</p><p>D</p>")
        callbacks = []
        for preview in window.previews:
            preview.find_marker = lambda text, callback: callbacks.append(callback)
        window.mark_ready()
        window.next_button.click()
        for callback in callbacks[:2]:
            callback(False)
        self.assertTrue(all("正在定位" in label.text() for label in window.location_labels))
        for callback in callbacks[2:]:
            callback(True)
        self.assertTrue(all("已找到改动标记" in label.text() for label in window.location_labels))


if __name__ == "__main__":
    unittest.main()
