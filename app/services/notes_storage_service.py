"""Service for storing and loading game notes in PGN tags."""

from typing import Optional, Dict, Any
from io import StringIO
from datetime import datetime

import chess.pgn

from app.models.database_model import GameData
from app.services.pgn_service import PgnService
from app.services.logging_service import LoggingService
from app.utils.pgn_tag_compression import (
    decode_and_decompress_to_str,
    compress_and_encode_from_str,
    compute_checksum,
)


class NotesStorageService:
    """Service for storing and loading game notes in PGN tags.

    Uses [CARANotes "..."] with gzip+base64 encoding (same as annotations/analysis).
    Optional [CARANotesInfo "..."] and [CARANotesChecksum "..."] for consistency.
    """

    TAG_NAME = "CARANotes"
    TAG_INFO = "CARANotesInfo"
    TAG_CHECKSUM = "CARANotesChecksum"

    @staticmethod
    def has_notes(game: GameData) -> bool:
        """Return True if game has a CARANotes tag."""
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return False
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            return chess_game is not None and NotesStorageService.TAG_NAME in chess_game.headers
        except Exception:
            return False

    @staticmethod
    def load_notes(game: GameData) -> str:
        """Load notes from game PGN. Caches result in game.notes. Returns "" if none or on error."""
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return ""
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if not chess_game or NotesStorageService.TAG_NAME not in chess_game.headers:
                game.notes = ""
                game.has_notes = False
                return ""
            encoded = chess_game.headers[NotesStorageService.TAG_NAME]
            text = decode_and_decompress_to_str(encoded)
            if NotesStorageService.TAG_CHECKSUM in chess_game.headers:
                stored = chess_game.headers[NotesStorageService.TAG_CHECKSUM]
                if compute_checksum(text.encode("utf-8")) != stored:
                    LoggingService.get_instance().warning("Notes checksum mismatch.")
                    NotesStorageService._remove_notes_tags(game)
                    game.notes = ""
                    game.has_notes = False
                    return ""
            game.notes = text
            game.has_notes = bool(text.strip())
            return text
        except ValueError:
            NotesStorageService._remove_notes_tags(game)
            game.notes = ""
            game.has_notes = False
            return ""
        except Exception:
            game.notes = ""
            game.has_notes = False
            return ""

    @staticmethod
    def store_notes(game: GameData, text: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """Store notes in game PGN (in memory). Returns True on success."""
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return False
        try:
            data_bytes = text.encode("utf-8")
            checksum = compute_checksum(data_bytes)
            encoded = compress_and_encode_from_str(text, compresslevel=9)
            app_version = (config or {}).get("version", "1.0")
            info_str = f"App Version: {app_version}, Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if not chess_game:
                return False
            chess_game.headers[NotesStorageService.TAG_NAME] = encoded
            chess_game.headers[NotesStorageService.TAG_INFO] = info_str
            chess_game.headers[NotesStorageService.TAG_CHECKSUM] = checksum
            game.pgn = PgnService.export_game_to_pgn(chess_game)
            game.notes = text
            game.has_notes = bool(text and text.strip())
            return True
        except Exception as e:
            LoggingService.get_instance().error(f"Error storing notes: {e}", exc_info=e)
            return False

    @staticmethod
    def clear_notes(game: GameData) -> bool:
        """Remove CARANotes tags from game PGN (in memory). Sets game.notes = \"\"."""
        if game is None or not hasattr(game, "pgn") or game.pgn is None:
            return False
        NotesStorageService._remove_notes_tags(game)
        game.notes = ""
        game.has_notes = False
        return True

    @staticmethod
    def _remove_notes_tags(game: GameData) -> None:
        """Remove CARANotes* tags from game PGN."""
        try:
            pgn_io = StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            if not chess_game:
                return
            for key in (NotesStorageService.TAG_NAME, NotesStorageService.TAG_INFO, NotesStorageService.TAG_CHECKSUM):
                if key in chess_game.headers:
                    del chess_game.headers[key]
            game.pgn = PgnService.export_game_to_pgn(chess_game)
        except Exception:
            pass
