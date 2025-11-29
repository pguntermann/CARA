"""Rule for evaluating weak squares."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class WeakSquareRule(PositionalRule):
    """Rule that evaluates weak squares.
    
    A weak square is a square that:
    - Cannot be defended by pawns
    - Is attacked by enemy pieces
    - Is in a strategically important area
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the weak square rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.weak_square_penalty = config.get('score', -8.0)
        self.undefended_penalty = config.get('undefended_penalty', -2.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate weak squares in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Negative scores for weak squares (only for squares with pieces).
        """
        scores: Dict[chess.Square, float] = {}
        opponent = not perspective
        
        # Only evaluate squares that have pieces
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece is None:
                continue  # Skip empty squares
            
            # Only evaluate pieces of the perspective color
            if piece.color != perspective:
                continue
            
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            
            # Check if square is weak
            weakness_score = 0.0
            
            # Only penalize if square is actually weak (attacked and undefended)
            # Don't penalize just because it can't be defended by pawns - that's too harsh
            if board.is_attacked_by(opponent, square):
                # Check if square is defended by friendly pieces
                if not board.is_attacked_by(perspective, square):
                    # Square is attacked but not defended - this is a weakness
                    # Scale penalty by piece value: Pawn -6.0, Knight/Bishop -8.0, Rook -10.0, Queen -12.0, King -15.0
                    piece_type = piece.piece_type
                    if piece_type == chess.PAWN:
                        base_penalty = -6.0
                    elif piece_type in [chess.KNIGHT, chess.BISHOP]:
                        base_penalty = -8.0
                    elif piece_type == chess.ROOK:
                        base_penalty = -10.0
                    elif piece_type == chess.QUEEN:
                        base_penalty = -12.0
                    elif piece_type == chess.KING:
                        base_penalty = -15.0
                    else:
                        # Fallback (shouldn't happen)
                        base_penalty = self.weak_square_penalty
                    
                    weakness_score += base_penalty
                    
                    # Also check if it can't be defended by pawns (additional weakness)
                    if not self._can_be_defended_by_pawns(board, file, rank, perspective):
                        weakness_score += self.undefended_penalty
            
            if weakness_score != 0.0:
                scores[square] = weakness_score
        
        return scores
    
    def _can_be_defended_by_pawns(self, board: chess.Board, file: int, rank: int,
                                  color: chess.Color) -> bool:
        """Check if a square can be defended by pawns.
        
        Args:
            board: Current position.
            file: Square's file (0-7).
            rank: Square's rank (0-7).
            color: Color to check defense for.
        
        Returns:
            True if square can be defended by pawns, False otherwise.
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        
        # Check if any friendly pawn can attack this square
        # Pawns attack diagonally forward
        if color == chess.WHITE:
            # White pawns attack diagonally forward (up)
            if rank > 0:
                # Check left diagonal
                if file > 0:
                    left_diag_square = chess.square(file - 1, rank - 1)
                    if left_diag_square in friendly_pawns:
                        return True
                # Check right diagonal
                if file < 7:
                    right_diag_square = chess.square(file + 1, rank - 1)
                    if right_diag_square in friendly_pawns:
                        return True
        else:
            # Black pawns attack diagonally forward (down)
            if rank < 7:
                # Check left diagonal
                if file > 0:
                    left_diag_square = chess.square(file - 1, rank + 1)
                    if left_diag_square in friendly_pawns:
                        return True
                # Check right diagonal
                if file < 7:
                    right_diag_square = chess.square(file + 1, rank + 1)
                    if right_diag_square in friendly_pawns:
                        return True
        
        return False

