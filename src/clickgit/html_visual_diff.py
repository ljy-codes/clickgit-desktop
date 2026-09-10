"""Bounded text-node comparison of sanitized HTML, never source-file edits.

This is a review aid, not a DOM/pixel diff. CSS visibility is not evaluated:
hidden text is included in the change details but may not be locatable.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from html import escape
from html.parser import HTMLParser

from clickgit.html_preview_policy import prepare_html, PreviewPolicyError

MAX_TEXT_NODES = 4000
MAX_COMPARE_WORK = 1_000_000
MAX_CHANGES = 500
_VOID = {"meta", "br", "col", "hr", "input", "wbr"}
_UNMARKABLE = {"textarea", "select", "option", "optgroup"}
_COLORS = {"新增": "#bbf7d0", "删除": "#fecaca", "修改": "#fed7aa"}


@dataclass(frozen=True)
class TextChange:
    kind: str
    left: str
    right: str
    marker: str
    left_marked: bool
    right_marked: bool


@dataclass(frozen=True)
class VisualComparison:
    left: str
    right: str
    changes: tuple[TextChange, ...]
    notice: str
    limited: bool = False


class _TextDocument(HTMLParser):
    CDATA_CONTENT_ELEMENTS = ("style",)

    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.nodes = []
        self.feed(document)
        self.close()

    def handle_decl(self, decl):
        self.parts.append("<!doctype html>")

    def handle_starttag(self, tag, attrs):
        # Only ever consumes prepare_html output, not untrusted raw tags.
        self.parts.append(self.get_starttag_text())
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        self.parts.append(f"</{tag}>")
        if tag in self.stack:
            del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag):]

    def handle_data(self, text):
        part = len(self.parts)
        self.parts.append(text if "style" in self.stack else escape(text, quote=False))
        if "body" in self.stack and "style" not in self.stack and text.strip():
            self.nodes.append((part, text, not any(t in _UNMARKABLE for t in self.stack)))

    def mark(self, begin, end, kind, marker):
        used = False
        for part, text, markable in self.nodes[begin:end]:
            if not markable:
                continue
            # Each node gets the group marker: an earlier hidden node must not
            # prevent native search from finding a later visible changed node.
            badge = (
                '<span style="display:inline!important;font:11px sans-serif!important;'
                'color:#111827!important;background-color:#fff!important;">'
                f'{escape(marker)}</span>')
            used = True
            self.parts[part] = (
                f'<span style="background-color:{_COLORS[kind]}!important;'
                'color:#111827!important;outline:1px solid #9a3412!important;">'
                f'{badge}{escape(text, quote=False)}</span>')
        return used


def compare_html_text(left: str, right: str) -> VisualComparison:
    """No IO or Qt. Inputs and generated outputs pass existing preview policy."""
    safe_left, safe_right = prepare_html(left), prepare_html(right)
    old, new = _TextDocument(safe_left), _TextDocument(safe_right)

    def limited():
        return VisualComparison(safe_left, safe_right, (),
                                "正文高亮超过比较或显示预算，已降级为原页面；请查看需求/源码对比。", True)

    if (len(old.nodes) + len(new.nodes) > MAX_TEXT_NODES
            or len(old.nodes) * len(new.nodes) > MAX_COMPARE_WORK):
        return limited()
    before, after = [n[1] for n in old.nodes], [n[1] for n in new.nodes]
    # Intern strings before SequenceMatcher's inner loops; cost is bounded by
    # node count rather than repeatedly comparing very long repeated strings.
    vocabulary = {}
    a = [vocabulary.setdefault(text, len(vocabulary)) for text in before]
    b = [vocabulary.setdefault(text, len(vocabulary)) for text in after]
    opcodes = SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    changed = [op for op in opcodes if op[0] != "equal"]
    if len(changed) > MAX_CHANGES:
        return limited()
    prefix = "[CG改动"
    for _ in range(32):
        if prefix not in safe_left and prefix not in safe_right:
            break
        prefix += "·"
    else:
        return limited()
    changes = []
    for index, (operation, i, j, k, m) in enumerate(changed, 1):
        kind = {"replace": "修改", "insert": "新增", "delete": "删除"}[operation]
        marker = f"{prefix}{index}]"
        changes.append(TextChange(
            kind, "\n".join(before[i:j]), "\n".join(after[k:m]), marker,
            old.mark(i, j, kind, marker), new.mark(k, m, kind, marker)))
    try:
        # Revalidation bounds the added markup as well as the original source.
        output_left = prepare_html("".join(old.parts))
        output_right = prepare_html("".join(new.parts))
    except PreviewPolicyError:
        return limited()
    notice = (
        f"共 {len(changes)} 处正文改动：绿＝新增，红＝删除，橙＝修改。"
        "隐藏正文请看下方详情；样式、属性、脚本变化请查源码。"
        if changes else
        "左右原文件内容完全相同。" if left == right else
        "未发现可提取正文差异，但原文件不同；请检查源码中的样式、属性、脚本或空白变化。"
    )
    return VisualComparison(output_left, output_right, tuple(changes), notice)
