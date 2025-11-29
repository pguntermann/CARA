"""Rule for detecting positional improvements."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation


class PositionalImprovementRule(HighlightRule):
    """Detects positional improvements (evaluation improvement without material change)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for positional improvement highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if context.prev_move:
            # Check white's positional improvement
            material_change = abs(move.white_material - context.prev_white_material)
            if move.eval_white and context.prev_move.eval_white and material_change < 50:
                eval_before = parse_evaluation(context.prev_move.eval_white)
                eval_after = parse_evaluation(move.eval_white)
                if eval_before is not None and eval_after is not None:
                    improvement = eval_after - eval_before
                    if improvement > 50:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. {move.white_move}",
                            description="White gained a positional advantage",
                            priority=25,
                            rule_type="positional_improvement"
                        ))
            
            # Check black's positional improvement
            material_change_black = abs(move.black_material - context.prev_black_material)
            if move.eval_black and context.prev_move.eval_black and material_change_black < 50:
                eval_before = parse_evaluation(context.prev_move.eval_black)
                eval_after = parse_evaluation(move.eval_black)
                if eval_before is not None and eval_after is not None:
                    improvement = eval_before - eval_after  # More negative = better for black
                    if improvement > 50:
                        # Require CPL < 30, exclude opponent mistakes
                        positional_improvement_meaningful = False
                        if move.cpl_black:
                            try:
                                cpl = float(move.cpl_black)
                                if cpl < 30:
                                    positional_improvement_meaningful = True
                            except (ValueError, TypeError):
                                pass
                        
                        # Exclude if opponent's next move was a mistake (which would make this improvement less meaningful)
                        if positional_improvement_meaningful and context.next_move and context.next_move.cpl_white:
                            try:
                                opponent_cpl = float(context.next_move.cpl_white)
                                if opponent_cpl > 100:
                                    positional_improvement_meaningful = False  # Opponent's mistake, not this move's quality
                            except (ValueError, TypeError):
                                pass
                        
                        if positional_improvement_meaningful:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black gained a positional advantage",
                                priority=25,
                                rule_type="positional_improvement"
                            ))
        
        return highlights

