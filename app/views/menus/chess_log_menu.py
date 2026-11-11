"""Chess Log menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar

from app.utils.themed_icon import (
    SVG_CONTEXT_DELETE,
    SVG_MENU_SAVE,
    set_menubar_themable_action_icon,
)
from app.views.menus.chess_log_charts_menu import ChessLogChartsMenuController


def setup_chess_log_menu(mw, menu_bar: QMenuBar) -> None:
    chess_log_menu = menu_bar.addMenu("Chess Log")
    mw._apply_menu_styling(chess_log_menu)

    mw.chess_log_settings_action = QAction("Chess Log Settings…", mw)
    mw.chess_log_settings_action.triggered.connect(mw._show_chess_log_settings)
    chess_log_menu.addAction(mw.chess_log_settings_action)

    chess_log_menu.addSeparator()

    mw.clear_chess_log_action = QAction("Clear Chess Log for current game", mw)
    mw.clear_chess_log_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
    set_menubar_themable_action_icon(mw, mw.clear_chess_log_action, SVG_CONTEXT_DELETE)
    mw.clear_chess_log_action.triggered.connect(mw._clear_chess_log_for_current_game)
    chess_log_menu.addAction(mw.clear_chess_log_action)

    mw.save_chess_log_action = QAction("Save Chess Log to current game", mw)
    mw.save_chess_log_action.setShortcut(QKeySequence("Ctrl+Alt+L"))
    set_menubar_themable_action_icon(mw, mw.save_chess_log_action, SVG_MENU_SAVE)
    mw.save_chess_log_action.triggered.connect(mw._save_chess_log_for_current_game)
    chess_log_menu.addAction(mw.save_chess_log_action)

    mw.save_all_chess_logs_action = QAction("Save Chess Logs for all games", mw)
    set_menubar_themable_action_icon(mw, mw.save_all_chess_logs_action, SVG_MENU_SAVE)
    mw.save_all_chess_logs_action.triggered.connect(mw._save_chess_logs_for_all_games)
    chess_log_menu.addAction(mw.save_all_chess_logs_action)

    mw.show_all_chess_logs_action = QAction("Show Logged Moments for All Games", mw)
    mw.show_all_chess_logs_action.triggered.connect(mw._show_chess_logs_for_all_games)
    chess_log_menu.addAction(mw.show_all_chess_logs_action)

    mw.show_saved_shallow_logs_action = QAction("Show Shallow/Vague Logs", mw)
    mw.show_saved_shallow_logs_action.setToolTip(
        "Open stored Check Logs results for this database — shows saved Shallow and Vague chips."
    )
    mw.show_saved_shallow_logs_action.triggered.connect(mw._show_saved_shallow_logs)
    chess_log_menu.addAction(mw.show_saved_shallow_logs_action)

    chess_log_menu.addSeparator()

    mw.highlight_chess_log_moves_action = QAction("Highlight Logged Moments in Moves List", mw)
    mw.highlight_chess_log_moves_action.setCheckable(True)
    mw.highlight_chess_log_moves_action.setChecked(False)
    mw.highlight_chess_log_moves_action.triggered.connect(mw._on_highlight_chess_log_moves_toggled)
    chess_log_menu.addAction(mw.highlight_chess_log_moves_action)

    mw._chess_log_charts_settings_separator = chess_log_menu.addSeparator()

    _setup_chess_log_charts_submenu(mw, chess_log_menu)


def _setup_chess_log_charts_submenu(mw, chess_log_menu) -> None:
    from app.services.user_settings_service import UserSettingsService

    mw._cl_charts_menu_controller = ChessLogChartsMenuController(mw, mw._apply_menu_styling)
    mw.chess_log_charts_settings_menu = mw._cl_charts_menu_controller.attach_to_parent_menu(chess_log_menu)
    UserSettingsService.get_instance().get_model().chess_log_charts_changed.connect(
        mw._cl_charts_menu_controller.sync_from_settings
    )
