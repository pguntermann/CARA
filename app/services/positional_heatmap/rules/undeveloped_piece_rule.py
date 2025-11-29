"""Rule for evaluating undeveloped pieces."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class UndevelopedPieceRule(PositionalRule):
    """Rule that evaluates undeveloped pieces.
    
    An undeveloped piece is a piece that is still on its starting square
    and is blocked by pawns (has no legal moves). Undeveloped pieces are
    generally a positional weakness.
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the undeveloped piece rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.undeveloped_penalty = config.get('penalty', -8.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate undeveloped pieces in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Negative scores for undeveloped pieces.
        """
        scores: Dict[chess.Square, float] = {}
        
        # Starting squares for each piece type and color
        starting_squares = self._get_starting_squares(perspective)
        
        # Check each piece type that can be undeveloped
        for piece_type in [chess.KNIGHT, chess.BISHOP, chess.ROOK]:
            pieces = board.pieces(piece_type, perspective)
            
            for piece_square in pieces:
                # Check if piece is on its starting square
                if piece_square not in starting_squares.get(piece_type, []):
                    continue
                
                # Check if piece has legal moves (if not, it's blocked/undeveloped)
                if perspective == board.turn:
                    # Current side to move - can use board.legal_moves directly
                    legal_moves = [move for move in board.legal_moves 
                                 if move.from_square == piece_square]
                    num_moves = len(legal_moves)
                else:
                    # Not current side to move - need to generate moves for this piece's color
                    temp_board = board.copy()
                    temp_board.turn = perspective
                    legal_moves = [move for move in temp_board.generate_legal_moves() 
                                 if move.from_square == piece_square]
                    num_moves = len(legal_moves)
                
                # If piece has no legal moves, it's undeveloped (blocked)
                if num_moves == 0:
                    scores[piece_square] = self.undeveloped_penalty
        
        return scores
    
    def _get_starting_squares(self, color: chess.Color) -> Dict[int, list]:
        """Get starting squares for each piece type.
        
        Args:
            color: Color to get starting squares for.
        
        Returns:
            Dictionary mapping piece_type -> list of starting squares.
        """
        if color == chess.WHITE:
            return {
                chess.KNIGHT: [chess.B1, chess.G1],  # b1, g1
                chess.BISHOP: [chess.C1, chess.F1],  # c1, f1
                chess.ROOK: [chess.A1, chess.H1],    # a1, h1
            }
        else:  # BLACK
            return {
                chess.KNIGHT: [chess.B8, chess.G8],  # b8, g8
                chess.BISHOP: [chess.C8, chess.F8],  # c8, f8
                chess.ROOK: [chess.A8, chess.H8],    # a8, h8
            }

