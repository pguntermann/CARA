"""Book move service for detecting opening book moves using ECO and Polyglot formats."""

import chess
import chess.polyglot
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.services.opening_service import OpeningService


class BookMoveService:
    """Service for detecting if moves are in opening books (ECO or Polyglot format).
    
    This service provides a hybrid approach:
    1. First checks ECO database (position-based lookup)
    2. Then checks Polyglot opening books (move-based lookup)
    """
    
    def __init__(self, config: Dict[str, Any], opening_service: OpeningService) -> None:
        """Initialize the book move service.
        
        Args:
            config: Configuration dictionary.
            opening_service: OpeningService instance for ECO lookup.
        """
        self.config = config
        self.opening_service = opening_service
        self._polyglot_readers: List[chess.polyglot.PolyglotReader] = []
        self._is_loaded = False
        
        # Load Polyglot books if enabled
        book_config = config.get("game_analysis", {}).get("book_move_detection", {})
        if book_config.get("use_opening_book", False):
            self._load_polyglot_books()
    
    def _load_polyglot_books(self) -> None:
        """Load Polyglot opening book files."""
        if self._is_loaded:
            return
        
        book_config = self.config.get("game_analysis", {}).get("book_move_detection", {})
        book_files = book_config.get("opening_book_files", [])
        books_path_str = self.config.get("resources", {}).get("opening_books_path", "app/resources/openingbooks/lpb")
        
        # Resolve path relative to app root
        app_root = Path(__file__).parent.parent.parent
        books_path = app_root / books_path_str
        
        if not books_path.exists():
            self._is_loaded = True
            return
        
        # Load each book file
        for book_file_name in book_files:
            book_file_path = books_path / book_file_name
            if book_file_path.exists() and book_file_path.is_file():
                try:
                    reader = chess.polyglot.open_reader(str(book_file_path))
                    self._polyglot_readers.append(reader)
                except Exception:
                    # Silently skip files that can't be opened
                    continue
        
        self._is_loaded = True
    
    def is_book_move(self, board: chess.Board, move: chess.Move) -> bool:
        """Check if a move is in the opening book (ECO or Polyglot).
        
        Args:
            board: Chess board position before the move.
            move: Move to check.
            
        Returns:
            True if the move is in the book, False otherwise.
        """
        # 1. Check ECO database first (position-based)
        # Note: ECO lookup is position-based, so we check if the position
        # after the move is in ECO database
        board_copy = board.copy()
        board_copy.push(move)
        fen_after = board_copy.fen().split(' ')[0]  # Just position part
        
        eco_info = self.opening_service.get_opening_info(fen_after)
        if eco_info[0] is not None:  # ECO code found
            return True
        
        # 2. Check Polyglot books (move-based)
        for reader in self._polyglot_readers:
            try:
                for entry in reader.find_all(board):
                    # Compare moves - check exact match first
                    if entry.move == move:
                        return True
                    # Also check by from/to squares and promotion
                    if (entry.move.from_square == move.from_square and
                        entry.move.to_square == move.to_square and
                        entry.move.promotion == move.promotion):
                        return True
            except Exception:
                # Silently handle errors (book might not have position)
                continue
        
        return False
    
    def close(self) -> None:
        """Close all Polyglot book readers."""
        for reader in self._polyglot_readers:
            try:
                reader.close()
            except Exception:
                pass
        self._polyglot_readers.clear()
        self._is_loaded = False

