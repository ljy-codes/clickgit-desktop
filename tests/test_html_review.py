import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from clickgit.document_workflow import TextComparison
from clickgit.ui.html_review import HtmlReviewDialog, is_html_path


def html(body, css=""):
    return '<html><head><style>' + css + '</style></head><body>\n<div class="prd-body">\n' + body + '\n</div></body></html>'


class HtmlReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self, left, right, **kwargs):
        widget = HtmlReviewDialog(TextComparison("需求.HTML", left, right, "原版本", "新版本"), **kwargs)
        self.addCleanup(self.cleanup_dialog, widget)
        return widget

    @staticmethod
    def cleanup_dialog(dialog):
        dialog.reject()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_extension_is_explicit_not_html_content_sniffing(self):
        self.assertTrue(is_html_path("目录/a.HTM"))
        self.assertTrue(is_html_path("a.html"))
        self.assertFalse(is_html_path("a.html.txt"))

    def test_hidden_prd_is_default_view_without_loading_browser(self):
        dialog = self.dialog(html("<h2>规则</h2><p>原规则</p>"),
                             html("<h2>规则</h2><p>新规则</p>"))
        self.assertEqual(dialog.tabs.tabText(0), "需求对比")
        self.assertIn("新规则", dialog.requirements_viewer.right_editor.toPlainText())
        self.assertEqual(dialog.preview_widgets, [])
        self.assertTrue(dialog.source_left.isReadOnly())
        self.assertTrue(dialog.source_right.isReadOnly())

    def test_missing_section_has_empty_side_and_source_locator(self):
        dialog = self.dialog(html("<h2>旧章</h2><p>旧段</p>"),
                             html("<h2>旧章</h2><p>旧段</p>\n<h2>新增章</h2><p>新增段</p>"))
        row = next(i for i in range(dialog.section_list.count())
                   if "新增章" in dialog.section_list.item(i).text())
        dialog.section_list.setCurrentRow(row)
        # Aligned diff rows may contain display-only empty line placeholders.
        self.assertEqual(dialog.requirements_viewer.left_editor.toPlainText().strip(), "")
        dialog.locate_button.click()
        self.assertEqual(dialog.source_right.textCursor().blockNumber(), 3)
        self.assertEqual(dialog.source_right.toPlainText(), dialog.pair.right)

    def test_css_only_change_keeps_source_gate_and_scope_warning(self):
        dialog = self.dialog(html("<h2>规则</h2><p>相同</p>", "p{color:red}"),
                             html("<h2>规则</h2><p>相同</p>", "p{color:blue}"))
        self.assertIn("仅正文", dialog.warning_label.text())
        self.assertNotEqual(dialog.source_left.toPlainText(), dialog.source_right.toPlainText())
        self.assertTrue(dialog.source_viewer.comparison_loaded)

    def test_first_changed_section_selected_instead_of_unchanged_intro(self):
        dialog = self.dialog(html("<h2>概览</h2><p>相同</p><h2>规则</h2><p>旧</p>"),
                             html("<h2>概览</h2><p>相同</p><h2>规则</h2><p>新</p>"))
        self.assertIn("[修改]", dialog.section_list.currentItem().text())
        self.assertIn("新", dialog.requirements_viewer.right_editor.toPlainText())

    def test_analysis_failure_does_not_hide_source_or_claim_equal(self):
        with patch("clickgit.ui.html_review.analyze_html", side_effect=ValueError("测试解析预算")):
            dialog = self.dialog("<p>原</p>", "<p>新</p>")
        self.assertIn("测试解析预算", dialog.warning_label.text())
        self.assertEqual(dialog.source_right.toPlainText(), "<p>新</p>")
        self.assertFalse(dialog.locate_button.isEnabled())

    def test_result_check_can_switch_base_without_altering_result(self):
        right = html("<h2>结果</h2>")
        dialog = self.dialog(html("<h2>当前</h2>"), right,
                             baselines=(("当前侧", html("<h2>当前</h2>")),
                                        ("对方侧", html("<h2>对方</h2>")),
                                        ("共同基准", html("<h2>基准</h2>"))))
        dialog.baseline_combo.setCurrentIndex(2)
        self.assertIn("基准", dialog.pair.left)
        self.assertEqual(dialog.pair.right, right)

    def test_long_source_rejected_by_diff_is_not_replaced_with_extraction(self):
        dialog = self.dialog(html("<p>" + "a" * 9000 + "</p>"), html("<p>新</p>"))
        self.assertFalse(dialog.source_viewer.comparison_loaded)
        self.assertIn("8192", dialog.source_viewer.status_label.text())

    def test_non_lf_separators_cannot_bypass_source_budget_or_mislocate(self):
        for source in (
            "<p>" + ("a" * 8000 + "\v") * 3 + "</p>",
            "<p>" + "\u2029" * 20001 + "</p>",
            '<div class="prd-body"><p>A\u2029B</p>\n<h2>Target</h2></div>',
        ):
            with self.subTest(source_length=len(source)):
                dialog = self.dialog(source, source)
                self.assertFalse(dialog.source_right.property("sourceLoaded"))
                self.assertFalse(dialog.locate_button.isEnabled())
                self.assertEqual(dialog.source_right.toPlainText(), "")

    def test_conflict_markers_in_comments_visible_even_when_extraction_fails(self):
        source = html("<h2>规则</h2><p>相同</p>")
        conflict = source + "\n<!--\n<<<<<<< HEAD\nold\n=======\nnew\n>>>>>>> branch\n-->"
        dialog = self.dialog(source, conflict)
        self.assertIn("冲突标记", dialog.warning_label.text())
        with patch("clickgit.ui.html_review.analyze_html", side_effect=ValueError("预算")):
            dialog = self.dialog(source, conflict)
        self.assertIn("冲突标记", dialog.warning_label.text())


if __name__ == "__main__":
    unittest.main()
