"""Context menu builder for DetailPlayerStatsView.

This keeps the QMenu/QAction construction in the menus package while the view
retains the behavior (handlers on the view/controller).
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu


def build_player_stats_context_menu(
    view,
    *,
    section_name: Optional[str],
    click_in_opening_tree: bool,
    click_in_endgame_tree: bool,
) -> QMenu:
    menu = QMenu(view)

    ui_config = view.config.get("ui", {})
    panel_config = ui_config.get("panels", {}).get("detail", {})
    player_stats_config = panel_config.get("player_stats", {})
    colors_config = player_stats_config.get("colors", {})
    bg_color = colors_config.get("background", [40, 40, 45])

    from app.views.style import StyleManager

    StyleManager.style_context_menu(menu, view.config, bg_color)

    if section_name:
        copy_section_action = menu.addAction("Copy section to clipboard")
        copy_section_action.triggered.connect(
            lambda checked=False, name=section_name: view._copy_section_to_clipboard(name)
        )

    copy_full_action = menu.addAction("Copy stats to clipboard")
    copy_full_action.triggered.connect(view._copy_full_stats_to_clipboard)

    from app.views.menus.player_stats_activity_heatmap_menu import (
        PLAYER_STATS_ACTIVITY_HEATMAP_CONTEXT_SECTIONS,
    )
    from app.views.menus.player_stats_time_series_menu import (
        PLAYER_STATS_TIME_SERIES_CONTEXT_SECTIONS,
    )
    from app.views.menus.player_stats_accuracy_distribution_menu import (
        PLAYER_STATS_ACCURACY_DISTRIBUTION_CONTEXT_SECTIONS,
    )

    if section_name and section_name in PLAYER_STATS_TIME_SERIES_CONTEXT_SECTIONS:
        menu.addSeparator()
        view._ensure_player_stats_time_series_context_menu_controller()
        assert view._ps_ts_context_menu_controller is not None
        view._ps_ts_context_menu_controller.append_to_context_menu(menu)

    if section_name and section_name in PLAYER_STATS_ACTIVITY_HEATMAP_CONTEXT_SECTIONS:
        menu.addSeparator()
        view._ensure_player_stats_activity_heatmap_context_menu_controller()
        assert view._ps_ah_context_menu_controller is not None
        view._ps_ah_context_menu_controller.append_to_context_menu(menu)

    if section_name and section_name in PLAYER_STATS_ACCURACY_DISTRIBUTION_CONTEXT_SECTIONS:
        menu.addSeparator()
        view._ensure_player_stats_accuracy_distribution_context_menu_controller()
        assert view._ps_ad_context_menu_controller is not None
        view._ps_ad_context_menu_controller.append_to_context_menu(menu)

    if click_in_opening_tree and view._opening_tree_widget is not None:
        menu.addSeparator()
        expand_all_action = menu.addAction("Expand all")
        collapse_all_action = menu.addAction("Collapse all")
        expand_all_action.triggered.connect(
            lambda checked=False: view._opening_tree_widget.expandAll()
        )
        collapse_all_action.triggered.connect(
            lambda checked=False: view._opening_tree_widget.collapseAll()
        )

    if click_in_endgame_tree and view._endgame_tree_widget is not None:
        menu.addSeparator()
        expand_all_action = menu.addAction("Expand all")
        collapse_all_action = menu.addAction("Collapse all")
        expand_all_action.triggered.connect(
            lambda checked=False: view._endgame_tree_widget.expandAll()
        )
        collapse_all_action.triggered.connect(
            lambda checked=False: view._endgame_tree_widget.collapseAll()
        )

    return menu

