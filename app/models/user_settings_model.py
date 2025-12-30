"""User settings model for managing application-wide user preferences."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any, Optional


class UserSettingsModel(QObject):
    """Model representing user settings state.
    
    This model holds user preferences and emits signals when settings change.
    Views observe these signals to update the UI automatically.
    """
    
    # Signals emitted when settings change
    settings_changed = pyqtSignal()  # Emitted when any setting changes
    moves_list_profiles_changed = pyqtSignal()  # Emitted when column profiles change
    active_profile_changed = pyqtSignal(str)  # Emitted when active profile changes (profile_name)
    board_visibility_changed = pyqtSignal()  # Emitted when board visibility settings change
    pgn_visibility_changed = pyqtSignal()  # Emitted when PGN visibility settings change
    game_analysis_changed = pyqtSignal()  # Emitted when game analysis settings change
    manual_analysis_changed = pyqtSignal()  # Emitted when manual analysis settings change
    annotations_changed = pyqtSignal()  # Emitted when annotation settings change
    ai_settings_changed = pyqtSignal()  # Emitted when AI settings change
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the user settings model.
        
        Args:
            settings: Initial settings dictionary. If None, uses empty dict.
        """
        super().__init__()
        self._settings: Dict[str, Any] = settings.copy() if settings else {}
    
    def get_settings(self) -> Dict[str, Any]:
        """Get all settings.
        
        Returns:
            Complete settings dictionary.
        """
        return self._settings.copy()
    
    def get_moves_list_profiles(self) -> Dict[str, Any]:
        """Get moves list profiles.
        
        Returns:
            Dictionary of profile data.
        """
        return self._settings.get("moves_list_profiles", {}).copy()
    
    def set_moves_list_profiles(self, profiles: Dict[str, Any]) -> None:
        """Set moves list profiles.
        
        Args:
            profiles: Dictionary of profile data.
        """
        self._settings["moves_list_profiles"] = profiles.copy()
        self.moves_list_profiles_changed.emit()
        self.settings_changed.emit()
    
    def get_active_profile(self) -> str:
        """Get active profile name.
        
        Returns:
            Active profile name.
        """
        return self._settings.get("active_profile", "Default")
    
    def set_active_profile(self, profile_name: str) -> None:
        """Set active profile.
        
        Args:
            profile_name: Name of the active profile.
        """
        if self._settings.get("active_profile") != profile_name:
            self._settings["active_profile"] = profile_name
            self.active_profile_changed.emit(profile_name)
            self.settings_changed.emit()
    
    def get_profile_order(self) -> list:
        """Get profile order.
        
        Returns:
            List of profile names in order.
        """
        return self._settings.get("profile_order", []).copy()
    
    def set_profile_order(self, order: list) -> None:
        """Set profile order.
        
        Args:
            order: List of profile names in order.
        """
        self._settings["profile_order"] = order.copy()
        self.moves_list_profiles_changed.emit()
        self.settings_changed.emit()
    
    def get_board_visibility(self) -> Dict[str, Any]:
        """Get board visibility settings.
        
        Returns:
            Dictionary of board visibility settings.
        """
        return self._settings.get("board_visibility", {}).copy()
    
    def set_board_visibility(self, settings: Dict[str, Any]) -> None:
        """Set board visibility settings.
        
        Args:
            settings: Dictionary of board visibility settings.
        """
        self._settings["board_visibility"] = settings.copy()
        self.board_visibility_changed.emit()
        self.settings_changed.emit()
    
    def get_pgn_visibility(self) -> Dict[str, Any]:
        """Get PGN visibility settings.
        
        Returns:
            Dictionary of PGN visibility settings.
        """
        return self._settings.get("pgn_visibility", {}).copy()
    
    def set_pgn_visibility(self, settings: Dict[str, Any]) -> None:
        """Set PGN visibility settings.
        
        Args:
            settings: Dictionary of PGN visibility settings.
        """
        self._settings["pgn_visibility"] = settings.copy()
        self.pgn_visibility_changed.emit()
        self.settings_changed.emit()
    
    def get_game_analysis(self) -> Dict[str, Any]:
        """Get game analysis settings.
        
        Returns:
            Dictionary of game analysis settings.
        """
        return self._settings.get("game_analysis", {}).copy()
    
    def set_game_analysis(self, settings: Dict[str, Any]) -> None:
        """Set game analysis settings.
        
        Args:
            settings: Dictionary of game analysis settings.
        """
        self._settings["game_analysis"] = settings.copy()
        self.game_analysis_changed.emit()
        self.settings_changed.emit()
    
    def get_game_analysis_settings(self) -> Dict[str, Any]:
        """Get game analysis configuration settings.
        
        Returns:
            Dictionary of game analysis configuration settings.
        """
        return self._settings.get("game_analysis_settings", {}).copy()
    
    def set_game_analysis_settings(self, settings: Dict[str, Any]) -> None:
        """Set game analysis configuration settings.
        
        Args:
            settings: Dictionary of game analysis configuration settings.
        """
        self._settings["game_analysis_settings"] = settings.copy()
        self.game_analysis_changed.emit()
        self.settings_changed.emit()
    
    def get_manual_analysis(self) -> Dict[str, Any]:
        """Get manual analysis settings.
        
        Returns:
            Dictionary of manual analysis settings.
        """
        return self._settings.get("manual_analysis", {}).copy()
    
    def set_manual_analysis(self, settings: Dict[str, Any]) -> None:
        """Set manual analysis settings.
        
        Args:
            settings: Dictionary of manual analysis settings.
        """
        self._settings["manual_analysis"] = settings.copy()
        self.manual_analysis_changed.emit()
        self.settings_changed.emit()
    
    def get_annotations(self) -> Dict[str, Any]:
        """Get annotation settings.
        
        Returns:
            Dictionary of annotation settings.
        """
        return self._settings.get("annotations", {}).copy()
    
    def set_annotations(self, settings: Dict[str, Any]) -> None:
        """Set annotation settings.
        
        Args:
            settings: Dictionary of annotation settings.
        """
        self._settings["annotations"] = settings.copy()
        self.annotations_changed.emit()
        self.settings_changed.emit()
    
    def get_engines(self) -> list:
        """Get engines list.
        
        Returns:
            List of engine data.
        """
        return self._settings.get("engines", []).copy()
    
    def set_engines(self, engines: list) -> None:
        """Set engines list.
        
        Args:
            engines: List of engine data.
        """
        self._settings["engines"] = engines.copy()
        self.settings_changed.emit()
    
    def get_engine_assignments(self) -> Dict[str, Optional[str]]:
        """Get engine assignments.
        
        Returns:
            Dictionary mapping task to engine_id.
        """
        return self._settings.get("engine_assignments", {}).copy()
    
    def set_engine_assignments(self, assignments: Dict[str, Optional[str]]) -> None:
        """Set engine assignments.
        
        Args:
            assignments: Dictionary mapping task to engine_id.
        """
        self._settings["engine_assignments"] = assignments.copy()
        self.settings_changed.emit()
    
    def get_ai_models(self) -> Dict[str, Any]:
        """Get AI model settings.
        
        Returns:
            Dictionary of AI model settings.
        """
        return self._settings.get("ai_models", {}).copy()
    
    def set_ai_models(self, settings: Dict[str, Any]) -> None:
        """Set AI model settings.
        
        Args:
            settings: Dictionary of AI model settings.
        """
        self._settings["ai_models"] = settings.copy()
        self.ai_settings_changed.emit()
        self.settings_changed.emit()
    
    def get_ai_summary(self) -> Dict[str, Any]:
        """Get AI summary settings.
        
        Returns:
            Dictionary of AI summary settings.
        """
        return self._settings.get("ai_summary", {}).copy()
    
    def set_ai_summary(self, settings: Dict[str, Any]) -> None:
        """Set AI summary settings.
        
        Args:
            settings: Dictionary of AI summary settings.
        """
        self._settings["ai_summary"] = settings.copy()
        self.ai_settings_changed.emit()
        self.settings_changed.emit()
    
    def update_from_dict(self, settings: Dict[str, Any]) -> None:
        """Update settings from a dictionary (used when loading from file).
        
        Args:
            settings: Settings dictionary to merge.
        """
        self._settings.update(settings)
        self.settings_changed.emit()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary (for saving to file).
        
        Returns:
            Complete settings dictionary.
        """
        return self._settings.copy()

