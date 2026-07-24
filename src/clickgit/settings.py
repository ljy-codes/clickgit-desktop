from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from clickgit.models import AppSettings

__all__ = ["AppSettings", "SettingsStore"]


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return AppSettings(
                recent_repositories=list(data.get("recent_repositories", [])),
                favorite_repositories=list(data.get("favorite_repositories", [])),
                theme=str(data.get("theme", "system")),
                external_editor=str(data.get("external_editor", "")),
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self._preserve_corrupt_file()
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            asdict(settings),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle, temp_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temp_path.replace(self.path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _preserve_corrupt_file(self) -> None:
        backup = self.path.with_suffix(f"{self.path.suffix}.corrupt")
        sequence = 1
        while backup.exists():
            backup = self.path.with_suffix(
                f"{self.path.suffix}.corrupt.{sequence}"
            )
            sequence += 1
        try:
            self.path.replace(backup)
        except OSError:
            pass
