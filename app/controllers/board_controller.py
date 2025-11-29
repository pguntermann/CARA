"""Board controller for managing chess board operations."""

from typing import Dict, Any, Optional
import chess

from app.models.board_model import BoardModel


class BoardController:
    """Controller for managing chess board operations.
    
    This controller orchestrates board-related operations and manages
    the board model.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the board controller.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
        
        # Get initial FEN from config
        ui_config = config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('main', {})
        board_config = panel_config.get('board', {})
        initial_fen = board_config.get('initial_fen', None)
        
        # Initialize board model with FEN from config (or default starting position)
        self.board_model = BoardModel(fen=initial_fen)
        
        # Initialize coordinates visibility from config
        coords_config = board_config.get('coordinates', {})
        show_coords = coords_config.get('show', True)
        self.board_model.set_show_coordinates(show_coords)
    
    def get_board_model(self) -> BoardModel:
        """Get the board model.
        
        Returns:
            The BoardModel instance for observing board state.
        """
        return self.board_model
    
    def reset_board(self) -> None:
        """Reset board to standard starting position."""
        self.board_model.reset_to_starting_position()
    
    def set_position_from_fen(self, fen: str, last_move: Optional[chess.Move] = None) -> None:
        """Set board position from FEN string.
        
        Args:
            fen: FEN string representing the position.
            last_move: Optional last move that led to this position.
        """
        self.board_model.set_fen(fen, last_move=last_move)
    
    def get_position_fen(self) -> str:
        """Get current position as FEN string.
        
        Returns:
            Current position as FEN string.
        """
        return self.board_model.get_fen()
    
    def rotate_board_180(self) -> None:
        """Rotate the board 180 degrees (flip board)."""
        self.board_model.rotate_180()
    
    def toggle_coordinates_visibility(self) -> None:
        """Toggle the visibility of board coordinates."""
        self.board_model.toggle_coordinates_visibility()
    
    def toggle_turn_indicator_visibility(self) -> None:
        """Toggle the visibility of turn indicator."""
        self.board_model.toggle_turn_indicator_visibility()
    
    def toggle_game_info_visibility(self) -> None:
        """Toggle the visibility of game info."""
        self.board_model.toggle_game_info_visibility()
    
    def toggle_playedmove_arrow_visibility(self) -> None:
        """Toggle the visibility of played move arrow."""
        self.board_model.toggle_playedmove_arrow_visibility()
    
    def toggle_bestnextmove_arrow_visibility(self) -> None:
        """Toggle the visibility of best next move arrow."""
        self.board_model.toggle_bestnextmove_arrow_visibility()
    
    def toggle_pv2_arrow_visibility(self) -> None:
        """Toggle the visibility of PV2 arrow."""
        self.board_model.toggle_pv2_arrow_visibility()
    
    def toggle_pv3_arrow_visibility(self) -> None:
        """Toggle the visibility of PV3 arrow."""
        self.board_model.toggle_pv3_arrow_visibility()
    
    def toggle_bestalternativemove_arrow_visibility(self) -> None:
        """Toggle the visibility of best alternative move arrow."""
        self.board_model.toggle_bestalternativemove_arrow_visibility()
    
    def toggle_evaluation_bar_visibility(self) -> None:
        """Toggle the visibility of evaluation bar."""
        self.board_model.toggle_evaluation_bar_visibility()
    
    def toggle_material_widget_visibility(self) -> None:
        """Toggle the visibility of material widget."""
        self.board_model.toggle_material_widget_visibility()
    
    def set_fen_with_validation(self, fen: str, last_move: Optional[chess.Move] = None) -> bool:
        """Set board position from FEN string with validation.
        
        Args:
            fen: FEN string to set (will be validated with python-chess).
            last_move: Optional last move that led to this position.
            
        Returns:
            True if FEN is valid and board was updated, False otherwise.
        """
        try:
            # Validate FEN by trying to create a board from it
            test_board = chess.Board(fen)
            # If successful, set the position
            self.board_model.set_fen(fen, last_move=last_move)
            return True
        except ValueError:
            # Invalid FEN
            return False
    
    def format_fen_copied_message(self, fen: str) -> str:
        """Format status message for when FEN is copied to clipboard.
        
        Args:
            fen: FEN string that was copied.
            
        Returns:
            Formatted status message string.
        """
        return f"FEN copied to clipboard: {fen}"
    
    def format_fen_updated_message(self, fen: str) -> str:
        """Format status message for when board is updated from FEN.
        
        Args:
            fen: FEN string that was used to update the board.
            
        Returns:
            Formatted status message string.
        """
        return f"Board updated from clipboard: {fen}"
    
    def format_fen_invalid_message(self, fen: str) -> str:
        """Format status message for when FEN is invalid.
        
        Args:
            fen: Invalid FEN string.
            
        Returns:
            Formatted status message string (only first line to prevent statusbar growth).
        """
        # Extract only the first line to prevent multiline messages from growing the statusbar
        first_line = fen.split('\n')[0].strip()
        return f"Invalid FEN in clipboard: {first_line}"

