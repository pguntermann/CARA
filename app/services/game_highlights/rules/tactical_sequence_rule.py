"""Rule for detecting tactical sequences (multi-move forcing sequences that win material)."""

from typing import List, Tuple
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import PIECE_VALUES


class TacticalSequenceRule(HighlightRule):
    """Detects multi-move tactical sequences where material is temporarily given up but regained (or more is gained)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for tactical sequence highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if not context.prev_move or not context.moves:
            return highlights
        
        # White's tactical sequence
        if move.white_capture and move.cpl_white and context.move_index > 0:
            try:
                cpl = float(move.cpl_white)
                if cpl < context.good_move_max_cpl:
                    # Check if the sequence is forcing with narrow margins
                    # This is a defining criteria for tactical sequences
                    is_forcing = self._is_sequence_forcing(context, move_num, is_white=True)
                    
                    if is_forcing:
                        # Verify material change in the sequence
                        has_material_change = self._has_material_change_in_sequence(
                            context, move_num, is_white=True
                        )
                        
                        if has_material_change:
                            # Check evaluation improvement amount (primary indicator of material gain)
                            eval_improvement_amount = self._get_evaluation_improvement_amount(
                                context, move_num, is_white=True
                            )
                            
                            # For tactical sequences, require significant evaluation improvement (>=200cp)
                            # This indicates material gain even if material tracking is complex
                            if eval_improvement_amount >= 200:
                                # Find the end of the sequence for move range display
                                move_index = None
                                for i, m in enumerate(context.moves):
                                    if m.move_number == move_num:
                                        move_index = i
                                        break
                                
                                move_number_end = None
                                move_notation = f"{move_num}. {move.white_move}"
                                
                                if move_index is not None:
                                    sequence_end_index = self._find_sequence_end(context, move_index, is_white=True)
                                    if sequence_end_index is not None and sequence_end_index > move_index:
                                        end_move = context.moves[sequence_end_index]
                                        move_number_end = end_move.move_number
                                        if move_number_end != move_num:
                                            move_notation = f"{move_num}-{move_number_end}. {move.white_move}"
                                
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    move_number_end=move_number_end,
                                    is_white=True,
                                    move_notation=move_notation,
                                    description="White used a tactical sequence to win material",
                                    priority=42,
                                    rule_type="tactical_sequence"
                                ))
            except (ValueError, TypeError) as e:
                # Silently handle errors
                pass
        
        # Black's tactical sequence
        if move.black_capture and move.cpl_black and context.move_index > 0:
            try:
                cpl = float(move.cpl_black)
                if cpl < context.good_move_max_cpl:
                    # Check if the sequence is forcing with narrow margins
                    # This is a defining criteria for tactical sequences
                    is_forcing = self._is_sequence_forcing(context, move_num, is_white=False)
                    
                    if is_forcing:
                        # Verify material change in the sequence
                        has_material_change = self._has_material_change_in_sequence(
                            context, move_num, is_white=False
                        )
                        
                        if has_material_change:
                            # Check evaluation improvement amount (primary indicator of material gain)
                            eval_improvement_amount = self._get_evaluation_improvement_amount(
                                context, move_num, is_white=False
                            )
                            
                            # For tactical sequences, require significant evaluation improvement (>=200cp)
                            # This indicates material gain even if material tracking is complex
                            if eval_improvement_amount >= 200:
                                # Find the end of the sequence for move range display
                                move_index = None
                                for i, m in enumerate(context.moves):
                                    if m.move_number == move_num:
                                        move_index = i
                                        break
                                
                                move_number_end = None
                                move_notation = f"{move_num}. ...{move.black_move}"
                                
                                if move_index is not None:
                                    sequence_end_index = self._find_sequence_end(context, move_index, is_white=False)
                                    if sequence_end_index is not None and sequence_end_index > move_index:
                                        end_move = context.moves[sequence_end_index]
                                        move_number_end = end_move.move_number
                                        if move_number_end != move_num:
                                            move_notation = f"{move_num}-{move_number_end}. ...{move.black_move}"
                                
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    move_number_end=move_number_end,
                                    is_white=False,
                                    move_notation=move_notation,
                                    description="Black used a tactical sequence to win material",
                                    priority=42,
                                    rule_type="tactical_sequence"
                                ))
            except (ValueError, TypeError):
                pass
        
        return highlights
    
    def _check_material_in_sequence(self, context: RuleContext, move_num: int,
                                    is_white: bool, material_before: int) -> Tuple[bool, int]:
        """Check if material is regained (or more is gained) within 2-3 moves.
        
        Args:
            context: Rule context with move history.
            move_num: Move number of the potential sequence start.
            is_white: True if checking white's material, False for black.
            material_before: Material before the sequence started.
        
        Returns:
            Tuple of (material_regained: bool, net_gain: int)
        """
        if not context.moves:
            return (False, 0)
        
        # Find the move index
        move_index = None
        for i, m in enumerate(context.moves):
            if m.move_number == move_num:
                move_index = i
                break
        
        if move_index is None or move_index == 0:
            return (False, 0)
        
        # Get material at the start of the sequence (move_index)
        sequence_start_move = context.moves[move_index]
        if is_white:
            material_at_start = sequence_start_move.white_material
        else:
            material_at_start = sequence_start_move.black_material
        
        # Check material in follow-up moves (up to 3 moves ahead)
        # For a tactical sequence, we want to see net material gain
        # Check if material increases beyond the starting point
        for i in range(1, min(4, len(context.moves) - move_index)):
            check_index = move_index + i
            if check_index >= len(context.moves):
                break
            
            check_move = context.moves[check_index]
            if is_white:
                material_now = check_move.white_material
            else:
                material_now = check_move.black_material
            
            # Check if material is now greater than at the start of the sequence
            # This indicates net material gain in the sequence
            # (Allow small margin for rounding - 50cp)
            if material_now > material_at_start + 50:
                net_gain = material_now - material_at_start
                return (True, net_gain)
            # Also check if material is regained to at least the level before sequence started
            # (for cases where material was temporarily lost but then regained)
            elif material_now >= material_before - 50:
                net_gain = material_now - material_before
                # Only count as regained if there's actual net gain (not just breaking even)
                if net_gain > 0:
                    return (True, net_gain)
        
        return (False, 0)
    
    def _is_sequence_forcing(self, context: RuleContext, move_num: int, is_white: bool) -> bool:
        """Check if the sequence is forcing across multiple moves.
        
        A truly forcing tactical sequence requires consecutive moves where BOTH sides
        are playing best moves (very low CPL), indicating forced responses.
        This distinguishes tactical sequences from good positional moves.
        
        Args:
            context: Rule context with move history.
            move_num: Move number of the potential sequence start.
            is_white: True if checking white's sequence, False for black.
        
        Returns:
            True if sequence has at least 2 consecutive moves where both sides play best moves, False otherwise.
        """
        if not context.moves:
            return False
        
        # Find the move index
        move_index = None
        for i, m in enumerate(context.moves):
            if m.move_number == move_num:
                move_index = i
                break
        
        if move_index is None:
            return False
        
        # Track consecutive moves where BOTH sides play best moves (CPL < 10)
        # This indicates a truly forcing tactical sequence
        consecutive_best_moves = 0
        max_moves_to_check = min(6, len(context.moves) - move_index)  # Check up to 6 moves ahead
        
        # Each move object contains both white_move and black_move for that move number
        # For white's sequence starting at move N:
        #   - Move N: white_move (our start), black_move (opponent's response)
        #   - Move N+1: white_move (our continuation), black_move (opponent's response)
        #   - etc.
        
        if is_white:
            for i in range(1, max_moves_to_check):
                check_index = move_index + i
                if check_index >= len(context.moves):
                    break
                
                check_move = context.moves[check_index]
                
                # Check our continuation (white_move) - must be best move (CPL < 10)
                if not check_move.cpl_white:
                    break
                
                try:
                    our_cpl = float(check_move.cpl_white)
                    if our_cpl >= 10:
                        break  # Our move is not best, sequence ends
                    
                    # Our move is best, now check if opponent's response is also best
                    if not check_move.cpl_black:
                        break
                    
                    opponent_cpl = float(check_move.cpl_black)
                    if opponent_cpl < 10:
                        # Both sides played best moves - this is a forcing move pair
                        consecutive_best_moves += 1
                        # Require at least 2 consecutive best-move pairs for a tactical sequence
                        if consecutive_best_moves >= 2:
                            return True
                    else:
                        # Opponent's response is not best - sequence breaks
                        break
                except (ValueError, TypeError):
                    break
        else:
            # For black's sequence - same logic as white
            for i in range(1, max_moves_to_check):
                check_index = move_index + i
                if check_index >= len(context.moves):
                    break
                
                check_move = context.moves[check_index]
                
                # Check our continuation (black_move) - must be best move (CPL < 10)
                if not check_move.cpl_black:
                    break
                
                try:
                    our_cpl = float(check_move.cpl_black)
                    if our_cpl >= 10:
                        break  # Our move is not best, sequence ends
                    
                    # Our move is best, now check if opponent's response is also best
                    if not check_move.cpl_white:
                        break
                    
                    opponent_cpl = float(check_move.cpl_white)
                    if opponent_cpl < 10:
                        # Both sides played best moves - this is a forcing move pair
                        consecutive_best_moves += 1
                        # Require at least 2 consecutive best-move pairs for a tactical sequence
                        if consecutive_best_moves >= 2:
                            return True
                    else:
                        # Opponent's response is not best - sequence breaks
                        break
                except (ValueError, TypeError):
                    break
        
        # Require at least 2 consecutive best-move pairs for a tactical sequence
        return False
    
    def _is_move_forcing(self, cpl: float, cpl_2: str = None, cpl_3: str = None) -> bool:
        """Check if a single move is forcing based on CPL values with narrow margins.
        
        Requires that the best move is significantly better than alternatives,
        not just that it has low CPL (which could be positional).
        
        Args:
            cpl: Centipawn loss of the best move.
            cpl_2: Centipawn loss of 2nd best move (optional).
            cpl_3: Centipawn loss of 3rd best move (optional).
        
        Returns:
            True if move is forcing (narrow margins), False otherwise.
        """
        # Best move must have low CPL (<30)
        if cpl >= 30:
            return False
        
        # Require narrow margins: 2nd best move must have significantly higher CPL
        # This distinguishes forced moves from positions with multiple good options
        if cpl_2:
            try:
                cpl_2_val = float(cpl_2)
                # 2nd best move must be at least 50cp worse to indicate forcing
                margin = cpl_2_val - cpl
                if margin < 50:
                    return False  # Not forcing - multiple good options exist
            except (ValueError, TypeError):
                # If we can't verify margin, require very low CPL (<10) as fallback
                if cpl >= 10:
                    return False
        
        # If best move has very low CPL (<10), it's likely forcing even without margin data
        if cpl < 10:
            return True
        
        # If we have 2nd and 3rd best moves, verify narrow margins
        if cpl_2 and cpl_3:
            try:
                cpl_2_val = float(cpl_2)
                cpl_3_val = float(cpl_3)
                # Both 2nd and 3rd best moves should have high CPL (>50)
                # indicating limited options
                if cpl_2_val > 50 and cpl_3_val > 50:
                    return True
            except (ValueError, TypeError):
                pass
        
        # If best move is good (<30) and we verified narrow margin with 2nd best, it's forcing
        if cpl_2:
            try:
                cpl_2_val = float(cpl_2)
                if cpl_2_val - cpl >= 50:
                    return True
            except (ValueError, TypeError):
                pass
        
        return False
    
    def _check_evaluation_improvement(self, context: RuleContext, move_num: int, is_white: bool) -> bool:
        """Check if evaluation improves significantly after the sequence.
        
        Args:
            context: Rule context with move history.
            move_num: Move number of the potential sequence start.
            is_white: True if checking white's sequence, False for black.
        
        Returns:
            True if evaluation improves significantly, False otherwise.
        """
        if not context.prev_move:
            return False
        
        # Check evaluation improvement over the sequence (up to 3 moves)
        move_index = None
        for i, m in enumerate(context.moves):
            if m.move_number == move_num:
                move_index = i
                break
        
        if move_index is None or move_index == 0:
            return False
        
        # Get evaluation before sequence (from previous move)
        if is_white:
            eval_before = None
            if context.prev_move.eval_white:
                eval_before = parse_evaluation(context.prev_move.eval_white)
            
            # Also try getting eval from the move itself as fallback
            current_move = context.moves[move_index]
            if eval_before is None and current_move.eval_white:
                # Use eval from move before this one in the list
                if move_index > 0:
                    prev_move_in_list = context.moves[move_index - 1]
                    if prev_move_in_list.eval_white:
                        eval_before = parse_evaluation(prev_move_in_list.eval_white)
            
            # Check evaluation after sequence (up to 3 moves ahead)
            if eval_before is not None:
                for i in range(1, min(4, len(context.moves) - move_index)):
                    check_index = move_index + i
                    if check_index >= len(context.moves):
                        break
                    
                    check_move = context.moves[check_index]
                    if check_move.eval_white:
                        eval_after = parse_evaluation(check_move.eval_white)
                        if eval_after is not None:
                            eval_improvement = eval_after - eval_before
                            # Require significant improvement (>150cp)
                            if eval_improvement > 150:
                                return True
        else:
            eval_before = None
            if context.prev_move.eval_black:
                eval_before = parse_evaluation(context.prev_move.eval_black)
            
            # Also try getting eval from the move itself as fallback
            current_move = context.moves[move_index]
            if eval_before is None and current_move.eval_black:
                # Use eval from move before this one in the list
                if move_index > 0:
                    prev_move_in_list = context.moves[move_index - 1]
                    if prev_move_in_list.eval_black:
                        eval_before = parse_evaluation(prev_move_in_list.eval_black)
            
            # Check evaluation after sequence (up to 3 moves ahead)
            if eval_before is not None:
                for i in range(1, min(4, len(context.moves) - move_index)):
                    check_index = move_index + i
                    if check_index >= len(context.moves):
                        break
                    
                    check_move = context.moves[check_index]
                    if check_move.eval_black:
                        eval_after = parse_evaluation(check_move.eval_black)
                        if eval_after is not None:
                            # For black, improvement means eval becomes more negative
                            eval_improvement = eval_before - eval_after
                            # Require significant improvement (>150cp)
                            if eval_improvement > 150:
                                return True
        
        return False
    
    def _get_evaluation_improvement_amount(self, context: RuleContext, move_num: int, is_white: bool) -> float:
        """Get the amount of evaluation improvement across the complete forcing sequence.
        
        This measures from the start of the sequence to the end of the forcing sequence,
        not just to the next move.
        
        Args:
            context: Rule context with move history.
            move_num: Move number of the potential sequence start.
            is_white: True if checking white's sequence, False for black.
        
        Returns:
            Evaluation improvement amount in centipawns.
        """
        if not context.prev_move:
            return 0.0
        
        # Get evaluation before sequence
        if is_white:
            eval_before = None
            if context.prev_move.eval_white:
                eval_before = parse_evaluation(context.prev_move.eval_white)
        else:
            eval_before = None
            if context.prev_move.eval_black:
                eval_before = parse_evaluation(context.prev_move.eval_black)
        
        if eval_before is None:
            return 0.0
        
        # Find the move index
        move_index = None
        for i, m in enumerate(context.moves):
            if m.move_number == move_num:
                move_index = i
                break
        
        if move_index is None:
            return 0.0
        
        # Find the end of the forcing sequence
        sequence_end_index = self._find_sequence_end(context, move_index, is_white)
        if sequence_end_index is None or sequence_end_index <= move_index:
            return 0.0
        
        # Get evaluation at the end of the forcing sequence
        end_move = context.moves[sequence_end_index]
        if is_white:
            if end_move.eval_white:
                eval_after = parse_evaluation(end_move.eval_white)
                if eval_after is not None:
                    improvement = eval_after - eval_before  # Already in centipawns
                    return improvement
        else:
            if end_move.eval_black:
                eval_after = parse_evaluation(end_move.eval_black)
                if eval_after is not None:
                    # For black, improvement means eval becomes more negative
                    improvement = eval_before - eval_after  # Already in centipawns
                    return improvement
        
        return 0.0
    
    def _find_sequence_end(self, context: RuleContext, start_index: int, is_white: bool) -> int:
        """Find the index where the forcing sequence ends.
        
        The sequence ends when:
        1. Our move is not good (CPL >= 30), OR
        2. The opponent's response is not forcing (CPL >= 10) AND we've already captured material
        
        This ensures we don't extend the sequence beyond the actual tactical forcing moves.
        
        Args:
            context: Rule context with move history.
            start_index: Index of the move where sequence starts.
            is_white: True if checking white's sequence, False for black.
        
        Returns:
            Index of the move where sequence ends, or None if not found.
        """
        max_moves_to_check = min(6, len(context.moves) - start_index)
        last_forcing_index = start_index
        material_captured = False  # Track if we've captured material in the sequence
        
        for i in range(1, max_moves_to_check):
            check_index = start_index + i
            if check_index >= len(context.moves):
                break
            
            check_move = context.moves[check_index]
            
            if is_white:
                # Check our continuation (white_move) - must be good
                if not check_move.cpl_white:
                    break
                
                try:
                    our_cpl = float(check_move.cpl_white)
                    if our_cpl >= 30:
                        break  # Our move is not good, sequence ends
                    
                    # Check if we captured material
                    if check_move.white_capture:
                        material_captured = True
                    
                    # Check if opponent's response is forcing
                    if check_move.cpl_black:
                        opponent_cpl = float(check_move.cpl_black)
                        if opponent_cpl < 10:
                            # Opponent's response is best move (forcing), continue
                            last_forcing_index = check_index
                        else:
                            # Opponent's response is not forcing (CPL >= 10)
                            # Check if our next move is also a capture - if so, continue the sequence
                            next_index = check_index + 1
                            if next_index < len(context.moves):
                                next_move = context.moves[next_index]
                                if next_move.white_capture:
                                    # Next move is also a capture, continue sequence
                                    last_forcing_index = check_index
                                    continue
                            
                            # If we've already captured material and next move is not a capture, sequence ends
                            if material_captured:
                                break
                            # Otherwise, continue to see if we capture material
                            last_forcing_index = check_index
                    else:
                        # No CPL data for opponent
                        # If we've captured material, sequence likely ends
                        if material_captured:
                            break
                        last_forcing_index = check_index
                except (ValueError, TypeError):
                    break
            else:
                # For black's sequence - same logic as white
                if not check_move.cpl_black:
                    break
                
                try:
                    our_cpl = float(check_move.cpl_black)
                    if our_cpl >= 30:
                        break  # Our move is not good, sequence ends
                    
                    # Check if we captured material
                    if check_move.black_capture:
                        material_captured = True
                    
                    # Check if opponent's response is forcing
                    if check_move.cpl_white:
                        opponent_cpl = float(check_move.cpl_white)
                        if opponent_cpl < 10:
                            # Opponent's response is best move (forcing), continue
                            last_forcing_index = check_index
                        else:
                            # Opponent's response is not forcing (CPL >= 10)
                            # Check if our next move is also a capture - if so, continue the sequence
                            next_index = check_index + 1
                            if next_index < len(context.moves):
                                next_move = context.moves[next_index]
                                if next_move.black_capture:
                                    # Next move is also a capture, continue sequence
                                    last_forcing_index = check_index
                                    continue
                            
                            # If we've already captured material and next move is not a capture, sequence ends
                            if material_captured:
                                break
                            # Otherwise, continue to see if we capture material
                            last_forcing_index = check_index
                    else:
                        # No CPL data for opponent
                        # If we've captured material, sequence likely ends
                        if material_captured:
                            break
                        last_forcing_index = check_index
                except (ValueError, TypeError):
                    break
        
        return last_forcing_index if last_forcing_index > start_index else None
    
    def _has_material_change_in_sequence(self, context: RuleContext, move_num: int, is_white: bool) -> bool:
        """Verify that material actually changes in the sequence.
        
        This distinguishes tactical sequences (material changes) from
        positional sequences (no material change). Checks for captures
        or material exchanges in the sequence.
        
        Args:
            context: Rule context with move history.
            move_num: Move number of the potential sequence start.
            is_white: True if checking white's sequence, False for black.
        
        Returns:
            True if material changes in the sequence, False otherwise.
        """
        if not context.moves:
            return False
        
        # Find the move index
        move_index = None
        for i, m in enumerate(context.moves):
            if m.move_number == move_num:
                move_index = i
                break
        
        if move_index is None:
            return False
        
        # Find the end of the forcing sequence
        sequence_end_index = self._find_sequence_end(context, move_index, is_white)
        if sequence_end_index is None or sequence_end_index <= move_index:
            return False
        
        # Check for captures in the sequence (indicates material change)
        # This is more reliable than material count tracking which can be complex
        for i in range(move_index, sequence_end_index + 1):
            if i >= len(context.moves):
                break
            
            check_move = context.moves[i]
            if is_white:
                # Check if white captured something
                if check_move.white_capture and check_move.white_capture != "":
                    return True
                # Check if black captured something (material exchange)
                if check_move.black_capture and check_move.black_capture != "":
                    return True
            else:
                # Check if black captured something
                if check_move.black_capture and check_move.black_capture != "":
                    return True
                # Check if white captured something (material exchange)
                if check_move.white_capture and check_move.white_capture != "":
                    return True
        
        # Fallback: Check material count change if no captures found
        # (for cases where material changes through promotion or other means)
        if context.prev_move:
            if is_white:
                material_before = context.prev_white_material
                end_move = context.moves[sequence_end_index]
                material_after = end_move.white_material
            else:
                material_before = context.prev_black_material
                end_move = context.moves[sequence_end_index]
                material_after = end_move.black_material
            
            # Material must change by at least 100cp (1 pawn) to indicate a tactical sequence
            material_change = abs(material_after - material_before)
            return material_change >= 100
        
        return False
