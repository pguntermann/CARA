"""Deduplication controller for managing game deduplication operations."""

from typing import Dict, Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog

from app.models.database_model import DatabaseModel
from app.services.deduplication_service import DeduplicationService, DeduplicationResult
from app.services.progress_service import ProgressService


class DeduplicationController(QObject):
    """Controller for game deduplication operations.
    
    This controller orchestrates deduplication operations and manages
    the deduplication service.
    """
    
    # Signal emitted when operation completes
    operation_complete = pyqtSignal(DeduplicationResult)  # result
    
    def __init__(self, config: Dict[str, Any], database_controller, game_controller=None) -> None:
        """Initialize the deduplication controller.
        
        Args:
            config: Configuration dictionary.
            database_controller: DatabaseController instance.
            game_controller: Optional GameController instance for getting active game.
        """
        super().__init__()
        self.config = config
        self.database_controller = database_controller
        self.game_controller = game_controller
        
        # Initialize service
        self.service = DeduplicationService(config)
        
        # Get progress service
        self.progress_service = ProgressService.get_instance()
        
        # Track cancellation
        self._cancelled = False
    
    def get_active_database(self) -> Optional[DatabaseModel]:
        """Get the currently active database.
        
        Returns:
            The active DatabaseModel instance, or None.
        """
        return self.database_controller.get_active_database()
    
    def deduplicate(self, database: DatabaseModel, parent=None) -> Optional[DeduplicationResult]:
        """Remove duplicate games from a database.
        
        Args:
            database: DatabaseModel instance to process.
            parent: Parent widget for dialog.
            
        Returns:
            DeduplicationResult with operation statistics, or None if cancelled.
        """
        # Show criteria selection dialog
        from app.views.deduplication_criteria_dialog import DeduplicationCriteriaDialog, DeduplicationMode
        criteria_dialog = DeduplicationCriteriaDialog(self.config, parent)
        if criteria_dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        
        # Get selected criteria
        mode_enum, header_fields = criteria_dialog.get_criteria()
        mode = mode_enum.value
        
        self._cancelled = False
        
        # Get active game if available
        active_game = None
        if self.game_controller:
            game_model = self.game_controller.get_game_model()
            active_game = game_model.active_game
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Deduplicating games: Starting...")
        
        # Progress callback
        def progress_callback(current: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Deduplicating games: {message}")
        
        # Perform deduplication
        result = self.service.deduplicate(
            database,
            active_game,
            progress_callback,
            mode,
            header_fields
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # Show completion status
        if result.success:
            if result.games_removed > 0:
                self.progress_service.set_status(f"Deduplicated {result.games_removed} games from active database")
            else:
                self.progress_service.set_status("No duplicate games found")
        else:
            error_msg = result.error_message or "Unknown error"
            self.progress_service.set_status(f"Deduplication failed: {error_msg}")
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_removed > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def cancel_operation(self) -> None:
        """Cancel the current operation."""
        self._cancelled = True

