"""First-release preferences and bounded configuration resources.

These limits are application contracts, not user-overridable safety switches.
Other subsystem budgets are added when those subsystems are implemented.
"""

from typing import Final

SETTINGS_SCHEMA_VERSION: Final[int] = 1
PROJECTS_SCHEMA_VERSION: Final[int] = 1
MAX_CONFIG_BYTES: Final[int] = 1024 * 1024  # Per JSON document, bytes.
MAX_PATH_CHARACTERS: Final[int] = 4096
MAX_RECENT_PROJECTS: Final[int] = 12
MAX_FAVORITE_PROJECTS: Final[int] = 256

DEFAULT_MODE: Final[str] = "simple"
DEFAULT_THEME: Final[str] = "system"
DEFAULT_FONT_SIZE_PX: Final[int] = 14
DEFAULT_DENSITY: Final[str] = "comfortable"
UI_MODES: Final[tuple[str, ...]] = ("simple", "professional")
UI_THEMES: Final[tuple[str, ...]] = ("system", "light", "dark", "tech")
UI_FONT_SIZES_PX: Final[tuple[int, ...]] = (12, 14, 16, 18)
UI_DENSITIES: Final[tuple[str, ...]] = ("comfortable", "compact")
