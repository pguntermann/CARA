"""Rule for detecting simplification (queen/rook trades)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext


class SimplificationRule(HighlightRule):
    """Detects simplification through piece trades."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for simplification highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Fact #11: Simplification (queen trade)
        # Require eval improvement >50cp after trade
        if move.white_capture == "q" and move.black_capture == "q" and move.black_move:
            trade_beneficial = False
            if move.eval_white and context.prev_move and context.prev_move.eval_white:
                from app.services.game_highlights.helpers import parse_evaluation
                eval_before = parse_evaluation(context.prev_move.eval_white)
                eval_after = parse_evaluation(move.eval_white)
                if eval_before is not None and eval_after is not None:
                    eval_improvement = eval_after - eval_before
                    if eval_improvement > 50:
                        trade_beneficial = True
            
            if trade_beneficial:
                highlights.append(GameHighlight(
                    move_number=move_num,
                    move_number_end=move_num,
                    is_white=True,
                    move_notation=f"{move_num}. {move.white_move} ... {move.black_move}",
                    description="Queens were traded",
                    priority=22,
                    rule_type="simplification"
                ))
        
        # Fact #12: Simplification (rook trade)
        # Require eval improvement >50cp after trade
        if move.white_capture == "r" and move.black_capture == "r" and move.black_move:
            trade_beneficial = False
            if move.eval_white and context.prev_move and context.prev_move.eval_white:
                from app.services.game_highlights.helpers import parse_evaluation
                eval_before = parse_evaluation(context.prev_move.eval_white)
                eval_after = parse_evaluation(move.eval_white)
                if eval_before is not None and eval_after is not None:
                    eval_improvement = eval_after - eval_before
                    if eval_improvement > 50:
                        trade_beneficial = True
            
            if trade_beneficial:
                highlights.append(GameHighlight(
                    move_number=move_num,
                    move_number_end=move_num,
                    is_white=True,
                    move_notation=f"{move_num}. {move.white_move} ... {move.black_move}",
                    description="Rooks were traded",
                    priority=18,
                    rule_type="simplification"
                ))
        
        return highlights

