from __future__ import annotations

import importlib
import importlib.util
import os
import random
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPalette, QTextCursor, QTextFormat
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from shiboken6 import isValid


class DiffViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.font_id = -1
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if not QFontDatabase.families() and font_path.is_file():
            cls.font_id = QFontDatabase.addApplicationFont(str(font_path))

    @classmethod
    def tearDownClass(cls) -> None:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if cls.font_id >= 0:
            QFontDatabase.removeApplicationFont(cls.font_id)

    def setUp(self) -> None:
        palette, font, stylesheet = (
            self.app.palette(), self.app.font(), self.app.styleSheet(),
        )

        def restore_appearance() -> None:
            self.app.setStyleSheet("")
            self.app.setPalette(palette)
            self.app.setFont(font)
            self.app.setStyleSheet(stylesheet)

        # MainWindow tests leave application-wide QSS behind. Its explicit text
        # color overrides setPalette(), so palette-only tests need a clean QSS.
        # Restore the caller's appearance after disposing this test's widgets.
        self.addCleanup(restore_appearance)
        self.app.setStyleSheet("")
        self.assertIsNotNone(
            importlib.util.find_spec("clickgit.ui.diff_viewer"),
            "独立 DiffViewer 尚未实现",
        )
        self.module = importlib.import_module("clickgit.ui.diff_viewer")
        self.viewer = self.module.DiffViewer()
        self.addCleanup(self.dispose_viewer)

    def dispose_viewer(self) -> None:
        if isValid(self.viewer):
            self.viewer.close()
            self.viewer.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def copied(self, editor: QPlainTextEdit) -> str:
        editor.selectAll()
        return editor.createMimeDataFromSelection().text()

    def inline_selections(self, editor: QPlainTextEdit):
        return [
            item for item in editor.extraSelections()
            if not item.format.boolProperty(QTextFormat.FullWidthSelection)
        ]

    def test_comparison_loaded_is_false_initially_and_after_clear(self) -> None:
        self.assertIs(getattr(self.viewer, "comparison_loaded", None), False)
        for message in (None, "正在读取", "无法比较"):
            self.viewer.set_comparison("old", "new")
            self.assertIs(self.viewer.comparison_loaded, True)
            if message is None:
                self.viewer.clear()
            else:
                self.viewer.clear(message)
            self.assertIs(self.viewer.comparison_loaded, False)

    def test_comparison_loaded_is_true_for_all_successful_render_modes(self) -> None:
        for left, right in (
            ("", ""), ("相同😀\n", "相同😀\n"), ("原😀", "新🙂"),
            ("a\nc", "a\nb\nc"), ("ab" * 2000, "ba" * 2000),
        ):
            with self.subTest(left_length=len(left), right_length=len(right)):
                self.viewer.set_comparison(left, right)
                self.assertIs(getattr(self.viewer, "comparison_loaded", None), True)

    def test_comparison_loaded_is_false_for_every_limit_after_success(self) -> None:
        cases = (
            ("a" * (2 * 1024 * 1024 + 1), "small", "2 MiB"),
            ("中" * 700000, "small", "2 MiB"),
            ("\n" * 20000, "small", "20000"),
            ("a" * 8193, "small", "单行"),
            ("a\nb\n" * 4000, "b\na\n" * 4000, "复杂度"),
        )
        for left, right, reason in cases:
            for a, b in ((left, right), (right, left)):
                with self.subTest(reason=reason, left_length=len(a)):
                    self.viewer.set_comparison("before", "after")
                    self.assertIs(getattr(self.viewer, "comparison_loaded", None), True)
                    self.viewer.set_comparison(a, b)
                    self.assertIs(self.viewer.comparison_loaded, False)
                    self.assertIn(reason, self.viewer.status_label.text())
                    self.viewer.set_comparison("recovered", "recovered")
                    self.assertIs(self.viewer.comparison_loaded, True)

    def test_comparison_loaded_stays_false_until_both_editors_finish(self) -> None:
        self.viewer.set_comparison("before", "after")
        self.assertIs(getattr(self.viewer, "comparison_loaded", None), True)
        original = self.viewer.right_editor.set_rows
        loaded_states = []

        def fail_render(source, rows):
            loaded_states.append(self.viewer.comparison_loaded)
            if rows:
                raise RuntimeError("simulated render failure")
            return original(source, rows)

        with patch.object(self.viewer.right_editor, "set_rows", side_effect=fail_render):
            with self.assertRaisesRegex(RuntimeError, "simulated render failure"):
                self.viewer.set_comparison("new left", "new right")
        self.assertEqual(loaded_states, [False, False])
        self.assertIs(self.viewer.comparison_loaded, False)
        self.viewer.set_comparison("recovered", "recovered")
        self.assertIs(self.viewer.comparison_loaded, True)

    def test_initial_and_clear_state_are_read_only_and_reset_everything(self) -> None:
        for editor in (self.viewer.left_editor, self.viewer.right_editor):
            self.assertIsInstance(editor, QPlainTextEdit)
            self.assertTrue(editor.isReadOnly())
            self.assertEqual(editor.lineWrapMode(), QPlainTextEdit.NoWrap)
        self.assertIn("请选择文件", self.viewer.status_label.text())
        self.viewer.set_comparison("old", "new", "左", "右", "不是最终合并结果")
        self.viewer.next_difference()
        self.viewer.clear("没有可显示的文本")
        self.assertEqual(self.viewer.status_label.text(), "没有可显示的文本")
        self.assertEqual(self.viewer.notice_label.text(), "")
        self.assertEqual(self.viewer.left_title_label.toolTip(), "")
        self.assertEqual(self.viewer.right_title_label.toolTip(), "")
        self.assertEqual(self.viewer.status_label.toolTip(), "")
        self.assertEqual(self.viewer.difference_count, 0)
        self.assertEqual(self.viewer.current_difference, -1)
        for editor in (self.viewer.left_editor, self.viewer.right_editor):
            self.assertEqual(editor.toPlainText(), "")
            self.assertFalse(editor.extraSelections())
        self.assertFalse(self.viewer.next_button.isEnabled())
        self.assertFalse(self.viewer.previous_button.isEnabled())

    def test_empty_and_identical_text(self) -> None:
        for text in ("", "相同😀", "one\n\nthree\n"):
            with self.subTest(text=text):
                self.viewer.set_comparison(text, text)
                self.assertEqual(self.viewer.difference_count, 0)
                self.assertIn("相同", self.viewer.status_label.text())
                self.assertEqual(self.copied(self.viewer.left_editor), text)
                self.assertFalse(self.viewer.left_editor.extraSelections())
                self.viewer.next_difference()
                self.viewer.previous_difference()
                self.assertEqual(self.viewer.current_difference, -1)

    def test_titles_and_notice_are_literal_plain_text(self) -> None:
        self.viewer.set_comparison("a", "b", "<b>原文</b>", "改后", "<i>不是合并结果</i>")
        self.assertEqual(self.viewer.left_title_label.text(), "<b>原文</b>")
        self.assertEqual(self.viewer.right_title_label.text(), "改后")
        self.assertEqual(self.viewer.notice_label.text(), "<i>不是合并结果</i>")
        for label in (self.viewer.left_title_label, self.viewer.notice_label):
            self.assertEqual(label.textFormat(), Qt.PlainText)

    def test_insert_delete_align_rows_without_polluting_copy(self) -> None:
        for left, right, numbers_left, numbers_right in (
            ("a\nc", "a\nb\nc", [1, None, 2], [1, 2, 3]),
            ("a\nb\nc", "a\nc", [1, 2, 3], [1, None, 2]),
            ("", "新增\n第二行", [1, None], [1, 2]),
            ("删除\n第二行", "", [1, 2], [1, None]),
        ):
            with self.subTest(left=left, right=right):
                self.viewer.set_comparison(left, right)
                self.assertEqual(self.viewer.left_editor.line_numbers, numbers_left)
                self.assertEqual(self.viewer.right_editor.line_numbers, numbers_right)
                self.assertEqual(self.viewer.left_editor.blockCount(),
                                 self.viewer.right_editor.blockCount())
                self.assertEqual(self.copied(self.viewer.left_editor), left)
                self.assertEqual(self.copied(self.viewer.right_editor), right)
                self.assertGreater(self.viewer.left_editor.viewportMargins().left(), 0)

    def test_partial_copy_skips_alignment_blanks_and_line_numbers(self) -> None:
        self.viewer.set_comparison("中文😀\n末尾", "中文😀\n插入\n末尾")
        editor = self.viewer.left_editor
        cursor = QTextCursor(editor.document())
        cursor.setPosition(1)
        last = editor.document().lastBlock()
        cursor.setPosition(last.position() + 1, QTextCursor.KeepAnchor)
        editor.setTextCursor(cursor)
        self.assertEqual(editor.createMimeDataFromSelection().text(), "文😀\n末")

    def test_native_copy_uses_original_text_not_padded_document(self) -> None:
        if self.app.platformName() != "offscreen":
            self.skipTest("Avoid changing the user's system clipboard")
        self.viewer.set_comparison("一\r\n😀三\n", "一\r\n二\n😀三\n")
        clipboard = self.app.clipboard()
        previous = clipboard.text()
        self.addCleanup(clipboard.setText, previous)
        self.viewer.left_editor.selectAll()
        self.viewer.left_editor.copy()
        self.assertEqual(clipboard.text(), "一\r\n😀三\n")

    def test_multiple_hunks_navigation_wraps_and_buttons_work(self) -> None:
        self.viewer.set_comparison("a\nold\nsame\nlast", "a\nnew\nsame\nadded\nlast")
        self.assertEqual(self.viewer.difference_count, 2)
        self.assertEqual(self.viewer.current_difference, -1)
        self.viewer.next_button.click()
        self.assertEqual(self.viewer.current_difference, 0)
        self.assertEqual(self.viewer.left_editor.textCursor().blockNumber(), 1)
        self.viewer.next_button.click()
        self.assertEqual(self.viewer.current_difference, 1)
        self.assertEqual(self.viewer.right_editor.textCursor().blockNumber(), 3)
        self.viewer.next_button.click()
        self.assertEqual(self.viewer.current_difference, 0)
        self.viewer.previous_button.click()
        self.assertEqual(self.viewer.current_difference, 1)
        self.assertIn("2/2", self.viewer.status_label.text())
        self.viewer.set_comparison("x", "x")
        self.assertEqual(self.viewer.current_difference, -1)
        self.assertFalse(self.viewer.next_button.isEnabled())

    def test_trailing_newline_is_a_real_difference(self) -> None:
        for left, right in (("a", "a\n"), ("a\n", "a"), ("", "\n"), ("a\n", "a\n\n")):
            with self.subTest(left=left, right=right):
                self.viewer.set_comparison(left, right)
                self.assertGreater(self.viewer.difference_count, 0)
                self.assertIn("末尾换行", self.viewer.status_label.text())
                self.assertEqual(self.copied(self.viewer.left_editor), left)
                self.assertEqual(self.copied(self.viewer.right_editor), right)

    def test_crlf_and_unicode_separators_copy_exactly(self) -> None:
        text = "中文😀\r\n中\u2028文\u2029段\r内\n"
        self.viewer.set_comparison(text, text)
        self.assertEqual(self.viewer.difference_count, 0)
        self.assertEqual(self.copied(self.viewer.left_editor), text)
        self.viewer.set_comparison("a\r\n", "a\n")
        self.assertGreater(self.viewer.difference_count, 0)
        self.assertEqual(self.copied(self.viewer.left_editor), "a\r\n")
        self.assertIn("CRLF", self.viewer.status_label.toolTip())

    def test_short_status_moves_display_details_to_tooltip(self) -> None:
        self.viewer.set_comparison("原\r\n", "新\n")
        for word in ("CRLF", "特殊分隔符", "复制"):
            self.assertNotIn(word, self.viewer.status_label.text())
            self.assertIn(word, self.viewer.status_label.toolTip())
        self.assertIn("差异", self.viewer.status_label.text())
        self.assertIn("末尾换行", self.viewer.status_label.text())
        self.assertLess(len(self.viewer.status_label.text()), 45)
        tooltip = self.viewer.status_label.toolTip()
        self.viewer.next_difference()
        self.assertEqual(self.viewer.status_label.toolTip(), tooltip)
        self.viewer.set_comparison("ab" * 2000, "ba" * 2000)
        self.assertIn("行级", self.viewer.status_label.text())
        self.assertLess(len(self.viewer.status_label.text()), 45)
        self.viewer.set_comparison("a" * 8193, "b")
        self.assertEqual(self.viewer.status_label.toolTip(), "")
        self.assertFalse(self.viewer.comparison_loaded)

    def test_unicode_character_highlights_use_utf16_positions(self) -> None:
        self.viewer.set_comparison("前😀旧文🙂后", "前😀新文🚀后")
        for editor, expected in (
            (self.viewer.left_editor, ["旧", "🙂"]),
            (self.viewer.right_editor, ["新", "🚀"]),
        ):
            selections = self.inline_selections(editor)
            self.assertEqual([item.cursor.selectedText() for item in selections], expected)
            self.assertEqual([item.cursor.selectionStart() for item in selections], [3, 5])
            self.assertEqual([item.cursor.selectionEnd() for item in selections], [4, 7])
            self.assertTrue(any(
                item.format.boolProperty(QTextFormat.FullWidthSelection)
                for item in editor.extraSelections()
            ))

    def test_scroll_is_synchronized_in_both_directions(self) -> None:
        left = "\n".join(f"line {i}" for i in range(250))
        right = left.replace("line 100", "inserted\nline 100")
        self.viewer.resize(800, 360)
        self.viewer.show()
        self.viewer.set_comparison(left, right)
        self.app.processEvents()
        a = self.viewer.left_editor.verticalScrollBar()
        b = self.viewer.right_editor.verticalScrollBar()
        self.assertGreater(a.maximum(), 20)
        self.assertEqual(a.maximum(), b.maximum())
        a.setValue(50)
        self.assertEqual(b.value(), 50)
        b.setValue(140)
        self.assertEqual(a.value(), 140)
        self.viewer.next_difference()
        self.assertEqual(a.value(), b.value())

    def test_horizontal_scroll_synchronizes_without_feedback_on_short_side(self) -> None:
        self.viewer.resize(800, 360)
        self.viewer.show()
        self.viewer.set_comparison("abc" * 500, "abc" * 100)
        self.app.processEvents()
        left = self.viewer.left_editor.horizontalScrollBar()
        right = self.viewer.right_editor.horizontalScrollBar()
        self.assertGreater(right.maximum(), 200)
        left.setValue(150)
        self.assertEqual(right.value(), 150)
        right.setValue(100)
        self.assertEqual(left.value(), 100)
        left.setValue(left.maximum())
        self.assertEqual(right.value(), right.maximum())
        self.assertEqual(left.value(), left.maximum())

    def test_three_palette_changes_rebuild_highlights_and_keep_text(self) -> None:
        from clickgit.ui.styles import theme_values

        self.viewer.set_comparison("中文😀old", "中文😀new")
        colors = []
        for theme in ("light", "dark", "tech"):
            values = theme_values(theme)
            palette = QPalette()
            for role, key in (
                (QPalette.Base, "surface"), (QPalette.Text, "text"),
                (QPalette.AlternateBase, "surface_alt"),
                (QPalette.Highlight, "selection"), (QPalette.Link, "primary"),
                (QPalette.LinkVisited, "muted"),
            ):
                palette.setColor(role, QColor(values[key]))
            self.viewer.setPalette(palette)
            self.app.processEvents()
            selection = self.viewer.left_editor.extraSelections()[0]
            colors.append(selection.format.background().color().name())
            self.assertEqual(selection.format.foreground().color(), QColor(values["text"]))
            self.assertEqual(self.copied(self.viewer.left_editor), "中文😀old")
        self.assertEqual(len(set(colors)), 3)

    def test_application_themes_with_qss_refresh_both_editors(self) -> None:
        from clickgit.models import AppSettings
        from clickgit.ui.styles import theme_values
        from clickgit.ui.themes import ThemeManager

        manager = ThemeManager(self.app)

        def dispose_manager() -> None:
            manager.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

        self.addCleanup(dispose_manager)
        self.viewer.set_comparison("中文😀old", "中文😀new")
        self.viewer.show()
        backgrounds = []
        for theme in ("light", "dark", "tech", "light"):
            with self.subTest(theme=theme):
                manager.apply(AppSettings(theme=theme))
                self.app.processEvents()
                self.assertTrue(self.app.styleSheet())
                expected = QColor(theme_values(theme)["text"])
                row_colors = []
                for editor, source in (
                    (self.viewer.left_editor, "中文😀old"),
                    (self.viewer.right_editor, "中文😀new"),
                ):
                    self.assertEqual(editor.palette().color(QPalette.Text), expected)
                    selections = editor.extraSelections()
                    self.assertGreater(len(selections), 1)
                    for selection in selections:
                        self.assertEqual(selection.format.foreground().color(), expected)
                    row_colors.append(selections[0].format.background().color().name())
                    self.assertEqual(self.copied(editor), source)
                backgrounds.append(tuple(row_colors))
        self.assertEqual(len(set(backgrounds[:3])), 3)
        self.assertEqual(backgrounds[0], backgrounds[3])

    def test_oversize_utf8_and_line_limits_refuse_before_diff_or_render(self) -> None:
        for text in ("a" * (2 * 1024 * 1024 + 1), "中" * 700000,
                     "\n" * 20000):
            with self.subTest(length=len(text)):
                self.viewer.set_comparison("stale", "changed")
                started = time.monotonic()
                with patch.object(self.module, "SequenceMatcher",
                                  side_effect=AssertionError("must reject before matching")):
                    self.viewer.set_comparison("small", text, notice="只读来源")
                self.assertLess(time.monotonic() - started, 2.0)
                self.assertIn("上限", self.viewer.status_label.text())
                self.assertEqual(self.viewer.notice_label.text(), "只读来源")
                self.assertEqual(self.viewer.left_editor.toPlainText(), "")
                self.assertEqual(self.viewer.right_editor.toPlainText(), "")
                self.assertEqual(self.viewer.difference_count, 0)

    def test_pathological_repeated_lines_and_long_line_are_bounded(self) -> None:
        left = "a\nb\n" * 4000
        right = "b\na\n" * 4000
        with patch.object(self.module, "SequenceMatcher",
                          side_effect=AssertionError("must reject pathological matrix")):
            started = time.monotonic()
            self.viewer.set_comparison(left, right)
            self.assertLess(time.monotonic() - started, 2.0)
        self.assertIn("复杂度", self.viewer.status_label.text())
        self.viewer.set_comparison("a" * 100000, "b" * 100000)
        self.assertIn("单行", self.viewer.status_label.text())
        self.assertEqual(self.viewer.left_editor.toPlainText(), "")

    def test_long_character_diff_falls_back_to_line_highlight(self) -> None:
        self.viewer.set_comparison("ab" * 2000, "ba" * 2000)
        self.assertEqual(self.viewer.difference_count, 1)
        self.assertTrue(self.viewer.left_editor.extraSelections())
        self.assertFalse(self.inline_selections(self.viewer.left_editor))
        self.assertIn("行级", self.viewer.status_label.text())

    def test_long_html_small_edits_highlight_only_changed_characters(self) -> None:
        prefix = "<tr>" + '<td class="seq">项目😀</td>' * 150 + "<td>电池接插件"
        suffix = "更换</td>" + "<td>保持原样</td>" * 150 + "</tr>"
        for old, new, expected_left, expected_right in (
            ("", "00", [], ["00"]),
            ("00", "", ["00"], []),
            ("旧🙂", "新🚀", ["旧🙂"], ["新🚀"]),
        ):
            with self.subTest(old=old, new=new):
                left, right = prefix + old + suffix, prefix + new + suffix
                self.viewer.set_comparison(left, right)
                self.assertTrue(self.viewer.comparison_loaded)
                self.assertNotIn("行级", self.viewer.status_label.text())
                for editor, expected, source in (
                    (self.viewer.left_editor, expected_left, left),
                    (self.viewer.right_editor, expected_right, right),
                ):
                    selections = self.inline_selections(editor)
                    self.assertEqual([s.cursor.selectedText() for s in selections], expected)
                    if selections:
                        self.assertEqual(selections[0].cursor.selectionStart(),
                                         len(prefix.encode("utf-16-le")) // 2)
                    self.assertEqual(self.copied(editor), source)

    def test_trimmed_middle_keeps_separate_edits_and_character_budget(self) -> None:
        prefix, suffix = "前😀" * 750, "后" * 2000
        calls = []
        original = self.module.SequenceMatcher

        def measured(junk, a, b, **kwargs):
            if isinstance(a, str):
                calls.append((len(a), len(b)))
            return original(junk, a, b, **kwargs)

        with patch.object(self.module, "SequenceMatcher", side_effect=measured):
            self.viewer.set_comparison(prefix + "旧-保持-甲" + suffix,
                                       prefix + "新-保持-乙" + suffix)
        self.assertEqual(calls, [(6, 6)])
        for editor, expected in ((self.viewer.left_editor, ["旧", "甲"]),
                                 (self.viewer.right_editor, ["新", "乙"])):
            self.assertEqual([s.cursor.selectedText() for s in self.inline_selections(editor)],
                             expected)

    def test_inline_semantic_colors_are_distinct_and_readable_in_three_themes(self) -> None:
        from clickgit.models import AppSettings
        from clickgit.ui.themes import ThemeManager

        def luminance(color):
            channels = [v / 255 for v in (color.red(), color.green(), color.blue())]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                      for v in channels]
            return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))

        manager = ThemeManager(self.app)
        self.addCleanup(manager.deleteLater)
        self.viewer.set_comparison("电池旧部件", "电池新部件")
        for theme in ("light", "dark", "tech"):
            with self.subTest(theme=theme):
                manager.apply(AppSettings(theme=theme))
                self.app.processEvents()
                backgrounds = []
                for editor in (self.viewer.left_editor, self.viewer.right_editor):
                    selection = self.inline_selections(editor)[0]
                    color = selection.format.background().color()
                    foreground = selection.format.foreground().color()
                    backgrounds.append(color)
                    light, dark = sorted((luminance(color), luminance(foreground)), reverse=True)
                    self.assertGreaterEqual((light + .05) / (dark + .05), 4.5)
                    row_selection = editor.extraSelections()[0]
                    row = row_selection.format.background().color()
                    self.assertGreater(sum(abs(a - b) for a, b in zip(
                        color.getRgb()[:3], row.getRgb()[:3])), 70)
                removed, added = backgrounds
                self.assertGreater(removed.red(), removed.green() + 35)
                self.assertGreater(added.green(), added.red() + 25)

    def test_distant_edits_in_long_line_still_fall_back_safely(self) -> None:
        self.viewer.set_comparison("旧" + "重复" * 1800 + "甲",
                                   "新" + "重复" * 1800 + "乙")
        self.assertTrue(self.viewer.comparison_loaded)
        self.assertIn("行级", self.viewer.status_label.text())
        self.assertFalse(self.inline_selections(self.viewer.left_editor))

    def test_insertion_at_long_line_edges_respects_exact_limit(self) -> None:
        source = "x" * 8190
        for offset in (0, 4095, 8190):
            with self.subTest(offset=offset):
                changed = source[:offset] + "00" + source[offset:]
                self.viewer.set_comparison(source, changed)
                self.assertTrue(self.viewer.comparison_loaded)
                selected = self.inline_selections(self.viewer.right_editor)
                self.assertEqual([s.cursor.selectedText() for s in selected], ["00"])
                self.assertEqual(selected[0].cursor.selectionStart(), offset)
                self.assertFalse(self.inline_selections(self.viewer.left_editor))
                self.assertEqual(self.copied(self.viewer.right_editor), changed)

    def test_large_identical_or_small_middle_change_remains_cheap(self) -> None:
        text = "\n".join(f"行{i}" for i in range(20000))
        started = time.monotonic()
        self.viewer.set_comparison(text, text)
        self.assertEqual(self.viewer.difference_count, 0)
        self.viewer.set_comparison(text, text.replace("行9999\n", "变更9999\n"))
        self.assertEqual(self.viewer.difference_count, 1)
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(self.copied(self.viewer.left_editor), text)

    def test_character_budget_is_shared_across_replacement_rows(self) -> None:
        left = "\n".join(f"{i}:" + "ab" * 30 for i in range(300))
        right = "\n".join(f"{i}:" + "ba" * 30 for i in range(300))
        calls = []
        original = self.module.SequenceMatcher

        def measured(junk, a, b, **kwargs):
            if isinstance(a, str):
                calls.append(len(a) * len(b))
            return original(junk, a, b, **kwargs)

        with patch.object(self.module, "SequenceMatcher", side_effect=measured):
            self.viewer.set_comparison(left, right)
        self.assertGreater(len(calls), 0)
        self.assertLess(len(calls), 300)
        self.assertLessEqual(sum(calls), 100000)
        self.assertTrue(self.inline_selections(self.viewer.left_editor))
        self.assertIn("行级", self.viewer.status_label.text())

    def test_exact_byte_limit_is_accepted_for_safe_lines(self) -> None:
        text = ("a" * 4095 + "\n") * 512
        self.assertEqual(len(text.encode("utf-8")), 2 * 1024 * 1024)
        started = time.monotonic()
        self.viewer.set_comparison(text, text)
        self.assertIn("相同", self.viewer.status_label.text())
        self.assertEqual(self.copied(self.viewer.left_editor), text)
        self.assertLess(time.monotonic() - started, 5.0)

    def test_seeded_small_inputs_preserve_both_sources_and_alignment(self) -> None:
        rng = random.Random(173)
        vocabulary = ["", "同", "中😀", "abc", "a\tb", "x\u2029y", "末\r内"]
        for _ in range(60):
            left = "\n".join(rng.choices(vocabulary, k=rng.randrange(1, 12)))
            right = "\n".join(rng.choices(vocabulary, k=rng.randrange(1, 12)))
            with self.subTest(left=left, right=right):
                self.viewer.set_comparison(left, right)
                self.assertEqual(self.copied(self.viewer.left_editor), left)
                self.assertEqual(self.copied(self.viewer.right_editor), right)
                self.assertEqual(self.viewer.left_editor.blockCount(),
                                 self.viewer.right_editor.blockCount())
                self.assertEqual(self.viewer.difference_count == 0, left == right)

    def test_disposal_destroys_native_widgets(self) -> None:
        editor = self.viewer.left_editor
        self.dispose_viewer()
        self.assertFalse(isValid(self.viewer))
        self.assertFalse(isValid(editor))


if __name__ == "__main__":
    unittest.main()
