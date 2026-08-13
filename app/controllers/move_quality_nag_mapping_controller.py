"""Controller for move quality NAG mapping dialog operations."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtCore import QObject

from app.services.move_quality_nag_service import (
    default_move_quality_nag_mapping,
    normalize_move_quality_nag_mapping,
)
from app.services.progress_service import ProgressService
from app.services.user_settings_service import UserSettingsService


class MoveQualityNagMappingController(QObject):
    """Load/save classification→NAG mapping via user settings (no immediate disk save)."""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__()
        self.config = config
        self.settings_service = UserSettingsService.get_instance()
        self.progress_service = ProgressService.get_instance()

    def set_status(self, message: str) -> None:
        """Set status bar message."""
        self.progress_service.set_status(message)

    def show_progress(self) -> None:
        """Show progress bar."""
        self.progress_service.show_progress()

    def hide_progress(self) -> None:
        """Hide progress bar."""
        self.progress_service.hide_progress()

    def get_defaults(self) -> Dict[str, Dict[str, Any]]:
        """Return built-in default mapping."""
        return default_move_quality_nag_mapping()

    def load_mapping(self) -> Dict[str, Dict[str, Any]]:
        """Load effective mapping from in-memory user settings."""
        settings = self.settings_service.get_settings()
        game_analysis = settings.get("game_analysis", {}) if isinstance(settings, dict) else {}
        raw = game_analysis.get("move_quality_nag_mapping") if isinstance(game_analysis, dict) else None
        return normalize_move_quality_nag_mapping(raw if isinstance(raw, dict) else None)

    def save_mapping(self, mapping: Dict[str, Dict[str, Any]]) -> None:
        """Persist mapping in memory via UserSettingsService (disk save on app exit)."""
        normalized = normalize_move_quality_nag_mapping(mapping)
        self.settings_service.update_game_analysis({"move_quality_nag_mapping": normalized})
