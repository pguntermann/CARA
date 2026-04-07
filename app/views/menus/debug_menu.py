"""Debug menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenuBar


def setup_debug_menu(mw, menu_bar: QMenuBar) -> None:
    debug_config = mw.config.get("debug", {})
    show_debug_menu = debug_config.get("show_debug_menu", False)
    if not show_debug_menu:
        return

    debug_menu = menu_bar.addMenu("Debug")
    mw._apply_menu_styling(debug_menu)

    debug_copy_pgn_html_action = QAction("Copy PGN HTML", mw)
    debug_copy_pgn_html_action.triggered.connect(mw._debug_copy_pgn_html)
    debug_menu.addAction(debug_copy_pgn_html_action)

    debug_copy_deserialize_analysis_action = QAction("Copy Deserialize Analysis Tag", mw)
    debug_copy_deserialize_analysis_action.triggered.connect(mw._debug_copy_deserialize_analysis_tag)
    debug_menu.addAction(debug_copy_deserialize_analysis_action)

    debug_copy_deserialize_annotation_action = QAction("Copy Deserialize Annotation Tag", mw)
    debug_copy_deserialize_annotation_action.triggered.connect(mw._debug_copy_deserialize_annotation_tag)
    debug_menu.addAction(debug_copy_deserialize_annotation_action)

    debug_copy_highlights_html_action = QAction("Copy Game Highlights HTML", mw)
    debug_copy_highlights_html_action.triggered.connect(mw._debug_copy_game_highlights_html)
    debug_menu.addAction(debug_copy_highlights_html_action)

    debug_copy_highlights_json_action = QAction("Copy Game Highlights JSON", mw)
    debug_copy_highlights_json_action.triggered.connect(mw._debug_copy_game_highlights_json)
    debug_menu.addAction(debug_copy_highlights_json_action)

    debug_menu.addSeparator()

    debug_create_highlight_test_data_action = QAction("Create Highlight Rule Test Data", mw)
    debug_create_highlight_test_data_action.triggered.connect(mw._debug_create_highlight_rule_test_data)
    debug_menu.addAction(debug_create_highlight_test_data_action)

    debug_menu.addSeparator()

    mw.debug_uci_lifecycle_action = QAction("Debug UCI Lifecycle", mw)
    mw.debug_uci_lifecycle_action.setCheckable(True)
    mw.debug_uci_lifecycle_action.setChecked(mw._uci_debug_lifecycle)
    mw.debug_uci_lifecycle_action.triggered.connect(mw._toggle_uci_debug_lifecycle)
    debug_menu.addAction(mw.debug_uci_lifecycle_action)

    mw.debug_uci_outbound_action = QAction("Debug UCI Outbound", mw)
    mw.debug_uci_outbound_action.setCheckable(True)
    mw.debug_uci_outbound_action.setChecked(mw._uci_debug_outbound)
    mw.debug_uci_outbound_action.triggered.connect(mw._toggle_uci_debug_outbound)
    debug_menu.addAction(mw.debug_uci_outbound_action)

    mw.debug_uci_inbound_action = QAction("Debug UCI Inbound", mw)
    mw.debug_uci_inbound_action.setCheckable(True)
    mw.debug_uci_inbound_action.setChecked(mw._uci_debug_inbound)
    mw.debug_uci_inbound_action.triggered.connect(mw._toggle_uci_debug_inbound)
    debug_menu.addAction(mw.debug_uci_inbound_action)

    debug_menu.addSeparator()

    mw.debug_ai_outbound_action = QAction("Debug AI Outbound", mw)
    mw.debug_ai_outbound_action.setCheckable(True)
    mw.debug_ai_outbound_action.setChecked(mw._ai_debug_outbound)
    mw.debug_ai_outbound_action.triggered.connect(mw._toggle_ai_debug_outbound)
    debug_menu.addAction(mw.debug_ai_outbound_action)

    mw.debug_ai_inbound_action = QAction("Debug AI Inbound", mw)
    mw.debug_ai_inbound_action.setCheckable(True)
    mw.debug_ai_inbound_action.setChecked(mw._ai_debug_inbound)
    mw.debug_ai_inbound_action.triggered.connect(mw._toggle_ai_debug_inbound)
    debug_menu.addAction(mw.debug_ai_inbound_action)

    debug_menu.addSeparator()

    mw.debug_toggle_game_analysis_action = QAction("Toggle Game Analysis State", mw)
    mw.debug_toggle_game_analysis_action.setCheckable(True)
    game_model = mw.controller.get_game_controller().get_game_model()
    mw.debug_toggle_game_analysis_action.setChecked(game_model.is_game_analyzed)
    mw.debug_toggle_game_analysis_action.triggered.connect(mw._toggle_game_analysis_state)
    debug_menu.addAction(mw.debug_toggle_game_analysis_action)

    game_model.is_game_analyzed_changed.connect(mw._on_game_analysis_state_changed)

