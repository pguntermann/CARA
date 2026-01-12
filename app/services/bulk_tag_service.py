"""Bulk tag service for adding and removing tags from database games."""

import os
import chess
import chess.pgn
from io import StringIO
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.models.database_model import DatabaseModel, GameData
from app.services.pgn_service import PgnService


@dataclass
class BulkTagResult:
    """Result of a bulk tag operation."""
    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None


def _process_game_for_add_tag(
    game_pgn: str,
    tag_name: str,
    tag_value: Optional[str],
    source_tag: Optional[str]
) -> Tuple[Optional[str], Optional[str], bool]:
    """Process a single game for tag addition (for parallel execution).
    
    Args:
        game_pgn: PGN string of the game.
        tag_name: PGN tag name to add.
        tag_value: Optional fixed value to set. If None and source_tag is None, tag is added empty.
        source_tag: Optional source tag to copy value from. If provided, tag_value is ignored.
        
    Returns:
        Tuple of (new_pgn, new_field_value, updated) or (None, None, False) if failed/skipped.
    """
    try:
        # Parse PGN
        pgn_io = StringIO(game_pgn)
        chess_game = chess.pgn.read_game(pgn_io)
        
        if not chess_game:
            return (None, None, False)
        
        # Check if tag already exists - if so, skip this game
        if tag_name in chess_game.headers:
            return (None, None, False)
        
        # Determine value to set
        if source_tag is not None:
            # Copy from source tag
            new_value = chess_game.headers.get(source_tag, "")
        elif tag_value is not None and tag_value.strip():
            # Use fixed value (non-empty)
            new_value = tag_value
        else:
            # Empty value
            new_value = ""
        
        # Add tag
        chess_game.headers[tag_name] = new_value
        
        # Regenerate PGN
        new_pgn = PgnService.export_game_to_pgn(chess_game)
        
        # Get field value if tag maps to a field
        tag_to_field_mapping = {
            "White": "white",
            "Black": "black",
            "Result": "result",
            "Date": "date",
            "ECO": "eco",
            "Event": "event",
            "Site": "site",
            "WhiteElo": "white_elo",
            "BlackElo": "black_elo",
        }
        
        field_value = new_value if tag_name in tag_to_field_mapping else None
        
        return (new_pgn, field_value, True)
        
    except Exception:
        return (None, None, False)


def _process_game_for_remove_tag(
    game_pgn: str,
    tag_name: str
) -> Tuple[Optional[str], Optional[str], bool]:
    """Process a single game for tag removal (for parallel execution).
    
    Args:
        game_pgn: PGN string of the game.
        tag_name: PGN tag name to remove.
        
    Returns:
        Tuple of (new_pgn, None, updated) or (None, None, False) if failed/skipped.
    """
    try:
        # Parse PGN
        pgn_io = StringIO(game_pgn)
        chess_game = chess.pgn.read_game(pgn_io)
        
        if not chess_game:
            return (None, None, False)
        
        # Check if tag exists
        if tag_name not in chess_game.headers:
            # Tag doesn't exist, skip
            return (None, None, False)
        
        # Remove tag
        del chess_game.headers[tag_name]
        
        # Regenerate PGN
        new_pgn = PgnService.export_game_to_pgn(chess_game)
        
        return (new_pgn, None, True)
        
    except Exception:
        return (None, None, False)


