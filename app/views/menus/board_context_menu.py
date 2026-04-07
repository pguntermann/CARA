"""Board context menu (mirrors the main Board menubar menu)."""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtWidgets import QMenu


def build_board_context_menu(mw: Any, *, parent: Optional[Any] = None) -> QMenu:
    """Build a context menu that mirrors the main 'Board' menu layout.

    Reuses the existing QActions from the menubar so checked states stay in sync.
    """
    menu = QMenu(parent if parent is not None else mw)

    # Style using context menu conventions (font/size/bg from ui.styles.context_menu).
    from app.views.style import StyleManager

    StyleManager.style_context_menu(menu, mw.config)

    def _add_action_attr(attr: str) -> None:
        act = getattr(mw, attr, None)
        if act is not None:
            menu.addAction(act)

    _add_action_attr("rotate_action")
    menu.addSeparator()

    _add_action_attr("game_info_action")
    _add_action_attr("coordinates_action")
    _add_action_attr("turn_indicator_action")
    _add_action_attr("material_widget_action")
    menu.addSeparator()

    _add_action_attr("evaluation_bar_action")
    _add_action_attr("positional_heatmap_action")
    menu.addSeparator()

    _add_action_attr("playedmove_arrow_action")
    _add_action_attr("bestnextmove_arrow_action")
    _add_action_attr("pv2_arrow_action")
    _add_action_attr("pv3_arrow_action")
    _add_action_attr("bestalternativemove_arrow_action")
    _add_action_attr("move_classification_icons_action")
    menu.addSeparator()

    _add_action_attr("show_annotations_layer_action")
    menu.addSeparator()

    # Submenu: trajectory style
    traj_menu = menu.addMenu("Path trajectory style")
    StyleManager.style_context_menu(traj_menu, mw.config)
    for attr in ("trajectory_style_straight_action", "trajectory_style_bezier_action"):
        act = getattr(mw, attr, None)
        if act is not None:
            traj_menu.addAction(act)

    return menu

