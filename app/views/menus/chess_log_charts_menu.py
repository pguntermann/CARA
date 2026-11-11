"""Chess Log Charts time-series settings menu controller (menubar).

Creates and syncs the 'Time series settings' submenu for Chess Log Charts.
Thin subclass of RadioMenuController — supplies _read_settings() and _apply().
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from PyQt6.QtWidgets import QMenu

from app.services.chess_log_charts_user import normalize_chess_log_charts_settings
from app.services.user_settings_service import UserSettingsService
from app.views.menus._radio_menu_controller import RadioMenuController


class ChessLogChartsMenuController(RadioMenuController):
    """Creates and syncs the nested 'Time series settings' menu for Chess Log Charts."""

    def __init__(self, action_parent, style_submenu: Callable[[QMenu], None]) -> None:
        super().__init__(action_parent, style_submenu)

    def _read_settings(self) -> Dict[str, Any]:
        return normalize_chess_log_charts_settings(
            UserSettingsService.get_instance().get_chess_log().get("charts", {})
        )

    def _apply(self, key: str, value: Any) -> None:
        UserSettingsService.get_instance().update_chess_log_charts_settings({key: value})