class BulkTagService:
    """Service for bulk tag operations on databases."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the bulk tag service.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
    
    def add_tag(
        self,
        database: DatabaseModel,
        tag_name: str,
        tag_value: Optional[str] = None,
        source_tag: Optional[str] = None,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_check: Optional[Callable[[], bool]] = None
    ) -> BulkTagResult:
        """Add a tag to games.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to add (e.g., "EventDate", "Round").
            tag_value: Optional fixed value to set. If None and source_tag is None, tag is added empty.
            source_tag: Optional source tag to copy value from. If provided, tag_value is ignored.
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            cancellation_check: Optional function that returns True if operation should be cancelled.
            
        Returns:
            BulkTagResult with operation statistics.
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
            return BulkTagResult(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        # Determine worker count (reserve 1-2 cores for UI)
        max_workers = max(1, os.cpu_count() - 2)
        
        # Collect all updated games for batch update
        updated_games = []
        games_updated = 0
        games_failed = 0
        games_skipped = 0
        
        executor = None
        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)
            
            # Submit all games for processing
            future_to_game = {
                executor.submit(
                    _process_game_for_add_tag,
                    game.pgn,
                    tag_name,
                    tag_value,
                    source_tag
                ): game
                for game in games_to_process
            }
            
            # Process results as they complete
            completed = 0
            tag_to_field_mapping = {
                "White": "white",
                "Black": "black",
                "Result": "result",
                "Date": "date",
                "ECO": "eco",
                "Event": "event",
                "Site": "site",
                "WhiteElo": "white_elo",
                "BlackElo": "black_elo",
            }
            
            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    # Cancel remaining futures
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break
                
                game = future_to_game[future]
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total_games, f"Processing game {completed}/{total_games}")
                
                try:
                    new_pgn, new_field_value, updated = future.result()
                    
                    if updated and new_pgn:
                        # Update game data
                        game.pgn = new_pgn
                        
                        # Update corresponding GameData fields if tag maps to a field
                        if tag_name in tag_to_field_mapping and new_field_value is not None:
                            field_name = tag_to_field_mapping[tag_name]
                            setattr(game, field_name, new_field_value)
                        
                        # Collect game for batch update
                        updated_games.append(game)
                        games_updated += 1
                    elif new_pgn is None and updated is False:
                        # Tag already exists or processing failed
                        games_skipped += 1
                except Exception:
                    games_failed += 1
        
        finally:
            if executor:
                executor.shutdown(wait=True)
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
        # Update tag cache with new tag
        database._add_tags_to_cache({tag_name})
        
        return BulkTagResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=games_skipped
        )
    
    def remove_tag(
        self,
        database: DatabaseModel,
        tag_name: str,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_check: Optional[Callable[[], bool]] = None
    ) -> BulkTagResult:
        """Remove a tag from games.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to remove (e.g., "EventDate", "Round").
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            cancellation_check: Optional function that returns True if operation should be cancelled.
            
        Returns:
            BulkTagResult with operation statistics.
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
            return BulkTagResult(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        # Determine worker count (reserve 1-2 cores for UI)
        max_workers = max(1, os.cpu_count() - 2)
        
        # Collect all updated games for batch update
        updated_games = []
        games_updated = 0
        games_failed = 0
        
        executor = None
        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)
            
            # Submit all games for processing
            future_to_game = {
                executor.submit(
                    _process_game_for_remove_tag,
                    game.pgn,
                    tag_name
                ): game
                for game in games_to_process
            }
            
            # Process results as they complete
            completed = 0
            tag_to_field_mapping = {
                "White": "white",
                "Black": "black",
                "Result": "result",
                "Date": "date",
                "ECO": "eco",
                "Event": "event",
                "Site": "site",
                "WhiteElo": "white_elo",
                "BlackElo": "black_elo",
            }
            
            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    # Cancel remaining futures
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break
                
                game = future_to_game[future]
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total_games, f"Processing game {completed}/{total_games}")
                
                try:
                    new_pgn, _, updated = future.result()
                    
                    if updated and new_pgn:
                        # Update game data
                        game.pgn = new_pgn
                        
                        # Update corresponding GameData fields if tag maps to a field
                        if tag_name in tag_to_field_mapping:
                            field_name = tag_to_field_mapping[tag_name]
                            setattr(game, field_name, "")
                        
                        # Collect game for batch update
                        updated_games.append(game)
                        games_updated += 1
                    elif new_pgn is None and updated is False:
                        # Tag doesn't exist or processing failed
                        pass
                except Exception:
                    games_failed += 1
        
        finally:
            if executor:
                executor.shutdown(wait=True)
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
        return BulkTagResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=0
        )

