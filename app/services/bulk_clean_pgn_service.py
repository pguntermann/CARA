"""Bulk PGN cleaning service for database operations."""

import os
from typing import Dict, Any, Optional, List, Callable, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.models.database_model import DatabaseModel
from app.services.bulk_operation_stats import BulkOperationStats, BulkProcessingOutcome
from app.services.pgn_cleaning_service import PgnCleaningService
from app.services.logging_service import LoggingService, init_worker_logging
from app.utils.concurrency_utils import get_process_pool_max_workers


def _process_game_for_cleaning(
    game_pgn: str,
    remove_comments: bool,
    remove_variations: bool,
    remove_non_standard_tags: bool,
    remove_annotations: bool
) -> Tuple[Optional[str], BulkProcessingOutcome]:
    """Process a single game for PGN cleaning (for parallel execution)."""
    try:
        class TempGame:
            def __init__(self, pgn: str):
                self.pgn = pgn
        
        temp_game = TempGame(game_pgn)
        game_modified = False
        
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
            return (temp_game.pgn, BulkProcessingOutcome.UPDATED)
        return (None, BulkProcessingOutcome.SKIPPED)
        
    except Exception:
        return (None, BulkProcessingOutcome.FAILED)


class BulkCleanPgnService:
    """Service for bulk PGN cleaning operations on databases."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
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
    ) -> BulkOperationStats:
        games = database.get_all_games()
        
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games
        
        total_games = len(games_to_process)
        
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkOperationStats(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        if not any([remove_comments, remove_variations, remove_non_standard_tags,
                   remove_annotations]):
            if progress_callback:
                progress_callback(0, total_games, "No cleaning options selected")
            return BulkOperationStats(
                success=True,
                games_processed=total_games,
                games_updated=0,
                games_failed=0,
                games_skipped=total_games
            )
        
        max_workers = get_process_pool_max_workers(os.cpu_count(), self.config)
        
        updated_games = []
        games_updated = 0
        games_failed = 0
        games_skipped = 0
        
        executor = None
        completed = 0
        try:
            log_queue = LoggingService.get_queue()
            executor = ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=init_worker_logging,
                initargs=(log_queue,)
            )
            
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
            
            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break
                
                game = future_to_game[future]
                completed += 1
                
                try:
                    new_pgn, outcome = future.result()
                    
                    if outcome == BulkProcessingOutcome.UPDATED:
                        if new_pgn:
                            game.pgn = new_pgn
                            updated_games.append(game)
                            games_updated += 1
                        else:
                            games_failed += 1
                    elif outcome == BulkProcessingOutcome.SKIPPED:
                        games_skipped += 1
                    else:
                        games_failed += 1
                except Exception:
                    games_failed += 1
                
                if progress_callback:
                    progress_callback(completed, total_games, f"Cleaning game {completed}/{total_games}")
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
            
            for future in future_to_game:
                if not future.done():
                    try:
                        future.result(timeout=1.0)
                    except Exception:
                        pass
        
        finally:
            if executor:
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                executor.shutdown(wait=True)
                QApplication.processEvents()
        
        if updated_games:
            database.batch_update_games(updated_games)
        
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
        logging_service.info(
            f"Bulk clean PGN operation completed: options=[{options_str}], games_processed={completed}, "
            f"games_updated={games_updated}, games_failed={games_failed}, games_skipped={games_skipped}"
        )
        
        return BulkOperationStats(
            success=True,
            games_processed=completed,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=games_skipped
        )
