"""Annotations menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.utils.themed_icon import (
    SVG_CONTEXT_DELETE,
    SVG_MENU_GEAR,
    SVG_MENU_SAVE,
    set_menubar_themable_action_icon,
)


def setup_annotations_menu(mw, menu_bar: QMenuBar) -> None:
    annotations_menu = menu_bar.addMenu("Annotations")
    mw._apply_menu_styling(annotations_menu)

    clear_all_annotations_action = QAction("Clear all Annotations for current game", mw)
    clear_all_annotations_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
    set_menubar_themable_action_icon(mw, clear_all_annotations_action, SVG_CONTEXT_DELETE)
    clear_all_annotations_action.triggered.connect(mw._clear_all_annotations_for_game)
    annotations_menu.addAction(clear_all_annotations_action)

    clear_move_annotations_action = QAction("Clear all Annotations for current move", mw)
    clear_move_annotations_action.setShortcut(QKeySequence("Ctrl+Alt+D"))
    set_menubar_themable_action_icon(mw, clear_move_annotations_action, SVG_CONTEXT_DELETE)
    clear_move_annotations_action.triggered.connect(mw._clear_annotations_for_current_move)
    annotations_menu.addAction(clear_move_annotations_action)

    save_annotations_action = QAction("Save Annotations to current game", mw)
    save_annotations_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
    set_menubar_themable_action_icon(mw, save_annotations_action, SVG_MENU_SAVE)
    save_annotations_action.triggered.connect(mw._save_annotations_to_current_game)
    annotations_menu.addAction(save_annotations_action)

    annotations_menu.addSeparator()

    mw.highlight_annotated_moves_action = QAction("Highlight annotated moves in moves list", mw)
    mw.highlight_annotated_moves_action.setCheckable(True)
    mw.highlight_annotated_moves_action.setChecked(False)
    mw.highlight_annotated_moves_action.triggered.connect(mw._on_highlight_annotated_moves_toggled)
    annotations_menu.addAction(mw.highlight_annotated_moves_action)

    annotations_menu.addSeparator()

    setup_preferences_action = QAction("Setup Preferences...", mw)
    setup_preferences_action.setMenuRole(QAction.MenuRole.NoRole)
    set_menubar_themable_action_icon(mw, setup_preferences_action, SVG_MENU_GEAR)
    setup_preferences_action.triggered.connect(mw._show_annotation_preferences)
    annotations_menu.addAction(setup_preferences_action)

