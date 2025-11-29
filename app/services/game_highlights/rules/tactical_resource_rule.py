"""Rule for detecting strong tactical resources."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import PIECE_VALUES


class TacticalResourceRule(HighlightRule):
    """Detects strong tactical resources (good moves with tactical elements)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for tactical resource highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Check if current move is a simple recapture with equal material
        # This includes recaptures on the same turn (equal exchanges), previous turn, or next turn
        is_simple_recapture = False
        
        # First check if it's an equal exchange on the same turn
        if move.white_capture and move.black_capture:
            captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
            captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
            if abs(captured_by_white - captured_by_black) <= 50:
                is_simple_recapture = True
        
        # Check if current move is a simple recapture of the previous move with equal material
        if not is_simple_recapture and context.prev_move:
            if move.white_capture and context.prev_move.black_capture:
                captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                captured_by_black = PIECE_VALUES.get(context.prev_move.black_capture.lower(), 0)
                if abs(captured_by_white - captured_by_black) <= 50:
                    is_simple_recapture = True
            
            if move.black_capture and context.prev_move.white_capture:
                captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                captured_by_white = PIECE_VALUES.get(context.prev_move.white_capture.lower(), 0)
                if abs(captured_by_black - captured_by_white) <= 50:
                    is_simple_recapture = True
        
        # Check if opponent recaptures on next move with equal material
        if not is_simple_recapture and context.next_move:
            if move.white_capture and context.next_move.black_capture:
                captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                captured_by_black = PIECE_VALUES.get(context.next_move.black_capture.lower(), 0)
                if abs(captured_by_white - captured_by_black) <= 50:
                    is_simple_recapture = True
            
            if move.black_capture and context.next_move.white_capture:
                captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                captured_by_white = PIECE_VALUES.get(context.next_move.white_capture.lower(), 0)
                if abs(captured_by_black - captured_by_white) <= 50:
                    is_simple_recapture = True
        
        # White's tactical resource
        if move.cpl_white and not is_simple_recapture:
            try:
                cpl = float(move.cpl_white)
                
                if cpl >= context.good_move_max_cpl:
                    # Not a good move, skip
                    pass
                else:
                    # CRITICAL: Check if this move is part of a forced sequence
                    # If the opponent's previous move was forcing (very low CPL) and this is a forced response,
                    # it's not a tactical resource - it's just following a forced line
                    is_part_of_forced_sequence = self._is_part_of_forced_sequence(context, move_num, is_white=True)
                    
                    if is_part_of_forced_sequence:
                        # Skip - this is a forced move in a tactical sequence, not a tactical resource
                        pass
                    else:
                        # Check for tactical resource: must create lasting tactical advantage
                        is_tactical_resource = False
                        
                        # Option A: Capture that results in net material gain (after considering recapture)
                        if move.white_capture:
                            captured_value = PIECE_VALUES.get(move.white_capture.lower(), 0)
                            net_material_gain = captured_value
                            
                            # Check if opponent recaptures on next move
                            if context.next_move and context.next_move.black_capture:
                                recaptured_value = PIECE_VALUES.get(context.next_move.black_capture.lower(), 0)
                                # Net gain = what we captured minus what we lost in recapture
                                net_material_gain = captured_value - recaptured_value
                            
                            # If net material gain > 0, it's a tactical resource
                            if net_material_gain > 0:
                                is_tactical_resource = True
                            # Option C: Capture >=300cp with eval improvement >=200cp AND no equal recapture
                            elif captured_value >= 300:
                                # Check if there's an equal recapture (already checked in is_simple_recapture)
                                # If not a simple recapture and eval improves significantly, it's tactical
                                if move.eval_white and context.prev_move and context.prev_move.eval_white:
                                    eval_before = parse_evaluation(context.prev_move.eval_white)
                                    eval_after = parse_evaluation(move.eval_white)
                                    if eval_before is not None and eval_after is not None:
                                        eval_improvement = eval_after - eval_before
                                        if eval_improvement >= 200:
                                            is_tactical_resource = True
                        
                        # Option B: Non-capture with evaluation improvement >=300cp (tactical sequence)
                        # Add phase-specific thresholds: require higher eval improvement in endgame (>=400cp vs >=300cp)
                        if not is_tactical_resource and not move.white_capture:
                            if move.eval_white and context.prev_move and context.prev_move.eval_white:
                                eval_before = parse_evaluation(context.prev_move.eval_white)
                                eval_after = parse_evaluation(move.eval_white)
                                if eval_before is not None and eval_after is not None:
                                    eval_improvement = eval_after - eval_before
                                    # Phase-specific threshold: endgame requires >=400cp, others >=300cp
                                    phase_threshold = 400 if move.move_number >= context.middlegame_end else 300
                                    if eval_improvement >= phase_threshold:
                                        is_tactical_resource = True
                        
                        if is_tactical_resource:
                            # Enhanced: Check if tactical resource was clearly superior to alternatives using PV2/PV3 CPL
                            is_clearly_best = False
                            if move.cpl_white_2 and move.cpl_white_3:
                                try:
                                    cpl_2 = float(move.cpl_white_2)
                                    cpl_3 = float(move.cpl_white_3)
                                    # If 2nd and 3rd best moves have high CPL (>50), this was clearly the best tactical option
                                    if cpl_2 > 50 and cpl_3 > 50:
                                        is_clearly_best = True
                                except (ValueError, TypeError):
                                    pass
                            
                            priority = 28 if is_clearly_best else 25
                            description = "White found a strong tactical resource"
                            if is_clearly_best:
                                description = "White found the clearly best tactical resource"
                            
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description=description,
                                priority=priority,
                                rule_type="tactical_resource"
                            ))
            except (ValueError, TypeError):
                pass
        
        # Black's tactical resource
        if move.cpl_black and not is_simple_recapture:
            try:
                cpl = float(move.cpl_black)
                
                if cpl >= context.good_move_max_cpl:
                    # Not a good move, skip
                    pass
                else:
                    # CRITICAL: Check if this move is part of a forced sequence
                    # If the opponent's previous move was forcing (very low CPL) and this is a forced response,
                    # it's not a tactical resource - it's just following a forced line
                    is_part_of_forced_sequence = self._is_part_of_forced_sequence(context, move_num, is_white=False)
                    
                    if is_part_of_forced_sequence:
                        # Skip - this is a forced move in a tactical sequence, not a tactical resource
                        pass
                    else:
                        # Check for tactical resource: must create lasting tactical advantage
                        is_tactical_resource = False
                        
                        # Option A: Capture that results in net material gain (after considering recapture)
                        if move.black_capture:
                            captured_value = PIECE_VALUES.get(move.black_capture.lower(), 0)
                            net_material_gain = captured_value
                            
                            # Check if opponent recaptures on next move
                            if context.next_move and context.next_move.white_capture:
                                recaptured_value = PIECE_VALUES.get(context.next_move.white_capture.lower(), 0)
                                # Net gain = what we captured minus what we lost in recapture
                                net_material_gain = captured_value - recaptured_value
                            
                            # If net material gain > 0, it's a tactical resource
                            if net_material_gain > 0:
                                is_tactical_resource = True
                            # Option C: Capture >=300cp with eval improvement >=200cp AND no equal recapture
                            elif captured_value >= 300:
                                # Check if there's an equal recapture (already checked in is_simple_recapture)
                                # If not a simple recapture and eval improves significantly, it's tactical
                                if move.eval_black and context.prev_move and context.prev_move.eval_black:
                                    eval_before = parse_evaluation(context.prev_move.eval_black)
                                    eval_after = parse_evaluation(move.eval_black)
                                    if eval_before is not None and eval_after is not None:
                                        # For black, improvement means eval becomes more negative (better for black)
                                        eval_improvement = eval_before - eval_after
                                        if eval_improvement >= 200:
                                            is_tactical_resource = True
                        
                        # Option B: Non-capture with evaluation improvement >=300cp (tactical sequence)
                        # Add phase-specific thresholds: require higher eval improvement in endgame (>=400cp vs >=300cp)
                        if not is_tactical_resource and not move.black_capture:
                            if move.eval_black and context.prev_move and context.prev_move.eval_black:
                                eval_before = parse_evaluation(context.prev_move.eval_black)
                                eval_after = parse_evaluation(move.eval_black)
                                if eval_before is not None and eval_after is not None:
                                    # For black, improvement means eval becomes more negative (better for black)
                                    eval_improvement = eval_before - eval_after
                                    # Phase-specific threshold: endgame requires >=400cp, others >=300cp
                                    phase_threshold = 400 if move.move_number >= context.middlegame_end else 300
                                    if eval_improvement >= phase_threshold:
                                        is_tactical_resource = True
                        
                        if is_tactical_resource:
                            # Enhanced: Check if tactical resource was clearly superior to alternatives using PV2/PV3 CPL
                            is_clearly_best = False
                            if move.cpl_black_2 and move.cpl_black_3:
                                try:
                                    cpl_2 = float(move.cpl_black_2)
                                    cpl_3 = float(move.cpl_black_3)
                                    # If 2nd and 3rd best moves have high CPL (>50), this was clearly the best tactical option
                                    if cpl_2 > 50 and cpl_3 > 50:
                                        is_clearly_best = True
                                except (ValueError, TypeError):
                                    pass
                            
                            priority = 28 if is_clearly_best else 25
                            description = "Black found a strong tactical resource"
                            if is_clearly_best:
                                description = "Black found the clearly best tactical resource"
                            
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description=description,
                                priority=priority,
                                rule_type="tactical_resource"
                            ))
            except (ValueError, TypeError):
                pass
        
        return highlights
    
    def _is_part_of_forced_sequence(self, context: RuleContext, move_num: int, is_white: bool) -> bool:
        """Check if a move is part of a forced sequence (not a tactical resource).
        
        A move is part of a forced sequence if:
        1. The opponent's previous move was forcing (very low CPL < 10)
        2. The current move is also a forced response (very low CPL < 10)
        3. The pattern continues in subsequent moves (both sides playing best moves)
        
        This distinguishes forced moves in tactical sequences from independent tactical resources.
        
        Args:
            context: Rule context with move history.
            move_num: Move number to check.
            is_white: True if checking white's move, False for black.
        
        Returns:
            True if move is part of a forced sequence, False otherwise.
        """
        if not context.moves or not context.prev_move:
            return False
        
        # Find the move index
        move_index = None
        for i, m in enumerate(context.moves):
            if m.move_number == move_num:
                move_index = i
                break
        
        if move_index is None or move_index == 0:
            return False
        
        # Check if opponent's previous move was forcing (very low CPL)
        prev_move = context.moves[move_index - 1]
        if is_white:
            # Checking white's move - check if black's previous move was forcing
            if not prev_move.cpl_black:
                return False
            try:
                opponent_prev_cpl = float(prev_move.cpl_black)
                # If opponent's move was not forcing (CPL >= 10), this is not part of forced sequence
                if opponent_prev_cpl >= 10:
                    return False
            except (ValueError, TypeError):
                return False
        else:
            # Checking black's move - check if white's previous move was forcing
            if not prev_move.cpl_white:
                return False
            try:
                opponent_prev_cpl = float(prev_move.cpl_white)
                # If opponent's move was not forcing (CPL >= 10), this is not part of forced sequence
                if opponent_prev_cpl >= 10:
                    return False
            except (ValueError, TypeError):
                return False
        
        # Check if current move is also a forced response (very low CPL)
        current_move = context.moves[move_index]
        if is_white:
            if not current_move.cpl_white:
                return False
            try:
                current_cpl = float(current_move.cpl_white)
                # If current move is not best (CPL >= 10), it's not a forced response
                if current_cpl >= 10:
                    return False
            except (ValueError, TypeError):
                return False
        else:
            if not current_move.cpl_black:
                return False
            try:
                current_cpl = float(current_move.cpl_black)
                # If current move is not best (CPL >= 10), it's not a forced response
                if current_cpl >= 10:
                    return False
            except (ValueError, TypeError):
                return False
        
        # Check if the pattern continues - look at next move to see if sequence is ongoing
        # If both sides continue playing best moves, it's a forced sequence
        if move_index + 1 < len(context.moves):
            next_move = context.moves[move_index + 1]
            if is_white:
                # Check if white's next move is also best, and black's response is also best
                if next_move.cpl_white and next_move.cpl_black:
                    try:
                        our_next_cpl = float(next_move.cpl_white)
                        opponent_next_cpl = float(next_move.cpl_black)
                        # If both continue playing best moves, it's a forced sequence
                        if our_next_cpl < 10 and opponent_next_cpl < 10:
                            return True
                    except (ValueError, TypeError):
                        pass
            else:
                # Check if black's next move is also best, and white's response is also best
                if next_move.cpl_black and next_move.cpl_white:
                    try:
                        our_next_cpl = float(next_move.cpl_black)
                        opponent_next_cpl = float(next_move.cpl_white)
                        # If both continue playing best moves, it's a forced sequence
                        if our_next_cpl < 10 and opponent_next_cpl < 10:
                            return True
                    except (ValueError, TypeError):
                        pass
        
        # If opponent's move was forcing (CPL < 10) and our response is also best (CPL < 10),
        # it's likely part of a forced sequence even if we can't verify continuation
        # This catches cases like forced recaptures in tactical sequences
        return True

