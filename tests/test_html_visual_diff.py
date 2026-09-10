import unittest

from clickgit.html_visual_diff import compare_html_text
from clickgit.html_preview_policy import prepare_html


class HtmlVisualDiffTests(unittest.TestCase):
    def test_changed_text_is_numbered_and_both_versions_retained(self):
        result = compare_html_text("<p>工时 3</p>", "<p>工时 5</p>")
        self.assertEqual(len(result.changes), 1)
        change = result.changes[0]
        self.assertEqual((change.kind, change.left, change.right), ("修改", "工时 3", "工时 5"))
        self.assertIn(change.marker, result.left)
        self.assertIn(change.marker, result.right)
        self.assertIn("background-color:", result.left)
        self.assertIn("工时 5", prepare_html(result.right))

    def test_insert_delete_and_repeated_text_have_stable_unique_markers(self):
        result = compare_html_text("<p>A</p><p>same</p><p>B</p><p>same</p>",
                                   "<p>A</p><p>same</p><p>C</p><p>same</p><p>D</p>")
        self.assertEqual([c.kind for c in result.changes], ["修改", "新增"])
        self.assertEqual(len({c.marker for c in result.changes}), 2)
        self.assertNotIn(result.changes[1].marker, result.left)
        deleted = compare_html_text("<p>A</p><p>B</p>", "<p>A</p>")
        self.assertEqual(deleted.changes[0].kind, "删除")

    def test_hidden_text_included_but_scripts_and_styles_are_not_text(self):
        result = compare_html_text('<style>.prd{display:none}</style><div class="prd">旧规则</div>',
                                   '<style>.prd{display:none}</style><div class="prd">新规则</div>')
        self.assertEqual(result.changes[0].left, "旧规则")
        css = compare_html_text("<style>p{color:red}</style><p>A</p><script>old()</script>",
                                "<style>p{color:blue}</style><p>A</p><script>new()</script>")
        self.assertEqual(css.changes, ())
        self.assertIn("源码", css.notice)
        self.assertNotIn("<script", css.left)

    def test_hidden_first_node_does_not_steal_visible_group_marker(self):
        old = '<div style="display:none">Hidden old</div><p>Visible old</p>'
        result = compare_html_text(old, old.replace("old", "new"))
        self.assertEqual(len(result.changes), 1)
        self.assertEqual(result.left.count(result.changes[0].marker), 2)
        self.assertEqual(result.right.count(result.changes[0].marker), 2)

    def test_identical_source_is_distinguished_from_equal_body(self):
        self.assertIn("完全相同", compare_html_text("<p>A</p>", "<p>A</p>").notice)
        self.assertNotIn("完全相同", compare_html_text('<p id="a">A</p>', '<p id="b">A</p>').notice)

    def test_controls_do_not_receive_invalid_inline_markup(self):
        result = compare_html_text("<select><option>旧</option></select>",
                                   "<select><option>新</option></select>")
        self.assertEqual(result.changes[0].kind, "修改")
        self.assertFalse(result.changes[0].left_marked)
        self.assertFalse(result.changes[0].right_marked)
        self.assertNotIn(result.changes[0].marker, result.right)

    def test_html_text_is_escaped_not_executed_and_source_unchanged(self):
        left, right = "<p>&lt;script&gt;old&lt;/script&gt;</p>", "<p>&lt;b&gt;new&lt;/b&gt;</p>"
        result = compare_html_text(left, right)
        self.assertIn("&lt;b&gt;", result.right)
        self.assertNotIn("<b>new", result.right)
        self.assertEqual(right, "<p>&lt;b&gt;new&lt;/b&gt;</p>")

    def test_budget_falls_back_without_claiming_equality(self):
        result = compare_html_text("<p>A</p>" * 1100, "<p>B</p>" * 1100)
        self.assertTrue(result.limited)
        self.assertEqual(result.changes, ())
        self.assertIn("预算", result.notice)

    def test_existing_marker_like_text_does_not_collide(self):
        result = compare_html_text("<p>[CG改动1] old</p>", "<p>[CG改动1] new</p>")
        self.assertNotEqual(result.changes[0].marker, "[CG改动1]")

    def test_pathological_marker_collision_is_bounded(self):
        text = "[CG改动" + "·" * 10000
        self.assertTrue(compare_html_text("<p>" + text + "</p>", "<p>new</p>").limited)

    def test_empty_file_and_whitespace_changes(self):
        result = compare_html_text("", "<p>新增文件</p>")
        self.assertEqual(result.changes[0].kind, "新增")
        result = compare_html_text("<pre>a b</pre>", "<pre>a  b</pre>")
        self.assertEqual(result.changes[0].kind, "修改")


if __name__ == "__main__":
    unittest.main()
