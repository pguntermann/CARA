"""Synchronize option state across menu presentations (menubar, context menus).

This controller is meant to keep UI option toggles consistent across different
presentations while using user settings/models as the source of truth.

Initial scope: Player Stats section visibility actions in the main menubar.
Future scope: Board options mirrored into chessboard context menus, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class _PlayerStatsBinding:
    section_actions: Dict[str, Any]
    view: Any


class MenuOptionsSyncController:
    """Controller that synchronizes menu option state with user settings."""

    def __init__(self, config: Dict[str, Any], user_settings_model: Any) -> None:
        self.config = config
        self._user_settings_model = user_settings_model
        self._player_stats: Optional[_PlayerStatsBinding] = None

        # Generic settings change is the only signal for section-visibility changes.
        try:
            self._user_settings_model.settings_changed.connect(self._on_settings_changed)
        except Exception:
            pass

    def bind_player_stats(self, *, view: Any, section_actions: Dict[str, Any]) -> None:
        """Bind Player Stats section visibility actions to the Player Stats view."""
        self._player_stats = _PlayerStatsBinding(
            section_actions={str(k): v for k, v in (section_actions or {}).items()},
            view=view,
        )

        # (Re-)wire QAction signals to this controller.
        for sid, act in self._player_stats.section_actions.items():
            try:
                act.triggered.disconnect()
            except Exception:
                pass
            try:
                act.triggered.connect(lambda checked, section_id=sid: self.set_player_stats_section_visible(section_id, checked))
            except Exception:
                pass

        self.sync_player_stats_from_settings()

    def sync_player_stats_from_settings(self) -> None:
        """Pull Player Stats visibility from settings and update actions + view wrappers."""
        if not self._player_stats:
            return

        try:
            vis = self._user_settings_model.get_player_stats_section_visibility()
        except Exception:
            vis = {}

        # Update menu actions.
        for sid, act in self._player_stats.section_actions.items():
            try:
                act.blockSignals(True)
                act.setChecked(bool(vis.get(str(sid), True)))
                act.blockSignals(False)
            except Exception:
                pass

        # Ensure the view reflects persisted prefs.
        try:
            self._player_stats.view.reload_player_stats_section_prefs_from_settings()
        except Exception:
            pass

    def set_player_stats_section_visible(self, section_id: str, visible: bool) -> None:
        """Handle a section visibility toggle from any menu presentation."""
        if not self._player_stats:
            return
        try:
            self._player_stats.view.set_player_stats_section_visible_from_menu(str(section_id), bool(visible))
        except Exception:
            # Fall back to just syncing actions from settings.
            pass
        self.sync_player_stats_from_settings()

    def set_all_player_stats_sections_visible(self, visible: bool) -> None:
        """Enable/disable all Player Stats sections."""
        if not self._player_stats:
            return
        try:
            self._player_stats.view.set_all_player_stats_sections_visible_from_menu(bool(visible))
        except Exception:
            pass
        self.sync_player_stats_from_settings()

    def _on_settings_changed(self) -> None:
        """Settings changed on disk or via service; resync bound menus."""
        self.sync_player_stats_from_settings()

