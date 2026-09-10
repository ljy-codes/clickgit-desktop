from __future__ import annotations

import importlib.util
import unittest


class HtmlDocumentTests(unittest.TestCase):
    def analyze(self, source):
        self.assertIsNotNone(
            importlib.util.find_spec("clickgit.html_document"),
            "必须提供纯 HTML 解析模块",
        )
        from clickgit.html_document import analyze_html
        return analyze_html(source)

    @staticmethod
    def text(result):
        return "\n".join(section.text for section in result.sections)

    def test_public_dataclasses_and_chinese_entities(self):
        result = self.analyze(
            '<div class="prd-body"><h1>中文 &amp; &#x9700;求</h1>'
            '<p>甲&nbsp; 乙 &lt;字段&gt;</p></div>'
        )
        from clickgit.html_document import HtmlAnalysis, HtmlSection
        self.assertIsInstance(result, HtmlAnalysis)
        self.assertIsInstance(result.sections, tuple)
        self.assertIsInstance(result.warnings, tuple)
        self.assertIsInstance(result.sections[0], HtmlSection)
        self.assertEqual(result.sections[0].title, "中文 & 需求")
        self.assertEqual(result.sections[0].text, "中文 & 需求\n甲 乙 <字段>")
        self.assertEqual(result.warnings, ())
        self.assertFalse(result.has_scripts)

    def test_hidden_prd_has_priority_over_app_drawer_and_controls(self):
        result = self.analyze(
            '<body><aside>应用菜单</aside><h1>应用标题</h1>'
            '<div id="prdDrawer" hidden style="display:none">'
            '<h2>抽屉标题</h2><button>关闭</button>'
            '<div class="drawer-bd prd-body extra"><h1>需求</h1>'
            '<nav>目录按钮</nav><aside>侧栏</aside><button>保存</button>'
            '<p>实际正文</p></div></div></body>'
        )
        self.assertEqual(self.text(result), "需求\n实际正文")
        self.assertEqual(result.warnings, ())

    def test_drawer_without_named_body_excludes_navigation(self):
        result = self.analyze(
            '<body><p>主界面</p><div id="prdDrawer">'
            '<button>关闭</button><div class="sidebar">侧栏</div>'
            '<div role="navigation">导航</div><h2>正文</h2><p>要求</p>'
            '</div></body>'
        )
        self.assertEqual(self.text(result), "正文\n要求")
        self.assertEqual(result.warnings, ())

    def test_class_tokens_multiple_regions_and_nested_regions(self):
        result = self.analyze(
            '<body><div class="not-prd-body">排除</div>'
            '<div class="prd-content"><h1>A</h1>'
            '<div class="prd-body"><h2>B</h2><p>唯一</p></div></div>'
            '<div class="prd-body"><h1>C</h1></div></body>'
        )
        self.assertEqual([s.title for s in result.sections], ["A", "B", "C"])
        self.assertEqual(self.text(result).count("唯一"), 1)
        self.assertNotIn("排除", self.text(result))

    def test_headings_have_original_lines_even_with_long_lines(self):
        source = '<div class="prd-body">\r\n' + " " * 10000
        source += '<h1\n class="title">一级</h1>\n<h2>二级</h2>'
        source += '<h3>三级</h3><h4>四级</h4><h5>五级</h5><h6>六级</h6></div>'
        result = self.analyze(source)
        self.assertEqual([s.line for s in result.sections], [2, 4, 4, 4, 4, 4])
        self.assertEqual([s.title for s in result.sections],
                         ["一级", "二级", "三级", "四级", "五级", "六级"])

    def test_keys_use_hierarchy_duplicates_not_line_or_unrelated_order(self):
        content = '<h1>A</h1><h2>同名</h2><h2>同名</h2><h1>B</h1><h2>同名</h2>'
        before = self.analyze('<div class="prd-body">' + content + '</div>')
        after = self.analyze('<div class="prd-body">\n<h1>新增</h1>' + content + '</div>')
        self.assertEqual([s.key for s in before.sections],
                         [s.key for s in after.sections[1:]])
        self.assertEqual(len({s.key for s in before.sections}), 5)
        self.assertNotEqual(before.sections[1].key, before.sections[-1].key)

    def test_keys_cannot_collide_on_delimiters(self):
        result = self.analyze(
            '<div class="prd-body"><h1>A/h2:B#1</h1>'
            '<h1>A</h1><h2>B</h2><h2>B#1</h2></div>'
        )
        self.assertEqual(len({s.key for s in result.sections}), 4)

    def test_fallback_body_and_fragment_warn(self):
        result = self.analyze(
            '<html><head><title>页签</title></head>'
            '<body><h1>通用</h1><button>可读按钮</button><p>内容</p></body></html>'
        )
        self.assertIn("可读按钮", self.text(result))
        self.assertNotIn("页签", self.text(result))
        self.assertIn("无专用正文", "".join(result.warnings))
        fragment = self.analyze("<p>片段</p>")
        self.assertIn("片段", self.text(fragment))
        self.assertIn("无专用正文", "".join(fragment.warnings))

    def test_suppressed_content_never_becomes_body_or_headings(self):
        result = self.analyze(
            '<html><head><style>.x{content:"泄漏"}</style><title>泄漏</title></head>'
            '<body><template><div class="prd-body"><h1>泄漏</h1></div></template>'
            '<script>const x = "<h1>泄漏</h1>";</script>'
            '<h1>正文</h1><p>保留</p></body></html>'
        )
        self.assertEqual(self.text(result), "正文\n保留")
        self.assertTrue(result.has_scripts)
        self.assertIn("无专用正文", "".join(result.warnings))

    def test_script_flags_include_handlers_and_javascript_urls(self):
        for source in (
            '<body onload="run()">正文</body>',
            '<body><a href=" java&#x73;cript:run()">链接</a></body>',
            '<template><script src="remote.js"></script></template>',
        ):
            with self.subTest(source=source):
                self.assertTrue(self.analyze(source).has_scripts)

    def test_pre_preserves_indentation_blank_lines_and_trailing_newline(self):
        result = self.analyze(
            '<div class="prd-body"><h1>示例</h1><p>行  内\n  空白</p>'
            '<pre>  第一行\n\n\t第二行 &lt;x&gt;\n</pre></div>'
        )
        self.assertEqual(self.text(result),
                         "示例\n行 内 空白\n  第一行\n\n\t第二行 <x>\n")

    def test_inline_spaces_blocks_and_br(self):
        result = self.analyze(
            '<div class="prd-body"><p>中<strong>文</strong> &amp; '
            '<em>English</em> text<br>下一行</p><p>新段</p></div>'
        )
        self.assertEqual(self.text(result), "中文 & English text\n下一行\n新段")

    def test_tables_have_cell_and_row_separators_including_empty_cells(self):
        result = self.analyze(
            '<div class="prd-body"><table><tr><th>字段</th><th>规则</th></tr>'
            '<tr><td>名称</td><td>必填</td></tr>'
            '<tr><td></td><td>空列</td><td></td></tr></table></div>'
        )
        self.assertEqual(self.text(result), "字段\t规则\n名称\t必填\n\t空列\t")

    def test_legal_optional_closures_do_not_warn(self):
        result = self.analyze(
            '<!doctype html><html><head><title>页签</title><body>'
            '<div class="prd-body"><h1>需求</h1><p>段一<p>段二'
            '<ul><li>一<li>二</ul><dl><dt>键<dd>值<dt>键二<dd>值二</dl>'
            '<table><thead><tr><th>字段<th>规则<tbody>'
            '<tr><td>名称<td>必填<tr><td>代码<td>唯一</table>'
            '<select><optgroup label="组"><option>A<option>B'
            '<optgroup label="组二"><option>C</select></div>'
        )
        self.assertEqual(result.warnings, ())
        self.assertIn("段一\n段二", self.text(result))
        self.assertIn("名称\t必填\n代码\t唯一", self.text(result))

    def test_many_optional_list_items_do_not_trigger_depth_budget(self):
        result = self.analyze('<div class="prd-body"><ul>' + '<li>项目' * 600 + '</ul></div>')
        self.assertEqual(result.warnings, ())
        self.assertEqual(self.text(result).count("项目"), 600)

    def test_omitted_head_and_body_end_tags_with_implicit_body_start(self):
        for content in ('<div class="prd-body"><h1>正文</h1></div>', '正文'):
            with self.subTest(content=content):
                result = self.analyze('<html><head><title>页签</title>' + content)
                self.assertEqual(self.text(result), "正文")
                self.assertNotIn("无正文", "".join(result.warnings))
                self.assertNotIn("不可靠", "".join(result.warnings))

    def test_cell_edge_whitespace_and_block_edges_do_not_break_rows(self):
        result = self.analyze(
            '<div class="prd-body"><table>'
            '<tr><td> A </td><td> B </td></tr>'
            '<tr><td><p>C</p></td><td><p>D</p></td></tr>'
            '</table></div>'
        )
        self.assertEqual(self.text(result), "A\tB\nC\tD")

    def test_textarea_markup_is_literal_not_a_dedicated_region(self):
        result = self.analyze(
            '<body><textarea>&lt;示例&gt;<div class="prd-body">伪正文</div>'
            '</textarea><h1>真实正文</h1></body>'
        )
        self.assertIn('<示例><div class="prd-body">伪正文</div>', self.text(result))
        self.assertIn("真实正文", self.text(result))
        self.assertIn("无专用正文", "".join(result.warnings))

    def test_title_rcdata_does_not_invent_script_elements(self):
        result = self.analyze(
            '<head><title><script>字面代码</script></title></head>'
            '<div class="prd-body"><h1>需求</h1></div>'
        )
        self.assertEqual(self.text(result), "需求")
        self.assertEqual(result.warnings, ())
        self.assertFalse(result.has_scripts)

    def test_textarea_entities_decode_once_without_unreliable_warning(self):
        result = self.analyze(
            '<div class="prd-body"><textarea>&amp;lt; &lt;x&gt;</textarea></div>'
        )
        self.assertEqual(self.text(result), "&lt; <x>")
        self.assertEqual(result.warnings, ())

    def test_nested_lists_and_tables_do_not_close_outer_scopes(self):
        result = self.analyze(
            '<div class="prd-body"><ul><li>外层<ul><li>内层一<li>内层二</ul>'
            '<li>外层二</ul><table><tr><td>外表'
            '<table><tr><td>内表</table><td>外表二</table></div>'
        )
        self.assertEqual(result.warnings, ())
        for text in ("内层一", "内层二", "外层二", "内表", "外表二"):
            self.assertIn(text, self.text(result))

    def test_duplicate_ids_warn_without_losing_sections(self):
        result = self.analyze(
            '<div class="prd-body"><h1 id="same">A</h1><h2 id="same">B</h2></div>'
        )
        self.assertEqual(len(result.sections), 2)
        self.assertIn("重复", "".join(result.warnings))
        self.assertIn("ID", "".join(result.warnings))

    def test_empty_dedicated_body_does_not_fallback_to_app(self):
        result = self.analyze('<body>应用<div class="prd-body"><script>x()</script></div></body>')
        self.assertEqual(result.sections, ())
        self.assertIn("无正文", "".join(result.warnings))
        self.assertTrue(result.has_scripts)

    def test_no_readable_body_warns(self):
        for source in ("", " \n\t", "<html><head><title>标题</title></head></html>",
                       '<div class="prd-body"><template>模板</template><style>x{}</style></div>'):
            with self.subTest(source=source):
                result = self.analyze(source)
                self.assertEqual(result.sections, ())
                self.assertIn("无正文", "".join(result.warnings))

    def test_preamble_and_empty_heading_are_not_silently_lost(self):
        result = self.analyze('<div class="prd-body">开场<h2> </h2><p>正文</p></div>')
        self.assertIn("开场", self.text(result))
        self.assertIn("正文", self.text(result))
        self.assertTrue(result.warnings)

    def test_truncated_or_malformed_markup_warns(self):
        for source in (
            '<div class="prd-body"><h1>标题</h1><p>未完',
            '<div class="prd-body">正文</div><!-- 未闭合',
            '<div class="prd-body">正文</div><h2 title="未完',
            '<div class="prd-body"><strong>文字</div>',
            '<div class="prd-body">正文</div></unknown>',
            '<div class="prd-body">正文<script>未完',
        ):
            with self.subTest(source=source):
                self.assertTrue(self.analyze(source).warnings)

    def test_depth_budget_including_ignored_templates(self):
        for prefix in ("", "<template>"):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, "深度"):
                self.analyze(prefix + "<div>" * 129 + "正文" + "</div>" * 129)

    def test_exact_depth_and_section_limits_are_accepted(self):
        source = '<div class="prd-body">' + "<div>" * 127 + "正文" + "</div>" * 128
        self.assertEqual(self.text(self.analyze(source)), "正文")
        source = '<div class="prd-body">' + "<h1>标题</h1>" * 2048 + "</div>"
        self.assertEqual(len(self.analyze(source).sections), 2048)

    def test_input_budget_counts_utf8_bytes_and_accepts_exact_limit(self):
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            self.analyze("x" * (2 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "2 MiB"):
            self.analyze("中" * 700000)
        source = "<!--" + "x" * (2 * 1024 * 1024 - 7) + "-->"
        self.assertEqual(self.analyze(source).sections, ())

    def test_node_budget(self):
        with self.assertRaisesRegex(ValueError, "节点"):
            self.analyze("<br>" * 50001)

    def test_output_budget(self):
        with self.assertRaisesRegex(ValueError, "输出"):
            self.analyze('<div class="prd-body">' + "x" * (1024 * 1024 + 1) + "</div>")

    def test_output_budget_includes_repeated_parent_keys(self):
        source = '<div class="prd-body"><h1>' + "x" * 50000 + "</h1>"
        source += "<h2>子标题</h2>" * 30 + "</div>"
        with self.assertRaisesRegex(ValueError, "输出"):
            self.analyze(source)

    def test_duplicate_warning_volume_is_bounded(self):
        source = '<div class="prd-body">' + '<p id="same">内容</p>' * 1000 + "</div>"
        result = self.analyze(source)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("重复 ID", result.warnings[0])

    def test_section_budget(self):
        with self.assertRaisesRegex(ValueError, "章节"):
            self.analyze('<div class="prd-body">' + "<h1>标题</h1>" * 2049 + "</div>")

    def test_invalid_unicode_and_nul_rejected_in_chinese(self):
        for source in ("\ud800", "<body>前\0后</body>"):
            with self.subTest(source=repr(source)), self.assertRaisesRegex(ValueError, "字符"):
                self.analyze(source)


if __name__ == "__main__":
    unittest.main()
