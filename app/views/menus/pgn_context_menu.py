"""PGN context menu additions (mirrors the main PGN menubar menu)."""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QMenu


def append_pgn_menu_items_to_context_menu(menu: QMenu, mw: Any, *, config: dict) -> None:
    """Append the PGN menubar actions to an existing context menu.

    Reuses the existing QActions from the menubar so checked states stay in sync.
    """
    def _add(attr: str) -> None:
        act = getattr(mw, attr, None)
        if act is not None:
            menu.addAction(act)

    _add("show_metadata_action")
    _add("show_comments_action")
    _add("show_variations_action")
    _add("show_non_standard_tags_action")
    _add("show_annotations_action")
    _add("show_results_action")

    menu.addSeparator()

    # Submenu: NAG display mode (reuse actions; rebuild submenu for this menu instance)
    nag_menu = menu.addMenu("Display NAG move assessments as...")
    from app.views.style import StyleManager

    StyleManager.style_context_menu(nag_menu, config)
    for attr in ("nag_display_symbols_action", "nag_display_text_action"):
        act = getattr(mw, attr, None)
        if act is not None:
            nag_menu.addAction(act)

    menu.addSeparator()

    _add("remove_comments_action")
    _add("remove_variations_action")
    _add("remove_non_standard_tags_action")
    _add("remove_annotations_action")

