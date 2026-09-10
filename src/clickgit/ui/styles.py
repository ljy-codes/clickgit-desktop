"""Shared semantic colors and Qt styles; no QApplication or platform side effects."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from clickgit.defaults import UI_DENSITIES, UI_FONT_SIZES_PX


# Diff values are backgrounds; consumers retain +/- markers and status labels.
THEME_PALETTES: Mapping[str, Mapping[str, str]] = MappingProxyType({
    "light": MappingProxyType({
        "background": "#f4f6f8", "surface": "#ffffff", "surface_alt": "#edf1f5",
        "text": "#17212b", "text_muted": "#546270", "muted": "#546270",
        "border": "#aebbc8", "primary": "#176b99", "primary_text": "#ffffff",
        "primary_hover": "#125a82", "focus": "#176b99",
        "success": "#176b35", "danger": "#a32424", "warning": "#805015",
        "diff_add": "#e3f2e7", "diff_remove": "#fbe6e6",
        "selection": "#d9eafa", "selection_text": "#17212b",
        "disabled_background": "#e8ecf0", "disabled_text": "#59636e",
        "hover": "#e5edf5", "scroll_handle": "#76899b", "shadow": "#8b98a5",
    }),
    "dark": MappingProxyType({
        "background": "#1b2028", "surface": "#242a33", "surface_alt": "#2c3440",
        "text": "#edf1f7", "text_muted": "#afbccb", "muted": "#afbccb",
        "border": "#4c596b", "primary": "#8ebcf2", "primary_text": "#101820",
        "primary_hover": "#b0d3fa", "focus": "#8ebcf2",
        "success": "#a0deb1", "danger": "#ffb1b1", "warning": "#f5ce88",
        "diff_add": "#243e33", "diff_remove": "#482e38",
        "selection": "#36506b", "selection_text": "#edf1f7",
        "disabled_background": "#303946", "disabled_text": "#b3bfcd",
        "hover": "#354354", "scroll_handle": "#708299", "shadow": "#10151b",
    }),
    "tech": MappingProxyType({
        "background": "#0b1926", "surface": "#122635", "surface_alt": "#1a3345",
        "text": "#e6f4ff", "text_muted": "#a7bfd2", "muted": "#a7bfd2",
        "border": "#3c5f73", "primary": "#59cee8", "primary_text": "#082330",
        "primary_hover": "#85ddef", "focus": "#59cee8",
        "success": "#89dfbd", "danger": "#ffb3bb", "warning": "#f4cd89",
        "diff_add": "#183e39", "diff_remove": "#442f40",
        "selection": "#245069", "selection_text": "#e6f4ff",
        "disabled_background": "#203748", "disabled_text": "#a8bccd",
        "hover": "#25465a", "scroll_handle": "#638da5", "shadow": "#060f19",
    }),
})


def theme_values(theme: str) -> Mapping[str, str]:
    """Return immutable semantic hex colors for an effective (not system) theme."""
    if theme not in THEME_PALETTES:
        raise ValueError(f"Unsupported effective theme: {theme!r}")
    return THEME_PALETTES[theme]


def build_stylesheet(
    theme: str, font_size_px: int = 14, density: str = "comfortable",
) -> str:
    """Generate application QSS, including popups and accessible state cues."""
    p = theme_values(theme)
    if type(font_size_px) is not int or font_size_px not in UI_FONT_SIZES_PX:
        raise ValueError(f"Unsupported font size: {font_size_px!r}")
    if density not in UI_DENSITIES:
        raise ValueError(f"Unsupported density: {density!r}")
    compact = density == "compact"
    pad = 2 if compact else 5
    horizontal = 8 if compact else 12
    content_height = font_size_px + 6
    row_height = font_size_px + (8 if compact else 16)
    scroll_width = 12 if compact else 16
    indicator_content = max(8, font_size_px - 4)
    return f"""
