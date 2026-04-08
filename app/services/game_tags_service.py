"""Service for managing per-game tag definitions (built-in + custom).

- Built-in tags (names + colors) are defined in ``app/config/config.json``.
- Custom tags are stored in user settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from app.services.user_settings_service import UserSettingsService


@dataclass(frozen=True)
class GameTagDefinition:
    name: str
    color: Tuple[int, int, int]
    builtin: bool = False


class GameTagsService:
    """Read tag definitions from config + user settings."""

    SETTINGS_KEY = "game_tags"

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._settings_service = UserSettingsService.get_instance()

    def get_definitions(self) -> List[GameTagDefinition]:
        settings = self._settings_service.get_settings()
        section = settings.get(self.SETTINGS_KEY, {}) if isinstance(settings, dict) else {}
        custom = section.get("custom", []) if isinstance(section, dict) else []

        # Built-in tags come from config.json
        builtins: List[GameTagDefinition] = []
        builtin_cfg = (self._config.get("game_tags") or {}).get("builtin", [])
        if isinstance(builtin_cfg, list):
            for item in builtin_cfg:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                col = item.get("color")
                if isinstance(col, list) and len(col) == 3:
                    try:
                        color = (int(col[0]), int(col[1]), int(col[2]))
                    except Exception:
                        color = (120, 120, 120)
                else:
                    color = (120, 120, 120)
                builtins.append(GameTagDefinition(name, color, builtin=True))

        customs: List[GameTagDefinition] = []
        if isinstance(custom, list):
            for item in custom:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                if ";" in name:
                    # v1: semicolon is reserved delimiter
                    name = name.replace(";", "").strip()
                    if not name:
                        continue
                col = item.get("color")
                if isinstance(col, list) and len(col) == 3:
                    try:
                        color = (int(col[0]), int(col[1]), int(col[2]))
                    except Exception:
                        color = (120, 120, 120)
                else:
                    color = (120, 120, 120)
                customs.append(GameTagDefinition(name, color, builtin=False))

        # De-duplicate case-insensitively; built-ins win over customs on name collision
        seen = set()
        result: List[GameTagDefinition] = []
        for d in builtins + customs:
            key = d.name.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(d)
        return result

    def get_definition_map(self) -> Dict[str, GameTagDefinition]:
        """Return a casefold-keyed map for quick lookup."""
        defs = self.get_definitions()
        return {d.name.casefold(): d for d in defs}

    def upsert_custom_definition(self, name: str, color: Tuple[int, int, int]) -> None:
        name = str(name or "").strip()
        if not name:
            return
        if ";" in name:
            name = name.replace(";", "").strip()
            if not name:
                return

        settings = self._settings_service.get_model().get_settings()
        section = settings.get(self.SETTINGS_KEY, {})
        if not isinstance(section, dict):
            section = {}
        custom = section.get("custom", [])
        if not isinstance(custom, list):
            custom = []

        key = name.casefold()
        new_custom: List[dict] = []
        replaced = False
        for item in custom:
            if not isinstance(item, dict):
                continue
            existing = str(item.get("name", "")).strip()
            if existing.casefold() == key:
                new_custom.append({"name": name, "color": [int(color[0]), int(color[1]), int(color[2])]})
                replaced = True
            else:
                new_custom.append(item)
        if not replaced:
            new_custom.append({"name": name, "color": [int(color[0]), int(color[1]), int(color[2])]})

        section["custom"] = new_custom
        updated = settings.copy()
        updated[self.SETTINGS_KEY] = section
        self._settings_service.get_model().update_from_dict(updated)

    def remove_custom_definition(self, name: str) -> None:
        key = str(name or "").strip().casefold()
        if not key:
            return
        settings = self._settings_service.get_model().get_settings()
        section = settings.get(self.SETTINGS_KEY, {})
        if not isinstance(section, dict):
            return
        custom = section.get("custom", [])
        if not isinstance(custom, list):
            return
        new_custom = [c for c in custom if isinstance(c, dict) and str(c.get("name", "")).strip().casefold() != key]
        section["custom"] = new_custom
        updated = settings.copy()
        updated[self.SETTINGS_KEY] = section
        self._settings_service.get_model().update_from_dict(updated)

