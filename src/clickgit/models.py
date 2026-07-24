from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AppSettings:
    recent_repositories: list[str] = field(default_factory=list)
    favorite_repositories: list[str] = field(default_factory=list)
    theme: str = "system"
    external_editor: str = ""

