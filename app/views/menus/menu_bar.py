"""Top-level menu bar construction for MainWindow."""

from __future__ import annotations

from PyQt6.QtWidgets import QMenuBar

from app.views.menus.ai_summary_menu import setup_ai_summary_menu
from app.views.menus.annotations_menu import setup_annotations_menu
from app.views.menus.board_menu import setup_board_menu
from app.views.menus.debug_menu import setup_debug_menu
from app.views.menus.edit_menu import setup_edit_menu
from app.views.menus.engines_menu import setup_engines_menu
from app.views.menus.file_menu import setup_file_menu
from app.views.menus.game_analysis_menu import setup_game_analysis_menu
from app.views.menus.help_menu import setup_help_menu
from app.views.menus.manual_analysis_menu import setup_manual_analysis_menu
from app.views.menus.moves_list_menu import setup_moves_list_menu
from app.views.menus.notes_menu import setup_notes_menu
from app.views.menus.pgn_menu import setup_pgn_menu
from app.views.menus.player_stats_menu import setup_player_stats_menu
from app.views.menus.view_menu import setup_view_menu


def setup_menu_bar(mw, menu_bar: QMenuBar) -> None:
    """Build the entire menu bar for the given MainWindow instance."""
    setup_file_menu(mw, menu_bar)
    setup_edit_menu(mw, menu_bar)
    setup_board_menu(mw, menu_bar)
    setup_pgn_menu(mw, menu_bar)
    setup_moves_list_menu(mw, menu_bar)
    setup_game_analysis_menu(mw, menu_bar)
    setup_manual_analysis_menu(mw, menu_bar)
    setup_player_stats_menu(mw, menu_bar)
    setup_annotations_menu(mw, menu_bar)
    setup_engines_menu(mw, menu_bar)
    setup_ai_summary_menu(mw, menu_bar)
    setup_notes_menu(mw, menu_bar)
    setup_view_menu(mw, menu_bar)
    setup_help_menu(mw, menu_bar)
    setup_debug_menu(mw, menu_bar)

