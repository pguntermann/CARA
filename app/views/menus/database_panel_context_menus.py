"""Context menu builders for DatabasePanel.

Keeps QMenu/QAction construction out of the view implementation. The DatabasePanel
retains the actual action handling (what to do when an action is chosen).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import sys

from PyQt6.QtWidgets import QApplication, QMenu


@dataclass(frozen=True)
class DatabaseTabContextMenu:
    menu: QMenu
    close_action: Any
    close_all_but_action: Optional[Any] = None


def build_database_tab_context_menu(panel, *, include_close_all_but: bool) -> DatabaseTabContextMenu:
    menu = QMenu(panel)
    close_action = menu.addAction("Close")
    close_all_but_action = None
    if include_close_all_but:
        close_all_but_action = menu.addAction("Close all but this")

    from app.utils.themed_icon import (
        SVG_MENU_LAYERS,
        SVG_SIMPLE_X,
        menu_icon_dark_tint_rgb,
        themed_icon_from_svg,
    )

    _ctx_tint = menu_icon_dark_tint_rgb(panel.config)
    close_action.setIcon(themed_icon_from_svg(SVG_SIMPLE_X, _ctx_tint))
    if close_all_but_action is not None:
        close_all_but_action.setIcon(themed_icon_from_svg(SVG_MENU_LAYERS, _ctx_tint))

    from app.views.style import StyleManager

    StyleManager.style_context_menu(menu, panel.config)
    from app.views.style.context_menu import try_wire_context_menu_shared_action_icons

    try_wire_context_menu_shared_action_icons(menu)
    return DatabaseTabContextMenu(menu=menu, close_action=close_action, close_all_but_action=close_all_but_action)


@dataclass(frozen=True)
class DatabaseTableContextMenu:
    menu: QMenu
    select_rows_menu: QMenu
    select_mode_menu: QMenu
    act_replace: Any
    act_append: Any
    act_select_all: Any
    act_unselect_all: Any
    act_invert_selection: Any
    act_with_this: Optional[Any]
    act_with_not_this: Optional[Any]
    act_with_empty: Optional[Any]
    act_with_not_empty: Optional[Any]
    act_with_tag: Optional[Any]
    act_without_tag: Optional[Any]
    act_copy_csv: Any
    act_copy_tsv: Any
    act_copy_selected_csv: Any
    act_copy_selected_tsv: Any
    act_copy_game: Optional[Any]
    act_copy_selected_games: Optional[Any]
    act_cut_selected_games: Optional[Any]
    act_paste_games: Optional[Any]
    act_clear_game_tags_selected: Optional[Any]


def build_database_table_context_menu(
    panel,
    *,
    has_cell: bool,
    selection_mode: str,
    enable_copy_game: bool,
    enable_copy_selected_games: bool,
    enable_cut_selected_games: bool,
    enable_paste_games: bool,
    enable_clear_game_tags_selected: bool = False,
    clicked_tag: Optional[str] = None,
) -> DatabaseTableContextMenu:
    select_rows_menu = QMenu("Select rows", panel)
    select_mode_menu = QMenu("Select mode", panel)
    act_replace = select_mode_menu.addAction("Replace")
    act_replace.setCheckable(True)
    act_replace.setChecked(selection_mode == "replace")
    act_append = select_mode_menu.addAction("Append")
    act_append.setCheckable(True)
    act_append.setChecked(selection_mode == "append")
    select_rows_menu.addMenu(select_mode_menu)
    select_rows_menu.addSeparator()
    act_select_all = select_rows_menu.addAction("Select all rows")
    act_unselect_all = select_rows_menu.addAction("Unselect all rows")
    act_invert_selection = select_rows_menu.addAction("Invert Selection")
    act_with_this = act_with_not_this = act_with_empty = act_with_not_empty = None
    act_with_tag = act_without_tag = None
    if has_cell:
        select_rows_menu.addSeparator()
        act_with_this = select_rows_menu.addAction("With this value")
        act_with_not_this = select_rows_menu.addAction("With not this value")
        act_with_empty = select_rows_menu.addAction("With empty value")
        act_with_not_empty = select_rows_menu.addAction("With not empty value")
        if clicked_tag:
            select_rows_menu.addSeparator()
            act_with_tag = select_rows_menu.addAction(f'With this tag: "{clicked_tag}"')
            act_without_tag = select_rows_menu.addAction(f'Without this tag: "{clicked_tag}"')

    menu = QMenu(panel)
    menu.addMenu(select_rows_menu)
    menu.addSeparator()
    act_copy_csv = menu.addAction("Copy table as CSV")
    act_copy_tsv = menu.addAction("Copy table as TSV")
    act_copy_selected_csv = menu.addAction("Copy selected rows as CSV")
    act_copy_selected_tsv = menu.addAction("Copy selected rows as TSV")
    act_clear_game_tags_selected = None
    if enable_clear_game_tags_selected:
        menu.addSeparator()
        act_clear_game_tags_selected = menu.addAction("Clear game tags from selected games")
    menu.addSeparator()
    act_copy_game = menu.addAction("Copy Game") if enable_copy_game and has_cell else None
    act_copy_selected_games = menu.addAction("Copy selected Games") if enable_copy_selected_games else None
    act_cut_selected_games = menu.addAction("Cut selected Games") if enable_cut_selected_games else None
    act_paste_games = menu.addAction("Paste Game(s)") if enable_paste_games else None

    from app.utils.themed_icon import (
        menu_icon_dark_tint_rgb,
        themed_icon_from_svg,
        SVG_MENU_COPY,
        SVG_MENU_CUT,
        SVG_MENU_PASTE_ACTIVE_DB,
    )

    _ctx_tint = menu_icon_dark_tint_rgb(panel.config)
    if act_copy_selected_games is not None:
        act_copy_selected_games.setIcon(themed_icon_from_svg(SVG_MENU_COPY, _ctx_tint))
    if act_cut_selected_games is not None:
        act_cut_selected_games.setIcon(themed_icon_from_svg(SVG_MENU_CUT, _ctx_tint))
    if act_paste_games is not None:
        act_paste_games.setIcon(themed_icon_from_svg(SVG_MENU_PASTE_ACTIVE_DB, _ctx_tint))

    from app.views.style import StyleManager

    StyleManager.style_context_menu(menu, panel.config)
    StyleManager.style_context_menu(select_rows_menu, panel.config)
    StyleManager.style_context_menu(select_mode_menu, panel.config)

    from app.views.style.context_menu import try_wire_context_menu_shared_action_icons

    try_wire_context_menu_shared_action_icons(menu)

    return DatabaseTableContextMenu(
        menu=menu,
        select_rows_menu=select_rows_menu,
        select_mode_menu=select_mode_menu,
        act_replace=act_replace,
        act_append=act_append,
        act_select_all=act_select_all,
        act_unselect_all=act_unselect_all,
        act_invert_selection=act_invert_selection,
        act_with_this=act_with_this,
        act_with_not_this=act_with_not_this,
        act_with_empty=act_with_empty,
        act_with_not_empty=act_with_not_empty,
        act_with_tag=act_with_tag,
        act_without_tag=act_without_tag,
        act_copy_csv=act_copy_csv,
        act_copy_tsv=act_copy_tsv,
        act_copy_selected_csv=act_copy_selected_csv,
        act_copy_selected_tsv=act_copy_selected_tsv,
        act_copy_game=act_copy_game,
        act_copy_selected_games=act_copy_selected_games,
        act_cut_selected_games=act_cut_selected_games,
        act_paste_games=act_paste_games,
        act_clear_game_tags_selected=act_clear_game_tags_selected,
    )


def dismiss_database_table_context_menus(panel, ctx: DatabaseTableContextMenu) -> None:
    """Close our database table context menu hierarchy reliably (macOS needs extra help)."""
    # During theme switches / UI rebuilds, the menus can be deleted while the QTimer
    # callback is still pending (PyQt then raises RuntimeError on any access).
    try:
        ctx.menu.close()
        ctx.menu.hide()
        ctx.select_rows_menu.close()
        ctx.select_rows_menu.hide()
        ctx.select_mode_menu.close()
        ctx.select_mode_menu.hide()
    except RuntimeError:
        return
    if sys.platform == "darwin":
        QApplication.processEvents()
        popup = QApplication.activePopupWidget()
        while popup is not None:
            try:
                popup.close()
                popup.hide()
            except RuntimeError:
                break
            QApplication.processEvents()
            popup = QApplication.activePopupWidget()

