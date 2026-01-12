"""Controller for managing annotation preferences operations."""

from typing import Dict, Any, List, Optional, Tuple
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QColor

from app.services.user_settings_service import UserSettingsService
from app.services.progress_service import ProgressService


class AnnotationPreferencesController(QObject):
    """Controller for orchestrating annotation preferences operations.
    
    This controller handles the business logic for loading, resetting,
    and saving annotation preferences (colors and fonts).
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the annotation preferences controller.
        
        Args:
            config: Configuration dictionary.
        """
        super().__init__()
        self.config = config
        self.settings_service = UserSettingsService.get_instance()
        self.progress_service = ProgressService.get_instance()
        
        # Get default colors from annotations config
        annotations_config = self.config.get('ui', {}).get('panels', {}).get('detail', {}).get('annotations', {})
        default_preset_colors = annotations_config.get('preset_colors', [[255, 100, 100], [100, 220, 100], [150, 200, 255], [255, 200, 100], [200, 100, 255], [100, 220, 255], [255, 150, 200], [150, 150, 255], [200, 200, 100], [240, 240, 240]])
        self.default_colors = [QColor(color[0], color[1], color[2]) for color in default_preset_colors]
        
        # Get default font from config
        self.default_font_family = annotations_config.get('text_font_family', 'Arial')
        self.default_font_size = annotations_config.get('text_font_size', 12)
    
    def set_status(self, message: str) -> None:
        """Set status message.
        
        Args:
            message: Status message to display.
        """
        self.progress_service.set_status(message)
    
    def load_settings(self) -> Tuple[List[QColor], str, int]:
        """Load current annotation preferences from user settings.
        
        Returns:
            Tuple of (colors: List[QColor], font_family: str, font_size: int).
        """
        settings = self.settings_service.get_settings()
        annotations_prefs = settings.get('annotations', {})
        
        # Load colors
        preset_colors = annotations_prefs.get('preset_colors', None)
        if preset_colors:
            colors = [QColor(color_list[0], color_list[1], color_list[2]) for color_list in preset_colors]
        else:
            # Use defaults
            colors = self.default_colors.copy()
        
        # Load font
        font_family = annotations_prefs.get('text_font_family', self.default_font_family)
        if font_family is None:
            font_family = self.default_font_family
        font_size = annotations_prefs.get('text_font_size', self.default_font_size)
        if font_size is None:
            font_size = self.default_font_size
        
        return (colors, font_family, font_size)
    
    def get_defaults(self) -> Tuple[List[QColor], str, int]:
        """Get default annotation preferences.
        
        Returns:
            Tuple of (colors: List[QColor], font_family: str, font_size: int).
        """
        return (self.default_colors.copy(), self.default_font_family, self.default_font_size)
    
    def save_settings(self, colors: List[QColor], font_family: str, font_size: int) -> Tuple[bool, str]:
        """Save annotation preferences to user settings.
        
        Args:
            colors: List of QColor objects for preset colors.
            font_family: Font family name.
            font_size: Font size.
            
        Returns:
            Tuple of (success: bool, message: str).
        """
        # Convert colors to lists
        colors_list = []
        for color in colors:
            colors_list.append([color.red(), color.green(), color.blue()])
        
        # Update user settings
        settings = self.settings_service.get_settings()
        if 'annotations' not in settings:
            settings['annotations'] = {}
        
        settings['annotations']['preset_colors'] = colors_list
        settings['annotations']['text_font_family'] = font_family
        settings['annotations']['text_font_size'] = font_size
        
        # Save to file
        if self.settings_service.save():
            return (True, "Annotation preferences saved")
        else:
            return (False, "Failed to save annotation preferences")

