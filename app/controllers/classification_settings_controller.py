"""Controller for managing classification settings dialog operations."""

from typing import Dict, Any, Tuple
from PyQt6.QtCore import QObject

from app.services.progress_service import ProgressService


class ClassificationSettingsController(QObject):
    """Controller for orchestrating classification settings dialog operations.
    
    This controller handles progress/status updates for the classification
    settings dialog, while delegating business logic to MoveClassificationController.
    """
    
    def __init__(self, config: Dict[str, Any], classification_controller) -> None:
        """Initialize the classification settings controller.
        
        Args:
            config: Configuration dictionary.
            classification_controller: MoveClassificationController instance.
        """
        super().__init__()
        self.config = config
        self.classification_controller = classification_controller
        self.progress_service = ProgressService.get_instance()
    
    def set_status(self, message: str) -> None:
        """Set status message.
        
        Args:
            message: Status message to display.
        """
        self.progress_service.set_status(message)
    
    def show_progress(self) -> None:
        """Show progress bar."""
        self.progress_service.show_progress()
    
    def hide_progress(self) -> None:
        """Hide progress bar."""
        self.progress_service.hide_progress()
    
    def get_classification_controller(self):
        """Get the underlying classification controller.
        
        Returns:
            The MoveClassificationController instance.
        """
        return self.classification_controller

