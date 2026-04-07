"""Help menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenuBar


def setup_help_menu(mw, menu_bar: QMenuBar) -> None:
    help_menu = menu_bar.addMenu("Help")
    mw._apply_menu_styling(help_menu)

    open_manual_action = QAction("Open Manual", mw)
    open_manual_action.triggered.connect(mw._open_manual)
    help_menu.addAction(open_manual_action)

    watch_video_tutorials_action = QAction("Watch Video Tutorials", mw)
    watch_video_tutorials_action.triggered.connect(mw._open_video_tutorials)
    help_menu.addAction(watch_video_tutorials_action)

    visit_github_action = QAction("Visit GitHub Repository", mw)
    visit_github_action.triggered.connect(mw._open_github_repository)
    help_menu.addAction(visit_github_action)

    help_menu.addSeparator()

    release_notes_action = QAction("View Release Notes", mw)
    release_notes_action.triggered.connect(mw._show_release_notes_dialog)
    help_menu.addAction(release_notes_action)

    license_action = QAction("View License", mw)
    license_action.triggered.connect(mw._show_license_dialog)
    help_menu.addAction(license_action)

    third_party_licenses_action = QAction("View Third Party Licenses", mw)
    third_party_licenses_action.triggered.connect(mw._show_third_party_licenses_dialog)
    help_menu.addAction(third_party_licenses_action)

    help_menu.addSeparator()

    open_user_data_dir_action = QAction("Open user data directory", mw)
    open_user_data_dir_action.triggered.connect(mw._open_user_data_directory)
    help_menu.addAction(open_user_data_dir_action)

    help_menu.addSeparator()

    check_updates_action = QAction("Check for Updates...", mw)
    check_updates_action.triggered.connect(mw._check_for_updates)
    help_menu.addAction(check_updates_action)

    help_menu.addSeparator()

    about_action = QAction("About...", mw)
    about_action.setMenuRole(QAction.MenuRole.NoRole)
    about_action.triggered.connect(mw._show_about_dialog)
    help_menu.addAction(about_action)

