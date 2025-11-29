"""Rule for detecting delayed mating (consecutive missed mate opportunities)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext


class DelayedMatingRule(HighlightRule):
    """Detects when a player misses mating moves 2+ times consecutively."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for delayed mating highlights.
        
        This rule also tracks individual missed mate opportunities and creates
        delayed mating highlights when 2+ consecutive misses occur.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances (both missed mates and delayed mating).
        """
        highlights = []
        move_num = move.move_number
        
        # Determine phase
        if move_num <= context.opening_end:
            phase = "opening"
        elif move_num < context.middlegame_end:
            phase = "middlegame"
        else:
            phase = "endgame"
        
        missed_mate_tracking = context.shared_state.get('missed_mate_tracking', {})
        delayed_mate_created = context.shared_state.get('delayed_mate_created', set())
        delayed_mating_ranges = context.shared_state.get('delayed_mating_ranges', [])
        
        # Check white's missed mate opportunity
        if move.best_white:
            is_mate_move = "#" in move.best_white
            eval_shows_mate = move.eval_white and move.eval_white.startswith("M") and not move.eval_white.startswith("-M")
            best_move_is_mate = is_mate_move or eval_shows_mate
            
            if best_move_is_mate and move.white_move != move.best_white:
                if move.cpl_white:
                    try:
                        cpl = float(move.cpl_white)
                        if cpl > context.good_move_max_cpl:
                            # Verify mate threat is real: check if mate is within 5 moves
                            # This is a simplified check - if eval shows mate (M1-M5), it's a real threat
                            mate_threat_real = False
                            if move.eval_white:
                                # Check if eval shows mate (M1, M2, M3, M4, M5)
                                if move.eval_white.startswith("M") and not move.eval_white.startswith("-M"):
                                    try:
                                        mate_in = int(move.eval_white[1:])
                                        if mate_in <= 5:
                                            mate_threat_real = True
                                    except (ValueError, TypeError):
                                        # If we can't parse, assume it's a mate threat if eval shows M
                                        mate_threat_real = True
                            
                            if mate_threat_real:
                                key = (True, phase)
                                if key in missed_mate_tracking:
                                    count, first_move, _, best_move = missed_mate_tracking[key]
                                    missed_mate_tracking[key] = (count + 1, first_move, move_num, move.best_white)
                                else:
                                    missed_mate_tracking[key] = (1, move_num, move_num, move.best_white)
                                
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    is_white=True,
                                    move_notation=f"{move_num}. {move.white_move}",
                                    description=f"White missed a checkmate opportunity (best move was {move.best_white})",
                                    priority=50,
                                    rule_type="delayed_mating"
                                ))
                    except (ValueError, TypeError):
                        pass
            elif best_move_is_mate and move.white_move == move.best_white:
                key = (True, phase)
                if key in missed_mate_tracking:
                    del missed_mate_tracking[key]
            elif not best_move_is_mate:
                key = (True, phase)
                if key in missed_mate_tracking:
                    del missed_mate_tracking[key]
        else:
            key = (True, phase)
            if key in missed_mate_tracking:
                del missed_mate_tracking[key]
        
        # Check black's missed mate opportunity
        if move.best_black:
            is_mate_move = "#" in move.best_black
            eval_shows_mate = move.eval_black and move.eval_black.startswith("-M")
            best_move_is_mate = is_mate_move or eval_shows_mate
            
            if best_move_is_mate and move.black_move != move.best_black:
                if move.cpl_black:
                    try:
                        cpl = float(move.cpl_black)
                        if cpl > context.good_move_max_cpl:
                            # Verify mate threat is real: check if mate is within 5 moves
                            # This is a simplified check - if eval shows mate (M1-M5), it's a real threat
                            mate_threat_real = False
                            if move.eval_black:
                                # Check if eval shows mate (-M1, -M2, -M3, -M4, -M5)
                                if move.eval_black.startswith("-M"):
                                    try:
                                        mate_in = int(move.eval_black[2:])
                                        if mate_in <= 5:
                                            mate_threat_real = True
                                    except (ValueError, TypeError):
                                        # If we can't parse, assume it's a mate threat if eval shows -M
                                        mate_threat_real = True
                            
                            if mate_threat_real:
                                key = (False, phase)
                                if key in missed_mate_tracking:
                                    count, first_move, _, best_move = missed_mate_tracking[key]
                                    missed_mate_tracking[key] = (count + 1, first_move, move_num, move.best_black)
                                else:
                                    missed_mate_tracking[key] = (1, move_num, move_num, move.best_black)
                                
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    is_white=False,
                                    move_notation=f"{move_num}. ...{move.black_move}",
                                    description=f"Black missed a checkmate opportunity (best move was {move.best_black})",
                                    priority=50,
                                    rule_type="delayed_mating"
                                ))
                    except (ValueError, TypeError):
                        pass
            elif best_move_is_mate and move.black_move == move.best_black:
                key = (False, phase)
                if key in missed_mate_tracking:
                    del missed_mate_tracking[key]
            elif not best_move_is_mate:
                key = (False, phase)
                if key in missed_mate_tracking:
                    del missed_mate_tracking[key]
        else:
            key = (False, phase)
            if key in missed_mate_tracking:
                del missed_mate_tracking[key]
        
        # Check for delayed mating (2+ consecutive misses)
        for (is_white_side, phase_key), (count, first_move_num, last_move_num, best_move) in list(missed_mate_tracking.items()):
            if count >= 2 and (is_white_side, phase_key) not in delayed_mate_created:
                if is_white_side:
                    move_notation = f"{first_move_num}." if first_move_num == last_move_num else f"{first_move_num}-{last_move_num}."
                    description = f"White delayed mating (best move was {best_move})"
                    
                    highlights.append(GameHighlight(
                        move_number=first_move_num,
                        move_number_end=last_move_num,
                        is_white=True,
                        move_notation=move_notation,
                        description=description,
                        priority=55,
                        rule_type="delayed_mating"
                    ))
                    delayed_mate_created.add((is_white_side, phase_key))
                    delayed_mating_ranges.append((first_move_num, last_move_num, True))
                else:
                    move_notation = f"{first_move_num}. ..." if first_move_num == last_move_num else f"{first_move_num}-{last_move_num}. ..."
                    description = f"Black delayed mating (best move was {best_move})"
                    
                    highlights.append(GameHighlight(
                        move_number=first_move_num,
                        move_number_end=last_move_num,
                        is_white=False,
                        move_notation=move_notation,
                        description=description,
                        priority=55,
                        rule_type="delayed_mating"
                    ))
                    delayed_mate_created.add((is_white_side, phase_key))
                    delayed_mating_ranges.append((first_move_num, last_move_num, False))
        
        # Update shared state
        context.shared_state['missed_mate_tracking'] = missed_mate_tracking
        context.shared_state['delayed_mate_created'] = delayed_mate_created
        context.shared_state['delayed_mating_ranges'] = delayed_mating_ranges
        
        return highlights

