"""Application-wide theme application and operating-system theme following."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from clickgit.models import AppSettings
from clickgit.ui.styles import build_stylesheet, theme_values

__all__ = ["ThemeManager", "theme_values"]


class ThemeManager(QObject):
    """Own one per QApplication, call apply on the GUI thread.

    Construction only subscribes to style hints; it does not change the current
    application appearance. ``changed`` fires after each successful application,
    including font/density changes, so consumers can refresh semantic item colors.
    No settings are persisted or mutated here.
    """

    changed = Signal(str)

    def __init__(self, application: QApplication) -> None:
        super().__init__(application)
        self._application = application
        self._hints = application.styleHints()
        self._preference: str | None = None
        self._font_size_px = 14
        self._density = "comfortable"
        self._effective_theme = self._system_theme(self._hints.colorScheme())
        self._hints.colorSchemeChanged.connect(self._on_color_scheme_changed)

    @property
    def effective_theme(self) -> str:
        return self._effective_theme

    @staticmethod
    def _system_theme(scheme: Qt.ColorScheme) -> str:
        # Platforms without a known scheme use a deterministic light fallback.
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"

    def apply(self, settings: AppSettings) -> None:
        """Apply a validated snapshot; invalid values leave the current UI intact."""
        theme = (self._system_theme(self._hints.colorScheme())
                 if settings.theme == "system" else settings.theme)
        qss = build_stylesheet(theme, settings.font_size_px, settings.density)
        self._preference = settings.theme
        self._font_size_px = settings.font_size_px
        self._density = settings.density
        self._apply_theme(theme, qss)

    def _on_color_scheme_changed(self, scheme: Qt.ColorScheme) -> None:
        if self._preference != "system":
            return
        theme = self._system_theme(scheme)
        self._apply_theme(theme, build_stylesheet(theme, self._font_size_px, self._density))

    def _apply_theme(self, theme: str, qss: str) -> None:
        p = theme_values(theme)
        palette = QPalette()
        roles = {
            QPalette.Window: "background", QPalette.WindowText: "text",
            QPalette.Base: "surface", QPalette.AlternateBase: "surface_alt",
            QPalette.Text: "text", QPalette.Button: "surface",
            QPalette.ButtonText: "text", QPalette.BrightText: "primary_text",
            QPalette.Highlight: "selection", QPalette.HighlightedText: "selection_text",
            QPalette.ToolTipBase: "surface", QPalette.ToolTipText: "text",
            QPalette.PlaceholderText: "muted", QPalette.Link: "primary",
            QPalette.LinkVisited: "muted", QPalette.Accent: "primary",
            QPalette.Light: "surface_alt", QPalette.Midlight: "hover",
            QPalette.Mid: "border", QPalette.Dark: "border", QPalette.Shadow: "shadow",
        }
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            for role, key in roles.items():
                palette.setColor(group, role, QColor(p[key]))
        for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText,
                     QPalette.PlaceholderText, QPalette.Link, QPalette.LinkVisited):
            palette.setColor(QPalette.Disabled, role, QColor(p["disabled_text"]))
        for role in (QPalette.Base, QPalette.Button, QPalette.AlternateBase):
            palette.setColor(QPalette.Disabled, role, QColor(p["disabled_background"]))
        font = QFont(self._application.font())
        font.setFamilies(["Microsoft YaHei UI", "PingFang SC", "Segoe UI"])
        font.setPixelSize(self._font_size_px)
        self._application.setPalette(palette)
        self._application.setFont(font)
        self._application.setStyleSheet(qss)
        self._effective_theme = theme
        self.changed.emit(theme)
