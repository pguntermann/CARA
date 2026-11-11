"""Player Stats time-series settings menus (menubar + chart context menu).

Two separate :class:`PlayerStatsTimeSeriesMenuController` instances are required if both
UIs are used: the same :class:`QAction` cannot appear in the menu bar and a popup at once.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from PyQt6.QtWidgets import QMenu

from app.services.user_settings_service import UserSettingsService
from app.views.menus._radio_menu_controller import RadioMenuController

PLAYER_STATS_TIME_SERIES_CONTEXT_SECTIONS: frozenset[str] = frozenset(
    {"Accuracy progression", "Move quality progression", "ACPL progression by phase"}
)


class PlayerStatsTimeSeriesMenuController(RadioMenuController):
    """Creates and syncs the nested "Time series settings" menu for one host (menubar or context)."""

    def __init__(self, action_parent, style_submenu: Callable[[QMenu], None]) -> None:
        super().__init__(action_parent, style_submenu)

    def append_to_context_menu(self, context_menu: QMenu) -> None:
        """Add a fresh "Time series settings" subtree (new QMenus; reuse cached QActions)."""
        ts_menu = context_menu.addMenu("Time series settings")
        self._style(ts_menu)
        self._ensure_actions()
        self._populate_tree(ts_menu)
        self.sync_from_settings()

    def _read_settings(self) -> Dict[str, Any]:
        return UserSettingsService.get_instance().get_model().get_player_stats_time_series()

    def _apply(self, key: str, value: Any) -> None:
        UserSettingsService.get_instance().update_player_stats_time_series({key: value})
