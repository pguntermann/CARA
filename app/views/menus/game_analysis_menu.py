"""Game Analysis menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar, QMenu

from app.services.game_auto_tagging_service import AUTO_TAGS


def setup_game_analysis_menu(mw, menu_bar: QMenuBar) -> None:
    game_analysis_menu = menu_bar.addMenu("Game Analysis")
    mw._apply_menu_styling(game_analysis_menu)

    mw.start_game_analysis_action = QAction("Start Game Analysis", mw)
    mw.start_game_analysis_action.setShortcut(QKeySequence("Ctrl+G"))
    mw.start_game_analysis_action.triggered.connect(mw._start_game_analysis)
    game_analysis_menu.addAction(mw.start_game_analysis_action)

    mw.cancel_game_analysis_action = QAction("Cancel Game Analysis", mw)
    mw.cancel_game_analysis_action.setShortcut(QKeySequence("Escape"))
    mw.cancel_game_analysis_action.triggered.connect(mw._cancel_game_analysis)
    mw.cancel_game_analysis_action.setEnabled(False)
    game_analysis_menu.addAction(mw.cancel_game_analysis_action)

    game_analysis_menu.addSeparator()

    mw.bulk_analyze_database_action = QAction("Bulk Analyze Database...", mw)
    mw.bulk_analyze_database_action.setMenuRole(QAction.MenuRole.NoRole)
    mw.bulk_analyze_database_action.triggered.connect(mw._on_bulk_analyze_database)
    game_analysis_menu.addAction(mw.bulk_analyze_database_action)

    game_analysis_menu.addSeparator()

    mw.configure_classification_action = QAction("Configure Classification Settings...", mw)
    mw.configure_classification_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
    mw.configure_classification_action.setMenuRole(QAction.MenuRole.NoRole)
    mw.configure_classification_action.triggered.connect(mw._open_classification_settings)
    game_analysis_menu.addAction(mw.configure_classification_action)

    game_analysis_menu.addSeparator()

    mw.normalized_graph_action = QAction("Normalized Evaluation Graph", mw)
    mw.normalized_graph_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
    mw.normalized_graph_action.setCheckable(True)
    mw.normalized_graph_action.setChecked(False)
    mw.normalized_graph_action.triggered.connect(mw._on_normalized_graph_toggled)
    game_analysis_menu.addAction(mw.normalized_graph_action)

    game_analysis_menu.addSeparator()

    mw.brilliant_move_detection_action = QAction("Brilliant Move Detection", mw)
    mw.brilliant_move_detection_action.setCheckable(True)
    mw.brilliant_move_detection_action.triggered.connect(mw._on_brilliant_move_detection_toggled)
    game_analysis_menu.addAction(mw.brilliant_move_detection_action)

    mw.auto_game_tagging_action = QAction("Auto Tag Games", mw)
    mw.auto_game_tagging_action.setCheckable(True)
    mw.auto_game_tagging_action.triggered.connect(mw._on_auto_game_tagging_toggled)
    game_analysis_menu.addAction(mw.auto_game_tagging_action)

    # Select which auto-tags/rules are applied
    mw.select_auto_tags_menu = QMenu("Select Tags for Auto-Tagging", game_analysis_menu)
    mw._apply_menu_styling(mw.select_auto_tags_menu)
    mw.auto_game_tagging_tag_actions = {}
    for tag in AUTO_TAGS:
        act = QAction(tag, mw)
        act.setCheckable(True)
        act.setChecked(True)
        act.triggered.connect(lambda checked=False, t=tag: mw._on_auto_game_tagging_tag_toggled(t, checked))
        mw.select_auto_tags_menu.addAction(act)
        mw.auto_game_tagging_tag_actions[tag] = act
    mw.select_auto_tags_menu.setEnabled(True)
    game_analysis_menu.addMenu(mw.select_auto_tags_menu)

    mw.return_to_first_move_action = QAction("Return to PLY 0 after analysis completes", mw)
    mw.return_to_first_move_action.setCheckable(True)
    mw.return_to_first_move_action.setChecked(False)
    mw.return_to_first_move_action.triggered.connect(mw._on_return_to_first_move_toggled)
    game_analysis_menu.addAction(mw.return_to_first_move_action)

    mw.switch_to_moves_list_action = QAction("Switch to Moves List at the start of Analysis", mw)
    mw.switch_to_moves_list_action.setCheckable(True)
    mw.switch_to_moves_list_action.setChecked(True)
    mw.switch_to_moves_list_action.triggered.connect(mw._on_switch_to_moves_list_toggled)
    game_analysis_menu.addAction(mw.switch_to_moves_list_action)

    mw.switch_to_summary_action = QAction("Switch to Game Summary after Analysis", mw)
    mw.switch_to_summary_action.setCheckable(True)
    mw.switch_to_summary_action.setChecked(False)
    mw.switch_to_summary_action.triggered.connect(mw._on_switch_to_summary_toggled)
    game_analysis_menu.addAction(mw.switch_to_summary_action)

    game_analysis_menu.addSeparator()

    mw.store_analysis_results_action = QAction("Store Analysis results in PGN Tag", mw)
    mw.store_analysis_results_action.setCheckable(True)
    mw.store_analysis_results_action.triggered.connect(mw._on_store_analysis_results_toggled)
    game_analysis_menu.addAction(mw.store_analysis_results_action)

