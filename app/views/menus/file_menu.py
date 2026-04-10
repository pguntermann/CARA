"""File menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar


def setup_file_menu(mw, menu_bar: QMenuBar) -> None:
    file_menu = menu_bar.addMenu("File")
    mw._apply_menu_styling(file_menu)

    open_pgn_database_action = QAction("Open PGN Database", mw)
    open_pgn_database_action.setShortcut(QKeySequence("Ctrl+O"))
    open_pgn_database_action.triggered.connect(mw._open_pgn_database)
    file_menu.addAction(open_pgn_database_action)

    file_menu.addSeparator()

    mw.close_pgn_database_action = QAction("Close PGN Database", mw)
    mw.close_pgn_database_action.setShortcut(QKeySequence("Ctrl+W"))
    mw.close_pgn_database_action.triggered.connect(mw._close_pgn_database)
    file_menu.addAction(mw.close_pgn_database_action)

    mw.close_all_databases_action = QAction("Close All PGN Databases", mw)
    mw.close_all_databases_action.setShortcut(QKeySequence("Ctrl+Alt+W"))
    mw.close_all_databases_action.triggered.connect(mw._close_all_pgn_databases)
    file_menu.addAction(mw.close_all_databases_action)

    clear_clipboard_action = QAction("Clear Clipboard Database", mw)
    clear_clipboard_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
    clear_clipboard_action.triggered.connect(mw._clear_clipboard_database)
    file_menu.addAction(clear_clipboard_action)

    file_menu.addSeparator()

    mw.save_pgn_database_action = QAction("Save PGN Database", mw)
    mw.save_pgn_database_action.setShortcut(QKeySequence("Ctrl+S"))
    mw.save_pgn_database_action.triggered.connect(mw._save_pgn_database)
    mw.save_pgn_database_action.setEnabled(False)
    file_menu.addAction(mw.save_pgn_database_action)

    save_pgn_database_as_action = QAction("Save PGN Database as...", mw)
    save_pgn_database_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    save_pgn_database_as_action.setMenuRole(QAction.MenuRole.NoRole)
    save_pgn_database_as_action.triggered.connect(mw._save_pgn_database_as)
    file_menu.addAction(save_pgn_database_as_action)

    file_menu.addSeparator()

    import_online_games_action = QAction("Import Games from Online...", mw)
    import_online_games_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
    import_online_games_action.setMenuRole(QAction.MenuRole.NoRole)
    import_online_games_action.triggered.connect(mw._import_online_games)
    file_menu.addAction(import_online_games_action)

    file_menu.addSeparator()

    bulk_replace_action = QAction("Bulk Replace PGN header tags...", mw)
    bulk_replace_action.setShortcut(QKeySequence("Ctrl+Shift+R"))
    bulk_replace_action.setMenuRole(QAction.MenuRole.NoRole)
    bulk_replace_action.triggered.connect(mw._bulk_replace)
    file_menu.addAction(bulk_replace_action)

    bulk_tag_action = QAction("Bulk Add/Remove PGN header tags...", mw)
    bulk_tag_action.setShortcut(QKeySequence("Ctrl+Alt+T"))
    bulk_tag_action.setMenuRole(QAction.MenuRole.NoRole)
    bulk_tag_action.triggered.connect(mw._bulk_tag)
    file_menu.addAction(bulk_tag_action)

    bulk_clean_pgn_action = QAction("Bulk Clean PGN...", mw)
    bulk_clean_pgn_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
    bulk_clean_pgn_action.setMenuRole(QAction.MenuRole.NoRole)
    bulk_clean_pgn_action.triggered.connect(mw._bulk_clean_pgn)
    file_menu.addAction(bulk_clean_pgn_action)

    file_menu.addSeparator()

    deduplicate_games_action = QAction("Deduplicate Games in Active Database...", mw)
    deduplicate_games_action.setShortcut(QKeySequence("Ctrl+Shift+U"))
    deduplicate_games_action.setMenuRole(QAction.MenuRole.NoRole)
    deduplicate_games_action.triggered.connect(mw._deduplicate_games)
    file_menu.addAction(deduplicate_games_action)

    file_menu.addSeparator()

    search_games_action = QAction("Search Games...", mw)
    search_games_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
    search_games_action.setMenuRole(QAction.MenuRole.NoRole)
    search_games_action.triggered.connect(mw._search_games)
    file_menu.addAction(search_games_action)

    mw.close_search_results_action = QAction("Close Search Results", mw)
    mw.close_search_results_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
    mw.close_search_results_action.triggered.connect(mw._close_search_results)
    mw.close_search_results_action.setEnabled(False)
    file_menu.addAction(mw.close_search_results_action)

    file_menu.addSeparator()

    close_action = QAction("Close Application", mw)
    close_action.setShortcut("Ctrl+Q")
    close_action.triggered.connect(mw._close_application)
    file_menu.addAction(close_action)

