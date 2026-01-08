"""Service for cleaning PGN notation by removing comments, variations, annotations, etc."""

import chess.pgn
from io import StringIO
from app.models.database_model import GameData
from app.services.pgn_formatter_service import PgnFormatterService
from app.services.pgn_service import PgnService


class PgnCleaningService:
    """Service for cleaning PGN notation by removing various elements.
    
    This service provides methods to permanently remove comments, variations, annotations,
    non-standard tags, and results from PGN text while preserving metadata tags and moves.
    
    This service uses PgnFormatterService filtering logic to ensure consistent behavior
    and proper metadata protection.
    """
    
    @staticmethod
    def remove_comments_from_game(game: GameData) -> bool:
        """Remove comments from game's PGN.
        
        Args:
            game: GameData instance to clean.
            
        Returns:
            True if successful, False otherwise.
        """
        if not game or not game.pgn:
            return False
        
        try:
            # Use PgnFormatterService to remove comments (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_comments(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                return True
            return False
        except Exception:
            # On any error, return False
            return False
    
    @staticmethod
    def remove_variations_from_game(game: GameData) -> bool:
        """Remove variations from game's PGN.
        
        Args:
            game: GameData instance to clean.
            
        Returns:
            True if successful, False otherwise.
        """
        if not game or not game.pgn:
            return False
        
        try:
            # Use PgnFormatterService to remove variations (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_variations(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                return True
            return False
        except Exception:
            # On any error, return False
            return False
    
    @staticmethod
    def remove_non_standard_tags_from_game(game: GameData) -> bool:
        """Remove non-standard tags (like [%evp], [%mdl], [%clk]) from comments in game's PGN.
        
        Args:
            game: GameData instance to clean.
            
        Returns:
            True if successful, False otherwise.
        """
        if not game or not game.pgn:
            return False
        
        try:
            # Use PgnFormatterService to remove non-standard tags (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_non_standard_tags(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                return True
            return False
        except Exception:
            # On any error, return False
            return False
    
    @staticmethod
    def remove_annotations_from_game(game: GameData) -> bool:
        """Remove annotations (NAGs and move annotations like !, ?, !!, ??) from game's PGN.
        
        This removes both NAGs ($2, $4, etc.) and move annotations (!, ?, !!, ??, etc.)
        from the PGN text while preserving metadata tags.
        
        Args:
            game: GameData instance to clean.
            
        Returns:
            True if successful, False otherwise.
        """
        if not game or not game.pgn:
            return False
        
        try:
            # Use PgnFormatterService to remove annotations (preserves metadata tags)
            # This fixes the bug where annotations in metadata tags were being removed
            cleaned_pgn = PgnFormatterService._remove_annotations(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                return True
            return False
        except Exception:
            # On any error, return False
            return False
    
    @staticmethod
    def remove_results_from_game(game: GameData) -> bool:
        """Remove results (1-0, 0-1, 1/2-1/2, *) from game's PGN.
        
        This removes results from move notation while preserving the Result metadata tag.
        
        Args:
            game: GameData instance to clean.
            
        Returns:
            True if successful, False otherwise.
        """
        if not game or not game.pgn:
            return False
        
        try:
            # Use PgnFormatterService to remove results (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_results(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                return True
            return False
        except Exception:
            # On any error, return False
            return False

