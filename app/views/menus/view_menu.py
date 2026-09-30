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

    from app.utils.miniature_board_scales import (
        GAME_SUMMARY_HIGHLIGHTS,
        MANUAL_ANALYSIS,
        MINIATURE_BOARD_SCALE_MENU_ITEMS,
        MINIATURE_BOARD_SCALE_PRESETS,
        MOVE_LINK_POPUPS,
        OPENING_EXPLORER,
    )
    from app.utils.miniature_board_arrows import (
        GAME_SUMMARY_BEST_ALTERNATIVE,
        GAME_SUMMARY_PLAYED,
        MOVE_LINK_BEST_ALTERNATIVE,
        MOVE_LINK_PLAYED,
        OPENING_EXPLORER as ARROWS_OPENING_EXPLORER,
    )

    miniature_boards_menu = view_menu.addMenu("Miniature Boards")
    mw._apply_menu_styling(miniature_boards_menu)
    mw.miniature_board_scale_actions = {}
    mw.miniature_board_arrow_actions = {}
    for surface_key, surface_label in MINIATURE_BOARD_SCALE_MENU_ITEMS:
        surface_menu = miniature_boards_menu.addMenu(surface_label)
        mw._apply_menu_styling(surface_menu)
        actions_for_surface = {}
        for scale in MINIATURE_BOARD_SCALE_PRESETS:
            action = QAction(f"{scale}x", mw)
            action.setCheckable(True)
            action.setData(scale)
            action.triggered.connect(
                lambda checked=False, key=surface_key, s=scale: mw._on_miniature_board_scale_selected(
                    key, s
                )
            )
            surface_menu.addAction(action)
            actions_for_surface[scale] = action
        mw.miniature_board_scale_actions[surface_key] = actions_for_surface

        # Arrow toggles use the same labels as Board → Show … Move
        if surface_key == MANUAL_ANALYSIS:
            surface_menu.addSeparator()
            mw.miniature_preview_move_arrow_action = QAction("Show Move Arrow", mw)
            mw.miniature_preview_move_arrow_action.setCheckable(True)
            mw.miniature_preview_move_arrow_action.setChecked(True)
            mw.miniature_preview_move_arrow_action.toggled.connect(
                mw._on_miniature_preview_move_arrow_toggled
            )
            surface_menu.addAction(mw.miniature_preview_move_arrow_action)
        elif surface_key == OPENING_EXPLORER:
            surface_menu.addSeparator()
            action = QAction("Show Played Move", mw)
            action.setCheckable(True)
            action.setChecked(True)
            action.triggered.connect(
                lambda checked=False, key=ARROWS_OPENING_EXPLORER: mw._on_miniature_board_arrow_toggled(
                    key, checked
                )
            )
            surface_menu.addAction(action)
            mw.miniature_board_arrow_actions[ARROWS_OPENING_EXPLORER] = action
        elif surface_key == GAME_SUMMARY_HIGHLIGHTS:
            surface_menu.addSeparator()
            played_action = QAction("Show Played Move", mw)
            played_action.setCheckable(True)
            played_action.setChecked(True)
            played_action.triggered.connect(
                lambda checked=False, key=GAME_SUMMARY_PLAYED: mw._on_miniature_board_arrow_toggled(
                    key, checked
                )
            )
            surface_menu.addAction(played_action)
            mw.miniature_board_arrow_actions[GAME_SUMMARY_PLAYED] = played_action

            alt_action = QAction("Show Best Alternative Move", mw)
            alt_action.setCheckable(True)
            alt_action.setChecked(True)
            alt_action.triggered.connect(
                lambda checked=False, key=GAME_SUMMARY_BEST_ALTERNATIVE: mw._on_miniature_board_arrow_toggled(
                    key, checked
                )
            )
            surface_menu.addAction(alt_action)
            mw.miniature_board_arrow_actions[GAME_SUMMARY_BEST_ALTERNATIVE] = alt_action
        elif surface_key == MOVE_LINK_POPUPS:
            surface_menu.addSeparator()
            played_action = QAction("Show Played Move", mw)
            played_action.setCheckable(True)
            played_action.setChecked(True)
            played_action.triggered.connect(
                lambda checked=False, key=MOVE_LINK_PLAYED: mw._on_miniature_board_arrow_toggled(
                    key, checked
                )
            )
            surface_menu.addAction(played_action)
            mw.miniature_board_arrow_actions[MOVE_LINK_PLAYED] = played_action

            alt_action = QAction("Show Best Alternative Move", mw)
            alt_action.setCheckable(True)
            alt_action.setChecked(True)
            alt_action.triggered.connect(
                lambda checked=False, key=MOVE_LINK_BEST_ALTERNATIVE: mw._on_miniature_board_arrow_toggled(
                    key, checked
                )
            )
            surface_menu.addAction(alt_action)
            mw.miniature_board_arrow_actions[MOVE_LINK_BEST_ALTERNATIVE] = alt_action

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
