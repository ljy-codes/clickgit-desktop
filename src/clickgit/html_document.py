"""Bounded, read-only HTML text extraction; NOT a sanitizer or browser DOM.

Only strings enter/leave this module. Nothing is opened, fetched, or executed.
Dedicated PRD regions are extracted even when hidden. CSS visibility is not
evaluated. Ordinary HTML whitespace collapses; pre text retains whitespace.
Table cells use tabs and rows use newlines (no rowspan/colspan expansion).

Section text includes its heading, ending before the next heading. Keys are
JSON paths of [heading level, normalized title, same-parent occurrence].
Unrelated heading insertions do not change keys; renaming/reparenting or
inserting an identical sibling can. Introductory text uses a separate key.
Lines reference original heading start tags, not a reconstructed DOM.

HTMLParser is not an HTML5 tree builder. Common optional end tags are handled;
detected repairs/truncation produce warnings, not a guarantee of valid HTML.
Never use this analysis as authorization to render the original HTML.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser


MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_NODES = 50_000
MAX_DEPTH = 128
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_SECTIONS = 2048

_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_IGNORED = frozenset(("script", "style", "template", "head"))
_HEADINGS = frozenset(f"h{i}" for i in range(1, 7))
_OPTIONAL = frozenset(
    "html head body p li dt dd rt rp option optgroup colgroup thead tbody tfoot tr td th".split()
)
_BLOCK = frozenset(
    "address article aside blockquote details dialog div dl dt dd fieldset "
    "figcaption figure footer form header hgroup hr li main menu nav ol p pre "
    "section table tbody thead tfoot tr ul h1 h2 h3 h4 h5 h6".split()
)
_SPACE = re.compile(r"\s+")
_HEAD_CONTENT = frozenset(
    "base basefont bgsound link meta title noscript noframes style script template".split()
)
_STRUCTURE_WARNING = "HTML 标签结构需要修复，解析结果可能不可靠，请对照源码。"


@dataclass(frozen=True)
class HtmlSection:
    key: str
    title: str
    line: int
    text: str


@dataclass(frozen=True)
class HtmlAnalysis:
    sections: tuple[HtmlSection, ...]
    warnings: tuple[str, ...]
    has_scripts: bool


@dataclass(slots=True)
class _Node:
    tag: str
    line: int
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node | str] = field(default_factory=list)


def _ui(node: _Node) -> bool:
    return (
        node.tag in {"button", "nav", "aside"}
        or node.attrs.get("role", "").lower() in {"navigation", "button", "complementary"}
        or "sidebar" in node.attrs.get("class", "").split()
    )


class _Parser(HTMLParser):
    # Make raw/RCDATA handling consistent on supported Python versions,
    # including versions where HTMLParser only treats script/style as raw.
    CDATA_CONTENT_ELEMENTS = (
        "script", "style", "xmp", "iframe", "noembed", "noframes", "textarea", "title",
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("", 1)
        self.stack = [self.root]
        self.nodes = 0
        self.ids: set[str] = set()
        self.warnings: list[str] = []
        self.has_scripts = False

    def warn(self, message: str):
        # Messages are categorical, never interpolate unbounded user input.
        if message not in self.warnings:
            self.warnings.append(message)

    def count(self):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ValueError("HTML 节点数量超过限制（50000）。")

    def pop_to(self, index: int):
        if any(node.tag not in _OPTIONAL for node in self.stack[index + 1:]):
            self.warn(_STRUCTURE_WARNING)
        del self.stack[index:]

    def close_in_scope(self, tags: set[str], barriers: set[str]):
        for index in range(len(self.stack) - 1, 0, -1):
            tag = self.stack[index].tag
            if tag in tags:
                self.pop_to(index)
                return
            if tag in barriers or tag in _IGNORED:
                return

    def implied_end(self, tag: str):
        # Scope barriers prevent closing an outer list/table cell from inside
        # a nested list/table; optional closures must not accumulate depth.
        if tag in _BLOCK:
            self.close_in_scope({"p"}, {"html", "table", "td", "th", "button"})
        if tag not in _HEAD_CONTENT:
            self.close_in_scope({"head"}, {"html"})
        if tag == "li":
            self.close_in_scope({"li"}, {"ul", "ol", "menu"})
        if tag in {"dt", "dd"}:
            self.close_in_scope({"dt", "dd"}, {"dl"})
        if tag in {"rt", "rp"}:
            self.close_in_scope({"rt", "rp"}, {"ruby"})
        if tag in {"option", "optgroup"}:
            self.close_in_scope({"option"}, {"select", "datalist"})
        if tag == "optgroup":
            self.close_in_scope({"optgroup"}, {"select"})
        if tag in {"td", "th"}:
            self.close_in_scope({"td", "th"}, {"tr", "table"})
        if tag == "tr":
            self.close_in_scope({"tr"}, {"table", "thead", "tbody", "tfoot"})
        if tag in {"thead", "tbody", "tfoot"}:
            self.close_in_scope({"thead", "tbody", "tfoot"}, {"table"})
        if tag != "col":
            self.close_in_scope({"colgroup"}, {"table"})
        if tag in _HEADINGS and self.stack[-1].tag in _HEADINGS:
            self.warn(_STRUCTURE_WARNING)
            self.stack.pop()

    def handle_starttag(self, tag, attrs):
        self.count()
        self.implied_end(tag)
        if len(self.stack) > MAX_DEPTH:
            raise ValueError("HTML 嵌套深度超过限制（128）。")
        attributes = {}
        for key, value in attrs:
            if key in attributes:
                self.warn("HTML 存在重复属性，解析结果可能不可靠。")
            attributes[key] = value or ""
            if key.startswith("on"):
                self.has_scripts = True
            if key in {"href", "src", "action", "formaction", "xlink:href"}:
                scheme = re.sub(r"[\x00-\x20]", "", value or "").lower()
                if scheme.startswith("javascript:"):
                    self.has_scripts = True
        self.has_scripts |= tag == "script"
        identity = attributes.get("id")
        if identity:
            if identity in self.ids:
                self.warn("HTML 存在重复 ID，源码定位请以标题行号为准。")
            self.ids.add(identity)
        if tag in {"svg", "math", "iframe", "object", "noscript", "plaintext", "xmp",
                   "noembed", "noframes"}:
            self.warn("HTML 含特殊解析元素，静态文字可能与浏览器不同，请对照源码。")
        node = _Node(tag, self.getpos()[0],
                     {k: v for k, v in attributes.items() if k in {"id", "class", "role"}})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.warn("HTML 非空元素使用自闭合语法，解析结果可能与浏览器不同。")
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.pop_to(index)
                return
        self.warn(_STRUCTURE_WARNING)

    def handle_data(self, data):
        self.count()
        if self.stack[-1].tag == "head" and data.strip():
            self.stack.pop()
        if self.stack[-1].tag in {"textarea", "title"}:
            data = unescape(data)
        self.stack[-1].children.append(data)

    def handle_comment(self, data):
        self.count()

    def handle_decl(self, decl):
        self.count()
        if not decl.lower().startswith("doctype html"):
            self.warn("HTML 声明无法可靠识别，请对照源码。")

    def unknown_decl(self, data):
        self.count()
        self.warn("HTML 含非标准声明，解析结果可能不可靠。")

    def handle_pi(self, data):
        self.count()
        self.warn("HTML 含处理指令，解析结果可能不可靠。")


def _regions(root: _Node, predicate, *, dedicated: bool) -> list[_Node]:
    found = []
    pending = [root]
    while pending:
        node = pending.pop()
        if node.tag in _IGNORED or (dedicated and _ui(node)):
            continue
        if predicate(node):
            found.append(node)
        else:
            pending.extend(child for child in reversed(node.children) if isinstance(child, _Node))
    return found


class _Budget:
    def __init__(self):
        self.used = 0

    def add(self, text: str):
        self.used += len(text.encode("utf-8"))
        if self.used > MAX_OUTPUT_BYTES:
            raise ValueError("HTML 提取输出超过限制（1 MiB，含标题和章节 key）。")


class _Writer:
    def __init__(self, budget: _Budget):
        self.budget = budget
        self.parts: list[str] = []
        self.pending = ""
        self.cell_start = False

    def append(self, text: str):
        if text:
            self.budget.add(text)
            self.parts.append(text)
            self.cell_start = False

    def flush(self):
        if self.parts and not (self.pending == "\n" and self.parts[-1].endswith("\n")):
            self.append(self.pending)
        self.pending = ""

    def text(self, data: str, *, pre: bool = False):
        if not data:
            return
        if pre:
            self.flush()
            self.append(data)
            return
        normalized = _SPACE.sub(" ", data)
        if normalized.startswith(" ") and not self.pending and not self.cell_start:
            self.pending = " "
        value = normalized.strip(" ")
        if value:
            self.flush()
            self.append(value)
            self.pending = " " if normalized.endswith(" ") else ""

    def line(self):
        if not self.cell_start:
            self.pending = "\n"

    def cell(self, *, first: bool):
        if first:
            self.flush()
        else:
            self.pending = ""
            self.append("\t")
        self.cell_start = True

    def value(self) -> str:
        return "".join(self.parts)


class _Extractor:
    def __init__(self, parser: _Parser, dedicated: bool):
        self.parser = parser
        self.dedicated = dedicated
        self.budget = _Budget()
        self.writer = _Writer(self.budget)
        self.sections: list[HtmlSection] = []
        self.path: list[tuple[int, str, int]] = []
        self.occurrences: dict[tuple, int] = {}
        self.key = '["preamble",1]'
        self.title = "正文"
        self.line = 1
        self.preambles = 0

    def skip(self, node: _Node) -> bool:
        return node.tag in _IGNORED or (self.dedicated and _ui(node))

    def finish(self):
        text = self.writer.value()
        if text.strip():
            if len(self.sections) >= MAX_SECTIONS:
                raise ValueError("HTML 章节数量超过限制（2048）。")
            self.budget.add(self.key)
            self.budget.add(self.title)
            self.sections.append(HtmlSection(self.key, self.title, self.line, text))
        self.writer = _Writer(self.budget)

    def heading_text(self, node: _Node) -> str:
        pieces = []
        pending: list[_Node | str] = list(reversed(node.children))
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                pieces.append(item)
            elif not self.skip(item):
                if item.tag == "br" or item.tag in _BLOCK:
                    pieces.append(" ")
                pending.extend(reversed(item.children))
        return _SPACE.sub(" ", "".join(pieces)).strip()

    def heading(self, node: _Node):
        self.finish()
        level = int(node.tag[1])
        self.title = self.heading_text(node)
        if not self.title:
            self.parser.warn("HTML 含空标题，已使用占位标题，请对照源码。")
            self.title = "（无标题）"
        while self.path and self.path[-1][0] >= level:
            self.path.pop()
        identity = (tuple(self.path), level, self.title)
        count = self.occurrences.get(identity, 0) + 1
        self.occurrences[identity] = count
        self.path.append((level, self.title, count))
        self.key = json.dumps(self.path, ensure_ascii=False, separators=(",", ":"))
        self.line = node.line
        self.writer.text(self.title)
        self.writer.line()

    def render(self, node: _Node, *, pre: bool = False):
        if self.skip(node):
            return
        if node.tag in _HEADINGS:
            self.heading(node)
            return
        if node.tag in _BLOCK or node.tag == "br":
            self.writer.line()
        in_pre = pre or node.tag == "pre"
        cells = 0
        for child in node.children:
            if isinstance(child, str):
                # Formatting whitespace between table cells is not content.
                if node.tag in {"table", "thead", "tbody", "tfoot", "tr"} and not child.strip():
                    continue
                self.writer.text(child, pre=in_pre)
            else:
                if node.tag == "tr" and child.tag in {"td", "th"}:
                    self.writer.cell(first=cells == 0)
                    cells += 1
                self.render(child, pre=in_pre)
                if node.tag == "tr" and child.tag in {"td", "th"}:
                    self.writer.cell_start = False
        if node.tag in _BLOCK:
            self.writer.line()

    def region(self, root: _Node):
        self.finish()
        self.preambles += 1
        self.key = json.dumps(["preamble", self.preambles], separators=(",", ":"))
        self.title, self.line = "正文", root.line
        self.path = []
        self.render(root)
        self.finish()


def analyze_html(source: str) -> HtmlAnalysis:
    """Extract comparable sections without I/O; reject resource limits in Chinese.

    Budgets: UTF-8 input 2 MiB; 50,000 element/text/comment/declaration nodes;
    depth 128; total output text/title/key 1 MiB; 2,048 sections.
    Input/node/depth limits also apply to hidden/ignored input. No partial
    successful result is returned on budget exhaustion. Warnings are
    deduplicated and categorical.
    ``has_scripts`` flags script tags, on* attributes and javascript: URLs;
    False is NOT a safety assessment. Output is plain text, never safe HTML.
    """
    if not isinstance(source, str):
        raise TypeError("HTML 源码必须是字符串。")
    if len(source) > MAX_INPUT_BYTES:
        raise ValueError("HTML 输入超过 2 MiB 限制。")
    try:
        size = len(source.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("HTML 输入含无效 Unicode 字符。") from exc
    if size > MAX_INPUT_BYTES:
        raise ValueError("HTML 输入超过 2 MiB 限制。")
    if "\0" in source:
        raise ValueError("HTML 输入含空字符，无法可靠解析。")
    parser = _Parser()
    try:
        # Universal line endings retain the source's physical line numbers.
        parser.feed(source.replace("\r\n", "\n").replace("\r", "\n"))
        if "<" in parser.rawdata:
            parser.warn("HTML 尾部标签或注释可能截断，请对照源码。")
        parser.close()
    except (AssertionError, RecursionError) as exc:
        raise ValueError("HTML 解析不可靠，已停止提取，请对照源码。") from exc
    if any(node.tag not in _OPTIONAL for node in parser.stack[1:]):
        parser.warn("HTML 存在未闭合标签，内容可能截断，解析结果可能不可靠。")
    roots = _regions(
        parser.root,
        lambda n: bool({"prd-body", "prd-content"} & set(n.attrs.get("class", "").split())),
        dedicated=True,
    )
    if not roots:
        roots = _regions(parser.root, lambda n: n.attrs.get("id") == "prdDrawer", dedicated=True)
    dedicated = bool(roots)
    if not dedicated:
        parser.warn("无专用正文，已退化为 body 全部可读文字（可能包含界面控件）。")
        roots = _regions(parser.root, lambda n: n.tag == "body", dedicated=False)
        if not roots:
            parser.warn("HTML 无 body 元素，按片段提取可读文字。")
            roots = [parser.root]
    extractor = _Extractor(parser, dedicated)
    for root in roots:
        extractor.region(root)
    if not extractor.sections:
        parser.warn("无正文：未找到可读正文文字。")
    return HtmlAnalysis(tuple(extractor.sections), tuple(parser.warnings), parser.has_scripts)
