"""Service for storing and loading game analysis results in PGN tags."""

import json
import gzip
import zlib
import base64
import hashlib
from typing import List, Optional, Dict, Any
from io import StringIO
from datetime import datetime

import chess.pgn

from app.models.moveslist_model import MoveData
from app.services.pgn_service import PgnService
from app.models.database_model import GameData
from app.services.logging_service import LoggingService


class AnalysisDataStorageService:
    """Service for storing and loading game analysis results in PGN tags.
    
    This service handles serialization, compression, and storage of analysis data
    in a custom PGN tag [CARAAnalysisData "..."] for persistence across sessions.
    Also stores [CARAAnalysisInfo "..."] with app version and datetime, and
    [CARAAnalysisChecksum "..."] for data integrity validation.
    """
    
    TAG_NAME = "CARAAnalysisData"
    TAG_INFO = "CARAAnalysisInfo"
    TAG_CHECKSUM = "CARAAnalysisChecksum"
    
    @staticmethod
    def has_analysis_data(game: GameData) -> bool:
        """Check if game has stored analysis data.
        
        Args:
            game: GameData instance to check.
            
        Returns:
            True if CARAAnalysisData tag exists, False otherwise.
        """
        # Check if game is None or has no PGN
        if game is None or not hasattr(game, 'pgn') or game.pgn is None:
            return False
        
        try:
            # Parse PGN to check for tag
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            # Check if tag exists
            return AnalysisDataStorageService.TAG_NAME in chess_game.headers
        except Exception:
            # On any error, return False
            return False
    
    @staticmethod
    def get_raw_analysis_data(game: GameData) -> Optional[str]:
        """Get raw decompressed JSON string from CARAAnalysisData tag.
        
        Args:
            game: GameData instance to read from.
            
        Returns:
            Decompressed JSON string if tag exists and is valid, None otherwise.
        """
        # Check if game is None or has no PGN
        if game is None or not hasattr(game, 'pgn') or game.pgn is None:
            return None
        
        try:
            # Parse PGN to read tag
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return None
            
            # Check if tag exists
            if AnalysisDataStorageService.TAG_NAME not in chess_game.headers:
                return None
            
            # Get encoded data
            encoded = chess_game.headers[AnalysisDataStorageService.TAG_NAME]
            
            # Base64 decode
            compressed = base64.b64decode(encoded.encode('ascii'))
            
            # Decompress
            try:
                json_str = gzip.decompress(compressed).decode('utf-8')
            except (gzip.BadGzipFile, OSError, zlib.error) as e:
                # Decompression error
                raise ValueError(f"Analysis data decompression failed: {e}") from e
            
            return json_str
        except Exception:
            # On any error, return None
            return None
    
    @staticmethod
    def store_analysis_data(game: GameData, moves: List[MoveData], config: Optional[Dict[str, Any]] = None) -> bool:
        """Store analysis data in PGN tag.
        
        Args:
            game: GameData instance to update.
            moves: List of MoveData instances to store.
            config: Optional configuration dictionary to get app version.
            
        Returns:
            True if storage was successful, False otherwise.
        """
        try:
            # Serialize moves to JSON
            moves_data = []
            for move in moves:
                move_dict = {
                    "move_number": move.move_number,
                    "white_move": move.white_move,
                    "black_move": move.black_move,
                    "eval_white": move.eval_white,
                    "eval_black": move.eval_black,
                    "cpl_white": move.cpl_white,
                    "cpl_black": move.cpl_black,
                    "cpl_white_2": move.cpl_white_2,
                    "cpl_white_3": move.cpl_white_3,
                    "cpl_black_2": move.cpl_black_2,
                    "cpl_black_3": move.cpl_black_3,
                    "assess_white": move.assess_white,
                    "assess_black": move.assess_black,
                    "best_white": move.best_white,
                    "best_black": move.best_black,
                    "best_white_2": move.best_white_2,
                    "best_white_3": move.best_white_3,
                    "best_black_2": move.best_black_2,
                    "best_black_3": move.best_black_3,
                    "white_is_top3": move.white_is_top3,
                    "black_is_top3": move.black_is_top3,
                    "white_depth": move.white_depth,
                    "black_depth": move.black_depth,
                    "white_seldepth": move.white_seldepth,
                    "black_seldepth": move.black_seldepth,
                    "eco": move.eco,
                    "opening_name": move.opening_name,
                    "comment": move.comment,
                    "white_capture": move.white_capture,
                    "black_capture": move.black_capture,
                    "white_material": move.white_material,
                    "black_material": move.black_material,
                    "white_queens": move.white_queens,
                    "white_rooks": move.white_rooks,
                    "white_bishops": move.white_bishops,
                    "white_knights": move.white_knights,
                    "white_pawns": move.white_pawns,
                    "black_queens": move.black_queens,
                    "black_rooks": move.black_rooks,
                    "black_bishops": move.black_bishops,
                    "black_knights": move.black_knights,
                    "black_pawns": move.black_pawns,
                    "fen_white": move.fen_white,
                    "fen_black": move.fen_black
                }
                moves_data.append(move_dict)
            
            # Convert to JSON string
            json_str = json.dumps(moves_data, ensure_ascii=False)
            
            # Calculate checksum (SHA256 hash of JSON string)
            checksum = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
            
            # Compress with gzip (level 9 for maximum compression)
            compressed = gzip.compress(json_str.encode('utf-8'), compresslevel=9)
            
            # Base64 encode
            encoded = base64.b64encode(compressed).decode('ascii')
            
            # Get app version from config
            app_version = config.get('version', '1.0') if config else '1.0'
            
            # Get current datetime (readable format)
            current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Create info string
            info_str = f"App Version: {app_version}, Created: {current_datetime}"
            
            # Parse PGN to add/update tags
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return False
            
            # Add or update the tags
            chess_game.headers[AnalysisDataStorageService.TAG_NAME] = encoded
            chess_game.headers[AnalysisDataStorageService.TAG_INFO] = info_str
            chess_game.headers[AnalysisDataStorageService.TAG_CHECKSUM] = checksum
            
            # Regenerate PGN text
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            
            # Update game's PGN
            game.pgn = new_pgn
            
            # Update analyzed field
            game.analyzed = True
            
            return True
        except Exception as e:
            # On any error, return False
            # Log error for debugging
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error storing analysis data: {e}", exc_info=e)
            return False
    
    @staticmethod
    def load_analysis_data(game: GameData) -> Optional[List[MoveData]]:
        """Load analysis data from PGN tag.
        
        Args:
            game: GameData instance to read from.
            
        Returns:
            List of MoveData instances if tag exists and is valid, None otherwise.
            Returns None if checksum validation fails.
        """
        # Check if game is None or has no PGN
        if game is None or not hasattr(game, 'pgn') or game.pgn is None:
            return None
        
        try:
            # Parse PGN to read tag
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return None
            
            # Check if tag exists
            if AnalysisDataStorageService.TAG_NAME not in chess_game.headers:
                return None
            
            # Get encoded data
            encoded = chess_game.headers[AnalysisDataStorageService.TAG_NAME]
            
            # Base64 decode
            compressed = base64.b64decode(encoded.encode('ascii'))
            
            # Decompress
            try:
                json_str = gzip.decompress(compressed).decode('utf-8')
            except (gzip.BadGzipFile, OSError, zlib.error) as e:
                # Decompression error detected - remove corrupted tags from game
                AnalysisDataStorageService._remove_corrupted_analysis_tags(game)
                # Re-raise as a more specific exception for decompression errors
                # OSError/zlib.error is raised for errors like "Error -3 while decompressing data: invalid code lengths set"
                raise ValueError(f"Analysis data decompression failed: {e}") from e
            
            # Verify checksum if present
            if AnalysisDataStorageService.TAG_CHECKSUM in chess_game.headers:
                stored_checksum = chess_game.headers[AnalysisDataStorageService.TAG_CHECKSUM]
                calculated_checksum = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
                
                if stored_checksum != calculated_checksum:
                    # Checksum mismatch - data may be corrupted
                    # Remove corrupted tags from game
                    AnalysisDataStorageService._remove_corrupted_analysis_tags(game)
                    logging_service = LoggingService.get_instance()
                    logging_service.warning(f"Analysis data checksum mismatch. Stored: {stored_checksum[:16]}..., Calculated: {calculated_checksum[:16]}...")
                    return None
            
            # Deserialize JSON
            moves_data = json.loads(json_str)
            
            # Convert to MoveData instances
            moves = []
            for move_dict in moves_data:
                move = MoveData(
                    move_number=move_dict.get("move_number", 0),
                    white_move=move_dict.get("white_move", ""),
                    black_move=move_dict.get("black_move", ""),
                    eval_white=move_dict.get("eval_white", ""),
                    eval_black=move_dict.get("eval_black", ""),
                    cpl_white=move_dict.get("cpl_white", ""),
                    cpl_black=move_dict.get("cpl_black", ""),
                    cpl_white_2=move_dict.get("cpl_white_2", ""),
                    cpl_white_3=move_dict.get("cpl_white_3", ""),
                    cpl_black_2=move_dict.get("cpl_black_2", ""),
                    cpl_black_3=move_dict.get("cpl_black_3", ""),
                    assess_white=move_dict.get("assess_white", ""),
                    assess_black=move_dict.get("assess_black", ""),
                    best_white=move_dict.get("best_white", ""),
                    best_black=move_dict.get("best_black", ""),
                    best_white_2=move_dict.get("best_white_2", ""),
                    best_white_3=move_dict.get("best_white_3", ""),
                    best_black_2=move_dict.get("best_black_2", ""),
                    best_black_3=move_dict.get("best_black_3", ""),
                    white_is_top3=move_dict.get("white_is_top3", False),
                    black_is_top3=move_dict.get("black_is_top3", False),
                    white_depth=move_dict.get("white_depth", 0),
                    black_depth=move_dict.get("black_depth", 0),
                    white_seldepth=move_dict.get("white_seldepth", 0),
                    black_seldepth=move_dict.get("black_seldepth", 0),
                    eco=move_dict.get("eco", ""),
                    opening_name=move_dict.get("opening_name", ""),
                    comment=move_dict.get("comment", ""),
                    white_capture=move_dict.get("white_capture", ""),
                    black_capture=move_dict.get("black_capture", ""),
                    white_material=move_dict.get("white_material", 0),
                    black_material=move_dict.get("black_material", 0),
                    white_queens=move_dict.get("white_queens", 0),
                    white_rooks=move_dict.get("white_rooks", 0),
                    white_bishops=move_dict.get("white_bishops", 0),
                    white_knights=move_dict.get("white_knights", 0),
                    white_pawns=move_dict.get("white_pawns", 0),
                    black_queens=move_dict.get("black_queens", 0),
                    black_rooks=move_dict.get("black_rooks", 0),
                    black_bishops=move_dict.get("black_bishops", 0),
                    black_knights=move_dict.get("black_knights", 0),
                    black_pawns=move_dict.get("black_pawns", 0),
                    fen_white=move_dict.get("fen_white", ""),
                    fen_black=move_dict.get("fen_black", "")
                )
                moves.append(move)
            
            return moves
        except ValueError as e:
            # Re-raise ValueError (decompression errors) so controller can handle them
            raise
        except Exception as e:
            # On any other error, return None silently
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error loading analysis data: {e}", exc_info=e)
            return None
    
    @staticmethod
    def _remove_corrupted_analysis_tags(game: GameData) -> None:
        """Remove corrupted analysis tags from a game's PGN.
        
        This method is called when analysis data cannot be decompressed,
        indicating the tags are corrupted. It removes all three analysis tags
        (CARAAnalysisData, CARAAnalysisInfo, CARAAnalysisChecksum) from the game's PGN.
        
        Args:
            game: GameData instance to clean up.
        """
        try:
            # Check if game has PGN
            if not game or not hasattr(game, 'pgn') or not game.pgn:
                return
            
            # Parse the current PGN
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                return
            
            # Check if any analysis tags exist
            has_analysis_tags = (
                AnalysisDataStorageService.TAG_NAME in chess_game.headers or
                AnalysisDataStorageService.TAG_INFO in chess_game.headers or
                AnalysisDataStorageService.TAG_CHECKSUM in chess_game.headers
            )
            
            if not has_analysis_tags:
                return
            
            # Remove all three analysis tags
            if AnalysisDataStorageService.TAG_NAME in chess_game.headers:
                del chess_game.headers[AnalysisDataStorageService.TAG_NAME]
            if AnalysisDataStorageService.TAG_INFO in chess_game.headers:
                del chess_game.headers[AnalysisDataStorageService.TAG_INFO]
            if AnalysisDataStorageService.TAG_CHECKSUM in chess_game.headers:
                del chess_game.headers[AnalysisDataStorageService.TAG_CHECKSUM]
            
            # Regenerate PGN text
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            
            # Update game's PGN
            game.pgn = new_pgn
            
            # Update analyzed field
            game.analyzed = False
        except Exception:
            # On any error, silently ignore (don't break the loading process)
            pass

