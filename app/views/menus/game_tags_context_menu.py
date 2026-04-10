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

    from app.views.dialogs.manage_game_tags_dialog import ManageGameTagsDialog
    from app.views.style import StyleManager
    from app.views.style.context_menu import wire_context_menu_icon_retheming
    from app.utils.themed_icon import (
        menu_icon_dark_tint_rgb,
        themed_icon_from_svg,
        SVG_MENU_CLEAR_ALL_GAME_TAGS,
        SVG_MENU_TAG_BUBBLE,
    )

    StyleManager.style_context_menu(menu, mw.config)

    svc = GameTagsService(mw.config)
    defs = svc.get_definitions()
    hidden = svc.get_hidden_builtin_names()
    game_model = mw.controller.get_game_controller().get_game_model()
    has_active_game = bool(getattr(game_model, "active_game", None))
    current = {t.casefold() for t in _get_active_game_tags(mw) if t.casefold() not in hidden} if has_active_game else set()

    _dark_tint = menu_icon_dark_tint_rgb(mw.config)

    # Dedicated QActions: reusing menubar QActions would apply light-OS icon tints on this dark menu.
    manage_act = QAction("Manage game tags…", mw)
    manage_act.setIcon(themed_icon_from_svg(SVG_MENU_TAG_BUBBLE, _dark_tint))
    manage_act.triggered.connect(lambda: ManageGameTagsDialog(mw.config, mw).exec())
    menu.addAction(manage_act)

    clear_act = QAction("Clear all game tags", mw)
    clear_act.setIcon(themed_icon_from_svg(SVG_MENU_CLEAR_ALL_GAME_TAGS, _dark_tint))
    clear_act.setEnabled(bool(has_active_game and current))
    clear_act.triggered.connect(lambda: _set_active_game_tags(mw, []))
    menu.addAction(clear_act)

    menu.addSeparator()

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
    unmanaged = [t for t in _get_active_game_tags(mw) if t.casefold() not in hidden and t.casefold() not in defined_names] if has_active_game else []
    if unmanaged:
        menu.addSeparator()
        header = QAction("Unmanaged game tags (this game)", mw)
        header.setEnabled(False)
        menu.addAction(header)
        for n in unmanaged:
            act = QAction(n, mw)
            act.setCheckable(True)
            act.setChecked(True)
            act.setEnabled(has_active_game)
            act.triggered.connect(lambda checked=False, name=n: _toggle_tag_for_active_game(mw, name))
            menu.addAction(act)

    wire_context_menu_icon_retheming(menu, mw)
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

