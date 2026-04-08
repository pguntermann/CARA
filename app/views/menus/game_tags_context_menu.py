"""Game tags widget context menu (mirrors the main Tag menu)."""

from __future__ import annotations

from typing import Any, List, Optional

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from app.services.game_tags_service import GameTagsService
from app.utils.game_tags_utils import parse_game_tags, format_game_tags, PGN_TAG_NAME_GAME_TAGS


def build_game_tags_context_menu(mw: Any, *, parent: Optional[Any] = None) -> QMenu:
    """Build a context menu for the board's GameTagsWidget.

    Uses the same conventions as other context menus:
    - styled via StyleManager.style_context_menu
    - dynamic rebuild so it reflects active game + definitions
    """
    menu = QMenu(parent if parent is not None else mw)

    from app.views.style import StyleManager

    StyleManager.style_context_menu(menu, mw.config)

    manage_act = getattr(mw, "manage_tags_action", None)
    if manage_act is not None:
        menu.addAction(manage_act)
    else:
        # Fallback: create action if Tag menu isn't initialized for some reason.
        from app.views.dialogs.manage_game_tags_dialog import ManageGameTagsDialog

        act = QAction("Manage tags…", mw)
        act.triggered.connect(lambda: ManageGameTagsDialog(mw.config, mw).exec())
        menu.addAction(act)

    clear_act = getattr(mw, "clear_all_tags_action", None)
    if clear_act is not None:
        menu.addAction(clear_act)

    menu.addSeparator()

    defs = GameTagsService(mw.config).get_definitions()
    game_model = mw.controller.get_game_controller().get_game_model()
    has_active_game = bool(getattr(game_model, "active_game", None))
    current = {t.casefold() for t in _get_active_game_tags(mw)} if has_active_game else set()

    builtins = [d for d in defs if d.builtin]
    customs = [d for d in defs if not d.builtin]

    for d in builtins:
        act = QAction(d.name, mw)
        act.setCheckable(True)
        act.setChecked(d.name.casefold() in current)
        act.setEnabled(has_active_game)
        act.triggered.connect(lambda checked=False, n=d.name: _toggle_tag_for_active_game(mw, n))
        menu.addAction(act)

    if customs:
        menu.addSeparator()
        for d in customs:
            act = QAction(d.name, mw)
            act.setCheckable(True)
            act.setChecked(d.name.casefold() in current)
            act.setEnabled(has_active_game)
            act.triggered.connect(lambda checked=False, n=d.name: _toggle_tag_for_active_game(mw, n))
            menu.addAction(act)

    defined_names = {d.name.casefold() for d in defs}
    unmanaged = [t for t in _get_active_game_tags(mw) if t.casefold() not in defined_names] if has_active_game else []
    if unmanaged:
        menu.addSeparator()
        header = QAction("Unmanaged (this game)", mw)
        header.setEnabled(False)
        menu.addAction(header)
        for n in unmanaged:
            act = QAction(n, mw)
            act.setCheckable(True)
            act.setChecked(True)
            act.setEnabled(has_active_game)
            act.triggered.connect(lambda checked=False, name=n: _toggle_tag_for_active_game(mw, name))
            menu.addAction(act)

    return menu


def _get_active_game_tags(mw: Any) -> List[str]:
    game_model = mw.controller.get_game_controller().get_game_model()
    game = getattr(game_model, "active_game", None)
    if not game:
        return []
    raw = getattr(game, "game_tags_raw", "") or ""
    return parse_game_tags(raw)


def _set_active_game_tags(mw: Any, tags: List[str]) -> None:
    metadata_controller = mw.controller.get_metadata_controller()
    raw = format_game_tags(tags)
    if raw:
        metadata_controller.update_metadata_tag(PGN_TAG_NAME_GAME_TAGS, raw)
    else:
        metadata_controller.remove_metadata_tag(PGN_TAG_NAME_GAME_TAGS)


def _toggle_tag_for_active_game(mw: Any, tag_name: str) -> None:
    tags = _get_active_game_tags(mw)
    key = tag_name.casefold()
    new_tags = [t for t in tags if t.casefold() != key]
    if len(new_tags) == len(tags):
        new_tags.append(tag_name)
    _set_active_game_tags(mw, new_tags)

