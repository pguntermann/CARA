"""Game controller for managing active game operations."""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import chess
import chess.pgn
import io

from app.models.game_model import GameModel
from app.models.database_model import GameData
from app.models.moveslist_model import MoveData, MovesListModel
from app.utils.material_tracker import get_captured_piece_letter, calculate_material_count, count_pieces
from app.controllers.board_controller import BoardController
from app.services.opening_service import OpeningService
from app.services.logging_service import LoggingService


@dataclass
class GameInfo:
    """Processed game information for display."""
    white_name: str
    black_name: str
    white_elo: int
    black_elo: int
    result: str
    eco: str
    opening_name: str


class GameController:
    """Controller for managing active game operations.
    
    This controller orchestrates game-related operations and manages
    the game model.
    """
    
    def __init__(self, config: Dict[str, Any], board_controller: BoardController) -> None:
        """Initialize the game controller.
        
        Args:
            config: Configuration dictionary.
            board_controller: BoardController instance for updating board position.
        """
        self.config = config
        self.board_controller = board_controller
        
        # Initialize opening service
        self.opening_service = OpeningService(config)
        self.opening_service.load()
        
        # Get opening repeat indicator from config
        self.opening_repeat_indicator = config.get('resources', {}).get('opening_repeat_indicator', '*')
        
        # Initialize game model
        self.game_model = GameModel()
    
    def get_game_model(self) -> GameModel:
        """Get the game model.
        
        Returns:
            The GameModel instance for observing active game state.
        """
        return self.game_model
    
    def set_active_game(self, game: GameData) -> None:
        """Set a game as active and load its starting position to the board.
        
        Args:
            game: GameData instance to set as active.
        """
        # Set the active game in the model
        self.game_model.set_active_game(game)
        
        # Reset active move to starting position
        self.game_model.set_active_move_ply(0)
        
        # Check if game has stored analysis data and set flag accordingly
        # Only set flag if data loads successfully (checksum validates)
        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        try:
            stored_moves = AnalysisDataStorageService.load_analysis_data(game)
            if stored_moves is not None:
                # Game has stored analysis data that loaded successfully (checksum validated)
                # Set flag to enable game summary
                self.game_model.set_is_game_analyzed(True)
        except ValueError as e:
            # Decompression error - show warning message
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            progress_service.set_status("Warning: Analysis data could not be restored (corrupted or invalid)")
        
        # Load the game's starting position to the board
        self._load_game_to_board(game)
    
    def refresh_active_game_analysis_state(self, moves_list_model: Optional[MovesListModel] = None) -> None:
        """Refresh the active game's analysis state after bulk analysis or external storage update.
        
        If the active game now has analysis data in storage, loads it into the moves list
        and sets is_game_analyzed so the Game Summary tab becomes available.
        
        Args:
            moves_list_model: Optional MovesListModel to populate with loaded analysis.
                             If None, only the is_game_analyzed flag is updated.
        """
        active_game = self.game_model.active_game
        if active_game is None:
            return
        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        if not AnalysisDataStorageService.has_analysis_data(active_game):
            return
        try:
            stored_moves = AnalysisDataStorageService.load_analysis_data(active_game)
        except ValueError:
            return
        if not stored_moves:
            return
        if moves_list_model is not None:
            current_ply = self.game_model.get_active_move_ply()
            moves_list_model.clear()
            for move in stored_moves:
                moves_list_model.add_move(move)
            moves_list_model.set_active_move_ply(current_ply)
        self.game_model.set_is_game_analyzed(True)
    
    def _load_game_to_board(self, game: GameData) -> None:
        """Load a game's starting position to the board.
        
        Args:
            game: GameData instance containing the game to load.
        """
        try:
            # Parse the PGN to get the game
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                # Invalid PGN, reset to starting position
                self.board_controller.reset_board()
                return
            
            # Get the starting position from the game
            # If there's a FEN header, use it; otherwise use standard starting position
            headers = chess_game.headers
            
            # Check for FEN header (SetUp "1" indicates custom position)
            if headers.get("SetUp") == "1" and "FEN" in headers:
                fen = headers.get("FEN")
                # Load the custom starting position
                self.board_controller.set_fen_with_validation(fen)
            else:
                # Standard starting position - reset the board
                self.board_controller.reset_board()
            
        except Exception:
            # If parsing fails, reset to starting position
            self.board_controller.reset_board()
    
    def clear_active_game(self) -> None:
        """Clear the active game."""
        self.game_model.clear_active_game()
        # Active move is already reset in clear_active_game()
    
    def navigate_to_next_move(self) -> bool:
        """Navigate to the next move in the active game.
        
        Returns:
            True if navigation was successful, False if already at last move or no game.
        """
        game = self.game_model.active_game
        if game is None:
            return False
        
        try:
            # Parse the PGN to get the game
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return False
            
            # Count total plies in the game
            total_plies = 0
            node = chess_game
            while node.variations:
                node = node.variation(0)
                total_plies += 1
            
            # Get current ply index
            current_ply = self.game_model.get_active_move_ply()
            
            # Check if we can move forward
            if current_ply >= total_plies:
                return False
            
            # Move to next ply
            new_ply = current_ply + 1
            self.game_model.set_active_move_ply(new_ply)
            
            # Update board position to the new move
            self._update_board_to_ply(chess_game, new_ply)
            
            return True
            
        except Exception:
            return False
    
    def navigate_to_previous_move(self) -> bool:
        """Navigate to the previous move in the active game.
        
        Returns:
            True if navigation was successful, False if already at first move or no game.
        """
        game = self.game_model.active_game
        if game is None:
            return False
        
        try:
            # Parse the PGN to get the game
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return False
            
            # Get current ply index
            current_ply = self.game_model.get_active_move_ply()
            
            # Check if we can move backward
            if current_ply <= 0:
                return False
            
            # Move to previous ply
            new_ply = current_ply - 1
            self.game_model.set_active_move_ply(new_ply)
            
            # Update board position to the new move
            self._update_board_to_ply(chess_game, new_ply)
            
            return True
            
        except Exception:
            return False
    
    def navigate_to_ply(self, ply_index: int) -> bool:
        """Navigate to a specific ply index in the active game.
        
        Args:
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
            
        Returns:
            True if navigation was successful, False if no game or invalid ply.
        """
        game = self.game_model.active_game
        if game is None:
            return False
        
        try:
            # Parse the PGN to get the game
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return False
            
            # Count total plies in the game
            total_plies = 0
            node = chess_game
            while node.variations:
                node = node.variation(0)
                total_plies += 1
            
            # Check if ply_index is valid
            if ply_index < 0 or ply_index > total_plies:
                return False
            
            # Set active move ply
            self.game_model.set_active_move_ply(ply_index)
            
            # Update board position to the new move
            self._update_board_to_ply(chess_game, ply_index)
            
            return True
            
        except Exception:
            return False
    
    def validate_and_clamp_active_move_ply(self) -> bool:
        """Validate and clamp the active move ply to the current game length.
        
        This should be called after the PGN is permanently modified to ensure
        the active_move_ply is still valid. If it's out of bounds, it will be
        clamped to the maximum valid ply.
        
        Returns:
            True if validation/clamping was successful, False if no game or parsing failed.
        """
        game = self.game_model.active_game
        if game is None:
            return False
        
        try:
            # Parse the PGN to get the game
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                # If parsing fails, don't modify state - just return False
                return False
            
            # Count total plies in the game
            total_plies = 0
            node = chess_game
            while node.variations:
                node = node.variation(0)
                total_plies += 1
            
            # Get current ply index
            current_ply = self.game_model.get_active_move_ply()
            
            # Only clamp if out of bounds - don't change if already valid
            if current_ply < 0:
                new_ply = 0
            elif current_ply > total_plies:
                new_ply = total_plies
            else:
                # Already valid, just update board position to current ply
                # Don't change active_move_ply to avoid unnecessary signal emissions
                self._update_board_to_ply(chess_game, current_ply)
                return True
            
            # Only update if we actually need to clamp
            if new_ply != current_ply:
                self.game_model.set_active_move_ply(new_ply)
                # Update board position to the clamped ply
                self._update_board_to_ply(chess_game, new_ply)
            
            return True
            
        except Exception:
            # If anything fails, don't modify state - just return False
            return False
    
    def _update_board_to_ply(self, chess_game: chess.pgn.Game, ply_index: int) -> None:
        """Update board position to a specific ply index.
        
        Args:
            chess_game: The parsed chess game.
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
        """
        try:
            if ply_index == 0:
                # Reset to starting position
                headers = chess_game.headers
                if headers.get("SetUp") == "1" and "FEN" in headers:
                    fen = headers.get("FEN")
                    self.board_controller.set_fen_with_validation(fen, last_move=None)
                else:
                    self.board_controller.reset_board()
            else:
                # Navigate to the ply_index-th move
                # When ply_index = 1, we want to show the position after the first move
                # and highlight that first move (e.g., e4)
                # When ply_index = 2, we want to show the position after the second move
                # and highlight that second move (e.g., e6)
                node = chess_game
                last_move = None
                
                # Navigate through the game tree to reach the target ply
                # We need to capture the move that was played to reach the target position
                # In python-chess, each node has a .move property that is the move that led TO this node
                # So after navigating to a node, node.move is the move that got us there
                # But we need to capture it BEFORE moving, so we get it from the variation
                for i in range(ply_index):
                    if not node.variations:
                        break
                    # Get the move that leads FROM the current node TO the next node
                    # node.variation(0) returns the child node
                    # node.variation(0).move gives us the move property of the child node
                    # which is the move that leads FROM the current node TO the child
                    # This is the move that was played to reach the next position
                    # CRITICAL: We capture the move BEFORE moving to ensure we get the correct one
                    move_played = node.variation(0).move
                    # Move to the next node
                    node = node.variation(0)
                    # Store the move - this will be overwritten each iteration
                    # The final value will be the move that got us to the target position
                    # For ply_index = 1: i=0, we get e4 (move from root to first child), move to node after e4, last_move = e4
                    # For ply_index = 2: i=0 gets e4, i=1 gets e6 (move from node after e4 to node after e6), last_move = e6
                    last_move = move_played
                
                # Get the FEN from the node's board position (after the move)
                fen = node.board().fen()
                
                # CRITICAL: last_move should be the move that was played to reach THIS position
                # If we're at ply_index = 1, last_move should be e4 (the first move)
                # If we're at ply_index = 2, last_move should be e6 (the second move)
                # The arrow should show the move that got us to where we are, not the next move
                self.board_controller.set_fen_with_validation(fen, last_move=last_move)
        except Exception:
            # If navigation fails, reset to starting position
            self.board_controller.reset_board()
    
    def _navigate_to_ply_in_game(self, chess_game: chess.pgn.Game, ply_index: int) -> Optional[chess.pgn.GameNode]:
        """Navigate to a specific ply index in a chess game.
        
        Args:
            chess_game: The parsed chess game.
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
            
        Returns:
            The game node at the specified ply index, or None if invalid.
        """
        if ply_index < 0:
            return None
        
        node = chess_game
        for i in range(ply_index):
            if not node.variations:
                return None
            node = node.variation(0)
        
        return node
    
    def _parse_move_from_san_at_position(self, board: chess.Board, san_string: str) -> Optional[chess.Move]:
        """Parse a move from SAN notation at a specific board position.
        
        Args:
            board: The chess board at the position to parse from.
            san_string: Move in SAN notation (e.g., "e4", "Nf3").
            
        Returns:
            The parsed Move object, or None if invalid.
        """
        if not san_string or not san_string.strip():
            return None
        
        try:
            return board.parse_san(san_string.strip())
        except (ValueError, chess.InvalidMoveError):
            return None
    
    def _is_white_turn_at_ply(self, ply_index: int) -> bool:
        """Determine if it's White's turn at a specific ply index.
        
        Args:
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
            
        Returns:
            True if it's White's turn, False if Black's turn.
        """
        # If ply_index is odd (1, 3, 5...), it's after a white move, so white is to move next
        # If ply_index is even (2, 4, 6...), it's after a black move, so black is to move next
        return (ply_index % 2 == 1)
    
    def _calculate_row_from_ply(self, ply_index: int) -> int:
        """Calculate the movelist row index from a ply index.
        
        Args:
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
            
        Returns:
            Row index in the movelist (0-based).
        """
        # ply_index 1 -> row 0 (after white's first move)
        # ply_index 2 -> row 0 (after black's first move)
        # ply_index 3 -> row 1 (after white's second move)
        # ply_index 4 -> row 1 (after black's second move)
        return (ply_index - 1) // 2
    
    def update_best_alternative_move(self, ply_index: int, moveslist_model) -> None:
        """Update best alternative move from movelist based on current position.
        
        This method calculates the best alternative move for the current position
        by looking up the move data in the movelist and parsing the best move
        from the position before the current move.
        
        Args:
            ply_index: Ply index of the current position (0 = starting position).
            moveslist_model: MovesListModel instance containing move data.
        """
        board_model = self.board_controller.get_board_model()
        
        # If at starting position (ply_index = 0), clear the best alternative move
        if ply_index == 0:
            board_model.set_best_alternative_move(None)
            return
        
        # Calculate row index in movelist
        row = self._calculate_row_from_ply(ply_index)
        
        # Validate row index
        if row < 0 or row >= moveslist_model.rowCount():
            board_model.set_best_alternative_move(None)
            return
        
        # Get move data for this row
        move_data = moveslist_model.get_move(row)
        if not move_data:
            board_model.set_best_alternative_move(None)
            return
        
        # Determine whose turn it is and get the appropriate best move
        is_white_turn = self._is_white_turn_at_ply(ply_index)
        best_move_san = move_data.best_white if is_white_turn else move_data.best_black
        
        # If no best move is available, clear it
        if not best_move_san or not best_move_san.strip():
            board_model.set_best_alternative_move(None)
            return
        
        # Get the active game
        active_game = self.game_model.active_game
        if not active_game:
            board_model.set_best_alternative_move(None)
            return
        
        # Parse the game to get the position before the move
        try:
            pgn_io = io.StringIO(active_game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if not chess_game:
                board_model.set_best_alternative_move(None)
                return
            
            # Navigate to the position BEFORE the move (ply_index - 1)
            # This is the position from which the best alternative move should be parsed
            node_before = self._navigate_to_ply_in_game(chess_game, ply_index - 1)
            if node_before is None:
                board_model.set_best_alternative_move(None)
                return
            
            # Get the board position before the move
            board_before = node_before.board()
            
            # Parse the best move from the position before the move
            best_move = self._parse_move_from_san_at_position(board_before, best_move_san)
            if best_move is None:
                board_model.set_best_alternative_move(None)
                return
            
            # Set the best alternative move
            board_model.set_best_alternative_move(best_move)
            
        except Exception:
            # If parsing fails, clear the best alternative move
            board_model.set_best_alternative_move(None)
    
    def check_best_alternative_move_matches_played(self, last_move: Optional[chess.Move]) -> None:
        """Check if best alternative move matches the played move and clear if it does.
        
        This is called after the board position is updated, so we can properly compare
        the best alternative move with the played move.
        
        Args:
            last_move: The last move that was played, or None.
        """
        board_model = self.board_controller.get_board_model()
        best_alternative_move = board_model.best_alternative_move
        
        # If there's no best alternative move, nothing to check
        if best_alternative_move is None:
            return
        
        # If there's no last move, keep the best alternative move
        if last_move is None:
            return
        
        # Compare moves - if they match, clear the best alternative move
        # Both moves should be from the same position (before the move), so they're comparable
        if best_alternative_move == last_move:
            board_model.set_best_alternative_move(None)
    
    def format_active_game_status_message(self, game: GameData) -> str:
        """Format status message for when a game becomes active.
        
        Args:
            game: GameData instance that became active.
            
        Returns:
            Formatted status message string.
        """
        white = game.white if game.white else "Unknown"
        black = game.black if game.black else "Unknown"
        return f"Active game: {white} vs {black}"
    
    def get_game_info(self, game: Optional[GameData]) -> Optional[GameInfo]:
        """Extract processed game information from GameData.
        
        This method extracts and processes game information including player names,
        ELOs, ECO codes, and opening names. It handles default values and extracts
        additional data from PGN headers when necessary.
        
        Args:
            game: GameData instance to process, or None to get default values.
            
        Returns:
            GameInfo instance with processed game information, or None if game is None.
        """
        # Default values
        DEFAULT_WHITE_NAME = "White"
        DEFAULT_BLACK_NAME = "Black"
        DEFAULT_WHITE_ELO = 1500
        DEFAULT_BLACK_ELO = 1500
        DEFAULT_RESULT = "*"
        DEFAULT_ECO = "A00"
        DEFAULT_OPENING_NAME = "Unknown Opening"
        
        if game is None:
            return GameInfo(
                white_name=DEFAULT_WHITE_NAME,
                black_name=DEFAULT_BLACK_NAME,
                white_elo=DEFAULT_WHITE_ELO,
                black_elo=DEFAULT_BLACK_ELO,
                result=DEFAULT_RESULT,
                eco=DEFAULT_ECO,
                opening_name=DEFAULT_OPENING_NAME
            )
        
        # Use GameData fields as base (these are already extracted from PGN)
        white_name = game.white if game.white else DEFAULT_WHITE_NAME
        black_name = game.black if game.black else DEFAULT_BLACK_NAME
        result = game.result if game.result else DEFAULT_RESULT
        eco = game.eco if game.eco else DEFAULT_ECO
        
        # Try to extract ELOs from PGN headers (not stored in GameData currently)
        white_elo = DEFAULT_WHITE_ELO
        black_elo = DEFAULT_BLACK_ELO
        
        try:
            # Parse PGN to extract ELO headers
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game:
                headers = chess_game.headers
                
                # Extract ELOs from headers
                white_elo_str = headers.get("WhiteElo", "")
                black_elo_str = headers.get("BlackElo", "")
                
                try:
                    if white_elo_str and white_elo_str.isdigit():
                        white_elo = int(white_elo_str)
                except (ValueError, AttributeError):
                    pass
                
                try:
                    if black_elo_str and black_elo_str.isdigit():
                        black_elo = int(black_elo_str)
                except (ValueError, AttributeError):
                    pass
        except Exception:
            # On any error, use defaults
            pass
        
        # Opening name: Use last known opening from calculated moves, or ECO from PGN header, or default
        opening_name = DEFAULT_OPENING_NAME
        
        # Try to get last known opening from moves if available
        if game:
            moves = self.extract_moves_from_game(game)
            if moves:
                # Find the last move with an opening (work backwards from the end)
                # This ensures we use the most recent opening classification, even if later positions
                # don't have openings in the database
                # Skip placeholder values (repeat indicator) - we want the actual opening
                for move in reversed(moves):
                    if move.opening_name and move.opening_name != self.opening_repeat_indicator:
                        opening_name = move.opening_name
                        # Also update ECO if we have a calculated one (overrides PGN header)
                        # Skip placeholder values for ECO as well
                        if move.eco and move.eco != self.opening_repeat_indicator:
                            eco = move.eco
                        break
                # If no moves had openings but we have ECO from PGN, keep default name
                # (opening_name already set to DEFAULT_OPENING_NAME)
        
        return GameInfo(
            white_name=white_name,
            black_name=black_name,
            white_elo=white_elo,
            black_elo=black_elo,
            result=result,
            eco=eco,
            opening_name=opening_name
        )
    
    def extract_moves_from_game(self, game: Optional[GameData]) -> List[MoveData]:
        """Extract moves and comments from a game's PGN.
        
        This method parses the PGN and extracts move information including
        move numbers, white/black moves, and comments.
        If analysis data is stored in a PGN tag, it will be loaded and merged.
        
        Args:
            game: GameData instance to extract moves from, or None.
            
        Returns:
            List of MoveData instances with moves and comments populated.
            If analysis data exists in PGN tag, analysis fields will be populated.
        """
        if game is None:
            return []
        
        # First, try to load analysis data from PGN tag
        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        try:
            stored_moves = AnalysisDataStorageService.load_analysis_data(game)
            
            # If analysis data exists, return it (it already contains all move data)
            if stored_moves:
                return stored_moves
        except ValueError as e:
            # Decompression error - show warning message
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            progress_service.set_status("Warning: Analysis data could not be restored (corrupted or invalid)")
            # Continue to parse PGN normally
        
        moves: List[MoveData] = []
        
        try:
            # Parse the PGN
            pgn_io = io.StringIO(game.pgn)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return []
            
            # Use a custom StringExporter visitor to collect comments from main line
            # This is the most reliable way since we can intercept comments during export
            comments_by_ply = {}  # Map ply_index -> comment
            
            class CommentCollector(chess.pgn.StringExporter):
                def __init__(self):
                    super().__init__(headers=False, variations=False, comments=True)
                    self.ply_index = 0
                    self.comments = {}
                    self._current_node = None
                
                def visit_move(self, board, move):
                    # Called for each move - board is the position before the move
                    # We need to access the node to get the comment
                    self.ply_index += 1
                    # Call parent first to let it process the move
                    result = super().visit_move(board, move)
                    # After parent processes, try to access comment from the current node
                    # The node should be accessible through the visitor's state
                    return result
                
                def visit_comment(self, comment):
                    # This is called when a comment is encountered during export
                    # This is the correct way to intercept comments!
                    if comment:
                        # Clean the comment - remove any brackets or extra formatting
                        comment_text = str(comment).strip()
                        # Remove surrounding brackets if present (handle both [ and ])
                        while comment_text.startswith('[') and comment_text.endswith(']'):
                            comment_text = comment_text[1:-1].strip()
                        # Also remove any leading/trailing quotes if present
                        if (comment_text.startswith("'") and comment_text.endswith("'")) or \
                           (comment_text.startswith('"') and comment_text.endswith('"')):
                            comment_text = comment_text[1:-1].strip()
                        
                        # Remove non-standard PGN tags like [%eval], [%wdl], [%mdl], [%clk], etc.
                        import re
                        # Pattern matches: [%tag content] or [%tag] or [#] or [tag]
                        tag_pattern = re.compile(r'\[%?[^\]]+\]')
                        comment_text = tag_pattern.sub('', comment_text).strip()
                        
                        # Remove variation-like patterns: ( -> ...move) or (-> move) etc.
                        # Pattern matches parentheses with arrow and move notation
                        variation_pattern = re.compile(r'\(\s*->\s*[^)]+\)')
                        comment_text = variation_pattern.sub('', comment_text).strip()
                        
                        # Clean up multiple spaces and semicolons
                        comment_text = re.sub(r'\s+', ' ', comment_text).strip()
                        # Remove leading/trailing semicolons and spaces
                        comment_text = comment_text.strip(';').strip()
                        
                        # Only store if there's actual content left after cleaning
                        if comment_text:
                            self.comments[self.ply_index] = comment_text
                    # Call parent to continue export
                    return super().visit_comment(comment)
            
            # Export main line and collect comments
            collector = CommentCollector()
            chess_game.accept(collector)
            comments_by_ply = collector.comments
            
            # Traverse the game tree to extract moves and map comments
            node = chess_game
            move_number = 0
            current_move_data: Optional[MoveData] = None
            ply_count = 0  # Track plies to match with comments
            last_known_eco = None  # Track last known ECO (for positions not in database)
            last_known_opening_name = None  # Track last known opening name (for positions not in database)
            previous_move_eco = None  # Track previous move's ECO for comparison
            previous_move_opening_name = None  # Track previous move's opening name for comparison
            
            # Iterate through the main line variations
            while node.variations:
                # Get the main line variation (first variation)
                next_node = node.variation(0)
                ply_count += 1
                
                # Get comment from comments_by_ply map (extracted from main line PGN only)
                node_comment = comments_by_ply.get(ply_count, "")
                
                # Get the board position after the move (for opening lookup)
                board_after = next_node.board()
                fen_after = board_after.fen()
                
                # Look up opening for this position (after the move)
                eco, opening_name = self.opening_service.get_opening_info(fen_after)
                
                # If we found an opening, update our tracking variables
                if eco:
                    last_known_eco = eco
                if opening_name:
                    last_known_opening_name = opening_name
                
                # Use the found opening, or fall back to last known opening if not found
                display_eco = eco if eco else (last_known_eco if last_known_eco else "")
                display_opening_name = opening_name if opening_name else (last_known_opening_name if last_known_opening_name else "")
                
                # Check if this opening is the same as the previous move's opening
                # Compare actual opening values (not display values) to determine if they match
                actual_eco = eco if eco else (last_known_eco if last_known_eco else "")
                actual_opening_name = opening_name if opening_name else (last_known_opening_name if last_known_opening_name else "")
                
                if actual_eco and actual_opening_name and previous_move_eco and previous_move_opening_name:
                    if actual_eco == previous_move_eco and actual_opening_name == previous_move_opening_name:
                        # Same as previous - use repeat indicator
                        display_eco = self.opening_repeat_indicator
                        display_opening_name = self.opening_repeat_indicator
                
                # Update previous move tracking for next iteration (use actual values, not display values)
                previous_move_eco = actual_eco if actual_eco else None
                previous_move_opening_name = actual_opening_name if actual_opening_name else None
                
                # Get the board position before the move
                board_before = node.board()
                
                # Determine if this is white or black move
                is_white_move = board_before.turn == chess.WHITE
                
                # node_comment was already extracted above when we got next_node
                
                # Check whose turn it is (determines if this is white or black move)
                if is_white_move:
                    move_number += 1
                    # White's move - start a new move entry
                    move_san = board_before.san(next_node.move)
                    
                    # Calculate capture and material for white's move
                    # Material should be calculated for BOTH sides after white's move
                    white_capture = get_captured_piece_letter(board_before, next_node.move)
                    white_material = calculate_material_count(board_after, is_white=True)
                    black_material = calculate_material_count(board_after, is_white=False)
                    
                    # Count pieces for both sides after white's move
                    white_pieces = count_pieces(board_after, is_white=True)
                    black_pieces = count_pieces(board_after, is_white=False)
                    
                    # Create move data for this move pair with opening info from position after white's move
                    current_move_data = MoveData(
                        move_number=move_number,
                        white_move=move_san,
                        black_move="",
                        eval_white="",
                        eval_black="",
                        cpl_white="",
                        cpl_black="",
                        cpl_white_2="",
                        cpl_white_3="",
                        cpl_black_2="",
                        cpl_black_3="",
                        assess_white="",
                        assess_black="",
                        best_white="",
                        best_black="",
                        eco=display_eco,
                        opening_name=display_opening_name,
                        comment=node_comment,
                        white_capture=white_capture,
                        black_capture="",
                        white_material=white_material,
                        black_material=black_material,
                        white_queens=white_pieces[chess.QUEEN],
                        white_rooks=white_pieces[chess.ROOK],
                        white_bishops=white_pieces[chess.BISHOP],
                        white_knights=white_pieces[chess.KNIGHT],
                        white_pawns=white_pieces[chess.PAWN],
                        black_queens=black_pieces[chess.QUEEN],
                        black_rooks=black_pieces[chess.ROOK],
                        black_bishops=black_pieces[chess.BISHOP],
                        black_knights=black_pieces[chess.KNIGHT],
                        black_pawns=black_pieces[chess.PAWN],
                        fen_white=board_after.fen(),
                        fen_black=""
                    )
                    moves.append(current_move_data)
                else:
                    # Black's move - update the current move entry
                    if current_move_data is not None:
                        move_san = board_before.san(next_node.move)
                        current_move_data.black_move = move_san
                        
                        # Calculate capture and material for black's move
                        # Material should be calculated for BOTH sides after black's move
                        current_move_data.black_capture = get_captured_piece_letter(board_before, next_node.move)
                        current_move_data.white_material = calculate_material_count(board_after, is_white=True)
                        current_move_data.black_material = calculate_material_count(board_after, is_white=False)
                        
                        # Count pieces for both sides after black's move
                        white_pieces = count_pieces(board_after, is_white=True)
                        black_pieces = count_pieces(board_after, is_white=False)
                        current_move_data.white_queens = white_pieces[chess.QUEEN]
                        current_move_data.white_rooks = white_pieces[chess.ROOK]
                        current_move_data.white_bishops = white_pieces[chess.BISHOP]
                        current_move_data.white_knights = white_pieces[chess.KNIGHT]
                        current_move_data.white_pawns = white_pieces[chess.PAWN]
                        current_move_data.black_queens = black_pieces[chess.QUEEN]
                        current_move_data.black_rooks = black_pieces[chess.ROOK]
                        current_move_data.black_bishops = black_pieces[chess.BISHOP]
                        current_move_data.black_knights = black_pieces[chess.KNIGHT]
                        current_move_data.black_pawns = black_pieces[chess.PAWN]
                        # Capture FEN after black's move
                        current_move_data.fen_black = board_after.fen()
                        
                        # Update opening info after black's move (position after black's move)
                        current_move_data.eco = display_eco
                        current_move_data.opening_name = display_opening_name
                        
                        # Combine comments if both white and black have comments
                        if current_move_data.comment and node_comment:
                            current_move_data.comment = f"{current_move_data.comment}; {node_comment}"
                        elif node_comment:
                            current_move_data.comment = node_comment
                
                # Move to next node
                node = next_node
        
        except Exception as e:
            # On any error, return empty list
            # Log error for debugging
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error extracting moves from game: {e}", exc_info=e)
            return []
        
        return moves

