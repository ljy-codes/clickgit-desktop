from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clickgit.defaults import (
    MAX_CONFIG_BYTES,
    MAX_FAVORITE_PROJECTS,
    MAX_PATH_CHARACTERS,
    MAX_RECENT_PROJECTS,
    PROJECTS_SCHEMA_VERSION,
    SETTINGS_SCHEMA_VERSION,
    UI_DENSITIES,
    UI_FONT_SIZES_PX,
    UI_MODES,
    UI_THEMES,
)
from clickgit.models import AppSettings

__all__ = [
    "AppSettings", "SettingsStore", "SettingsValidationError", "ProjectsSaveError",
]


class SettingsValidationError(ValueError):
    """Safe, value-free field validation message suitable for UI display."""


class ProjectsSaveError(OSError):
    """Preferences were saved, but project records were not."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def _text(value: Any, limit: int, *, empty: bool = True) -> bool:
    return (
        type(value) is str
        and (empty or bool(value.strip()))
        and len(value) <= limit
        and not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value)
    )


def _paths(value: Any, limit: int) -> bool:
    return (
        type(value) is list
        and len(value) <= limit
        and all(_text(item, MAX_PATH_CHARACTERS, empty=False) for item in value)
    )


class _JsonDocument:
    """Bounded first-release JSON storage; errors never expose input values."""

    def __init__(self, path: Path, schema: int, label: str) -> None:
        self.path = path
        self.schema = schema
        self.label = label
        self.warnings: list[str] = []
        self.read_only = False
        self._loaded = False
        self._fingerprint: bytes | None = None

    def _read(self) -> bytes | None:
        try:
            with self.path.open("rb") as stream:
                payload = stream.read(MAX_CONFIG_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(payload) > MAX_CONFIG_BYTES:
            raise ValueError("configuration too large")
        return payload

    @staticmethod
    def _digest(payload: bytes | None) -> bytes | None:
        return hashlib.sha256(payload).digest() if payload is not None else None

    def load(self) -> dict[str, Any]:
        self.warnings.clear()
        self.read_only = False
        self._loaded = True
        self._fingerprint = None
        try:
            payload = self._read()
            if payload is None:
                self._report_load("missing")
                return {}
            self._fingerprint = self._digest(payload)
            data = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            if type(data) is not dict:
                raise ValueError("configuration root must be an object")
        except OSError:
            self.read_only = True
            self.warnings.append(
                f"{self.label}无法读取，本次使用默认值并进入只读模式；"
                "请检查本机数据目录权限后重新启动。"
            )
            self._report_load("read_failed")
            return {}
        except (ValueError, UnicodeError, RecursionError):
            self._quarantine()
            self._report_load("invalid_json")
            return {}
        if type(data.get("schema_version")) is not int or data["schema_version"] != self.schema:
            self.read_only = True
            self.warnings.append(
                f"{self.label}结构版本不受支持，本次使用默认值并进入只读模式；"
                "原文件未修改，请先备份，不会自动转换或覆盖。"
            )
            self._report_load("schema_mismatch", data)
            return {}
        self._report_load("ok", data)
        return data

    def _report_load(self, reason: str, data=None) -> None:
        # Describe the exact read above, never re-read through another process
        # or include config values, recent repository paths, or editor commands.
        from clickgit.diagnostics import record_event
        fields = {
            "config_path": str(self.path.absolute()),
            "reason": reason, "expected_schema": self.schema,
            "settings_read_only": self.read_only,
            "schema_type": "missing",
        }
        if data is not None and "schema_version" in data:
            value = data["schema_version"]
            fields["schema_type"] = "null" if value is None else type(value).__name__
            if type(value) is int:
                fields["schema_value"] = value
        record_event("config_loaded", **fields)

    def _quarantine(self) -> None:
        try:
            directory = self.path.parent / "diagnostics"
            directory.mkdir(parents=True, exist_ok=True)
            backup = directory / f"{self.path.name}.{uuid.uuid4().hex}.corrupt"
            self.path.rename(backup)
        except OSError:
            self.read_only = True
            self.warnings.append(
                f"{self.label}损坏且无法隔离，本次只读使用默认值；"
                "请检查本机数据目录权限，原文件不会被覆盖。"
            )
        else:
            self._fingerprint = None
            self.warnings.append(
                f"{self.label}损坏或超出大小限制，已原样隔离到本机数据目录的 diagnostics；"
                "本次使用默认值。隔离件可能含私人信息，请勿直接分享。"
            )

    @staticmethod
    def encode(data: dict[str, Any]) -> bytes:
        payload = (json.dumps(
            data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False,
        ) + "\n").encode("utf-8")
        if len(payload) > MAX_CONFIG_BYTES:
            raise SettingsValidationError(
                f"配置内容超过单文件 {MAX_CONFIG_BYTES // 1024} KiB 上限，请减少项目记录。"
            )
        return payload

    def write(self, data: dict[str, Any]) -> None:
        payload = self.encode(data)
        if not self._loaded:
            self.load()
        self._check_unchanged()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp",
        )
        temp_path = Path(name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Detect already-observed external edits, not a cross-process lock.
            self._check_unchanged()
            temp_path.replace(self.path)
            self._fingerprint = self._digest(payload)
        finally:
            temp_path.unlink(missing_ok=True)

    def _check_unchanged(self) -> None:
        if self.read_only:
            raise PermissionError(f"{self.label}处于只读保护状态")
        try:
            changed = self._digest(self._read()) != self._fingerprint
        except (OSError, ValueError):
            changed = True
        if changed:
            self.read_only = True
            self.warnings.append(
                f"{self.label}已被其他操作修改或当前无法读取，已暂停保存并进入只读模式；"
                "请保留本次设置，检查文件后重新启动。"
            )
            raise PermissionError(f"{self.label}已变化，拒绝覆盖")


class SettingsStore:
    """Application preferences and project records are independent documents."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._settings = _JsonDocument(self.path, SETTINGS_SCHEMA_VERSION, "设置文件")
        self._projects = _JsonDocument(
            self.path.with_name("projects.json"), PROJECTS_SCHEMA_VERSION, "项目列表",
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._settings.warnings + self._projects.warnings)

    @property
    def read_only(self) -> bool:
        return self._settings.read_only or self._projects.read_only

    @staticmethod
    def _preferences(
        data: dict[str, Any], *, strict: bool = False,
        warnings: list[str] | None = None,
    ) -> AppSettings:
        settings = AppSettings()
        errors: list[str] = []

        def section(name: str) -> dict[str, Any]:
            value = data.get(name, {})
            if type(value) is not dict:
                errors.append(name)
                return {}
            return value

        def field(
            source: dict[str, Any], key: str, attribute: str,
            valid: Callable[[Any], bool], label: str,
        ) -> None:
            if key not in source:
                return
            if valid(source[key]):
                setattr(settings, attribute, source[key])
            else:
                errors.append(label)

        ui = section("ui")
        for key, values in (
            ("mode", UI_MODES), ("theme", UI_THEMES),
            ("font_size_px", UI_FONT_SIZES_PX), ("density", UI_DENSITIES),
        ):
            expected_type = type(values[0])
            field(
                ui, key, key,
                lambda value: type(value) is expected_type and value in values,
                f"ui.{key}",
            )
        field(data, "external_editor", "external_editor",
              lambda value: _text(value, MAX_PATH_CHARACTERS),
              f"外部编辑器（须为字符串，不超过 {MAX_PATH_CHARACTERS} 字符，且不含控制或非法字符）")
        field(data, "onboarding_completed", "onboarding_completed",
              lambda value: type(value) is bool, "onboarding_completed")
        if errors:
            if strict:
                raise SettingsValidationError("设置字段不合法：" + "、".join(errors))
            if warnings is not None:
                warnings.append(
                    "以下设置字段无效，已使用默认值：" + "、".join(errors) + "。可在设置中重新保存。"
                )
        return settings

    @staticmethod
    def _project_values(
        data: dict[str, Any], *, strict: bool = False,
        warnings: list[str] | None = None,
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for key, limit in (
            ("recent_repositories", MAX_RECENT_PROJECTS),
            ("favorite_repositories", MAX_FAVORITE_PROJECTS),
        ):
            value = data.get(key, [])
            if not _paths(value, limit):
                if strict:
                    raise SettingsValidationError(f"项目列表字段 {key} 不合法（最多 {limit} 项有效路径）。")
                if warnings is not None:
                    warnings.append(
                        f"项目列表字段 {key} 无效，本次使用空列表；"
                        "项目记录进入只读保护，请先备份并修正原文件。不会删除项目文件。"
                    )
                value = []
            result[key] = list(value)
        return result

    def load(self) -> AppSettings:
        settings = self._preferences(
            self._settings.load(), warnings=self._settings.warnings,
        )
        project_errors: list[str] = []
        projects = self._project_values(self._projects.load(), warnings=project_errors)
        if project_errors:
            # Opening a repository must not overwrite malformed records with defaults.
            self._projects.read_only = True
            self._projects.warnings.extend(project_errors)
        for key, value in projects.items():
            setattr(settings, key, value)
        return settings

    @staticmethod
    def _settings_data(settings: AppSettings) -> dict[str, Any]:
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "ui": {
                "mode": settings.mode, "theme": settings.theme,
                "font_size_px": settings.font_size_px, "density": settings.density,
            },
            "external_editor": settings.external_editor,
            "onboarding_completed": settings.onboarding_completed,
        }

    def save(self, settings: AppSettings) -> None:
        self.validate(settings)
        self._ensure_loaded()
        data = self._settings_data(settings)
        projects = self._project_data(settings)
        self._settings.write(data)
        self._settings.warnings.clear()
        # These are independent writes, not a cross-file transaction.
        try:
            self._projects.write(projects)
        except OSError as error:
            raise ProjectsSaveError("设置已保存，但项目记录未保存") from error
        self._projects.warnings.clear()

    @classmethod
    def validate(cls, settings: AppSettings) -> None:
        """Validate both documents without accessing the filesystem."""
        data = cls._settings_data(settings)
        cls._preferences(data, strict=True)
        _JsonDocument.encode(data)
        _JsonDocument.encode(cls._project_data(settings))

    @classmethod
    def _project_data(cls, settings: AppSettings) -> dict[str, Any]:
        return {
            "schema_version": PROJECTS_SCHEMA_VERSION,
            **cls._project_values({
                "recent_repositories": settings.recent_repositories,
                "favorite_repositories": settings.favorite_repositories,
            }, strict=True),
        }

    def save_projects(self, settings: AppSettings) -> None:
        self._ensure_loaded()
        self._projects.write(self._project_data(settings))
        self._projects.warnings.clear()

    def _ensure_loaded(self) -> None:
        if not self._settings._loaded or not self._projects._loaded:
            self.load()
