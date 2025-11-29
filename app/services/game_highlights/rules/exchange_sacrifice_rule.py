"""Rule for detecting exchange sacrifice (rook for minor piece with positional compensation)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import PIECE_VALUES


class ExchangeSacrificeRule(HighlightRule):
    """Detects when a rook is sacrificed for a minor piece with positional compensation."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for exchange sacrifice highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if not context.prev_move:
            return highlights
        
        # White's exchange sacrifice (white captures minor piece, black captures rook)
        if move.white_capture in ["n", "b"] and move.black_capture == "r":
            # Check material change
            material_before_white = context.prev_white_material
            material_after_white = move.white_material
            
            # White lost rook (500cp), gained minor piece (300cp) = net loss of 200cp
            material_loss = material_before_white - material_after_white
            
            if 150 <= material_loss <= 250:  # Approximate exchange sacrifice range
                # Check if evaluation improves or stays similar (>-100cp change)
                eval_change = 0
                if context.prev_move.eval_white and move.eval_white:
                    eval_before = parse_evaluation(context.prev_move.eval_white)
                    eval_after = parse_evaluation(move.eval_white)
                    if eval_before is not None and eval_after is not None:
                        eval_change = eval_after - eval_before
                
                # If evaluation doesn't drop significantly (within 100cp), it's positional compensation
                if eval_change > -100:
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=True,
                        move_notation=f"{move_num}. {move.white_move} ... {move.black_move}",
                        description="White sacrificed the exchange for positional compensation",
                        priority=36,
                        rule_type="exchange_sacrifice"
                    ))
        
        # Black's exchange sacrifice (black captures minor piece, white captures rook)
        if move.black_capture in ["n", "b"] and move.white_capture == "r":
            material_before_black = context.prev_black_material
            material_after_black = move.black_material
            material_loss = material_before_black - material_after_black
            
            if 150 <= material_loss <= 250:
                eval_change = 0
                if context.prev_move.eval_black and move.eval_black:
                    eval_before = parse_evaluation(context.prev_move.eval_black)
                    eval_after = parse_evaluation(move.eval_black)
                    if eval_before is not None and eval_after is not None:
                        eval_change = eval_before - eval_after  # Inverted for black
                
                if eval_change > -100:
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=False,
                        move_notation=f"{move_num}. {move.white_move} ... {move.black_move}",
                        description="Black sacrificed the exchange for positional compensation",
                        priority=36,
                        rule_type="exchange_sacrifice"
                    ))
        
        return highlights

