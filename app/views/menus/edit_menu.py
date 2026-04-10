"""Edit menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.utils.themed_icon import (
    set_menubar_themable_action_icon,
    SVG_MENU_COPY,
    SVG_MENU_CUT,
    SVG_MENU_PASTE_CLIPBOARD,
    SVG_MENU_PASTE_ACTIVE_DB,
)


def setup_edit_menu(mw, menu_bar: QMenuBar) -> None:
    edit_menu = menu_bar.addMenu("Edit")
    mw._apply_menu_styling(edit_menu)

    mw.copy_fen_action = QAction("Copy FEN", mw)
    mw.copy_fen_action.setShortcut(QKeySequence("Shift+F"))
    set_menubar_themable_action_icon(mw, mw.copy_fen_action, SVG_MENU_COPY)
    mw.copy_fen_action.triggered.connect(mw._copy_fen_to_clipboard)
    edit_menu.addAction(mw.copy_fen_action)

    mw.copy_pgn_action = QAction("Copy PGN", mw)
    mw.copy_pgn_action.setShortcut(QKeySequence("Ctrl+P"))
    set_menubar_themable_action_icon(mw, mw.copy_pgn_action, SVG_MENU_COPY)
    mw.copy_pgn_action.triggered.connect(mw._copy_pgn_to_clipboard)
    edit_menu.addAction(mw.copy_pgn_action)

    edit_menu.addSeparator()

    mw.copy_selected_games_action = QAction("Copy selected Games", mw)
    mw.copy_selected_games_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
    set_menubar_themable_action_icon(mw, mw.copy_selected_games_action, SVG_MENU_COPY)
    mw.copy_selected_games_action.triggered.connect(mw._copy_selected_games)
    edit_menu.addAction(mw.copy_selected_games_action)

    mw.cut_selected_games_action = QAction("Cut selected Games", mw)
    mw.cut_selected_games_action.setShortcut(QKeySequence("Ctrl+Shift+X"))
    set_menubar_themable_action_icon(mw, mw.cut_selected_games_action, SVG_MENU_CUT)
    mw.cut_selected_games_action.triggered.connect(mw._cut_selected_games)
    edit_menu.addAction(mw.cut_selected_games_action)

    edit_menu.addSeparator()

    paste_fen_action = QAction("Paste FEN to Board", mw)
    paste_fen_action.setShortcut(QKeySequence("Ctrl+F"))
    paste_fen_action.triggered.connect(mw._paste_fen_to_board)
    edit_menu.addAction(paste_fen_action)

    edit_menu.addSeparator()

    mw.paste_pgn_clipboard_db_action = QAction("Paste PGN to Clipboard DB", mw)
    mw.paste_pgn_clipboard_db_action.setShortcut(QKeySequence("Ctrl+V"))
    set_menubar_themable_action_icon(mw, mw.paste_pgn_clipboard_db_action, SVG_MENU_PASTE_CLIPBOARD)
    mw.paste_pgn_clipboard_db_action.triggered.connect(mw._paste_pgn_to_clipboard_db)
    edit_menu.addAction(mw.paste_pgn_clipboard_db_action)

    mw.paste_pgn_active_db_action = QAction("Paste PGN to active DB", mw)
    mw.paste_pgn_active_db_action.setShortcut(QKeySequence("Ctrl+Alt+V"))
    set_menubar_themable_action_icon(mw, mw.paste_pgn_active_db_action, SVG_MENU_PASTE_ACTIVE_DB)
    mw.paste_pgn_active_db_action.triggered.connect(mw._paste_pgn_to_active_db)
    edit_menu.addAction(mw.paste_pgn_active_db_action)

