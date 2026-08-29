"""View menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.services.detail_panel_visibility import DETAIL_PANEL_VISIBILITY_UNITS
from app.utils.themed_icon import (
    SVG_MENU_KEYBOARD,
    set_menubar_themable_action_icon,
)


def setup_view_menu(mw, menu_bar: QMenuBar) -> None:
    view_menu = menu_bar.addMenu("View")
    mw._apply_menu_styling(view_menu)

    # Theme switching (runtime) should be at the top
    mw._setup_theme_menu(view_menu)
    view_menu.addSeparator()

    mw.view_keyboard_shortcuts_action = QAction("Keyboard Shortcuts...", mw)
    set_menubar_themable_action_icon(
        mw, mw.view_keyboard_shortcuts_action, SVG_MENU_KEYBOARD
    )
    mw.view_keyboard_shortcuts_action.triggered.connect(
        mw._show_keyboard_shortcuts_dialog
    )
    view_menu.addAction(mw.view_keyboard_shortcuts_action)
    view_menu.addSeparator()

    mw.view_moves_list_action = QAction("Moves List", mw)
    mw.view_moves_list_action.setShortcut(QKeySequence("F1"))
    mw.view_moves_list_action.setCheckable(True)
    mw.view_moves_list_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("moves_list")
    )
    view_menu.addAction(mw.view_moves_list_action)

    mw.view_metadata_action = QAction("PGN header tags", mw)
    mw.view_metadata_action.setShortcut(QKeySequence("F2"))
    mw.view_metadata_action.setCheckable(True)
    mw.view_metadata_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("metadata")
    )
    view_menu.addAction(mw.view_metadata_action)

    mw.view_manual_analysis_action = QAction("Manual Analysis", mw)
    mw.view_manual_analysis_action.setShortcut(QKeySequence("F3"))
    mw.view_manual_analysis_action.setCheckable(True)
    mw.view_manual_analysis_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("manual_analysis")
    )
    view_menu.addAction(mw.view_manual_analysis_action)

    mw.view_opening_explorer_action = QAction("Opening Explorer", mw)
    mw.view_opening_explorer_action.setShortcut(QKeySequence("F4"))
    mw.view_opening_explorer_action.setCheckable(True)
    mw.view_opening_explorer_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("opening_explorer")
    )
    view_menu.addAction(mw.view_opening_explorer_action)

    mw.view_game_summary_action = QAction("Game Summary", mw)
    mw.view_game_summary_action.setShortcut(QKeySequence("F5"))
    mw.view_game_summary_action.setCheckable(True)
    mw.view_game_summary_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("game_summary")
    )
    view_menu.addAction(mw.view_game_summary_action)

    mw.view_player_stats_action = QAction("Player Stats", mw)
    mw.view_player_stats_action.setShortcut(QKeySequence("F6"))
    mw.view_player_stats_action.setCheckable(True)
    mw.view_player_stats_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("player_stats")
    )
    view_menu.addAction(mw.view_player_stats_action)

    mw.view_annotations_action = QAction("Annotations", mw)
    mw.view_annotations_action.setShortcut(QKeySequence("F7"))
    mw.view_annotations_action.setCheckable(True)
    mw.view_annotations_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("annotations")
    )
    view_menu.addAction(mw.view_annotations_action)

    mw.view_ai_summary_action = QAction("AI Summary", mw)
    mw.view_ai_summary_action.setShortcut(QKeySequence("F8"))
    mw.view_ai_summary_action.setCheckable(True)
    mw.view_ai_summary_action.triggered.connect(
        lambda: mw._switch_detail_tab_by_id("ai_summary")
    )
    view_menu.addAction(mw.view_ai_summary_action)

    mw.view_notes_action = QAction("Notes", mw)
    mw.view_notes_action.setShortcut(QKeySequence("F9"))
    mw.view_notes_action.setCheckable(True)
    mw.view_notes_action.triggered.connect(lambda: mw._switch_detail_tab_by_id("notes"))
    view_menu.addAction(mw.view_notes_action)

    mw.view_previous_detail_tab_action = QAction("Previous detail tab", mw)
    mw.view_previous_detail_tab_action.triggered.connect(
        lambda: mw._cycle_detail_tab(-1)
    )
    view_menu.addAction(mw.view_previous_detail_tab_action)

    mw.view_next_detail_tab_action = QAction("Next detail tab", mw)
    mw.view_next_detail_tab_action.triggered.connect(
        lambda: mw._cycle_detail_tab(1)
    )
    view_menu.addAction(mw.view_next_detail_tab_action)

    view_menu.addSeparator()

    # Show/Hide detail tabs and related top-level menus (persisted).
    show_hide_menu = view_menu.addMenu("Show/Hide")
    mw._apply_menu_styling(show_hide_menu)
    mw._detail_panel_visibility_actions = {}
    for unit in DETAIL_PANEL_VISIBILITY_UNITS:
        action = QAction(unit.label, mw)
        action.setCheckable(True)
        action.setChecked(True)
        action.triggered.connect(
            lambda checked=False, unit_id=unit.id: mw._on_detail_panel_visibility_toggled(
                unit_id, checked
            )
        )
        show_hide_menu.addAction(action)
        mw._detail_panel_visibility_actions[unit.id] = action

    view_menu.addSeparator()

    mw.view_hide_pgn_pane_action = QAction("Hide PGN Pane", mw)
    mw.view_hide_pgn_pane_action.setShortcut(QKeySequence("Ctrl+Shift+Up"))
    mw.view_hide_pgn_pane_action.setCheckable(True)
    mw.view_hide_pgn_pane_action.setChecked(False)
    mw.view_hide_pgn_pane_action.triggered.connect(mw._toggle_pgn_pane)
    view_menu.addAction(mw.view_hide_pgn_pane_action)

    mw.view_hide_database_panel_action = QAction("Hide Database Panel", mw)
    mw.view_hide_database_panel_action.setShortcut(QKeySequence("Ctrl+Shift+Down"))
    mw.view_hide_database_panel_action.setCheckable(True)
    mw.view_hide_database_panel_action.setChecked(False)
    mw.view_hide_database_panel_action.triggered.connect(mw._toggle_database_panel)
    view_menu.addAction(mw.view_hide_database_panel_action)

    mw.view_menu_actions = [
        mw.view_moves_list_action,
        mw.view_metadata_action,
        mw.view_manual_analysis_action,
        mw.view_opening_explorer_action,
        mw.view_game_summary_action,
        mw.view_player_stats_action,
        mw.view_annotations_action,
        mw.view_ai_summary_action,
        mw.view_notes_action,
    ]
