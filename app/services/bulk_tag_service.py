"""Bulk tag service for adding and removing tags from database games."""

import chess
import chess.pgn
from io import StringIO
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

from app.models.database_model import DatabaseModel, GameData


@dataclass
class BulkTagResult:
    """Result of a bulk tag operation."""
    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None


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
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> BulkTagResult:
        """Add a tag to games.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to add (e.g., "EventDate", "Round").
            tag_value: Optional fixed value to set. If None and source_tag is None, tag is added empty.
            source_tag: Optional source tag to copy value from. If provided, tag_value is ignored.
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            
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
        games_updated = 0
        games_failed = 0
        games_skipped = 0
        
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
        
        # Determine tag value source
        if source_tag is not None:
            # Copy from source tag
            value_mode = "copy"
        elif tag_value is not None and tag_value.strip():
            # Use fixed value (non-empty)
            value_mode = "fixed"
        else:
            # Empty value (tag_value is None or empty string)
            value_mode = "empty"
        
        # Collect all updated games for batch update
        updated_games = []
        
        # Process each game
        for idx, game in enumerate(games_to_process):
            if progress_callback:
                progress_callback(idx, total_games, f"Processing game {idx + 1}/{total_games}")
            
            try:
                # Parse PGN
                pgn_io = StringIO(game.pgn)
                chess_game = chess.pgn.read_game(pgn_io)
                
                if not chess_game:
                    games_failed += 1
                    continue
                
                # Check if tag already exists - if so, skip this game
                if tag_name in chess_game.headers:
                    games_skipped += 1
                    continue
                
                # Determine value to set
                if value_mode == "copy":
                    # Copy from source tag
                    source_value = chess_game.headers.get(source_tag, "")
                    new_value = source_value
                elif value_mode == "fixed":
                    # Use fixed value
                    new_value = tag_value
                else:
                    # Empty value
                    new_value = ""
                
                # Add tag (we know it doesn't exist from check above)
                chess_game.headers[tag_name] = new_value
                
                # Regenerate PGN
                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                new_pgn = chess_game.accept(exporter).strip()
                
                # Update game data
                game.pgn = new_pgn
                
                # Update corresponding GameData fields if tag maps to a field
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
                
                if tag_name in tag_to_field_mapping:
                    field_name = tag_to_field_mapping[tag_name]
                    setattr(game, field_name, new_value)
                
                # Collect game for batch update
                updated_games.append(game)
                games_updated += 1
                
            except Exception as e:
                games_failed += 1
                continue
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
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
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> BulkTagResult:
        """Remove a tag from games.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to remove (e.g., "EventDate", "Round").
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            
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
        games_updated = 0
        games_failed = 0
        
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
        
        # Collect all updated games for batch update
        updated_games = []
        
        # Process each game
        for idx, game in enumerate(games_to_process):
            if progress_callback:
                progress_callback(idx, total_games, f"Processing game {idx + 1}/{total_games}")
            
            try:
                # Parse PGN
                pgn_io = StringIO(game.pgn)
                chess_game = chess.pgn.read_game(pgn_io)
                
                if not chess_game:
                    games_failed += 1
                    continue
                
                # Check if tag exists
                if tag_name not in chess_game.headers:
                    # Tag doesn't exist, skip
                    continue
                
                # Remove tag
                del chess_game.headers[tag_name]
                
                # Regenerate PGN
                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                new_pgn = chess_game.accept(exporter).strip()
                
                # Update game data
                game.pgn = new_pgn
                
                # Update corresponding GameData fields if tag maps to a field
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
                
                if tag_name in tag_to_field_mapping:
                    field_name = tag_to_field_mapping[tag_name]
                    setattr(game, field_name, "")
                
                # Collect game for batch update
                updated_games.append(game)
                games_updated += 1
                
            except Exception as e:
                games_failed += 1
                continue
        
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

