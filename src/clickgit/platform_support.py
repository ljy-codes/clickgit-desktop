from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Mapping
from pathlib import Path


def application_data_dir(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    current_platform = platform_name or sys.platform
    current_environment = environ if environ is not None else os.environ
    current_home = Path(home) if home is not None else Path.home()
    if current_platform == "win32":
        appdata = current_environment.get("APPDATA")
        if appdata:
            return Path(appdata) / "ClickGit"
    if current_platform == "darwin":
        return current_home / "Library" / "Application Support" / "ClickGit"
    return current_home / ".clickgit"


def preferred_ui_font(platform_name: str | None = None) -> str:
    current_platform = platform_name or sys.platform
    if current_platform == "darwin":
        return "PingFang SC"
    if current_platform == "win32":
        return "Microsoft YaHei UI"
    return "Noto Sans CJK SC"


def application_executable_dir() -> Path:
    if sys.platform == "win32":
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetModuleFileNameW(
            None,
            buffer,
            len(buffer),
        )
        if length:
            return Path(buffer.value).resolve().parent
    return Path(sys.executable).resolve().parent

