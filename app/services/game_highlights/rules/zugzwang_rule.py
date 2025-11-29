"""Rule for detecting zugzwang (position where any move worsens the position)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation


class ZugzwangRule(HighlightRule):
    """Detects zugzwang: position where any move worsens the position."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for zugzwang highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Zugzwang is rare and typically occurs in simplified endgames
        # Prevent consecutive zugzwang detections (if one side is in zugzwang, 
        # the other side shouldn't be immediately after)
        zugzwang_tracking = context.shared_state.get('zugzwang_tracking', {})
        last_white_zugzwang = zugzwang_tracking.get('last_white_zugzwang', 0)
        last_black_zugzwang = zugzwang_tracking.get('last_black_zugzwang', 0)
        
        # White's zugzwang
        if move.white_move and move.cpl_white and move.cpl_white_2 and move.cpl_white_3:
            try:
                cpl = float(move.cpl_white)
                cpl_2 = float(move.cpl_white_2)
                cpl_3 = float(move.cpl_white_3)
                
                # All top 3 moves have very high CPL (>150), indicating no good moves available
                # Higher threshold to reduce false positives
                if cpl > 150 and cpl_2 > 150 and cpl_3 > 150:
                    # Verify this is in endgame (zugzwang is more common in endgames)
                    if move.move_number >= context.middlegame_end:
                        # Check if position is simplified (low material = zugzwang more likely)
                        # Zugzwang typically occurs with few pieces (total material < 2000cp = ~20 points)
                        total_material = move.white_material + move.black_material
                        is_simplified = total_material < 2000
                        
                        # Verify position actually worsened after the move
                        position_worsened = False
                        if context.prev_move and move.eval_white and context.prev_move.eval_white:
                            eval_before = parse_evaluation(context.prev_move.eval_white)
                            eval_after = parse_evaluation(move.eval_white)
                            if eval_before is not None and eval_after is not None:
                                # Position worsened if evaluation decreased (for white)
                                position_worsened = eval_after < eval_before - 50
                        
                        # Prevent consecutive zugzwang (if black was in zugzwang recently, skip)
                        recent_black_zugzwang = last_black_zugzwang > 0 and (move_num - last_black_zugzwang) <= 2
                        
                        if is_simplified and position_worsened and not recent_black_zugzwang:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description="White is in zugzwang (any move worsens the position)",
                                priority=35,
                                rule_type="zugzwang"
                            ))
                            zugzwang_tracking['last_white_zugzwang'] = move_num
            except (ValueError, TypeError):
                pass
        
        # Black's zugzwang
        if move.black_move and move.cpl_black and move.cpl_black_2 and move.cpl_black_3:
            try:
                cpl = float(move.cpl_black)
                cpl_2 = float(move.cpl_black_2)
                cpl_3 = float(move.cpl_black_3)
                
                if cpl > 150 and cpl_2 > 150 and cpl_3 > 150:
                    if move.move_number >= context.middlegame_end:
                        # Check if position is simplified
                        total_material = move.white_material + move.black_material
                        is_simplified = total_material < 2000
                        
                        # Verify position actually worsened after the move
                        position_worsened = False
                        if context.prev_move and move.eval_black and context.prev_move.eval_black:
                            eval_before = parse_evaluation(context.prev_move.eval_black)
                            eval_after = parse_evaluation(move.eval_black)
                            if eval_before is not None and eval_after is not None:
                                # Position worsened if evaluation increased (for black, inverted)
                                position_worsened = eval_after > eval_before + 50
                        
                        # Prevent consecutive zugzwang (if white was in zugzwang recently, skip)
                        recent_white_zugzwang = last_white_zugzwang > 0 and (move_num - last_white_zugzwang) <= 2
                        
                        if is_simplified and position_worsened and not recent_white_zugzwang:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black is in zugzwang (any move worsens the position)",
                                priority=35,
                                rule_type="zugzwang"
                            ))
                            zugzwang_tracking['last_black_zugzwang'] = move_num
            except (ValueError, TypeError):
                pass
        
        # Update shared state
        context.shared_state['zugzwang_tracking'] = zugzwang_tracking
        
        return highlights

