"""Pure, bounded HTML reconstruction for the *restricted static* preview.

This is not an HTML/CSS execution environment or a general-purpose sanitizer.
Only feed the result to HtmlPreview's isolated, network-denying WebEngine page.
Inline CSS is preserved, including CSS URLs which CSP AND the interceptor deny.
No input paths, files, network, Qt objects, or persistent state are used here.
"""

from __future__ import annotations

from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import quote

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_ENCODED_BYTES = 2 * 1024 * 1024
DATA_URL_PREFIX = "data:text/html;charset=UTF-8,"
CSP = (
    "default-src 'none'; script-src 'none'; script-src-attr 'none'; "
    "style-src 'unsafe-inline'; img-src 'none'; font-src 'none'; "
    "connect-src 'none'; media-src 'none'; object-src 'none'; "
    "frame-src 'none'; child-src 'none'; worker-src 'none'; "
    "manifest-src 'none'; form-action 'none'; base-uri 'none'"
)
NOTICE = (
    "安全静态简化模式（静态不交互）：仅显示白名单 HTML 和内联 CSS，控件全部禁用；"
    "脚本、事件、表单提交、外链、图片、外部 CSS/字体及任意本地资源均不可用。"
)

# No custom elements, foreign namespaces, media or navigable links.
_TAGS = frozenset(
    "a abbr address article aside b bdi bdo blockquote br caption center cite code "
    "col colgroup dd del div dl dt em figcaption figure footer h1 h2 h3 h4 h5 h6 "
    "header hr i ins kbd li main mark nav ol p pre q rp rt ruby s samp section "
    "small span strong style sub sup table tbody td tfoot th thead time tr u ul var wbr "
    "button input label select option optgroup textarea"
    .split()
)
_VOID = frozenset("br col hr input wbr".split())
_DROP_CONTENT = frozenset(
    "script iframe object embed svg math template noscript noembed noframes "
    "xmp plaintext title video audio canvas"
    .split()
)
_ATTRS = frozenset("id class title lang dir style colspan rowspan span scope start value".split())
_CONTROL_ATTRS = {
    "label": frozenset({"for"}),
    "input": frozenset({"placeholder", "maxlength"}),
    "textarea": frozenset({"placeholder", "maxlength", "rows", "cols"}),
    "select": frozenset({"size", "multiple"}),
    "option": frozenset({"selected", "label"}),
    "optgroup": frozenset({"label"}),
}
_ALIASES = {"form": "div"}
_MAX_NODES = 20000
_MAX_DEPTH = 128


class PreviewPolicyError(ValueError):
    """Safe-to-display validation failure (never includes source material)."""


def _attributes(values: dict[str, str]) -> str:
    return "".join(f' {key}="{escape(value, quote=True)}"' for key, value in values.items())


class _StaticHTML(HTMLParser):
    CDATA_CONTENT_ELEMENTS = ("script", "style", "textarea")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.dropped: list[str] = []
        self.root_attrs: dict[str, dict[str, str]] = {}
        self.nodes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > _MAX_NODES:
            raise PreviewPolicyError("HTML 节点过多，无法安全预览。")
        if self.dropped:
            if tag in _DROP_CONTENT:
                self.dropped.append(tag)
            if len(self.dropped) > _MAX_DEPTH:
                raise PreviewPolicyError("HTML 嵌套过深，无法安全预览。")
            return
        if tag in _DROP_CONTENT:
            self.dropped.append(tag)
            return
        if tag in {"html", "body"}:
            if tag not in self.root_attrs:
                self.root_attrs[tag] = {
                    key: value for key, value in attrs
                    if key in {"id", "class", "lang", "dir", "style", "title"}
                    and value is not None
                }
            return
        rendered = _ALIASES.get(tag, tag)
        if rendered not in _TAGS:
            return
        if len(self.stack) >= _MAX_DEPTH:
            raise PreviewPolicyError("HTML 嵌套过深，无法安全预览。")
        # Re-serialize parsed attributes; never reuse raw start-tag text.
        kept: dict[str, str] = {}
        allowed = _ATTRS | _CONTROL_ATTRS.get(tag, frozenset())
        for key, value in attrs:
            if key in allowed and key not in kept:
                kept[key] = value or ""
        if tag == "input":
            input_type = (dict(attrs).get("type") or "text").lower()
            if input_type not in {"text", "number"}:
                return
            kept["type"] = input_type
        if tag == "button":
            kept["type"] = "button"
        if tag in {"button", "input", "select", "option", "optgroup", "textarea"}:
            kept["disabled"] = ""
        if tag in {"input", "textarea"}:
            kept["readonly"] = ""
        self.parts.append(f"<{rendered}{_attributes(kept)}>")
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.dropped:
            if tag == self.dropped[-1]:
                self.dropped.pop()
            return
        if tag not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            self.parts.append(f"</{_ALIASES.get(top, top)}>")
            if top == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.dropped:
            return
        if self.stack and self.stack[-1] == "style":
            # CSS raw-text must never manufacture an HTML closing delimiter.
            self.parts.append(data.replace("<", r"\3c "))
        elif self.stack and self.stack[-1] == "textarea":
            self.parts.append(escape(unescape(data), quote=False))
        else:
            self.parts.append(escape(data, quote=False))

    def finish(self) -> str:
        self.close()
        while self.stack:
            top = self.stack.pop()
            self.parts.append(f"</{_ALIASES.get(top, top)}>")
        return "".join(self.parts)


def encoded_size(document: str) -> int:
    """Conservative setHtml data-URL size, including its ASCII MIME prefix."""
    return len(DATA_URL_PREFIX) + len(quote(document, safe="-._~", encoding="utf-8"))


def prepare_html(source: str, title: str = "") -> str:
    """Rebuild a static document or raise before a renderer is allocated.

    Limits apply both to each UTF-8 input and to the complete percent-encoded
    setHtml document. Equality with Chromium's 2 MiB ceiling is rejected too.
    """
    for value in (source, title):
        if not isinstance(value, str):
            raise PreviewPolicyError("HTML 源码和标题必须是字符串。")
        if len(value) > MAX_SOURCE_BYTES:
            raise PreviewPolicyError("HTML 源码或标题超过 2 MiB，未加载。")
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            raise PreviewPolicyError("HTML 包含无效 UTF-8 字符，未加载。") from None
        if size > MAX_SOURCE_BYTES:
            raise PreviewPolicyError("HTML 源码或标题超过 2 MiB，未加载。")
    parser = _StaticHTML()
    parser.feed(source)
    body = parser.finish()
    document = (
        f'<!doctype html><html{_attributes(parser.root_attrs.get("html", {}))}><head>'
        f'<meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}">'
        '<meta charset="utf-8">'
        f"<title>静态不交互 — {escape(title)}</title></head>"
        f'<body{_attributes(parser.root_attrs.get("body", {}))}>{body}</body></html>'
    )
    if encoded_size(document) >= MAX_ENCODED_BYTES:
        raise PreviewPolicyError("HTML 经 setHtml 百分号编码后达到 2 MiB 上限，未加载。")
    return document
