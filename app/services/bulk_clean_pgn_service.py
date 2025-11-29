"""Bulk PGN cleaning service for database operations."""

from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

from app.models.database_model import DatabaseModel, GameData
from app.services.pgn_cleaning_service import PgnCleaningService


@dataclass
class BulkCleanPgnResult:
    """Result of a bulk PGN cleaning operation."""
    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None


class BulkCleanPgnService:
    """Service for bulk PGN cleaning operations on databases."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the bulk clean PGN service.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
    
    def clean_pgn(
        self,
        database: DatabaseModel,
        remove_comments: bool = False,
        remove_variations: bool = False,
        remove_non_standard_tags: bool = False,
        remove_annotations: bool = False,
        remove_results: bool = False,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
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
            progress_callback: Optional callback function(game_index, total, message).
            
        Returns:
            BulkCleanPgnResult with operation statistics.
        """
        games = database.get_all_games()
        
        # Filter games if indices provided
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games
        
        total_games = len(games_to_process)
        games_updated = 0
        games_failed = 0
        
        # If no games to process, return early
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkCleanPgnResult(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        # If no cleaning options selected, return early
        if not any([remove_comments, remove_variations, remove_non_standard_tags, 
                   remove_annotations, remove_results]):
            if progress_callback:
                progress_callback(0, total_games, "No cleaning options selected")
            return BulkCleanPgnResult(
                success=True,
                games_processed=total_games,
                games_updated=0,
                games_failed=0,
                games_skipped=total_games
            )
        
        # Collect all updated games for batch update
        updated_games = []
        
        # Process each game
        for idx, game in enumerate(games_to_process):
            if progress_callback:
                progress_callback(idx, total_games, f"Cleaning game {idx + 1}/{total_games}")
            
            try:
                # Track if game was modified
                game_modified = False
                
                # Apply cleaning operations in order
                if remove_comments:
                    if PgnCleaningService.remove_comments_from_game(game):
                        game_modified = True
                
                if remove_variations:
                    if PgnCleaningService.remove_variations_from_game(game):
                        game_modified = True
                
                if remove_non_standard_tags:
                    if PgnCleaningService.remove_non_standard_tags_from_game(game):
                        game_modified = True
                
                if remove_annotations:
                    if PgnCleaningService.remove_annotations_from_game(game):
                        game_modified = True
                
                if remove_results:
                    if PgnCleaningService.remove_results_from_game(game):
                        game_modified = True
                
                # If game was modified, add to updated list
                if game_modified:
                    updated_games.append(game)
                    games_updated += 1
                
            except Exception:
                games_failed += 1
                continue
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
        return BulkCleanPgnResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=total_games - games_updated - games_failed
        )

