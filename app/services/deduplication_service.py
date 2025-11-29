"""Deduplication service for removing duplicate games from databases."""

import re
import chess.pgn
from io import StringIO
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from collections import defaultdict

from app.models.database_model import DatabaseModel, GameData


@dataclass
class DeduplicationResult:
    """Result of a deduplication operation."""
    success: bool
    games_processed: int
    games_removed: int
    duplicate_groups: int
    error_message: Optional[str] = None


class DeduplicationService:
    """Service for deduplicating games in databases."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the deduplication service.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
    
    def _extract_moves_only(self, pgn_str: str) -> str:
        """Extract moves from PGN string, ignoring headers.
        
        Args:
            pgn_str: PGN string.
            
        Returns:
            Moves portion of PGN as string.
        """
        try:
            pgn_io = StringIO(pgn_str)
            game = chess.pgn.read_game(pgn_io)
            if not game:
                return ""
            
            # Export only the moves (no headers, no variations, no comments)
            exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
            moves_str = game.accept(exporter)
            return moves_str.strip() if moves_str else ""
        except Exception:
            return ""
    
    def _normalize_pgn(self, pgn_str: str) -> str:
        """Normalize PGN by removing comments, variations, and extra whitespace.
        
        Args:
            pgn_str: PGN string.
            
        Returns:
            Normalized PGN string.
        """
        try:
            pgn_io = StringIO(pgn_str)
            game = chess.pgn.read_game(pgn_io)
            if not game:
                return ""
            
            # Export without comments and variations
            exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
            normalized = game.accept(exporter)
            # Remove extra whitespace
            normalized = re.sub(r'\s+', ' ', normalized.strip())
            return normalized
        except Exception:
            return ""
    
    def _extract_headers(self, pgn_str: str, header_fields: List[str]) -> str:
        """Extract selected header fields from PGN.
        
        Args:
            pgn_str: PGN string.
            header_fields: List of header field names to extract.
            
        Returns:
            String representation of selected headers.
        """
        try:
            pgn_io = StringIO(pgn_str)
            game = chess.pgn.read_game(pgn_io)
            if not game:
                return ""
            
            header_values = []
            for field in header_fields:
                value = game.headers.get(field, "")
                header_values.append(f"{field}:{value}")
            
            return "|".join(header_values)
        except Exception:
            return ""
    
    def _get_match_key(self, game: GameData, mode: str, header_fields: List[str]) -> str:
        """Get matching key for a game based on deduplication mode.
        
        Args:
            game: GameData instance.
            mode: Deduplication mode ('exact_pgn', 'moves_only', 'normalized_pgn', 'header_based').
            header_fields: List of header fields for header_based mode.
            
        Returns:
            Matching key string.
        """
        if not game.pgn or not game.pgn.strip():
            return ""
        
        pgn_str = game.pgn.strip()
        
        if mode == 'exact_pgn':
            return pgn_str
        elif mode == 'moves_only':
            return self._extract_moves_only(pgn_str)
        elif mode == 'normalized_pgn':
            return self._normalize_pgn(pgn_str)
        elif mode == 'header_based':
            return self._extract_headers(pgn_str, header_fields)
        else:
            # Default to exact PGN
            return pgn_str
    
    def deduplicate(
        self,
        database: DatabaseModel,
        active_game: Optional[GameData] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        mode: str = 'exact_pgn',
        header_fields: Optional[List[str]] = None
    ) -> DeduplicationResult:
        """Remove duplicate games from a database.
        
        Games are considered duplicates based on the selected matching mode.
        If active_game is provided and is a duplicate, it will be preserved
        and other duplicates will be removed.
        
        Args:
            database: DatabaseModel instance to process.
            active_game: Optional active game to preserve if it's a duplicate.
            progress_callback: Optional callback function(current, total, message).
            mode: Deduplication mode ('exact_pgn', 'moves_only', 'normalized_pgn', 'header_based').
            header_fields: List of header fields for header_based mode (required if mode is 'header_based').
            
        Returns:
            DeduplicationResult with operation statistics.
        """
        if header_fields is None:
            header_fields = []
        
        games = database.get_all_games()
        total_games = len(games)
        
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return DeduplicationResult(
                success=True,
                games_processed=0,
                games_removed=0,
                duplicate_groups=0
            )
        
        # Group games by match key based on selected mode
        match_groups: Dict[str, List[GameData]] = defaultdict(list)
        
        if progress_callback:
            progress_callback(0, total_games, "Comparing games...")
        
        for idx, game in enumerate(games):
            if progress_callback and idx % 100 == 0:
                progress_callback(idx, total_games, f"Comparing games... {idx}/{total_games}")
            
            # Get match key based on mode
            match_key = self._get_match_key(game, mode, header_fields)
            if not match_key:
                continue
            
            match_groups[match_key].append(game)
        
        # Find duplicate groups (groups with more than one game)
        duplicate_groups = {key: games_list for key, games_list in match_groups.items() if len(games_list) > 1}
        duplicate_groups_count = len(duplicate_groups)
        
        if duplicate_groups_count == 0:
            if progress_callback:
                progress_callback(total_games, total_games, "No duplicates found")
            return DeduplicationResult(
                success=True,
                games_processed=total_games,
                games_removed=0,
                duplicate_groups=0
            )
        
        # Collect games to remove
        games_to_remove = []
        
        if progress_callback:
            progress_callback(0, duplicate_groups_count, "Identifying duplicates to remove...")
        
        for idx, (match_key, duplicate_games) in enumerate(duplicate_groups.items()):
            if progress_callback:
                progress_callback(idx, duplicate_groups_count, f"Processing duplicate group {idx + 1}/{duplicate_groups_count}")
            
            # If active game is in this duplicate group, preserve it and remove others
            if active_game and active_game in duplicate_games:
                # Remove all games except the active one
                for game in duplicate_games:
                    if game != active_game:
                        games_to_remove.append(game)
            else:
                # Keep the first occurrence, remove the rest
                for game in duplicate_games[1:]:
                    games_to_remove.append(game)
        
        # Remove duplicates from database
        if games_to_remove:
            if progress_callback:
                progress_callback(0, 1, f"Removing {len(games_to_remove)} duplicate games...")
            
            database.remove_games(games_to_remove)
        
        if progress_callback:
            progress_callback(1, 1, "Deduplication complete")
        
        return DeduplicationResult(
            success=True,
            games_processed=total_games,
            games_removed=len(games_to_remove),
            duplicate_groups=duplicate_groups_count
        )

