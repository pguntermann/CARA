"""Rule for evaluating doubled pawns."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class DoubledPawnRule(PositionalRule):
    """Rule that evaluates doubled pawns.
    
    Doubled pawns are two or more pawns of the same color on the same file.
    Doubled pawns are generally weak because they cannot defend each other.
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the doubled pawn rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.doubled_pawn_penalty = config.get('score', -8.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate doubled pawns in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Negative scores for doubled pawns.
        """
        scores: Dict[chess.Square, float] = {}
        
        # Get all pawns for the perspective color
        pawns = board.pieces(chess.PAWN, perspective)
        opponent = not perspective
        
        # Central files (c, d, e, f) - files 2, 3, 4, 5
        central_files = [2, 3, 4, 5]
        
        # Count pawns per file
        pawns_per_file: Dict[int, list] = {}
        for pawn_square in pawns:
            file = chess.square_file(pawn_square)
            if file not in pawns_per_file:
                pawns_per_file[file] = []
            pawns_per_file[file].append(pawn_square)
        
        # Mark doubled pawns
        for file, file_pawns in pawns_per_file.items():
            if len(file_pawns) > 1:
                # Multiple pawns on same file - all are doubled
                # Base penalty: central files -6.0, edge files -8.0
                if file in central_files:
                    base_penalty = -6.0
                else:
                    base_penalty = -8.0
                
                # Check if file is open (no opposing pawns on the file)
                opponent_pawns = board.pieces(chess.PAWN, opponent)
                is_open_file = True
                for opp_pawn_square in opponent_pawns:
                    if chess.square_file(opp_pawn_square) == file:
                        is_open_file = False
                        break
                
                # If file is open, reduce penalty by 50%
                if is_open_file:
                    base_penalty *= 0.5
                
                # Apply penalty to all doubled pawns on this file
                for pawn_square in file_pawns:
                    scores[pawn_square] = base_penalty
        
        return scores

