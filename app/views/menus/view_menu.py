"""View menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar


def setup_view_menu(mw, menu_bar: QMenuBar) -> None:
    view_menu = menu_bar.addMenu("View")
    mw._apply_menu_styling(view_menu)

    mw.view_moves_list_action = QAction("Moves List", mw)
    mw.view_moves_list_action.setShortcut(QKeySequence("F1"))
    mw.view_moves_list_action.setCheckable(True)
    mw.view_moves_list_action.triggered.connect(lambda: mw._switch_detail_tab(0))
    view_menu.addAction(mw.view_moves_list_action)

    mw.view_metadata_action = QAction("Metadata", mw)
    mw.view_metadata_action.setShortcut(QKeySequence("F2"))
    mw.view_metadata_action.setCheckable(True)
    mw.view_metadata_action.triggered.connect(lambda: mw._switch_detail_tab(1))
    view_menu.addAction(mw.view_metadata_action)

    mw.view_manual_analysis_action = QAction("Manual Analysis", mw)
    mw.view_manual_analysis_action.setShortcut(QKeySequence("F3"))
    mw.view_manual_analysis_action.setCheckable(True)
    mw.view_manual_analysis_action.triggered.connect(lambda: mw._switch_detail_tab(2))
    view_menu.addAction(mw.view_manual_analysis_action)

    mw.view_game_summary_action = QAction("Game Summary", mw)
    mw.view_game_summary_action.setShortcut(QKeySequence("F4"))
    mw.view_game_summary_action.setCheckable(True)
    mw.view_game_summary_action.triggered.connect(lambda: mw._switch_detail_tab(3))
    view_menu.addAction(mw.view_game_summary_action)

    mw.view_player_stats_action = QAction("Player Stats", mw)
    mw.view_player_stats_action.setShortcut(QKeySequence("F5"))
    mw.view_player_stats_action.setCheckable(True)
    mw.view_player_stats_action.triggered.connect(lambda: mw._switch_detail_tab(4))
    view_menu.addAction(mw.view_player_stats_action)

    mw.view_annotations_action = QAction("Annotations", mw)
    mw.view_annotations_action.setShortcut(QKeySequence("F6"))
    mw.view_annotations_action.setCheckable(True)
    mw.view_annotations_action.triggered.connect(lambda: mw._switch_detail_tab(5))
    view_menu.addAction(mw.view_annotations_action)

    mw.view_ai_summary_action = QAction("AI Summary", mw)
    mw.view_ai_summary_action.setShortcut(QKeySequence("F7"))
    mw.view_ai_summary_action.setCheckable(True)
    mw.view_ai_summary_action.triggered.connect(lambda: mw._switch_detail_tab(6))
    view_menu.addAction(mw.view_ai_summary_action)

    mw.view_notes_action = QAction("Notes", mw)
    mw.view_notes_action.setShortcut(QKeySequence("F8"))
    mw.view_notes_action.setCheckable(True)
    mw.view_notes_action.triggered.connect(lambda: mw._switch_detail_tab(7))
    view_menu.addAction(mw.view_notes_action)

    view_menu.addSeparator()

    mw.view_hide_database_panel_action = QAction("Hide Database Panel", mw)
    mw.view_hide_database_panel_action.setCheckable(True)
    mw.view_hide_database_panel_action.setChecked(False)
    mw.view_hide_database_panel_action.triggered.connect(mw._toggle_database_panel)
    view_menu.addAction(mw.view_hide_database_panel_action)

    mw.view_menu_actions = [
        mw.view_moves_list_action,
        mw.view_metadata_action,
        mw.view_manual_analysis_action,
        mw.view_game_summary_action,
        mw.view_player_stats_action,
        mw.view_annotations_action,
        mw.view_ai_summary_action,
        mw.view_notes_action,
    ]

