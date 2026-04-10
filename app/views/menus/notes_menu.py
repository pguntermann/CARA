"""Notes menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.utils.themed_icon import (
    SVG_CONTEXT_DELETE,
    SVG_MENU_SAVE,
    set_menubar_themable_action_icon,
)


def setup_notes_menu(mw, menu_bar: QMenuBar) -> None:
    notes_menu = menu_bar.addMenu("Notes")
    mw._apply_menu_styling(notes_menu)

    mw.clear_notes_action = QAction("Clear Notes for current game", mw)
    mw.clear_notes_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
    set_menubar_themable_action_icon(mw, mw.clear_notes_action, SVG_CONTEXT_DELETE)
    mw.clear_notes_action.triggered.connect(mw._clear_notes_for_current_game)
    notes_menu.addAction(mw.clear_notes_action)

    mw.save_notes_action = QAction("Save Notes to current game", mw)
    mw.save_notes_action.setShortcut(QKeySequence("Ctrl+Alt+N"))
    set_menubar_themable_action_icon(mw, mw.save_notes_action, SVG_MENU_SAVE)
    mw.save_notes_action.triggered.connect(mw._save_notes_to_current_game)
    notes_menu.addAction(mw.save_notes_action)

