from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette, QStyleHints
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QHeaderView, QLabel, QLineEdit,
    QListWidget, QMenu, QPlainTextEdit, QProgressBar, QPushButton,
    QSpinBox, QStyle, QStyleOptionButton, QTabWidget, QTableWidget,
    QToolButton, QTreeWidget, QVBoxLayout,
)

from clickgit.models import AppSettings
from clickgit.ui import styles


def contrast(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        color = QColor(value)
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    first, second = sorted((luminance(foreground), luminance(background)))
    return (second + 0.05) / (first + 0.05)


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.test_font_id = -1
        # Windows offscreen has no font database. Use an installed local font so
        # geometry tests measure real glyphs, without shipping/downloading fonts.
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if not QFontDatabase.families() and font_path.is_file():
            cls.test_font_id = QFontDatabase.addApplicationFont(str(font_path))

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.test_font_id >= 0:
            QFontDatabase.removeApplicationFont(cls.test_font_id)

    def setUp(self) -> None:
        self.original_style = self.app.styleSheet()
        self.original_palette = QPalette(self.app.palette())
        self.original_font = QFont(self.app.font())
        self.addCleanup(self.restore_application)

    def restore_application(self) -> None:
        # All widget/manager deleteLater cleanups run before this (LIFO).
        # processEvents() alone does not deliver DeferredDelete without exec().
        # Leaving these objects alive lets a later suite repolish stale native
        # widget/style state and can crash inside QApplication.setStyleSheet().
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.setStyleSheet("")
        self.app.setPalette(self.original_palette)
        self.app.setFont(self.original_font)
        self.app.setStyleSheet(self.original_style)
        self.app.processEvents()

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("clickgit.ui.themes"),
                             "ThemeManager module has not been implemented")
        return importlib.import_module("clickgit.ui.themes")

    def values(self, theme: str):
        self.assertTrue(hasattr(styles, "theme_values"), "Semantic theme API is missing")
        return styles.theme_values(theme)

    def manager(self):
        manager = self.api().ThemeManager(self.app)
        self.addCleanup(manager.deleteLater)
        # Disconnect first: deferred QObject deletion may occur after another test.
        self.addCleanup(self.app.styleHints().colorSchemeChanged.disconnect,
                        manager._on_color_scheme_changed)
        return manager

    def test_three_complete_distinct_semantic_palettes(self) -> None:
        required = {
            "background", "surface", "surface_alt", "text", "text_muted", "muted",
            "border", "primary", "primary_text", "danger", "warning", "success",
            "diff_add", "diff_remove", "selection", "selection_text",
            "disabled_background", "disabled_text", "focus",
        }
        palettes = [self.values(theme) for theme in ("light", "dark", "tech")]
        self.assertEqual(set(styles.THEME_PALETTES), {"light", "dark", "tech"})
        self.assertEqual(len({p["background"] for p in palettes}), 3)
        self.assertEqual(palettes[0]["surface"], "#ffffff")
        for palette in palettes:
            self.assertTrue(required <= palette.keys())
            self.assertEqual(palette["muted"], palette["text_muted"])
            self.assertTrue(all(QColor(value).isValid() for value in palette.values()))

    def test_text_status_selection_and_disabled_contrast(self) -> None:
        for theme in ("light", "dark", "tech"):
            p = self.values(theme)
            for foreground in ("text", "muted", "success", "danger", "warning"):
                for background in ("background", "surface", "surface_alt"):
                    with self.subTest(theme=theme, fg=foreground, bg=background):
                        self.assertGreaterEqual(contrast(p[foreground], p[background]), 4.5)
            for fg, bg in (("primary_text", "primary"), ("selection_text", "selection"),
                           ("disabled_text", "disabled_background"),
                           ("text", "diff_add"), ("text", "diff_remove")):
                self.assertGreaterEqual(contrast(p[fg], p[bg]), 4.5, (theme, fg, bg))

    def test_semantic_values_cannot_mutate_global_theme(self) -> None:
        values = self.values("dark")
        original = values["text"]
        try:
            values["text"] = "#123456"
        except TypeError:
            pass
        self.assertEqual(self.values("dark")["text"], original)

    def test_legacy_import_is_generated_default_light(self) -> None:
        self.values("light")
        self.assertEqual(styles.APP_STYLE, styles.build_stylesheet("light"))
        self.assertIn("font-size: 14px", styles.APP_STYLE)

    def test_theme_values_is_reexported_for_main_window(self) -> None:
        self.assertIs(self.api().theme_values, styles.theme_values)

    def test_primary_focus_border_contrasts_with_button_fill(self) -> None:
        for theme in ("light", "dark", "tech"):
            p = self.values(theme)
            qss = styles.build_stylesheet(theme)
            borders = []
            for selectors, body in re.findall(r"([^{}]+)\{([^{}]+)\}", qss):
                if "QPushButton#primaryButton:focus" in selectors:
                    borders.extend(re.findall(r"border:\s*2px dashed (#[0-9a-f]{6})", body))
            self.assertTrue(borders)
            self.assertGreaterEqual(contrast(borders[-1], p["primary"]), 3.0)

    def test_semantic_status_labels_have_readable_foreground_and_emphasis(self) -> None:
        manager = self.manager()
        labels = {}
        for key in ("danger", "warning"):
            label = QLabel(f"{key}: status explanation")
            label.setObjectName(f"{key}Label")
            self.addCleanup(label.deleteLater)
            labels[key] = label
        for theme in ("light", "dark", "tech"):
            manager.apply(AppSettings(theme=theme))
            for key, label in labels.items():
                with self.subTest(theme=theme, label=key):
                    label.ensurePolished()
                    self.app.processEvents()
                    self.assertEqual(label.palette().color(QPalette.WindowText).name(),
                                     self.values(theme)[key])
                    self.assertGreaterEqual(label.font().weight(), 600)

    def test_header_container_does_not_double_apply_section_padding(self) -> None:
        manager = self.manager()
        table = QTableWidget(1, 2)
        table.setHorizontalHeaderLabels(["状态 Status", "文件 File"])
        self.addCleanup(table.deleteLater)
        for font_size in (12, 14, 16, 18):
            manager.apply(AppSettings(theme="dark", font_size_px=font_size))
            table.ensurePolished()
            table.horizontalHeader().ensurePolished()
            self.app.processEvents()
            header = table.horizontalHeader()
            self.assertEqual(header.contentsMargins().top(), 0)
            self.assertEqual(header.contentsMargins().bottom(), 0)
            self.assertGreaterEqual(header.sizeHint().height(), header.fontMetrics().height() + 4)

    def test_qss_covers_controls_states_and_existing_object_names(self) -> None:
        self.values("light")
        selectors = (
            "QDialog", "QMenu", "QMenuBar", "QComboBox QAbstractItemView", "QToolTip",
            "QTabBar::tab", "QHeaderView::section", "QScrollBar", "QProgressBar::chunk",
            ":focus", ":read-only", ":disabled", "#navigation", "#recentRepositories",
            "#repositoryBar", "#repositoryName", "#branchBadge", "#primaryButton",
            "#commitButton", "#dangerButton", "#pageTitle", "#mutedLabel", "#sectionLine",
            "#settingsNotice",
        )
        for theme in ("light", "dark", "tech"):
            qss = styles.build_stylesheet(theme)
            for selector in selectors:
                self.assertIn(selector, qss, (theme, selector))
            # Focus/selection have shape/weight cues as well as color.
            self.assertIn("dashed", qss)
            self.assertIn("font-weight: 600", qss)

    def test_invalid_style_inputs_fail_before_changing_application(self) -> None:
        manager = self.manager()
        manager.apply(AppSettings(theme="dark"))
        original = (self.app.styleSheet(), self.app.palette(), self.app.font())
        for settings in (AppSettings(theme="unknown"), AppSettings(font_size_px=15),
                         AppSettings(density="tiny")):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                manager.apply(settings)
            self.assertEqual((self.app.styleSheet(), self.app.palette(), self.app.font()),
                             original)
        for theme in ("system", "unknown"):
            with self.assertRaises(ValueError):
                styles.theme_values(theme)

    def test_constructor_does_not_apply_any_style_or_font(self) -> None:
        before = (self.app.styleSheet(), self.app.palette(), self.app.font())
        manager = self.manager()
        self.assertIsInstance(manager.effective_theme, str)
        self.app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        self.app.processEvents()
        self.assertEqual((self.app.styleSheet(), self.app.palette(), self.app.font()), before)

    def test_apply_updates_palette_font_and_signal_for_all_themes(self) -> None:
        manager = self.manager()
        changes = []
        manager.changed.connect(changes.append)
        role_keys = {
            QPalette.Window: "background", QPalette.Base: "surface",
            QPalette.AlternateBase: "surface_alt", QPalette.WindowText: "text",
            QPalette.Text: "text", QPalette.ButtonText: "text",
            QPalette.Highlight: "selection", QPalette.HighlightedText: "selection_text",
            QPalette.ToolTipBase: "surface", QPalette.ToolTipText: "text",
            QPalette.PlaceholderText: "muted",
        }
        for theme in ("light", "dark", "tech"):
            manager.apply(AppSettings(theme=theme, font_size_px=16, density="compact"))
            self.assertEqual(manager.effective_theme, theme)
            self.assertEqual(changes[-1], theme)
            self.assertEqual(self.app.font().pixelSize(), 16)
            palette = self.app.palette()
            p = self.values(theme)
            for group in (QPalette.Active, QPalette.Inactive):
                for role, key in role_keys.items():
                    self.assertEqual(palette.color(group, role).name(), p[key])
            self.assertEqual(palette.color(QPalette.Disabled, QPalette.Text).name(),
                             p["disabled_text"])
            self.assertEqual(palette.color(QPalette.Disabled, QPalette.Base).name(),
                             p["disabled_background"])
        self.assertEqual(changes, ["light", "dark", "tech"])

    def test_system_apply_reads_actual_style_hints_with_unknown_light_fallback(self) -> None:
        manager = self.manager()
        for scheme, expected in ((Qt.ColorScheme.Dark, "dark"),
                                 (Qt.ColorScheme.Light, "light"),
                                 (Qt.ColorScheme.Unknown, "light")):
            with patch.object(QStyleHints, "colorScheme", return_value=scheme):
                manager.apply(AppSettings(theme="system"))
            self.assertEqual(manager.effective_theme, expected)

    def test_system_signal_reapplies_latest_font_and_density_without_mutating_settings(self) -> None:
        manager = self.manager()
        settings = AppSettings(theme="system", font_size_px=18, density="compact")
        manager.apply(settings)
        changes = []
        manager.changed.connect(changes.append)
        # Caller mutation must not silently replace the last applied preferences.
        settings.font_size_px = 12
        for scheme, expected in ((Qt.ColorScheme.Dark, "dark"),
                                 (Qt.ColorScheme.Light, "light")):
            self.app.styleHints().colorSchemeChanged.emit(scheme)
            self.app.processEvents()
            self.assertEqual(manager.effective_theme, expected)
            self.assertEqual(self.app.styleSheet(),
                             styles.build_stylesheet(expected, 18, "compact"))
            self.assertEqual(self.app.font().pixelSize(), 18)
        self.assertEqual(settings.theme, "system")
        self.assertEqual(changes[-1], "light")

    def test_explicit_themes_ignore_os_signals_and_can_return_to_system(self) -> None:
        manager = self.manager()
        for theme in ("light", "dark", "tech"):
            manager.apply(AppSettings(theme=theme))
            changes = []
            manager.changed.connect(changes.append)
            before = self.app.styleSheet()
            for scheme in (Qt.ColorScheme.Dark, Qt.ColorScheme.Light):
                self.app.styleHints().colorSchemeChanged.emit(scheme)
                self.app.processEvents()
                self.assertEqual(manager.effective_theme, theme)
                self.assertEqual(self.app.styleSheet(), before)
            self.assertEqual(changes, [])
            manager.changed.disconnect(changes.append)
        manager.apply(AppSettings(theme="system"))
        self.app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        self.assertEqual(manager.effective_theme, "dark")

    def test_existing_widgets_restyle_and_preserve_content_and_selection(self) -> None:
        manager = self.manager()
        dialog = QDialog()
        self.addCleanup(dialog.deleteLater)
        layout = QVBoxLayout(dialog)
        edit = QLineEdit("keep this text")
        readonly = QPlainTextEdit("read-only text")
        readonly.setReadOnly(True)
        disabled = QPushButton("Unavailable — explain why nearby")
        disabled.setObjectName("primaryButton")
        disabled.setEnabled(False)
        combo = QComboBox()
        combo.addItems(["One", "Two"])
        combo.setCurrentIndex(1)
        tabs = QTabWidget()
        tabs.addTab(QLabel("Tab content"), "Details")
        table = QTableWidget(1, 1)
        tree = QTreeWidget()
        menu = QMenu(dialog)
        menu.addAction("Open")
        progress = QProgressBar()
        progress.setValue(42)
        for widget in (edit, readonly, disabled, combo, tabs, table, tree, progress):
            layout.addWidget(widget)
        edit.setSelection(0, 4)
        for theme in ("dark", "light", "tech"):
            manager.apply(AppSettings(theme=theme))
            for widget in (dialog, edit, readonly, disabled, combo, combo.view(),
                           tabs, table, tree, menu, progress):
                widget.ensurePolished()
            self.app.processEvents()
            p = self.values(theme)
            self.assertEqual(dialog.palette().color(QPalette.Window).name(), p["background"])
            self.assertEqual(edit.palette().color(QPalette.Base).name(), p["surface"])
            self.assertEqual(combo.view().palette().color(QPalette.Base).name(), p["surface"])
            self.assertEqual(disabled.palette().color(QPalette.Disabled,
                                                     QPalette.ButtonText).name(),
                             p["disabled_text"])
            self.assertEqual(edit.selectedText(), "keep")
            self.assertEqual(readonly.toPlainText(), "read-only text")
            self.assertEqual(combo.currentIndex(), 1)

    def test_font_sizes_and_density_change_real_control_geometry(self) -> None:
        manager = self.manager()
        controls = [QPushButton("Apply"), QToolButton(), QLineEdit("Text"),
                    QComboBox(), QSpinBox()]
        controls[1].setText("Tool")
        controls[3].addItem("Choose")
        for control in controls:
            self.addCleanup(control.deleteLater)
        sizes = {}
        for density in ("comfortable", "compact"):
            for font_size in (12, 14, 16, 18):
                manager.apply(AppSettings(theme="tech", font_size_px=font_size,
                                          density=density))
                for control in controls:
                    control.ensurePolished()
                self.app.processEvents()
                sizes[density, font_size] = [c.sizeHint().height() for c in controls]
                for control in controls:
                    self.assertEqual(control.font().pixelSize(), font_size)
                    self.assertGreaterEqual(control.sizeHint().height(),
                                            control.fontMetrics().height() + 4)
            for smaller, larger in zip((12, 14, 16), (14, 16, 18)):
                for before, after in zip(sizes[density, smaller], sizes[density, larger]):
                    self.assertGreater(after, before)
        for font_size in (12, 14, 16, 18):
            for compact, comfortable in zip(sizes["compact", font_size],
                                            sizes["comfortable", font_size]):
                self.assertGreater(comfortable, compact)

    def test_checkbox_indicator_actual_rendering_has_border_and_checked_mark(self) -> None:
        # Set the application style, not QWidget.setStyle(), which bypasses
        # application QSS and would incorrectly test an unthemed native checkbox.
        original_style_name = self.app.style().objectName() or "Fusion"
        self.app.setStyle("Fusion")
        self.addCleanup(self.app.setStyle, original_style_name)
        manager = self.manager()
        dialog = QDialog()
        self.addCleanup(dialog.deleteLater)
        dialog.resize(256, 64)
        checkbox = QCheckBox("Allow AI", dialog)
        checkbox.move(8, 8)
        checkbox.resize(240, 48)
        checkbox.setTristate(True)

        def indicator_image():
            dialog.ensurePolished()
            checkbox.ensurePolished()
            self.app.processEvents()
            option = QStyleOptionButton()
            checkbox.initStyleOption(option)
            rect = checkbox.style().subElementRect(
                QStyle.SE_CheckBoxIndicator, option, checkbox)
            rect.translate(checkbox.pos())
            # Composite onto the real parent, not transparent ARGB black.
            image = dialog.grab().toImage()
            ratio = image.devicePixelRatio()
            return image.copy(round(rect.x() * ratio), round(rect.y() * ratio),
                              round(rect.width() * ratio), round(rect.height() * ratio))

        for theme in ("light", "dark", "tech"):
            for font_size, density in ((12, "compact"), (14, "comfortable"),
                                       (16, "compact"), (18, "comfortable")):
                manager.apply(AppSettings(theme=theme, font_size_px=font_size,
                                          density=density))
                p = self.values(theme)
                for enabled in (True, False):
                    with self.subTest(theme=theme, font_size=font_size, enabled=enabled):
                        checkbox.setEnabled(enabled)
                        checkbox.setCheckState(Qt.Unchecked)
                        unchecked = indicator_image()
                        w, h = unchecked.width(), unchecked.height()
                        # Four physical edges must be visible against the parent.
                        # Sample inside the 2px stroke: its outermost pixel can
                        # be half-covered at fractional device scales (150%).
                        edge = round(unchecked.devicePixelRatio() / 2)
                        for x, y in ((w // 2, edge), (w // 2, h - 1 - edge),
                                     (edge, h // 2), (w - 1 - edge, h // 2)):
                            self.assertGreaterEqual(
                                contrast(unchecked.pixelColor(x, y).name(), p["background"]),
                                3.0, "unchecked indicator border is invisible")
                        checkbox.setCheckState(Qt.Checked)
                        checked = indicator_image()
                        # A real interior mark, not only a different border/fill:
                        # inset content contains both light and dark pixels.
                        inset = max(2, round(2 * checked.devicePixelRatio()))
                        colors = {checked.pixelColor(x, y).name()
                                  for x in range(inset, w - inset)
                                  for y in range(inset, h - inset)}
                        self.assertGreaterEqual(
                            max(contrast(a, b) for a in colors for b in colors),
                            3.0, "checked indicator has no contrasting interior mark")
                        self.assertNotEqual(unchecked, checked)
                        checkbox.setCheckState(Qt.PartiallyChecked)
                        partial = indicator_image()
                        self.assertNotEqual(partial, checked)
                        self.assertNotEqual(partial, unchecked)


class ThemeFixtureLifecycleTests(unittest.TestCase):
    def test_cleanup_releases_widgets_and_managers_before_font_teardown(self) -> None:
        """Do not leave deleteLater objects for the following UI test suite."""
        ThemeTests.setUpClass()
        self.addCleanup(ThemeTests.tearDownClass)
        app = ThemeTests.app
        from clickgit.ui.themes import ThemeManager

        previous_widgets = set(app.allWidgets())
        previous_managers = set(app.findChildren(ThemeManager))
        # Exercise the real fixture and a representative complex widget graph;
        # unittest.run invokes its registered cleanups but not class teardown.
        result = unittest.TestResult()
        ThemeTests("test_existing_widgets_restyle_and_preserve_content_and_selection").run(result)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
        remaining_widgets = set(app.allWidgets()) - previous_widgets
        remaining_managers = set(app.findChildren(ThemeManager)) - previous_managers
        self.assertEqual(
            (len(remaining_widgets), len(remaining_managers)), (0, 0),
            "Theme fixture must destroy its Qt objects before restoring styles/unloading fonts",
        )


if __name__ == "__main__":
    unittest.main()
