"""Controller for keyboard-shortcut dialog operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from PyQt6.QtCore import QObject

from app.services.keyboard_shortcuts_service import KeyboardShortcutsService
from app.utils.keyboard_shortcuts_catalog import (
    ShortcutEntry,
    format_shortcut_for_display,
)


@dataclass(frozen=True)
class ShortcutConflict:
    """Another binding that already uses the requested shortcut."""

    binding_id: str
    category: str
    action: str
    shortcut: str


class KeyboardShortcutsController(QObject):
    """Orchestrates shortcut listing, filtering, and mutation via the service.

    The dialog stays presentation-only: it asks this controller for data and
    to apply changes; confirmation UI remains in the view.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = KeyboardShortcutsService.get_instance()

    def list_entries(self) -> List[ShortcutEntry]:
        """Return all bindable shortcut rows with effective bindings."""
        return self._service.list_entries()

    def filter_entries(
        self,
        entries: Sequence[ShortcutEntry],
        query: str,
    ) -> List[ShortcutEntry]:
        """Filter rows by category, action, or shortcut text (case-insensitive).

        Shortcut matching covers both portable storage text (``Ctrl+O``) and
        the platform-native display form (e.g. ``⌘O`` on macOS).
        """
        needle = (query or "").strip().lower()
        if not needle:
            return list(entries)
        matched: List[ShortcutEntry] = []
        for entry in entries:
            if (
                needle in entry.category.lower()
                or needle in entry.action.lower()
            ):
                matched.append(entry)
                continue
            portable = (entry.shortcut or "").lower()
            if needle in portable:
                matched.append(entry)
                continue
            native = format_shortcut_for_display(entry.shortcut).lower()
            if native and needle in native:
                matched.append(entry)
        return matched

    def count_bound(self, entries: Sequence[ShortcutEntry]) -> int:
        """Count entries that currently have a non-empty shortcut."""
        return sum(1 for entry in entries if (entry.shortcut or "").strip())

    def status_summary(
        self,
        *,
        visible_count: int,
        total_count: int,
        entries: Sequence[ShortcutEntry],
    ) -> str:
        """Build the idle status line for the dialog."""
        bound = self.count_bound(entries)
        if visible_count == total_count:
            return (
                f"{total_count} actions · {bound} with shortcuts — "
                "double-click a shortcut to change it"
            )
        return (
            f"Showing {visible_count} of {total_count} actions · "
            f"{bound} with shortcuts"
        )

    def display_shortcut(self, shortcut: str, empty_display: str = "—") -> str:
        """Format a shortcut for UI (native glyphs; empty → placeholder)."""
        text = (shortcut or "").strip()
        if not text:
            return empty_display
        display = format_shortcut_for_display(text)
        return display if display else empty_display

    def find_conflict(
        self,
        binding_id: str,
        shortcut: str,
    ) -> Optional[ShortcutConflict]:
        """Return a conflict descriptor if ``shortcut`` is already used."""
        conflict = self._service.find_conflict(binding_id, shortcut)
        if conflict is None:
            return None
        return ShortcutConflict(
            binding_id=conflict.binding_id,
            category=conflict.category,
            action=conflict.action,
            shortcut=conflict.shortcut,
        )

    def set_binding(
        self,
        binding_id: str,
        shortcut: str,
        *,
        steal_from: Optional[str] = None,
    ) -> None:
        """Assign or clear one binding (empty ``shortcut`` clears)."""
        self._service.set_binding(
            binding_id,
            shortcut,
            steal_from=steal_from,
            persist=True,
        )

    def clear_binding(self, binding_id: str) -> None:
        """Clear the shortcut for one binding."""
        self.set_binding(binding_id, "")

    def clear_all(self) -> None:
        """Clear every keyboard shortcut."""
        self._service.clear_all(persist=True)

    def restore_defaults(self) -> None:
        """Restore factory-default shortcuts."""
        self._service.restore_defaults(persist=True)
