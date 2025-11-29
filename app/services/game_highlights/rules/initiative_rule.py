"""Rule for detecting initiative seized."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation


class InitiativeRule(HighlightRule):
    """Detects when a side seizes the initiative."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for initiative highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if context.prev_move:
            # Check if White seized the initiative
            if move.eval_white and context.prev_move.eval_white and move.eval_black and context.prev_move.eval_black:
                eval_white_curr = parse_evaluation(move.eval_white)
                eval_white_prev = parse_evaluation(context.prev_move.eval_white)
                eval_black_curr = parse_evaluation(move.eval_black)
                eval_black_prev = parse_evaluation(context.prev_move.eval_black)
                
                if all(e is not None for e in [eval_white_curr, eval_white_prev, eval_black_curr, eval_black_prev]):
                    white_improved = eval_white_curr - eval_white_prev
                    black_worsened = eval_black_prev - eval_black_curr
                    if white_improved >= 50 and black_worsened >= 50:
                        # Require move CPL < 30 AND opponent response CPL > 50
                        move_quality_good = False
                        opponent_response_poor = False
                        
                        if move.cpl_white:
                            try:
                                cpl = float(move.cpl_white)
                                if cpl < 30:
                                    move_quality_good = True
                            except (ValueError, TypeError):
                                pass
                        
                        if context.next_move and context.next_move.cpl_black:
                            try:
                                opponent_cpl = float(context.next_move.cpl_black)
                                if opponent_cpl > 50:
                                    opponent_response_poor = True
                            except (ValueError, TypeError):
                                pass
                        
                        # Enhanced: Verify opponent had limited good responses using PV2/PV3 CPL
                        opponent_constrained = False
                        if move.cpl_black_2 and move.cpl_black_3:
                            try:
                                cpl_2 = float(move.cpl_black_2)
                                cpl_3 = float(move.cpl_black_3)
                                # If 2nd and 3rd best moves have high CPL (>50), opponent had few good options
                                if cpl_2 > 50 and cpl_3 > 50:
                                    opponent_constrained = True
                            except (ValueError, TypeError):
                                pass
                        
                        if not (move_quality_good and opponent_response_poor):
                            opponent_constrained = False  # Don't highlight if move quality or opponent response doesn't meet criteria
                        
                        # Higher priority if opponent was truly constrained
                        priority = 30 if opponent_constrained else 28
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. {move.white_move}",
                            description="White seized the initiative",
                            priority=priority,
                            rule_type="initiative"
                        ))
            
            # Check if Black seized the initiative
            if move.eval_black and context.prev_move.eval_black and move.eval_white and context.prev_move.eval_white:
                eval_black_curr = parse_evaluation(move.eval_black)
                eval_black_prev = parse_evaluation(context.prev_move.eval_black)
                eval_white_curr = parse_evaluation(move.eval_white)
                eval_white_prev = parse_evaluation(context.prev_move.eval_white)
                
                if all(e is not None for e in [eval_black_curr, eval_black_prev, eval_white_curr, eval_white_prev]):
                    black_improved = eval_black_prev - eval_black_curr  # Positive if black improved
                    white_worsened = eval_white_prev - eval_white_curr  # Positive if white worsened
                    if black_improved >= 50 and white_worsened >= 50:
                        # Enhanced: Verify opponent had limited good responses using PV2/PV3 CPL
                        opponent_constrained = False
                        if move.cpl_white_2 and move.cpl_white_3:
                            try:
                                cpl_2 = float(move.cpl_white_2)
                                cpl_3 = float(move.cpl_white_3)
                                # If 2nd and 3rd best moves have high CPL (>50), opponent had few good options
                                if cpl_2 > 50 and cpl_3 > 50:
                                    opponent_constrained = True
                            except (ValueError, TypeError):
                                pass
                        
                        # Higher priority if opponent was truly constrained
                        priority = 30 if opponent_constrained else 28
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=False,
                            move_notation=f"{move_num}. ...{move.black_move}",
                            description="Black seized the initiative",
                            priority=priority,
                            rule_type="initiative"
                        ))
        
        return highlights

