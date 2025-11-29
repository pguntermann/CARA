"""Rule for detecting forcing combinations."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import (
    PIECE_VALUES, MATERIAL_SACRIFICE_THRESHOLD, 
    EVALUATION_IMPROVEMENT_THRESHOLD
)


class ForcingCombinationRule(HighlightRule):
    """Detects forcing combinations (material sacrifice with forced response)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for forcing combination highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's forcing combination
        if move.white_capture and move.cpl_white and context.move_index > 0:
            try:
                cpl = float(move.cpl_white)
                material_sacrificed = context.prev_white_material - move.white_material
                
                if material_sacrificed >= MATERIAL_SACRIFICE_THRESHOLD and cpl < context.good_move_max_cpl:
                    is_equal_recapture = False
                    opponent_response_forced = False
                    evaluation_improved = False
                    
                    # First check if opponent's move on the same turn is an equal recapture
                    if move.black_capture:
                        captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                        captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                        if abs(captured_by_white - captured_by_black) <= 50:
                            is_equal_recapture = True
                    
                    # If not equal recapture on same turn, check next move
                    if not is_equal_recapture and context.next_move:
                        # Check if black's response on next move is an equal material recapture
                        if context.next_move.black_capture:
                            captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                            captured_by_black = PIECE_VALUES.get(context.next_move.black_capture.lower(), 0)
                            if abs(captured_by_white - captured_by_black) <= 50:
                                is_equal_recapture = True
                        
                        # Check if black's response has low CPL (forced response)
                        # True forcing combinations require opponent to have very few good options
                        # Enhanced: Check if opponent has fewer than 3 good moves (CPL < 30 for best, and CPL > 50 for 2nd/3rd best)
                        if not is_equal_recapture and context.next_move.cpl_black:
                            try:
                                opponent_cpl = float(context.next_move.cpl_black)
                                # Basic check: best move has low CPL
                                opponent_response_forced = opponent_cpl < 30
                                
                                # Enhanced check: verify opponent has <3 good moves using PV2/PV3 CPL
                                if opponent_response_forced and context.next_move.cpl_black_2 and context.next_move.cpl_black_3:
                                    try:
                                        opponent_cpl_2 = float(context.next_move.cpl_black_2)
                                        opponent_cpl_3 = float(context.next_move.cpl_black_3)
                                        # If 2nd and 3rd best moves also have high CPL (>50), opponent truly has <3 good moves
                                        if opponent_cpl_2 > 50 and opponent_cpl_3 > 50:
                                            opponent_response_forced = True  # Confirmed: opponent has very limited options
                                        else:
                                            # Opponent has multiple good options, less forcing
                                            opponent_response_forced = False
                                    except (ValueError, TypeError):
                                        pass  # Fall back to basic check if PV2/PV3 data unavailable
                            except (ValueError, TypeError):
                                pass
                        
                        # Check if evaluation improved significantly after the sequence
                        if move.eval_white and context.next_move.eval_black:
                            eval_after_capture = parse_evaluation(move.eval_white)
                            eval_after_response = parse_evaluation(context.next_move.eval_black)
                            if eval_after_capture is not None and eval_after_response is not None:
                                evaluation_improved = eval_after_response > eval_after_capture + EVALUATION_IMPROVEMENT_THRESHOLD
                    
                    # Also check if evaluation improved immediately after capture
                    # But exclude if it's a simple equal exchange (no net material change)
                    if not evaluation_improved and not is_equal_recapture and move.eval_white and context.prev_move and context.prev_move.eval_white:
                        eval_before = parse_evaluation(context.prev_move.eval_white)
                        eval_after = parse_evaluation(move.eval_white)
                        if eval_before is not None and eval_after is not None:
                            evaluation_improved = eval_after > eval_before + EVALUATION_IMPROVEMENT_THRESHOLD
                    
                    # Exclude simple equal exchanges - they're not forcing combinations
                    # Add verification: require evaluation improvement >100cp after opponent's response
                    if not is_equal_recapture and (opponent_response_forced or evaluation_improved):
                        # Verify combination actually worked: require eval improvement >100cp after opponent's response
                        combination_worked = evaluation_improved
                        if not combination_worked and context.next_move and move.eval_white and context.next_move.eval_black:
                            eval_after_capture = parse_evaluation(move.eval_white)
                            eval_after_response = parse_evaluation(context.next_move.eval_black)
                            if eval_after_capture is not None and eval_after_response is not None:
                                eval_improvement = eval_after_response - eval_after_capture
                                combination_worked = eval_improvement > 100
                        
                        if combination_worked:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description="White initiated a forcing combination",
                                priority=45,
                                rule_type="forcing_combination"
                            ))
            except (ValueError, TypeError):
                pass
        
        # Black's forcing combination
        if move.black_capture and move.cpl_black and context.move_index > 0:
            try:
                cpl = float(move.cpl_black)
                material_sacrificed = context.prev_black_material - move.black_material
                
                if material_sacrificed >= MATERIAL_SACRIFICE_THRESHOLD and cpl < context.good_move_max_cpl:
                    is_equal_recapture = False
                    opponent_response_forced = False
                    evaluation_improved = False
                    
                    # First check if opponent's move on the same turn is an equal recapture
                    if move.white_capture:
                        captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                        captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                        if abs(captured_by_black - captured_by_white) <= 50:
                            is_equal_recapture = True
                    
                    # If not equal recapture on same turn, check next move
                    if not is_equal_recapture and context.next_move:
                        # Check if white's response on next move is an equal material recapture
                        if context.next_move.white_capture:
                            captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                            captured_by_white = PIECE_VALUES.get(context.next_move.white_capture.lower(), 0)
                            if abs(captured_by_black - captured_by_white) <= 50:
                                is_equal_recapture = True
                        
                        # Check if white's response has low CPL (forced response)
                        # True forcing combinations require opponent to have very few good options
                        # Enhanced: Check if opponent has fewer than 3 good moves (CPL < 30 for best, and CPL > 50 for 2nd/3rd best)
                        if not is_equal_recapture and context.next_move.cpl_white:
                            try:
                                opponent_cpl = float(context.next_move.cpl_white)
                                # Basic check: best move has low CPL
                                opponent_response_forced = opponent_cpl < 30
                                
                                # Enhanced check: verify opponent has <3 good moves using PV2/PV3 CPL
                                if opponent_response_forced and context.next_move.cpl_white_2 and context.next_move.cpl_white_3:
                                    try:
                                        opponent_cpl_2 = float(context.next_move.cpl_white_2)
                                        opponent_cpl_3 = float(context.next_move.cpl_white_3)
                                        # If 2nd and 3rd best moves also have high CPL (>50), opponent truly has <3 good moves
                                        if opponent_cpl_2 > 50 and opponent_cpl_3 > 50:
                                            opponent_response_forced = True  # Confirmed: opponent has very limited options
                                        else:
                                            # Opponent has multiple good options, less forcing
                                            opponent_response_forced = False
                                    except (ValueError, TypeError):
                                        pass  # Fall back to basic check if PV2/PV3 data unavailable
                            except (ValueError, TypeError):
                                pass
                        
                        # Check if evaluation improved significantly after the sequence
                        if move.eval_black and context.next_move.eval_white:
                            eval_after_capture = parse_evaluation(move.eval_black)
                            eval_after_response = parse_evaluation(context.next_move.eval_white)
                            if eval_after_capture is not None and eval_after_response is not None:
                                evaluation_improved = eval_after_response < eval_after_capture - EVALUATION_IMPROVEMENT_THRESHOLD
                    
                    # Also check if evaluation improved immediately after capture
                    # But exclude if it's a simple equal exchange (no net material change)
                    if not evaluation_improved and not is_equal_recapture and move.eval_black and context.prev_move and context.prev_move.eval_black:
                        eval_before = parse_evaluation(context.prev_move.eval_black)
                        eval_after = parse_evaluation(move.eval_black)
                        if eval_before is not None and eval_after is not None:
                            evaluation_improved = eval_after < eval_before - EVALUATION_IMPROVEMENT_THRESHOLD
                    
                    # Exclude simple equal exchanges - they're not forcing combinations
                    # Add verification: require evaluation improvement >100cp after opponent's response
                    if not is_equal_recapture and (opponent_response_forced or evaluation_improved):
                        # Verify combination actually worked: require eval improvement >100cp after opponent's response
                        combination_worked = evaluation_improved
                        if not combination_worked and context.next_move and move.eval_black and context.next_move.eval_white:
                            eval_after_capture = parse_evaluation(move.eval_black)
                            eval_after_response = parse_evaluation(context.next_move.eval_white)
                            if eval_after_capture is not None and eval_after_response is not None:
                                eval_improvement = eval_after_capture - eval_after_response  # Inverted for black
                                combination_worked = eval_improvement > 100
                        
                        if combination_worked:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black initiated a forcing combination",
                                priority=45,
                                rule_type="forcing_combination"
                            ))
            except (ValueError, TypeError):
                pass
        
        return highlights

