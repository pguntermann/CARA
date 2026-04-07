"""Moves List menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenuBar


def setup_moves_list_menu(mw, menu_bar: QMenuBar) -> None:
    moves_list_menu = menu_bar.addMenu("Moves List")
    mw._apply_menu_styling(moves_list_menu)

    profile_model = mw.controller.get_column_profile_controller().get_profile_model()
    profile_controller = mw.controller.get_column_profile_controller()

    mw.moves_list_menu = moves_list_menu
    mw.profile_model = profile_model
    mw.profile_controller = profile_controller

    mw.profile_actions = {}
    mw.column_actions = {}

    profile_model.active_profile_changed.connect(mw._on_active_profile_changed)
    profile_model.profile_added.connect(mw._on_profile_added)
    profile_model.profile_removed.connect(mw._on_profile_removed)
    profile_model.column_visibility_changed.connect(mw._on_column_visibility_changed)

    mw._update_moves_list_menu()


def rebuild_moves_list_menu(mw) -> None:
    """Rebuild the Moves List menu with current profiles and columns."""
    menu = mw.moves_list_menu
    menu.clear()

    # Clear action dictionaries
    mw.profile_actions.clear()
    mw.column_actions.clear()

    profile_names = mw.profile_model.get_profile_names()
    active_profile_name = mw.profile_model.get_active_profile_name()

    # Add profile toggle actions (at top)
    for index, profile_name in enumerate(profile_names):
        profile_action = QAction(profile_name, mw)
        profile_action.setCheckable(True)
        profile_action.setChecked(profile_name == active_profile_name)
        profile_action.triggered.connect(
            lambda checked, name=profile_name: mw._on_profile_selected(name)
        )

        if index < 9:
            shortcut = QKeySequence(str(index + 1))
            profile_action.setShortcut(shortcut)

        menu.addAction(profile_action)
        mw.profile_actions[profile_name] = profile_action

    if profile_names:
        menu.addSeparator()

    from app.models.column_profile_model import DEFAULT_PROFILE_NAME

    if active_profile_name != DEFAULT_PROFILE_NAME:
        save_profile_action = QAction("Save Profile", mw)
        save_profile_action.setMenuRole(QAction.MenuRole.NoRole)
        save_profile_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        save_profile_action.triggered.connect(mw._save_current_profile)
        menu.addAction(save_profile_action)

    save_profile_as_action = QAction("Save Profile as...", mw)
    save_profile_as_action.setMenuRole(QAction.MenuRole.NoRole)
    save_profile_as_action.setShortcut(QKeySequence("Ctrl+Alt+P"))
    save_profile_as_action.triggered.connect(mw._save_profile_as)
    menu.addAction(save_profile_as_action)

    if active_profile_name != DEFAULT_PROFILE_NAME:
        remove_profile_action = QAction("Remove Profile", mw)
        remove_profile_action.setMenuRole(QAction.MenuRole.NoRole)
        remove_profile_action.setShortcut(QKeySequence("Ctrl+Shift+Delete"))
        remove_profile_action.triggered.connect(mw._remove_profile)
        menu.addAction(remove_profile_action)

    menu.addSeparator()

    setup_profile_action = QAction("Setup Profile...", mw)
    setup_profile_action.setMenuRole(QAction.MenuRole.NoRole)
    setup_profile_action.triggered.connect(mw._on_setup_profile)
    menu.addAction(setup_profile_action)

    menu.addSeparator()

    column_names = mw.profile_model.get_column_names()
    column_visibility = mw.profile_model.get_current_column_visibility()

    from app.models.column_profile_model import (
        COL_NUM,
        COL_WHITE,
        COL_BLACK,
        COL_COMMENT,
        COL_EVAL_WHITE,
        COL_EVAL_BLACK,
        COL_CPL_WHITE,
        COL_CPL_BLACK,
        COL_CPL_WHITE_2,
        COL_CPL_WHITE_3,
        COL_CPL_BLACK_2,
        COL_CPL_BLACK_3,
        COL_BEST_WHITE,
        COL_BEST_BLACK,
        COL_BEST_WHITE_2,
        COL_BEST_WHITE_3,
        COL_BEST_BLACK_2,
        COL_BEST_BLACK_3,
        COL_WHITE_IS_TOP3,
        COL_BLACK_IS_TOP3,
        COL_ASSESS_WHITE,
        COL_ASSESS_BLACK,
        COL_WHITE_DEPTH,
        COL_BLACK_DEPTH,
        COL_WHITE_SELDEPTH,
        COL_BLACK_SELDEPTH,
        COL_WHITE_CAPTURE,
        COL_BLACK_CAPTURE,
        COL_WHITE_MATERIAL,
        COL_BLACK_MATERIAL,
        COL_ECO,
        COL_OPENING,
        COL_FEN_WHITE,
        COL_FEN_BLACK,
    )

    column_categories = {
        "Basic Columns": [COL_NUM, COL_WHITE, COL_BLACK, COL_COMMENT],
        "Evaluation Columns": [
            COL_EVAL_WHITE,
            COL_EVAL_BLACK,
            COL_CPL_WHITE,
            COL_CPL_BLACK,
            COL_CPL_WHITE_2,
            COL_CPL_WHITE_3,
            COL_CPL_BLACK_2,
            COL_CPL_BLACK_3,
        ],
        "Best Moves Columns": [
            COL_BEST_WHITE,
            COL_BEST_BLACK,
            COL_BEST_WHITE_2,
            COL_BEST_WHITE_3,
            COL_BEST_BLACK_2,
            COL_BEST_BLACK_3,
            COL_WHITE_IS_TOP3,
            COL_BLACK_IS_TOP3,
        ],
        "Analysis Columns": [
            COL_ASSESS_WHITE,
            COL_ASSESS_BLACK,
            COL_WHITE_DEPTH,
            COL_BLACK_DEPTH,
            COL_WHITE_SELDEPTH,
            COL_BLACK_SELDEPTH,
        ],
        "Material Columns": [
            COL_WHITE_CAPTURE,
            COL_BLACK_CAPTURE,
            COL_WHITE_MATERIAL,
            COL_BLACK_MATERIAL,
        ],
        "Position Columns": [COL_ECO, COL_OPENING, COL_FEN_WHITE, COL_FEN_BLACK],
    }

    categorized_columns: set[str] = set()
    for category_name, category_columns in column_categories.items():
        category_menu = menu.addMenu(category_name)
        mw._apply_menu_styling(category_menu)

        for column_name in category_columns:
            if column_name in column_names:
                categorized_columns.add(column_name)
                display_name = mw.profile_model.get_column_display_name(column_name)
                visible = column_visibility.get(column_name, True)

                column_action = QAction(display_name, mw)
                column_action.setCheckable(True)
                column_action.setChecked(visible)
                column_action.triggered.connect(
                    lambda checked, name=column_name: mw._on_column_toggled(name)
                )
                category_menu.addAction(column_action)
                mw.column_actions[column_name] = column_action

    uncategorized_columns = [col for col in column_names if col not in categorized_columns]
    if uncategorized_columns:
        other_menu = menu.addMenu("Other")
        mw._apply_menu_styling(other_menu)
        for column_name in uncategorized_columns:
            display_name = mw.profile_model.get_column_display_name(column_name)
            visible = column_visibility.get(column_name, True)

            column_action = QAction(display_name, mw)
            column_action.setCheckable(True)
            column_action.setChecked(visible)
            column_action.triggered.connect(
                lambda checked, name=column_name: mw._on_column_toggled(name)
            )
            other_menu.addAction(column_action)
            mw.column_actions[column_name] = column_action

    menu.addSeparator()

