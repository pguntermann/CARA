"""Notes context menu additions (mirrors the main Notes menubar menu)."""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QMenu


def append_notes_menu_items_to_context_menu(menu: QMenu, mw: Any) -> None:
    """Append the Notes menubar actions to an existing context menu.

    Reuses the existing QActions from the menubar so shortcuts and behavior stay in sync.
    """
    for attr in ("clear_notes_action", "save_notes_action"):
        act = getattr(mw, attr, None)
        if act is not None:
            menu.addAction(act)
