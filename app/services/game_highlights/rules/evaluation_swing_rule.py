"""Rule for detecting large evaluation swings."""

from typing import List, Tuple
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import EVALUATION_SWING_THRESHOLD


class EvaluationSwingRule(HighlightRule):
    """Detects large evaluation swings (excluding momentum shifts)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for evaluation swing highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances (empty, as highlights are stored in shared state).
        """
        # This rule stores highlights in shared_state for deduplication
        # Highlights are added in post-processing
        eval_swing_highlights = context.shared_state.get('eval_swing_highlights', {})
        
        if context.prev_move:
            # White's evaluation swing
            if move.eval_white and context.prev_move.eval_white:
                eval_before = parse_evaluation(context.prev_move.eval_white)
                eval_after = parse_evaluation(move.eval_white)
                if eval_before is not None and eval_after is not None:
                    diff = eval_after - eval_before
                    swing = abs(diff)
                    sign_changed = (eval_before > 0 and eval_after < 0) or (eval_before < 0 and eval_after > 0)
                    
                    if swing > EVALUATION_SWING_THRESHOLD and not sign_changed:
                        # Verify swing was caused by this move: require CPL < 30 (good move) AND exclude if opponent's next move CPL > 100 (opponent's mistake)
                        swing_caused_by_move = True
                        if move.cpl_white:
                            try:
                                cpl = float(move.cpl_white)
                                if cpl >= 30:
                                    swing_caused_by_move = False  # Not a good move, swing might be from other factors
                            except (ValueError, TypeError):
                                pass
                        
                        # Check if opponent's next move was a mistake (which would make this swing less meaningful)
                        if swing_caused_by_move and context.next_move and context.next_move.cpl_black:
                            try:
                                opponent_cpl = float(context.next_move.cpl_black)
                                if opponent_cpl > 100:
                                    swing_caused_by_move = False  # Opponent's mistake, not this move's quality
                            except (ValueError, TypeError):
                                pass
                        
                        if swing_caused_by_move:
                            change_pawns = swing / 100.0
                            direction = "increased" if diff > 0 else "decreased"
                            
                            # Determine phase
                            if move.move_number <= context.opening_end:
                                phase = "opening"
                            elif move.move_number < context.middlegame_end:
                                phase = "middlegame"
                            else:
                                phase = "endgame"
                            
                            key = (True, phase, direction)
                            
                            if key not in eval_swing_highlights or swing > eval_swing_highlights[key][0]:
                                eval_swing_highlights[key] = (
                                    swing,
                                    GameHighlight(
                                        move_number=move.move_number,
                                        is_white=True,
                                        move_notation=f"{move.move_number}. {move.white_move}",
                                        description=f"White's evaluation {direction} by {change_pawns:.1f} pawns",
                                        priority=30,
                                        rule_type="evaluation_swing"
                                    )
                                )
            
            # Black's evaluation swing
            if move.eval_black and context.prev_move.eval_black:
                eval_before = parse_evaluation(context.prev_move.eval_black)
                eval_after = parse_evaluation(move.eval_black)
                if eval_before is not None and eval_after is not None:
                    diff = eval_before - eval_after  # Inverted for black's perspective
                    swing = abs(diff)
                    sign_changed = (eval_before > 0 and eval_after < 0) or (eval_before < 0 and eval_after > 0)
                    
                    if swing > EVALUATION_SWING_THRESHOLD and not sign_changed:
                        # Verify swing was caused by this move: require CPL < 30 (good move) AND exclude if opponent's next move CPL > 100 (opponent's mistake)
                        swing_caused_by_move = True
                        if move.cpl_black:
                            try:
                                cpl = float(move.cpl_black)
                                if cpl >= 30:
                                    swing_caused_by_move = False  # Not a good move, swing might be from other factors
                            except (ValueError, TypeError):
                                pass
                        
                        # Check if opponent's next move was a mistake (which would make this swing less meaningful)
                        if swing_caused_by_move and context.next_move and context.next_move.cpl_white:
                            try:
                                opponent_cpl = float(context.next_move.cpl_white)
                                if opponent_cpl > 100:
                                    swing_caused_by_move = False  # Opponent's mistake, not this move's quality
                            except (ValueError, TypeError):
                                pass
                        
                        if swing_caused_by_move:
                            change_pawns = swing / 100.0
                            direction = "increased" if diff > 0 else "decreased"
                            
                            if move.move_number <= context.opening_end:
                                phase = "opening"
                            elif move.move_number < context.middlegame_end:
                                phase = "middlegame"
                            else:
                                phase = "endgame"
                            
                            key = (False, phase, direction)
                            
                            if key not in eval_swing_highlights or swing > eval_swing_highlights[key][0]:
                                eval_swing_highlights[key] = (
                                    swing,
                                    GameHighlight(
                                        move_number=move.move_number,
                                        is_white=False,
                                        move_notation=f"{move.move_number}. ...{move.black_move}",
                                        description=f"Black's evaluation {direction} by {change_pawns:.1f} pawns",
                                        priority=30,
                                        rule_type="evaluation_swing"
                                    )
                                )
        
        # Update shared state
        context.shared_state['eval_swing_highlights'] = eval_swing_highlights
        
        # Return empty list - highlights are added in post-processing
        return []

