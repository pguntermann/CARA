"""Bulk clean PGN controller for managing bulk PGN cleaning operations."""

from typing import Dict, Any, Optional, List
from PyQt6.QtCore import QObject, pyqtSignal

from app.models.database_model import DatabaseModel
from app.services.bulk_clean_pgn_service import BulkCleanPgnService, BulkCleanPgnResult
from app.services.progress_service import ProgressService


class BulkCleanPgnController(QObject):
    """Controller for bulk PGN cleaning operations.
    
    This controller orchestrates bulk PGN cleaning operations and manages
    the bulk clean PGN service.
    """
    
    # Signal emitted when operation completes
    operation_complete = pyqtSignal(BulkCleanPgnResult)  # result
    
    def __init__(self, config: Dict[str, Any], database_controller, game_controller=None, database_panel=None) -> None:
        """Initialize the bulk clean PGN controller.
        
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
        self.service = BulkCleanPgnService(config)
        
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
    
    def clean_pgn(
        self,
        database: DatabaseModel,
        remove_comments: bool = False,
        remove_variations: bool = False,
        remove_non_standard_tags: bool = False,
        remove_annotations: bool = False,
        remove_results: bool = False,
        game_indices: Optional[List[int]] = None
    ) -> BulkCleanPgnResult:
        """Clean PGN notation for games in a database.
        
        Args:
            database: DatabaseModel instance to process.
            remove_comments: If True, remove comments from PGN.
            remove_variations: If True, remove variations from PGN.
            remove_non_standard_tags: If True, remove non-standard tags from PGN.
            remove_annotations: If True, remove annotations from PGN.
            remove_results: If True, remove results from PGN.
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkCleanPgnResult with operation statistics.
        """
        self._cancelled = False
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Clean PGN: Starting...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Clean PGN: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform cleaning
        result = self.service.clean_pgn(
            database,
            remove_comments,
            remove_variations,
            remove_non_standard_tags,
            remove_annotations,
            remove_results,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update views
        if self.game_controller and result.success:
            self._refresh_active_game_if_updated(database, game_indices)
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def _refresh_active_game_if_updated(self, database: DatabaseModel, game_indices: Optional[List[int]]) -> None:
        """Refresh the active game if it was among the updated games.
        
        Args:
            database: DatabaseModel instance that was updated.
            game_indices: Optional list of game indices that were processed (None = all games).
        """
        if not self.game_controller:
            return
        
        game_model = self.game_controller.get_game_model()
        active_game = game_model.active_game
        if not active_game:
            return
        
        # Get all games from database
        games = database.get_all_games()
        
        # Determine which games were updated
        if game_indices is not None:
            updated_games = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            updated_games = games
        
        # Check if active game is in the updated games
        # Compare by reference since GameData objects are the same instances
        if active_game in updated_games:
            # Refresh active game to update views
            game_model.refresh_active_game()
    
    def cancel_operation(self) -> None:
        """Cancel the current operation."""
        self._cancelled = True

