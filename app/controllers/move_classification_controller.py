"""Move classification controller for managing classification settings."""

from typing import Dict, Any, Optional

from app.models.move_classification_model import MoveClassificationModel
from app.services.user_settings_service import UserSettingsService


class MoveClassificationController:
    """Controller for managing move classification settings operations.
    
    This controller orchestrates classification settings operations and manages
    the move classification model and user settings service.
    """
    
    def __init__(self, config: Dict[str, Any], user_settings_service: Optional[UserSettingsService] = None) -> None:
        """Initialize the move classification controller.
        
        Args:
            config: Configuration dictionary.
            user_settings_service: Optional UserSettingsService instance. If None, creates a new one.
        """
        self.config = config
        
        # Get singleton service instance (ignore user_settings_service parameter for consistency)
        self.settings_service = UserSettingsService.get_instance()
        
        # Initialize model
        self.classification_model = MoveClassificationModel()
        
        # Load settings and initialize model
        self._load_settings()
    
    def _load_settings(self) -> None:
        """Load settings from config and user settings, then update model."""
        # Get defaults from config
        game_analysis_config = self.config.get("game_analysis", {})
        default_thresholds = game_analysis_config.get("assessment_thresholds", {})
        default_brilliant = game_analysis_config.get("brilliant_criteria", {})
        
        # Get user settings
        user_settings = self.settings_service.get_settings()
        user_game_analysis = user_settings.get("game_analysis_settings", {})
        user_thresholds = user_game_analysis.get("assessment_thresholds", {})
        user_brilliant = user_game_analysis.get("brilliant_criteria", {})
        
        # Merge: user settings override defaults
        thresholds = {**default_thresholds, **user_thresholds}
        brilliant = {**default_brilliant, **user_brilliant}
        
        # shallow_error_classifications is config-only, always use from config
        brilliant["shallow_error_classifications"] = default_brilliant.get("shallow_error_classifications", ["Mistake", "Blunder", "Miss"])
        
        # Load into model
        self.classification_model.load_settings(thresholds, brilliant)
    
    def _save_settings(self) -> bool:
        """Save current settings to user settings file.
        
        Returns:
            True if save was successful, False otherwise.
        """
        # Update settings through UserSettingsService. brilliant_criteria comes from
        # get_brilliant_criteria() (so it contains shallow_error_classifications); on load we
        # overwrite shallow_error_classifications from config only.
        self.settings_service.update_game_analysis_settings({
            "assessment_thresholds": self.classification_model.get_assessment_thresholds(),
            "brilliant_criteria": self.classification_model.get_brilliant_criteria()
        })
        
        # Persist to file
        return self.settings_service.save()
    
    def save_settings(self) -> bool:
        """Public method to save settings (for external use).
        
        Returns:
            True if save was successful, False otherwise.
        """
        return self._save_settings()
    
    def get_classification_model(self) -> MoveClassificationModel:
        """Get the move classification model.
        
        Returns:
            The MoveClassificationModel instance for observing settings state.
        """
        return self.classification_model
    
    def update_assessment_thresholds(self, thresholds: Dict[str, int]) -> bool:
        """Update assessment thresholds and save to user settings.
        
        Args:
            thresholds: Dictionary with threshold values to update.
            
        Returns:
            True if update and save were successful, False otherwise.
        """
        self.classification_model.update_assessment_thresholds(thresholds)
        return self._save_settings()
    
    def update_brilliant_criteria(self, criteria: Dict[str, Any]) -> bool:
        """Update brilliancy criteria and save to user settings.
        
        Args:
            criteria: Dictionary with criteria values to update.
            
        Returns:
            True if update and save were successful, False otherwise.
        """
        self.classification_model.update_brilliant_criteria(criteria)
        return self._save_settings()
    
    def update_all_settings(self, thresholds: Dict[str, int], criteria: Dict[str, Any]) -> bool:
        """Update all settings and save to user settings.
        
        Args:
            thresholds: Dictionary with threshold values to update.
            criteria: Dictionary with criteria values to update.
            
        Returns:
            True if update and save were successful, False otherwise.
        """
        self.classification_model.update_assessment_thresholds(thresholds)
        self.classification_model.update_brilliant_criteria(criteria)
        return self._save_settings()
    
    def reset_to_defaults(self) -> bool:
        """Reset all settings to defaults from config.
        
        Returns:
            True if reset and save were successful, False otherwise.
        """
        # Get defaults from config
        game_analysis_config = self.config.get("game_analysis", {})
        default_thresholds = game_analysis_config.get("assessment_thresholds", {})
        default_brilliant = game_analysis_config.get("brilliant_criteria", {})
        
        # Update model with defaults
        self.classification_model.load_settings(default_thresholds, default_brilliant)
        
        # Clear user settings for these values by updating with empty dict
        # This will remove the game_analysis_settings section
        self.settings_service.update_game_analysis_settings({})
        
        # Persist to file
        return self.settings_service.save()
    
    def reload_settings(self) -> None:
        """Reload settings from config and user settings."""
        self._load_settings()

