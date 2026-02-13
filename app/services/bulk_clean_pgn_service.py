"""Bulk PGN cleaning service for database operations."""

import os
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.models.database_model import DatabaseModel, GameData
from app.services.pgn_cleaning_service import PgnCleaningService
from app.services.logging_service import LoggingService, init_worker_logging


@dataclass
class BulkCleanPgnResult:
    """Result of a bulk PGN cleaning operation."""
    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None


def _process_game_for_cleaning(
    game_pgn: str,
    remove_comments: bool,
    remove_variations: bool,
    remove_non_standard_tags: bool,
    remove_annotations: bool
) -> Tuple[Optional[str], bool]:
    """Process a single game for PGN cleaning (for parallel execution).
    
    Args:
        game_pgn: PGN string of the game.
        remove_comments: If True, remove comments from PGN.
        remove_variations: If True, remove variations from PGN.
        remove_non_standard_tags: If True, remove non-standard tags from PGN.
        remove_annotations: If True, remove annotations from PGN.
        
    Returns:
        Tuple of (new_pgn, updated) or (None, False) if failed.
    """
    try:
        # Create a temporary GameData-like object for processing
        class TempGame:
            def __init__(self, pgn: str):
                self.pgn = pgn
        
        temp_game = TempGame(game_pgn)
        game_modified = False
        
        # Apply cleaning operations in order
        if remove_comments:
            if PgnCleaningService.remove_comments_from_game(temp_game):
                game_modified = True
        
        if remove_variations:
            if PgnCleaningService.remove_variations_from_game(temp_game):
                game_modified = True
        
        if remove_non_standard_tags:
            if PgnCleaningService.remove_non_standard_tags_from_game(temp_game):
                game_modified = True
        
        if remove_annotations:
            if PgnCleaningService.remove_annotations_from_game(temp_game):
                game_modified = True
        
        if game_modified:
            return (temp_game.pgn, True)
        else:
            return (None, False)
        
    except Exception:
        return (None, False)


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
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_check: Optional[Callable[[], bool]] = None
    ) -> BulkCleanPgnResult:
        """Clean PGN notation for games in a database.
        
        Args:
            database: DatabaseModel instance to process.
            remove_comments: If True, remove comments from PGN.
            remove_variations: If True, remove variations from PGN.
            remove_non_standard_tags: If True, remove non-standard tags from PGN.
            remove_annotations: If True, remove annotations from PGN.
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            cancellation_check: Optional function that returns True if operation should be cancelled.
            
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
                   remove_annotations]):
            if progress_callback:
                progress_callback(0, total_games, "No cleaning options selected")
            return BulkCleanPgnResult(
                success=True,
                games_processed=total_games,
                games_updated=0,
                games_failed=0,
                games_skipped=total_games
            )
        
        # Determine worker count (reserve 1-2 cores for UI)
        max_workers = max(1, os.cpu_count() - 2)
        
        # Collect all updated games for batch update
        updated_games = []
        games_updated = 0
        games_failed = 0
        
        executor = None
        try:
            # Initialize logging for worker processes since PgnCleaningService methods use LoggingService
            log_queue = LoggingService.get_queue()
            executor = ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=init_worker_logging,
                initargs=(log_queue,)
            )
            
            # Submit all games for processing
            future_to_game = {
                executor.submit(
                    _process_game_for_cleaning,
                    game.pgn,
                    remove_comments,
                    remove_variations,
                    remove_non_standard_tags,
                    remove_annotations
                ): game
                for game in games_to_process
            }
            
            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    # Cancel remaining futures
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break
                
                game = future_to_game[future]
                completed += 1
                
                try:
                    new_pgn, updated = future.result()
                    
                    if updated and new_pgn:
                        # Update game data
                        game.pgn = new_pgn
                        
                        # Collect game for batch update
                        updated_games.append(game)
                        games_updated += 1
                    elif new_pgn is None and updated is False:
                        # Game was not modified or processing failed
                        pass
                except Exception:
                    games_failed += 1
                
                # Update progress AFTER processing result to ensure accurate count
                if progress_callback:
                    progress_callback(completed, total_games, f"Cleaning game {completed}/{total_games}")
                    # Process events to keep UI responsive
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
            
            # Ensure all futures are complete before shutdown
            # Wait for any remaining futures that might not have been processed
            for future in future_to_game:
                if not future.done():
                    try:
                        future.result(timeout=1.0)
                    except Exception:
                        pass
        
        finally:
            if executor:
                # Process events before shutdown to ensure UI updates
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                
                # Shutdown executor and wait for processes to finish
                executor.shutdown(wait=True)
                
                # Process events after shutdown to ensure UI can update
                QApplication.processEvents()
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
        # Log bulk clean operation
        logging_service = LoggingService.get_instance()
        options = []
        if remove_comments:
            options.append("comments")
        if remove_variations:
            options.append("variations")
        if remove_non_standard_tags:
            options.append("non_standard_tags")
        if remove_annotations:
            options.append("annotations")
        options_str = ", ".join(options) if options else "none"
        logging_service.info(f"Bulk clean PGN operation completed: options=[{options_str}], games_processed={total_games}, games_updated={games_updated}, games_failed={games_failed}")
        
        return BulkCleanPgnResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=total_games - games_updated - games_failed
        )
    

