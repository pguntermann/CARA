"""Rule for evaluating isolated pawns."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class IsolatedPawnRule(PositionalRule):
    """Rule that evaluates isolated pawns.
    
    An isolated pawn has no friendly pawns on adjacent files.
    Isolated pawns are generally weak because they cannot be defended by other pawns.
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the isolated pawn rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.isolated_pawn_penalty = config.get('score', -10.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate isolated pawns in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Negative scores for isolated pawns.
        """
        scores: Dict[chess.Square, float] = {}
        
        # Get all pawns for the perspective color
        pawns = board.pieces(chess.PAWN, perspective)
        
        for pawn_square in pawns:
            file = chess.square_file(pawn_square)
            
            if self._is_isolated_pawn(board, file, perspective):
                scores[pawn_square] = self.isolated_pawn_penalty
        
        return scores
    
    def _is_isolated_pawn(self, board: chess.Board, file: int, color: chess.Color) -> bool:
        """Check if a pawn is isolated.
        
        An isolated pawn has no friendly pawns on adjacent files.
        
        Args:
            board: Current position.
            file: Pawn's file (0-7).
            color: Pawn's color.
        
        Returns:
            True if pawn is isolated, False otherwise.
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        
        # Check adjacent files
        if file > 0:
            # Check left file
            left_file_has_pawn = any(chess.square_file(sq) == file - 1 for sq in friendly_pawns)
            if left_file_has_pawn:
                return False  # Has pawn on adjacent file
        
        if file < 7:
            # Check right file
            right_file_has_pawn = any(chess.square_file(sq) == file + 1 for sq in friendly_pawns)
            if right_file_has_pawn:
                return False  # Has pawn on adjacent file
        
        return True  # No pawns on adjacent files

