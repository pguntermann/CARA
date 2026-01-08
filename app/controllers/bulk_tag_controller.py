"""Bulk tag controller for managing bulk tag operations."""

import re
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import QObject, pyqtSignal

from app.models.database_model import DatabaseModel
from app.services.bulk_tag_service import BulkTagService, BulkTagResult
from app.services.progress_service import ProgressService


class BulkTagController(QObject):
    """Controller for bulk tag operations.
    
    This controller orchestrates bulk tag operations and manages
    the bulk tag service.
    """
    
    # Signal emitted when operation completes
    operation_complete = pyqtSignal(BulkTagResult)  # result
    
    def __init__(self, config: Dict[str, Any], database_controller, game_controller=None, database_panel=None) -> None:
        """Initialize the bulk tag controller.
        
        Args:
            config: Configuration dictionary.
            database_controller: DatabaseController instance.
            game_controller: Optional GameController instance for refreshing active game.
            database_panel: Optional DatabasePanel view instance for getting selected games.
        """
        super().__init__()
        self.config = config
        self.database_controller = database_controller
        self.game_controller = game_controller
        self.database_panel = database_panel
        
        # Initialize service
        self.service = BulkTagService(config)
        
        # Get progress service
        self.progress_service = ProgressService.get_instance()
        
        # Track cancellation
        self._cancelled = False
    
    def set_database_panel(self, database_panel) -> None:
        """Set the database panel view reference.
        
        Args:
            database_panel: DatabasePanel view instance.
        """
        self.database_panel = database_panel
    
    def get_active_database(self) -> Optional[DatabaseModel]:
        """Get the currently active database.
        
        Returns:
            The active DatabaseModel instance, or None.
        """
        return self.database_controller.get_active_database()
    
    def get_selected_game_indices(self) -> List[int]:
        """Get selected game indices from the database panel.
        
        Returns:
            List of selected game row indices.
        """
        if not self.database_panel:
            return []
        
        return self.database_panel.get_selected_game_indices()
    
    @staticmethod
    def sanitize_tag_name(tag_name: str) -> str:
        """Sanitize a tag name to ensure it's valid for PGN format.
        
        PGN tag names must:
        - Start with a letter or digit
        - Contain only letters, digits, and underscores
        - Not contain whitespace or other special characters
        
        Args:
            tag_name: Raw tag name from user input.
            
        Returns:
            Sanitized tag name valid for PGN format.
        """
        # Remove all whitespace
        tag_name = re.sub(r'\s+', '', tag_name)
        # Remove all characters that aren't alphanumeric or underscore
        tag_name = re.sub(r'[^A-Za-z0-9_]', '', tag_name)
        # Ensure it starts with a letter or digit (not underscore)
        if tag_name and not tag_name[0].isalnum():
            # If it starts with underscore or is empty, prepend 'Tag'
            tag_name = 'Tag' + tag_name
        return tag_name
    
    def add_tag(
        self,
        database: DatabaseModel,
        tag_name: str,
        tag_value: Optional[str] = None,
        source_tag: Optional[str] = None,
        game_indices: Optional[List[int]] = None
    ) -> BulkTagResult:
        """Add a tag to games.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to add (will be sanitized).
            tag_value: Optional fixed value to set. If None and source_tag is None, tag is added empty.
            source_tag: Optional source tag to copy value from (will be sanitized). If provided, tag_value is ignored.
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkTagResult with operation statistics.
        """
        self._cancelled = False
        
        # Sanitize tag names to ensure they're valid for PGN format
        tag_name = self.sanitize_tag_name(tag_name)
        if source_tag:
            source_tag = self.sanitize_tag_name(source_tag)
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Tag: Starting...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Tag: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform operation
        result = self.service.add_tag(
            database,
            tag_name,
            tag_value,
            source_tag,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            game_model = self.game_controller.get_game_model()
            active_game = game_model.active_game
            if active_game:
                # Check if any of the updated games is the active game
                games = database.get_all_games()
                if game_indices is not None:
                    updated_games = [games[i] for i in game_indices if 0 <= i < len(games)]
                else:
                    updated_games = games
                
                # Check if active game is in the updated games
                if active_game in updated_games:
                    # Refresh active game to update metadata view
                    game_model.refresh_active_game()
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def remove_tag(
        self,
        database: DatabaseModel,
        tag_name: str,
        game_indices: Optional[List[int]] = None
    ) -> BulkTagResult:
        """Remove a tag from games.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to remove (will be sanitized).
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkTagResult with operation statistics.
        """
        self._cancelled = False
        
        # Sanitize tag name to ensure it's valid for PGN format
        tag_name = self.sanitize_tag_name(tag_name)
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Tag: Starting...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Tag: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform operation
        result = self.service.remove_tag(
            database,
            tag_name,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            game_model = self.game_controller.get_game_model()
            active_game = game_model.active_game
            if active_game:
                # Check if any of the updated games is the active game
                games = database.get_all_games()
                if game_indices is not None:
                    updated_games = [games[i] for i in game_indices if 0 <= i < len(games)]
                else:
                    updated_games = games
                
                # Check if active game is in the updated games
                if active_game in updated_games:
                    # Refresh active game to update metadata view
                    game_model.refresh_active_game()
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def cancel_operation(self) -> None:
        """Cancel the current operation."""
        self._cancelled = True

