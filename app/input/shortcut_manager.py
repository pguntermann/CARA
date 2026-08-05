"""Global keyboard shortcut manager for routing key commands."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget

from app.utils.keyboard_shortcuts_catalog import format_shortcut, parse_shortcut


class ShortcutManager:
    """Manages global keyboard shortcuts and routes them to handlers.

    Shortcuts are registered by stable binding id so keys can be rebound
    at runtime without recreating handlers.
    """

    def __init__(self, parent: QWidget) -> None:
        self.parent = parent
        self._handlers: Dict[str, Callable[[], None]] = {}
        self._keys: Dict[str, str] = {}
        self._shortcuts: Dict[str, QShortcut] = {}

    def register_shortcut(
        self,
        binding_id: str,
        key: str,
        handler: Callable[[], None],
    ) -> None:
        """Register (or replace) a global shortcut by binding id."""
        self._handlers[binding_id] = handler
        self.set_key(binding_id, key)

    def has_binding(self, binding_id: str) -> bool:
        return binding_id in self._handlers

    def get_key(self, binding_id: str) -> str:
        return self._keys.get(binding_id, "")

    def get_all_keys(self) -> Dict[str, str]:
        return dict(self._keys)

    def set_key(self, binding_id: str, key: str) -> None:
        """Update the key for an existing binding. Empty key disables it."""
        if binding_id not in self._handlers:
            return
        self._destroy_qt_shortcut(binding_id)
        normalized = format_shortcut(parse_shortcut(key)) if (key or "").strip() else ""
        self._keys[binding_id] = normalized
        if not normalized:
            return
        shortcut = QShortcut(parse_shortcut(normalized), self.parent)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._handlers[binding_id])
        self._shortcuts[binding_id] = shortcut

    def unregister_shortcut(self, binding_id: str) -> None:
        """Remove a binding entirely."""
        self._destroy_qt_shortcut(binding_id)
        self._handlers.pop(binding_id, None)
        self._keys.pop(binding_id, None)

    def _destroy_qt_shortcut(self, binding_id: str) -> None:
        existing = self._shortcuts.pop(binding_id, None)
        if existing is not None:
            try:
                existing.setEnabled(False)
                existing.activated.disconnect()
            except Exception:
                pass
            existing.deleteLater()
