"""Service for cleaning PGN notation by removing comments, variations, annotations, etc."""

import chess.pgn
from io import StringIO
from app.models.database_model import GameData
from app.services.pgn_formatter_service import PgnFormatterService
from app.services.pgn_service import PgnService
from app.services.logging_service import LoggingService


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
        
        # Get game identifier for debug logging
        game_id = f"#{game.game_number}" if hasattr(game, 'game_number') else "unknown"
        if hasattr(game, 'white') and hasattr(game, 'black') and (game.white or game.black):
            white = game.white or "?"
            black = game.black or "?"
            game_id = f"{game_id} {white} vs {black}"
        
        try:
            # Use PgnFormatterService to remove comments (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_comments(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                
                # Debug log: comments removed
                logging_service = LoggingService.get_instance()
                logging_service.debug(f"PGN element removed: game={game_id}, element_type=comments")
                
                return True
            
            # Debug log: removal failed
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal failed: game={game_id}, element_type=comments, reason=parse_failed")
            return False
        except Exception as e:
            # On any error, return False
            # Debug log: removal error
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal error: game={game_id}, element_type=comments, error={str(e)}")
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
        
        # Get game identifier for debug logging
        game_id = f"#{game.game_number}" if hasattr(game, 'game_number') else "unknown"
        if hasattr(game, 'white') and hasattr(game, 'black') and (game.white or game.black):
            white = game.white or "?"
            black = game.black or "?"
            game_id = f"{game_id} {white} vs {black}"
        
        try:
            # Use PgnFormatterService to remove variations (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_variations(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                # Validate that the parsed game has moves (not just headers)
                # Count moves in the mainline to ensure we didn't lose the game
                mainline_moves = list(chess_game.mainline())
                if len(mainline_moves) == 0:
                    # No moves parsed - this suggests the cleaned PGN is malformed
                    # Return False to indicate failure
                    logging_service = LoggingService.get_instance()
                    logging_service.debug(f"PGN element removal failed: game={game_id}, element_type=variations, reason=no_moves_parsed")
                    return False
                
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                
                # Debug log: variations removed
                logging_service = LoggingService.get_instance()
                logging_service.debug(f"PGN element removed: game={game_id}, element_type=variations")
                
                return True
            
            # Debug log: removal failed
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal failed: game={game_id}, element_type=variations, reason=parse_failed")
            return False
        except Exception as e:
            # On any error, return False
            # Log the error for debugging
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error removing variations: {e}", exc_info=e)
            logging_service.debug(f"PGN element removal error: game={game_id}, element_type=variations, error={str(e)}")
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
        
        # Get game identifier for debug logging
        game_id = f"#{game.game_number}" if hasattr(game, 'game_number') else "unknown"
        if hasattr(game, 'white') and hasattr(game, 'black') and (game.white or game.black):
            white = game.white or "?"
            black = game.black or "?"
            game_id = f"{game_id} {white} vs {black}"
        
        try:
            # Use PgnFormatterService to remove non-standard tags (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_non_standard_tags(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                
                # Debug log: non-standard tags removed
                logging_service = LoggingService.get_instance()
                logging_service.debug(f"PGN element removed: game={game_id}, element_type=non_standard_tags")
                
                return True
            
            # Debug log: removal failed
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal failed: game={game_id}, element_type=non_standard_tags, reason=parse_failed")
            return False
        except Exception as e:
            # On any error, return False
            # Debug log: removal error
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal error: game={game_id}, element_type=non_standard_tags, error={str(e)}")
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
        
        # Get game identifier for debug logging
        game_id = f"#{game.game_number}" if hasattr(game, 'game_number') else "unknown"
        if hasattr(game, 'white') and hasattr(game, 'black') and (game.white or game.black):
            white = game.white or "?"
            black = game.black or "?"
            game_id = f"{game_id} {white} vs {black}"
        
        try:
            # Use PgnFormatterService to remove annotations (preserves metadata tags)
            # This fixes the bug where annotations in metadata tags were being removed
            cleaned_pgn = PgnFormatterService._remove_annotations(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                
                # Debug log: annotations removed
                logging_service = LoggingService.get_instance()
                logging_service.debug(f"PGN element removed: game={game_id}, element_type=annotations")
                
                return True
            
            # Debug log: removal failed
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal failed: game={game_id}, element_type=annotations, reason=parse_failed")
            return False
        except Exception as e:
            # On any error, return False
            # Debug log: removal error
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal error: game={game_id}, element_type=annotations, error={str(e)}")
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
        
        # Get game identifier for debug logging
        game_id = f"#{game.game_number}" if hasattr(game, 'game_number') else "unknown"
        if hasattr(game, 'white') and hasattr(game, 'black') and (game.white or game.black):
            white = game.white or "?"
            black = game.black or "?"
            game_id = f"{game_id} {white} vs {black}"
        
        try:
            # Use PgnFormatterService to remove results (preserves metadata tags)
            cleaned_pgn = PgnFormatterService._remove_results(game.pgn)
            
            # Re-export through PgnService to apply proper formatting
            pgn_io = StringIO(cleaned_pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if chess_game:
                game.pgn = PgnService.export_game_to_pgn(chess_game)
                
                # Debug log: results removed
                logging_service = LoggingService.get_instance()
                logging_service.debug(f"PGN element removed: game={game_id}, element_type=results")
                
                return True
            
            # Debug log: removal failed
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal failed: game={game_id}, element_type=results, reason=parse_failed")
            return False
        except Exception as e:
            # On any error, return False
            # Debug log: removal error
            logging_service = LoggingService.get_instance()
            logging_service.debug(f"PGN element removal error: game={game_id}, element_type=results, error={str(e)}")
            return False

