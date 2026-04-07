"""Notes menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar


def setup_notes_menu(mw, menu_bar: QMenuBar) -> None:
    notes_menu = menu_bar.addMenu("Notes")
    mw._apply_menu_styling(notes_menu)

    clear_notes_action = QAction("Clear Notes for current game", mw)
    clear_notes_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
    clear_notes_action.triggered.connect(mw._clear_notes_for_current_game)
    notes_menu.addAction(clear_notes_action)

    save_notes_action = QAction("Save Notes to current game", mw)
    save_notes_action.setShortcut(QKeySequence("Ctrl+Alt+N"))
    save_notes_action.triggered.connect(mw._save_notes_to_current_game)
    notes_menu.addAction(save_notes_action)

