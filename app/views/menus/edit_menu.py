"""Edit menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar


def setup_edit_menu(mw, menu_bar: QMenuBar) -> None:
    edit_menu = menu_bar.addMenu("Edit")
    mw._apply_menu_styling(edit_menu)

    copy_fen_action = QAction("Copy FEN", mw)
    copy_fen_action.setShortcut(QKeySequence("Shift+F"))
    copy_fen_action.triggered.connect(mw._copy_fen_to_clipboard)
    edit_menu.addAction(copy_fen_action)

    copy_pgn_action = QAction("Copy PGN", mw)
    copy_pgn_action.setShortcut(QKeySequence("Ctrl+P"))
    copy_pgn_action.triggered.connect(mw._copy_pgn_to_clipboard)
    edit_menu.addAction(copy_pgn_action)

    edit_menu.addSeparator()

    copy_selected_games_action = QAction("Copy selected Games", mw)
    copy_selected_games_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
    copy_selected_games_action.triggered.connect(mw._copy_selected_games)
    edit_menu.addAction(copy_selected_games_action)

    cut_selected_games_action = QAction("Cut selected Games", mw)
    cut_selected_games_action.setShortcut(QKeySequence("Ctrl+Shift+X"))
    cut_selected_games_action.triggered.connect(mw._cut_selected_games)
    edit_menu.addAction(cut_selected_games_action)

    edit_menu.addSeparator()

    paste_fen_action = QAction("Paste FEN to Board", mw)
    paste_fen_action.setShortcut(QKeySequence("Ctrl+F"))
    paste_fen_action.triggered.connect(mw._paste_fen_to_board)
    edit_menu.addAction(paste_fen_action)

    edit_menu.addSeparator()

    paste_pgn_clipboard_action = QAction("Paste PGN to Clipboard DB", mw)
    paste_pgn_clipboard_action.setShortcut(QKeySequence("Ctrl+V"))
    paste_pgn_clipboard_action.triggered.connect(mw._paste_pgn_to_clipboard_db)
    edit_menu.addAction(paste_pgn_clipboard_action)

    paste_pgn_active_action = QAction("Paste PGN to active DB", mw)
    paste_pgn_active_action.setShortcut(QKeySequence("Ctrl+Alt+V"))
    paste_pgn_active_action.triggered.connect(mw._paste_pgn_to_active_db)
    edit_menu.addAction(paste_pgn_active_action)

