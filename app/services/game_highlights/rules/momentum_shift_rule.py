"""Rule for detecting momentum shifts (advantage switching sides)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import MOMENTUM_SHIFT_THRESHOLD


class MomentumShiftRule(HighlightRule):
    """Detects when the advantage switches sides."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for momentum shift highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Get or initialize momentum shift tracking in shared state
        last_momentum_shift = context.shared_state.get('last_momentum_shift', None)
        # Format: (move_number, side) where side is 'white' or 'black'
        
        if context.prev_move:
            # Check if white's move caused the advantage to switch
            # Compare evaluation before white's move to evaluation after white's move
            if move.white_move and move.eval_white:
                # Get evaluation before white's move (from previous move, which was black's move)
                eval_before = None
                if context.prev_move.eval_black:
                    eval_before = parse_evaluation(context.prev_move.eval_black)
                elif context.prev_move.eval_white:
                    # Fallback: if prev move was white, use its eval_white
                    eval_before = parse_evaluation(context.prev_move.eval_white)
                
                eval_after = parse_evaluation(move.eval_white)
                if eval_before is not None and eval_after is not None:
                    # Check if evaluation crossed zero (advantage switched sides)
                    # Require absolute eval change >200cp AND move CPL < 50
                    eval_change = abs(eval_after - eval_before)
                    if ((eval_before > 0 and eval_after < 0) or (eval_before < 0 and eval_after > 0)) and \
                       eval_change > 200:
                        # Verify move quality: require CPL < 50
                        move_quality_good = False
                        if move.cpl_white:
                            try:
                                cpl = float(move.cpl_white)
                                if cpl < 50:
                                    move_quality_good = True
                            except (ValueError, TypeError):
                                pass
                        
                        if move_quality_good:
                            # Check if previous move also had a momentum shift
                            is_again = False
                            if last_momentum_shift:
                                prev_move_num, prev_side = last_momentum_shift
                                # Check if momentum shift was on the immediately previous move
                                # Could be black's move in prev_move.move_number, or white's move in prev_move.move_number
                                # Also check if it was black's move in the same move number (if we're processing white first)
                                if prev_move_num == context.prev_move.move_number or \
                                   (prev_move_num == move_num and prev_side == 'black'):
                                    is_again = True
                            
                            description = "The advantage switched sides again" if is_again else "The advantage switched sides"
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description=description,
                                priority=45,
                                rule_type="momentum_shift"
                            ))
                            # Update shared state
                            context.shared_state['last_momentum_shift'] = (move_num, 'white')
            
            # Check if black's move caused the advantage to switch
            # Compare evaluation after black's move to evaluation after white's move (same move number)
            if move.black_move and move.eval_black and move.eval_white:
                # Get evaluation before black's move (from white's move in the same move number)
                eval_before = parse_evaluation(move.eval_white)
                eval_after = parse_evaluation(move.eval_black)
                if eval_before is not None and eval_after is not None:
                    # Check if evaluation crossed zero (advantage switched sides)
                    # Require absolute eval change >200cp AND move CPL < 50
                    eval_change = abs(eval_after - eval_before)
                    if ((eval_before > 0 and eval_after < 0) or (eval_before < 0 and eval_after > 0)) and \
                       eval_change > 200:
                        # Verify move quality: require CPL < 50
                        move_quality_good = False
                        if move.cpl_black:
                            try:
                                cpl = float(move.cpl_black)
                                if cpl < 50:
                                    move_quality_good = True
                            except (ValueError, TypeError):
                                pass
                        
                        if move_quality_good:
                            # Re-read shared state to get updated value (in case white's move was processed first)
                            current_momentum_shift = context.shared_state.get('last_momentum_shift', None)
                            # Check if white's move in the same move number also had a momentum shift
                            is_again = False
                            if current_momentum_shift:
                                prev_move_num, prev_side = current_momentum_shift
                                # Check if momentum shift was on white's move in the same move number
                                if prev_move_num == move_num and prev_side == 'white':
                                    is_again = True
                            
                            description = "The advantage switched sides again" if is_again else "The advantage switched sides"
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description=description,
                                priority=45,
                                rule_type="momentum_shift"
                            ))
                            # Update shared state
                            context.shared_state['last_momentum_shift'] = (move_num, 'black')
        
        return highlights

