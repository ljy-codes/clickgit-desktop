"""Shared application identity; call apply_branding(app) before creating windows.

Resources are relative to this package, never to the process working directory.
The Windows spec mirrors this layout inside PyInstaller's ``_internal`` folder.
No theme, installation, registry, or global icon-cache changes are performed.
"""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


APP_USER_MODEL_ID = "ljy-codes.ClickGit"
_LOGGER = logging.getLogger(__name__)


def resource_path(name: str) -> Path:
    """Return an absolute package asset path for a single file name."""
    if not name or name in {".", ".."} or any(c in name for c in "/\\:"):
        raise ValueError("Brand resources must use a single file name")
    return Path(__file__).resolve().parent / "resources" / name


def application_icon() -> QIcon:
    """Load the same multi-size artwork embedded in the Windows executable."""
    return QIcon(str(resource_path("clickgit.ico")))


def set_windows_app_user_model_id() -> bool:
    """Set stable taskbar grouping, without making a shell failure fatal."""
    if sys.platform != "win32":
        return False
    try:
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        result = setter(APP_USER_MODEL_ID)
        if result < 0:
            _LOGGER.warning("Windows application identity failed: HRESULT %#x", result & 0xFFFFFFFF)
            return False
        return True
    except (AttributeError, OSError):
        _LOGGER.warning("Windows application identity is unavailable", exc_info=True)
        return False


def apply_branding(app: QApplication) -> None:
    """Apply process identity and default window icon, without altering UI themes.

    The entry point should call this immediately after obtaining QApplication,
    both in normal startup and GUI smoke diagnostics, before any window is made.
    """
    set_windows_app_user_model_id()
    app.setWindowIcon(application_icon())
