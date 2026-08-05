"""Manage keyboard shortcut defaults, overrides, and live application."""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtWidgets import QMenuBar, QWidget

from app.input.shortcut_manager import ShortcutManager
from app.services.user_settings_service import UserSettingsService
from app.utils.keyboard_shortcuts_catalog import (
    ShortcutEntry,
    collect_all_shortcuts,
    entries_with_shortcuts,
    find_menu_action,
    parse_shortcut,
)


class KeyboardShortcutsService:
    """Captures factory defaults and applies user overrides without restart."""

    _instance: Optional["KeyboardShortcutsService"] = None

    def __init__(self) -> None:
        self._window: Optional[QWidget] = None
        self._shortcut_manager: Optional[ShortcutManager] = None
        self._defaults: Dict[str, str] = {}
        self._bound = False

    @classmethod
    def get_instance(cls) -> "KeyboardShortcutsService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def bind(
        self,
        window: QWidget,
        shortcut_manager: ShortcutManager,
    ) -> None:
        """Capture defaults from the live UI and apply stored overrides."""
        self._window = window
        self._shortcut_manager = shortcut_manager
        self._defaults = self._snapshot_current_bindings()
        self._bound = True
        self.reapply()

    def is_bound(self) -> bool:
        return self._bound and self._window is not None

    def _menu_bar(self) -> Optional[QMenuBar]:
        if self._window is None or not hasattr(self._window, "menuBar"):
            return None
        try:
            return self._window.menuBar()
        except Exception:
            return None

    def _snapshot_current_bindings(self) -> Dict[str, str]:
        entries = collect_all_shortcuts(self._menu_bar(), include_unbound=True)
        nav_keys: Dict[str, str] = {}
        if self._shortcut_manager is not None:
            nav_keys = self._shortcut_manager.get_all_keys()
        result: Dict[str, str] = {}
        for entry in entries:
            if entry.is_navigation:
                result[entry.binding_id] = nav_keys.get(
                    entry.binding_id, entry.shortcut
                )
            else:
                result[entry.binding_id] = entry.shortcut
        return result

    def get_defaults(self) -> Dict[str, str]:
        return dict(self._defaults)

    def get_overrides(self) -> Dict[str, str]:
        raw = UserSettingsService.get_instance().get_keyboard_shortcuts()
        overrides = raw.get("overrides", {}) if isinstance(raw, dict) else {}
        if not isinstance(overrides, dict):
            return {}
        cleaned: Dict[str, str] = {}
        for key, value in overrides.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if value is None:
                cleaned[key] = ""
            else:
                cleaned[key] = str(value)
        return cleaned

    def effective_bindings(self) -> Dict[str, str]:
        """Defaults merged with overrides (override wins, including empty clear)."""
        # Ensure newly appeared catalog ids get a factory default snapshot.
        live = self._snapshot_current_bindings()
        for binding_id, shortcut in live.items():
            if binding_id not in self._defaults:
                overrides = self.get_overrides()
                # If an override already exists we cannot recover the original;
                # treat empty as factory default for restore semantics.
                self._defaults[binding_id] = (
                    "" if binding_id in overrides else shortcut
                )

        effective = dict(self._defaults)
        for binding_id, shortcut in self.get_overrides().items():
            if binding_id in effective:
                effective[binding_id] = shortcut
        return effective

    def list_entries(self) -> List[ShortcutEntry]:
        catalog = collect_all_shortcuts(self._menu_bar(), include_unbound=True)
        # Side effect: refresh defaults for new ids via effective_bindings().
        bindings = self.effective_bindings()
        return entries_with_shortcuts(catalog, bindings)

    def find_conflict(
        self,
        binding_id: str,
        shortcut: str,
    ) -> Optional[ShortcutEntry]:
        """Return another entry that already uses ``shortcut``, if any."""
        key = (shortcut or "").strip()
        if not key:
            return None
        for entry in self.list_entries():
            if entry.binding_id == binding_id:
                continue
            if (entry.shortcut or "").strip().lower() == key.lower():
                return entry
        return None

    def set_binding(
        self,
        binding_id: str,
        shortcut: str,
        *,
        steal_from: Optional[str] = None,
        persist: bool = True,
    ) -> None:
        """Set one binding (empty string clears). Optionally clear a conflict id."""
        overrides = self.get_overrides()
        if steal_from:
            overrides[steal_from] = ""
            self._apply_one(steal_from, "")

        default = self._defaults.get(binding_id, "")
        normalized = (shortcut or "").strip()
        if normalized == default:
            overrides.pop(binding_id, None)
            self._apply_one(binding_id, default)
        else:
            overrides[binding_id] = normalized
            self._apply_one(binding_id, normalized)

        if persist:
            self._save_overrides(overrides)

    def clear_all(self, *, persist: bool = True) -> None:
        """Remove every shortcut (all bindings empty)."""
        ids = set(self._defaults.keys()) | set(self.effective_bindings().keys())
        for entry in collect_all_shortcuts(self._menu_bar(), include_unbound=True):
            ids.add(entry.binding_id)
        overrides = {binding_id: "" for binding_id in ids}
        for binding_id in ids:
            self._apply_one(binding_id, "")
        if persist:
            self._save_overrides(overrides)

    def restore_defaults(self, *, persist: bool = True) -> None:
        """Drop all overrides and re-apply factory defaults."""
        if persist:
            self._save_overrides({})
        for binding_id, shortcut in self._defaults.items():
            self._apply_one(binding_id, shortcut)
        for entry in collect_all_shortcuts(self._menu_bar(), include_unbound=True):
            if entry.binding_id not in self._defaults:
                self._defaults[entry.binding_id] = entry.shortcut
                self._apply_one(entry.binding_id, entry.shortcut)

    def reapply(self) -> None:
        """Re-apply effective bindings to the live UI (after menu rebuilds)."""
        if not self.is_bound():
            return
        effective = self.effective_bindings()
        for binding_id, shortcut in effective.items():
            self._apply_one(binding_id, shortcut)

    def _save_overrides(self, overrides: Dict[str, str]) -> None:
        UserSettingsService.get_instance().update_keyboard_shortcuts(
            {"overrides": overrides}
        )

    def _apply_one(self, binding_id: str, shortcut: str) -> None:
        if binding_id.startswith("Navigation/") and self._shortcut_manager is not None:
            if self._shortcut_manager.has_binding(binding_id):
                self._shortcut_manager.set_key(binding_id, shortcut)
                return
        action = find_menu_action(self._menu_bar(), binding_id)
        if action is not None:
            action.setShortcut(parse_shortcut(shortcut))