QWidget {{
    background-color: {p["background"]};
    color: {p["text"]};
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI";
    font-size: {font_size_px}px;
    selection-background-color: {p["selection"]};
    selection-color: {p["selection_text"]};
}}
QMainWindow, QDialog, QMessageBox, QFileDialog {{
    background-color: {p["background"]};
    color: {p["text"]};
}}
QLabel, QCheckBox, QRadioButton, QGroupBox {{
    background-color: transparent;
}}
QToolBar {{
    background-color: {p["surface"]};
    border: 0;
    border-bottom: 1px solid {p["border"]};
    spacing: 4px;
    padding: {pad}px {horizontal}px;
}}
QPushButton, QToolButton {{
    background-color: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 4px;
    min-height: {content_height}px;
    padding: {pad}px {horizontal}px;
}}
QPushButton:hover, QToolButton:hover {{
    background-color: {p["hover"]};
    border-color: {p["focus"]};
}}
QPushButton:pressed, QToolButton:pressed, QToolButton:checked {{
    background-color: {p["selection"]};
    color: {p["selection_text"]};
    border-color: {p["focus"]};
}}
QPushButton:default {{
    border: 2px solid {p["focus"]};
    font-weight: 600;
}}
QPushButton#primaryButton, QPushButton#commitButton {{
    background-color: {p["primary"]};
    color: {p["primary_text"]};
    border-color: {p["primary"]};
    font-weight: 600;
}}
QPushButton#primaryButton:hover, QPushButton#commitButton:hover,
QPushButton#primaryButton:pressed, QPushButton#commitButton:pressed {{
    background-color: {p["primary_hover"]};
}}
QPushButton#dangerButton {{
    color: {p["danger"]};
    border-color: {p["danger"]};
    font-weight: 600;
}}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QAbstractSpinBox,
QAbstractItemView {{
    background-color: {p["surface"]};
    alternate-background-color: {p["surface_alt"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 4px;
    selection-background-color: {p["selection"]};
    selection-color: {p["selection_text"]};
}}
QLineEdit, QComboBox, QAbstractSpinBox {{
    min-height: {content_height}px;
    padding: {pad}px {horizontal}px;
}}
QPlainTextEdit, QTextEdit {{
    padding: {pad + 2}px;
}}
QLineEdit:read-only, QPlainTextEdit[readOnly="true"], QTextEdit[readOnly="true"] {{
    background-color: {p["surface_alt"]};
    border-style: dashed;
}}
QComboBox {{
    padding-right: {horizontal + 18}px;
}}
QComboBox QAbstractItemView {{
    background-color: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    selection-background-color: {p["selection"]};
    selection-color: {p["selection_text"]};
    outline: 1px dashed {p["focus"]};
}}
QComboBox QAbstractItemView::item {{
    min-height: {row_height}px;
    padding: {pad}px;
}}
QTreeView, QTableView, QListView {{
    show-decoration-selected: 1;
    outline: 1px dashed {p["focus"]};
}}
QTableView {{
    gridline-color: {p["border"]};
}}
QTreeView::item, QTableView::item, QListView::item {{
    min-height: {row_height}px;
    padding: {pad}px 6px;
}}
QTreeView::item:hover, QTableView::item:hover, QListView::item:hover {{
    background-color: {p["hover"]};
}}
QTreeView::item:selected, QTableView::item:selected, QListView::item:selected,
QComboBox QAbstractItemView::item:selected {{
    background-color: {p["selection"]};
    color: {p["selection_text"]};
}}
QHeaderView {{
    background-color: {p["surface_alt"]};
    color: {p["text"]};
    border: 0;
    padding: 0;
}}
QHeaderView::section, QTableCornerButton::section {{
    background-color: {p["surface_alt"]};
    color: {p["text"]};
    border: 0;
    border-right: 1px solid {p["border"]};
    border-bottom: 1px solid {p["border"]};
    padding: {pad + 2}px;
    font-weight: 600;
}}
#repositoryBar {{
    background-color: {p["surface"]};
    border-bottom: 1px solid {p["border"]};
}}
#repositoryName {{
    font-size: {font_size_px + 2}px;
    font-weight: 600;
}}
#branchBadge {{
    background-color: {p["diff_add"]};
    color: {p["success"]};
    border: 1px solid {p["success"]};
    border-radius: 4px;
    padding: {pad}px 7px;
    font-weight: 600;
}}
QListWidget#navigation {{
    background-color: {p["surface_alt"]};
    color: {p["text"]};
    border: 0;
    padding-top: {pad + 3}px;
}}
QListWidget#navigation::item {{
    min-height: {row_height + 4}px;
    padding: {pad}px {horizontal}px;
    border-left: 3px solid transparent;
}}
QListWidget#navigation::item:hover {{
    background-color: {p["hover"]};
}}
QListWidget#navigation::item:selected {{
    background-color: {p["selection"]};
    color: {p["selection_text"]};
    border-left: 3px solid {p["focus"]};
    font-weight: 600;
}}
QListWidget#recentRepositories {{
    background-color: {p["surface"]};
}}
QLabel#pageTitle {{
    font-size: {font_size_px + 4}px;
    font-weight: 600;
}}
QLabel#mutedLabel {{
    color: {p["muted"]};
}}
QLabel#dangerLabel {{
    color: {p["danger"]};
    font-weight: 600;
}}
QLabel#warningLabel {{
    color: {p["warning"]};
    font-weight: 600;
}}
QLabel#settingsNotice {{
    color: {p["warning"]};
    background-color: {p["surface"]};
    border: 1px solid {p["warning"]};
    padding: {pad + 2}px;
}}
QFrame#sectionLine {{
    color: {p["border"]};
    background-color: {p["border"]};
}}
QMenuBar, QMenu, QStatusBar {{
    background-color: {p["surface"]};
    color: {p["text"]};
}}
QMenu {{
    border: 1px solid {p["border"]};
    padding: 4px;
}}
QMenuBar::item, QMenu::item {{
    padding: {pad + 2}px {horizontal + 8}px;
    background-color: transparent;
}}
QMenuBar::item:selected, QMenuBar::item:pressed, QMenu::item:selected {{
    background-color: {p["selection"]};
    color: {p["selection_text"]};
}}
QMenu::separator {{
    height: 1px;
    background-color: {p["border"]};
    margin: 4px 8px;
}}
QToolTip {{
    background-color: {p["surface"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    padding: {pad + 3}px;
}}
QTabWidget::pane {{
    background-color: {p["surface"]};
    border: 1px solid {p["border"]};
}}
QTabBar::tab {{
    background-color: {p["surface_alt"]};
    color: {p["muted"]};
    border: 1px solid {p["border"]};
    min-height: {content_height}px;
    padding: {pad}px {horizontal}px;
}}
QTabBar::tab:hover {{
    background-color: {p["hover"]};
    color: {p["text"]};
}}
QTabBar::tab:selected {{
    background-color: {p["surface"]};
    color: {p["text"]};
    border-bottom: 3px solid {p["focus"]};
    font-weight: 600;
}}
QScrollBar:vertical {{
    background-color: {p["surface_alt"]};
    width: {scroll_width}px;
    margin: 0;
}}
QScrollBar:horizontal {{
    background-color: {p["surface_alt"]};
    height: {scroll_width}px;
    margin: 0;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background-color: {p["scroll_handle"]};
    border: 2px solid {p["surface_alt"]};
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::handle:hover {{
    background-color: {p["focus"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
    border: 0;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QProgressBar {{
    background-color: {p["surface_alt"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 4px;
    min-height: {content_height}px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {p["selection"]};
    border-radius: 3px;
}}
QGroupBox {{
    border: 1px solid {p["border"]};
    border-radius: 4px;
    margin-top: {font_size_px}px;
    padding-top: {pad + 4}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QCheckBox, QRadioButton {{
    min-height: {content_height}px;
    spacing: 6px;
}}
/* Explicit indicators avoid transparent QWidget backgrounds suppressing the
   native checkbox frame. An inset square means checked; a bar means partial.
   These geometry cues need no font glyph, image, resource file or Qt plugin. */
QCheckBox::indicator {{
    width: {indicator_content}px;
    height: {indicator_content}px;
    padding: 3px;
    border: 2px solid {p["muted"]};
    border-radius: 2px;
    background-color: {p["surface"]};
}}
QCheckBox::indicator:hover {{
    border-color: {p["focus"]};
}}
QCheckBox::indicator:checked {{
    background-color: {p["text"]};
    background-clip: content;
}}
QCheckBox::indicator:indeterminate {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 transparent, stop:0.34 transparent, stop:0.35 {p["text"]},
        stop:0.65 {p["text"]}, stop:0.66 transparent, stop:1 transparent);
    background-clip: content;
}}
QCheckBox::indicator:disabled {{
    border-color: {p["disabled_text"]};
    background-color: {p["disabled_background"]};
}}
QCheckBox::indicator:checked:disabled {{
    background-color: {p["disabled_text"]};
}}
QCheckBox::indicator:indeterminate:disabled {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 transparent, stop:0.34 transparent, stop:0.35 {p["disabled_text"]},
        stop:0.65 {p["disabled_text"]}, stop:0.66 transparent, stop:1 transparent);
}}
QSplitter::handle {{
    background-color: {p["border"]};
}}
QStatusBar {{
    border-top: 1px solid {p["border"]};
}}
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QPlainTextEdit:focus,
QTextEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QAbstractItemView:focus,
QCheckBox:focus, QRadioButton:focus, QTabBar::tab:focus,
QPushButton#dangerButton:focus, QListWidget#navigation:focus {{
    border: 2px dashed {p["focus"]};
}}
QPushButton#primaryButton:focus, QPushButton#commitButton:focus {{
    border: 2px dashed {p["primary_text"]};
}}
/* Keep disabled controls readable and visibly non-actionable, including IDs. */
QWidget:disabled, QMenu::item:disabled, QMenuBar::item:disabled,
QTabBar::tab:disabled, QHeaderView::section:disabled,
QLabel#mutedLabel:disabled, QLabel#branchBadge:disabled {{
    color: {p["disabled_text"]};
}}
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled, QComboBox:disabled,
QAbstractSpinBox:disabled, QAbstractItemView:disabled,
QPushButton#primaryButton:disabled, QPushButton#commitButton:disabled,
QPushButton#dangerButton:disabled, QListWidget#navigation:disabled,
QListWidget#recentRepositories:disabled {{
    background-color: {p["disabled_background"]};
    color: {p["disabled_text"]};
    border: 1px dashed {p["border"]};
}}
"""


# Compatibility for startup/importers that have not yet adopted ThemeManager.
APP_STYLE = build_stylesheet("light")
