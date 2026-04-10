"""Tag menu definition for MainWindow."""

from __future__ import annotations

from typing import Any, List

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenuBar, QMenu

from app.services.game_tags_service import GameTagsService
from app.utils.game_tags_utils import parse_game_tags, format_game_tags, PGN_TAG_NAME_GAME_TAGS
from app.views.dialogs.manage_game_tags_dialog import ManageGameTagsDialog


def setup_tag_menu(mw: Any, menu_bar: QMenuBar) -> None:
    tag_menu = menu_bar.addMenu("Game tags")
    mw._apply_menu_styling(tag_menu)

    mw.manage_tags_action = QAction("Manage game tags…", mw)
    mw.manage_tags_action.triggered.connect(lambda: _open_manage_tags_dialog(mw))
    tag_menu.addAction(mw.manage_tags_action)

    tag_menu.addSeparator()
    mw.clear_all_tags_action = QAction("Clear all game tags", mw)
    mw.clear_all_tags_action.triggered.connect(lambda: _set_active_game_tags(mw, []))
    tag_menu.addAction(mw.clear_all_tags_action)
    tag_menu.addSeparator()

    # Rebuild per-game toggles dynamically so they reflect active game + definitions.
    tag_menu.aboutToShow.connect(lambda: _rebuild_tag_menu(mw, tag_menu))


def _open_manage_tags_dialog(mw: Any) -> None:
    dlg = ManageGameTagsDialog(mw.config, mw)
    dlg.exec()


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

    # Keep board widget in sync immediately (if present)
    if hasattr(mw, "main_panel") and hasattr(mw.main_panel, "chessboard_view"):
        board_widget = getattr(mw.main_panel.chessboard_view, "chessboard", None)
        if board_widget is not None and hasattr(board_widget, "game_tags_widget") and board_widget.game_tags_widget:
            board_widget.game_tags_widget._refresh()


def _rebuild_tag_menu(mw: Any, menu: QMenu) -> None:
    # Keep the first four items intact: Manage game tags… + separator + Clear all + separator.
    actions = menu.actions()
    for act in actions[4:]:
        menu.removeAction(act)

    defs = GameTagsService(mw.config).get_definitions()
    game_model = mw.controller.get_game_controller().get_game_model()
    has_active_game = bool(getattr(game_model, "active_game", None))
    current = {t.casefold() for t in _get_active_game_tags(mw)} if has_active_game else set()

    if hasattr(mw, "clear_all_tags_action") and mw.clear_all_tags_action:
        mw.clear_all_tags_action.setEnabled(bool(has_active_game and current))

    builtins = [d for d in defs if d.builtin]
    customs = [d for d in defs if not d.builtin]

    # Built-in tags directly in the menu (no submenu)
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

    # Unmanaged tags currently present in this game
    defined_names = {d.name.casefold() for d in defs}
    unmanaged = [t for t in _get_active_game_tags(mw) if t.casefold() not in defined_names] if has_active_game else []
    if unmanaged:
        menu.addSeparator()
        unmanaged_header = QAction("Unmanaged game tags (this game)", mw)
        unmanaged_header.setEnabled(False)
        menu.addAction(unmanaged_header)
        for n in unmanaged:
            act = QAction(n, mw)
            act.setCheckable(True)
            act.setChecked(True)
            act.setEnabled(has_active_game)
            act.triggered.connect(lambda checked=False, name=n: _toggle_tag_for_active_game(mw, name))
            menu.addAction(act)

