"""PGN menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.utils.themed_icon import set_menubar_themable_action_icon, SVG_SIMPLE_X


def setup_pgn_menu(mw, menu_bar: QMenuBar) -> None:
    pgn_menu = menu_bar.addMenu("PGN")
    mw._apply_menu_styling(pgn_menu)

    mw.show_metadata_action = QAction("Show PGN header tags", mw)
    mw.show_metadata_action.setShortcut(QKeySequence("Ctrl+M"))
    mw.show_metadata_action.setCheckable(True)
    mw.show_metadata_action.setChecked(True)
    mw.show_metadata_action.triggered.connect(mw._on_show_metadata_toggled)
    pgn_menu.addAction(mw.show_metadata_action)

    mw.show_comments_action = QAction("Show Comments", mw)
    mw.show_comments_action.setShortcut(QKeySequence("Ctrl+Shift+M"))
    mw.show_comments_action.setCheckable(True)
    mw.show_comments_action.setChecked(True)
    mw.show_comments_action.triggered.connect(mw._on_show_comments_toggled)
    pgn_menu.addAction(mw.show_comments_action)

    mw.show_variations_action = QAction("Show Variations", mw)
    mw.show_variations_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
    mw.show_variations_action.setCheckable(True)
    mw.show_variations_action.setChecked(True)
    mw.show_variations_action.triggered.connect(mw._on_show_variations_toggled)
    pgn_menu.addAction(mw.show_variations_action)

    mw.show_non_standard_tags_action = QAction("Show Non-Standard Tags", mw)
    mw.show_non_standard_tags_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
    mw.show_non_standard_tags_action.setCheckable(True)
    mw.show_non_standard_tags_action.setChecked(False)
    mw.show_non_standard_tags_action.triggered.connect(mw._on_show_non_standard_tags_toggled)
    pgn_menu.addAction(mw.show_non_standard_tags_action)

    mw.show_annotations_action = QAction("Show Annotations", mw)
    mw.show_annotations_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
    mw.show_annotations_action.setCheckable(True)
    mw.show_annotations_action.setChecked(True)
    mw.show_annotations_action.triggered.connect(mw._on_show_annotations_toggled)
    pgn_menu.addAction(mw.show_annotations_action)

    mw.show_results_action = QAction("Show Results", mw)
    mw.show_results_action.setShortcut(QKeySequence("Ctrl+R"))
    mw.show_results_action.setCheckable(True)
    mw.show_results_action.setChecked(True)
    mw.show_results_action.triggered.connect(mw._on_show_results_toggled)
    pgn_menu.addAction(mw.show_results_action)

    pgn_menu.addSeparator()

    mw.nag_display_menu = pgn_menu.addMenu("Display NAG move assessments as...")
    mw._apply_menu_styling(mw.nag_display_menu)

    mw.nag_display_symbols_action = QAction("Symbols (??, ?, ?! ..)", mw)
    mw.nag_display_symbols_action.setCheckable(True)
    mw.nag_display_symbols_action.setChecked(True)
    mw.nag_display_symbols_action.triggered.connect(lambda: mw._on_nag_display_mode_selected(True))
    mw.nag_display_menu.addAction(mw.nag_display_symbols_action)

    mw.nag_display_text_action = QAction("Text", mw)
    mw.nag_display_text_action.setCheckable(True)
    mw.nag_display_text_action.setChecked(False)
    mw.nag_display_text_action.triggered.connect(lambda: mw._on_nag_display_mode_selected(False))
    mw.nag_display_menu.addAction(mw.nag_display_text_action)

    pgn_menu.addSeparator()

    mw.remove_comments_action = QAction("Remove Comments", mw)
    set_menubar_themable_action_icon(mw, mw.remove_comments_action, SVG_SIMPLE_X)
    mw.remove_comments_action.triggered.connect(mw._on_remove_comments_clicked)
    pgn_menu.addAction(mw.remove_comments_action)

    mw.remove_variations_action = QAction("Remove Variations", mw)
    set_menubar_themable_action_icon(mw, mw.remove_variations_action, SVG_SIMPLE_X)
    mw.remove_variations_action.triggered.connect(mw._on_remove_variations_clicked)
    pgn_menu.addAction(mw.remove_variations_action)

    mw.remove_non_standard_tags_action = QAction("Remove Non-Standard Tags", mw)
    set_menubar_themable_action_icon(mw, mw.remove_non_standard_tags_action, SVG_SIMPLE_X)
    mw.remove_non_standard_tags_action.triggered.connect(mw._on_remove_non_standard_tags_clicked)
    pgn_menu.addAction(mw.remove_non_standard_tags_action)

    mw.remove_annotations_action = QAction("Remove Annotations", mw)
    set_menubar_themable_action_icon(mw, mw.remove_annotations_action, SVG_SIMPLE_X)
    mw.remove_annotations_action.triggered.connect(mw._on_remove_annotations_clicked)
    pgn_menu.addAction(mw.remove_annotations_action)

