"""Synthetic inputs only; policy tests never initialize Qt."""

import importlib
import importlib.util
import unittest
from html.parser import HTMLParser
from urllib.parse import quote


class _Tags(HTMLParser):
    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class HtmlPreviewPolicyTests(unittest.TestCase):
    def policy(self):
        name = "clickgit.html_preview_policy"
        self.assertIsNotNone(importlib.util.find_spec(name), "static preview policy is missing")
        return importlib.import_module(name)

    def test_preserves_inline_css_and_static_document(self):
        p = self.policy()
        result = p.prepare_html(
            '<!doctype html><html><head><style>.card {color: #123456}</style></head>'
            '<body><h1>合成 PRD</h1><div class="card" style="padding: 8px">'
            '<table><tr><td colspan="2">内容 &amp; 示例</td></tr></table></div></body></html>',
            "静态标题",
        )
        self.assertIn(".card {color: #123456}", result)
        self.assertIn('style="padding: 8px"', result)
        self.assertIn('colspan="2"', result)
        self.assertIn("<title>静态不交互 — 静态标题</title>", result)
        self.assertIn("内容 &amp; 示例", result)

    def test_preserves_root_inline_style_without_reusing_root_markup(self):
        p = self.policy()
        result = p.prepare_html(
            '<html class="theme" lang="zh-CN" onclick="bad()">'
            '<head><style>.theme .page {padding:8px}</style></head>'
            '<body class="page" style="background:#123456" onload="bad()">'
            '<p>synthetic</p></body></html>'
        )
        tags = _Tags(result).tags
        self.assertEqual([attrs for tag, attrs in tags if tag == "html"],
                         [{"class": "theme", "lang": "zh-CN"}])
        self.assertEqual([attrs for tag, attrs in tags if tag == "body"],
                         [{"class": "page", "style": "background:#123456"}])

    def test_rebuilds_no_executable_tags_or_attributes(self):
        p = self.policy()
        source = (
            '<meta http-equiv="refresh" content="0;url=https://synthetic.invalid">'
            '<base href="file:///C:/synthetic/"><link rel="stylesheet" href="bad.css">'
            '<script>window.SYNTHETIC_EXECUTED=1</script>'
            '<svg><script>bad()</script><a xlink:href="javascript:bad()">x</a></svg>'
            '<math><annotation-xml encoding="text/html"><iframe srcdoc="bad"></iframe>'
            '</annotation-xml></math><object data="file:///synthetic"></object>'
            '<iframe src="https://synthetic.invalid"></iframe>'
            '<img src="data:image/svg+xml,bad" onerror="bad()">'
            '<form action="https://synthetic.invalid"><input autofocus><button>Send</button></form>'
            '<a href="javascript:bad()" ping="https://synthetic.invalid" download>label</a>'
            '<p id="good" class="x" onclick="bad()" contenteditable="true" '
            'onpointerover="bad()" draggable="true">safe</p>'
        )
        result = p.prepare_html(source)
        tags = _Tags(result).tags
        forbidden = {"script", "svg", "math", "iframe", "object", "embed", "link",
                     "base", "img", "form", "video", "audio"}
        for tag, attrs in tags:
            self.assertNotIn(tag, forbidden)
            for attr in attrs:
                self.assertFalse(attr.startswith("on"))
                self.assertNotIn(attr, {"href", "src", "srcdoc", "ping", "download",
                                        "contenteditable", "draggable", "action"})
        self.assertNotIn("SYNTHETIC_EXECUTED", result)
        self.assertIn("safe", result)
        self.assertIn("label", result)

    def test_csp_is_first_and_cannot_be_replaced(self):
        p = self.policy()
        result = p.prepare_html(
            '</head><meta http-equiv="Content-Security-Policy" content="default-src *">'
            '<plaintext><script>bad()</script></plaintext>',
            '</title><script>title_attack()</script>',
        )
        policies = [attrs["content"] for tag, attrs in _Tags(result).tags
                    if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"]
        self.assertEqual(policies, [p.CSP])
        for directive in ("default-src 'none'", "script-src 'none'", "style-src 'unsafe-inline'",
                          "connect-src 'none'", "img-src 'none'", "font-src 'none'",
                          "form-action 'none'", "base-uri 'none'", "frame-src 'none'"):
            self.assertIn(directive, p.CSP)
        self.assertNotIn("<script", result)
        self.assertLess(result.index("Content-Security-Policy"), result.index("<title>"))

    def test_malformed_markup_cannot_escape_rebuilt_static_tree(self):
        p = self.policy()
        samples = [
            '<style><!--</style><img/src=x onerror=bad()>',
            '<svg><style><img src=x onerror=bad()></style></svg><p>ok</p>',
            '<math><mtext><table><mglyph><style><!--</style>'
            '<img title="--><img src=x onerror=bad()>">',
            '<noscript><p title="</noscript><img src=x onerror=bad()>">text</p>',
            '<div style="color:red&quot; onclick=&quot;bad()">text</div>',
            '<!--><script>bad()</script>--><p>ok</p>',
            '<template><script>bad()</script></template><p>ok</p>',
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                for tag, attrs in _Tags(p.prepare_html(sample)).tags:
                    self.assertNotIn(tag, {"script", "img", "svg", "math", "template", "noscript"})
                    self.assertFalse(any(key.startswith("on") for key in attrs))

    def test_raw_utf8_limit_and_invalid_unicode_are_explicit(self):
        p = self.policy()
        for source in ("a" * (p.MAX_SOURCE_BYTES + 1), "中" * 700000, "\ud800"):
            with self.subTest(length=len(source)):
                with self.assertRaises(p.PreviewPolicyError):
                    p.prepare_html(source)
        with self.assertRaises(p.PreviewPolicyError):
            p.prepare_html(None)

    def test_encoded_limit_includes_wrapper_and_title(self):
        p = self.policy()
        for source, title in (("中" * 240000, ""), ("%" * 710000, ""),
                              ("", "中" * 240000), ("a" * p.MAX_SOURCE_BYTES, "")):
            with self.subTest(length=len(source), title_length=len(title)):
                with self.assertRaisesRegex(p.PreviewPolicyError, "setHtml"):
                    p.prepare_html(source, title)
        html = p.prepare_html("<p>中 % &amp;</p>")
        actual = len(p.DATA_URL_PREFIX) + len(quote(html, safe="-._~"))
        self.assertEqual(p.encoded_size(html), actual)
        self.assertLess(actual, p.MAX_ENCODED_BYTES)

    def test_encoded_boundary_is_strict(self):
        p = self.policy()
        overhead = p.encoded_size(p.prepare_html(""))
        source = "a" * (p.MAX_ENCODED_BYTES - overhead - 1)
        self.assertEqual(p.encoded_size(p.prepare_html(source)), p.MAX_ENCODED_BYTES - 1)
        with self.assertRaisesRegex(p.PreviewPolicyError, "setHtml"):
            p.prepare_html(source + "a")

    def test_complexity_is_bounded_without_recursion(self):
        p = self.policy()
        for source in ("<div>" * 1000, "<br>" * 30000):
            with self.assertRaises(p.PreviewPolicyError):
                p.prepare_html(source)

    def test_inert_controls_keep_filter_and_operation_layout(self):
        p = self.policy()
        document = p.prepare_html(
            '<form action="https://synthetic.invalid" method="post" class="filters">'
            '<label for="query">搜索</label>'
            '<input id="query" type="text" placeholder="合成关键字" value="静态值" maxlength="30">'
            '<input type="number" value="42" readonly>'
            '<select name="state"><option value="all">全部</option>'
            '<option selected value="ok">完成</option></select>'
            '<textarea placeholder="备注" rows="3" cols="20">literal &lt;b&gt;text&lt;/b&gt;</textarea>'
            '<table><tr><td><button type="submit" onclick="bad()" formaction="/bad">'
            '查看</button></td></tr></table></form>',
            "合成筛选原型",
        )
        tags = _Tags(document).tags
        controls = [(tag, attrs) for tag, attrs in tags
                    if tag in {"button", "input", "select", "textarea"}]
        self.assertEqual([tag for tag, _ in controls],
                         ["input", "input", "select", "textarea", "button"])
        for tag, attrs in controls:
            self.assertIn("disabled", attrs, tag)
            self.assertNotIn("onclick", attrs)
            self.assertNotIn("formaction", attrs)
            self.assertNotIn("name", attrs)
        self.assertEqual(controls[0][1]["placeholder"], "合成关键字")
        self.assertEqual(controls[0][1]["value"], "静态值")
        self.assertEqual(controls[0][1]["maxlength"], "30")
        self.assertEqual(controls[-1][1]["type"], "button")
        self.assertIn("readonly", controls[0][1])
        self.assertIn("readonly", controls[3][1])
        self.assertIn(("label", {"for": "query"}), tags)
        self.assertIn(("div", {"class": "filters"}), tags)
        self.assertIn("静态不交互", document)
        self.assertIn("literal &lt;b&gt;text&lt;/b&gt;", document)

    def test_control_types_and_raw_text_cannot_become_active(self):
        p = self.policy()
        document = p.prepare_html(
            '<input type="file"><input type="image" src="file:///synthetic">'
            '<input type="password" value="synthetic"><input type="hidden">'
            '<input type="TEXT" autofocus onfocus="bad()" form="outside" list="x">'
            '<textarea><script>literal_not_code()</script><img src=x onerror=bad()></textarea>'
            '<select onchange="bad()" multiple><option selected onclick="bad()" value="x">X</option></select>'
            '<button popovertarget="x" commandfor="x" accesskey="a">inert</button>'
        )
        tags = _Tags(document).tags
        inputs = [attrs for tag, attrs in tags if tag == "input"]
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0]["type"], "text")
        self.assertIn("disabled", inputs[0])
        for tag, attrs in tags:
            self.assertNotIn(tag, {"script", "img", "form"})
            self.assertFalse(any(key.startswith("on") for key in attrs))
            self.assertTrue({"autofocus", "form", "list", "popovertarget",
                             "commandfor", "accesskey"}.isdisjoint(attrs))
        self.assertIn("&lt;script&gt;literal_not_code()", document)


if __name__ == "__main__":
    unittest.main()
