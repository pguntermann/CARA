"""Rule for detecting perpetual check."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation


class PerpetualCheckRule(HighlightRule):
    """Detects perpetual check: repeated checks that lead to draw."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for perpetual check highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Track perpetual check sequences in shared state
        perpetual_check_tracking = context.shared_state.get('perpetual_check_tracking', {})
        
        # White's perpetual check
        if move.white_move and ("+" in move.white_move or "#" in move.white_move):
            key = (True,)
            is_consecutive = False
            if key in perpetual_check_tracking:
                prev_last_move = perpetual_check_tracking[key].get('last_move', 0)
                if move_num == prev_last_move or move_num == prev_last_move + 1:
                    is_consecutive = True
            
            if key not in perpetual_check_tracking or not is_consecutive:
                perpetual_check_tracking[key] = {
                    'count': 1,
                    'first_move': move_num,
                    'last_move': move_num,
                    'eval_values': []
                }
            else:
                perpetual_check_tracking[key]['count'] += 1
                perpetual_check_tracking[key]['last_move'] = move_num
            
            # Store evaluation
            if move.eval_white:
                eval_val = parse_evaluation(move.eval_white)
                if eval_val is not None:
                    perpetual_check_tracking[key]['eval_values'].append(eval_val)
            
            # Check if we have 3+ consecutive checks
            perpetual_data = perpetual_check_tracking[key]
            if perpetual_data['count'] >= 3:
                # Check if evaluation returns to similar value (indicating repetition/draw)
                eval_values = perpetual_data['eval_values']
                if len(eval_values) >= 3:
                    # Check if evaluations are oscillating or returning to similar values
                    eval_range = max(eval_values) - min(eval_values)
                    if eval_range < 50:  # Evaluations are similar (within 50cp)
                        perpetual_created = context.shared_state.get('perpetual_check_created', set())
                        if key not in perpetual_created:
                            perpetual_created.add(key)
                            context.shared_state['perpetual_check_created'] = perpetual_created
                            
                            first_move = perpetual_data['first_move']
                            last_move = perpetual_data['last_move']
                            move_notation = f"{first_move}." if first_move == last_move else f"{first_move}-{last_move}."
                            
                            highlights.append(GameHighlight(
                                move_number=first_move,
                                move_number_end=last_move,
                                is_white=True,
                                move_notation=move_notation,
                                description="White initiated perpetual check",
                                priority=46,
                                rule_type="perpetual_check"
                            ))
        
        # Black's perpetual check
        if move.black_move and ("+" in move.black_move or "#" in move.black_move):
            key = (False,)
            is_consecutive = False
            if key in perpetual_check_tracking:
                prev_last_move = perpetual_check_tracking[key].get('last_move', 0)
                if move_num == prev_last_move or move_num == prev_last_move + 1:
                    is_consecutive = True
            
            if key not in perpetual_check_tracking or not is_consecutive:
                perpetual_check_tracking[key] = {
                    'count': 1,
                    'first_move': move_num,
                    'last_move': move_num,
                    'eval_values': []
                }
            else:
                perpetual_check_tracking[key]['count'] += 1
                perpetual_check_tracking[key]['last_move'] = move_num
            
            if move.eval_black:
                eval_val = parse_evaluation(move.eval_black)
                if eval_val is not None:
                    perpetual_check_tracking[key]['eval_values'].append(eval_val)
            
            perpetual_data = perpetual_check_tracking[key]
            if perpetual_data['count'] >= 3:
                eval_values = perpetual_data['eval_values']
                if len(eval_values) >= 3:
                    eval_range = max(eval_values) - min(eval_values)
                    if eval_range < 50:
                        perpetual_created = context.shared_state.get('perpetual_check_created', set())
                        if key not in perpetual_created:
                            perpetual_created.add(key)
                            context.shared_state['perpetual_check_created'] = perpetual_created
                            
                            first_move = perpetual_data['first_move']
                            last_move = perpetual_data['last_move']
                            move_notation = f"{first_move}. ..." if first_move == last_move else f"{first_move}-{last_move}. ..."
                            
                            highlights.append(GameHighlight(
                                move_number=first_move,
                                move_number_end=last_move,
                                is_white=False,
                                move_notation=move_notation,
                                description="Black initiated perpetual check",
                                priority=46,
                                rule_type="perpetual_check"
                            ))
        
        # Reset tracking if move doesn't continue perpetual check
        if move.white_move and not ("+" in move.white_move or "#" in move.white_move):
            key = (True,)
            if key in perpetual_check_tracking:
                prev_last_move = perpetual_check_tracking[key].get('last_move', 0)
                if move_num > prev_last_move + 1:
                    del perpetual_check_tracking[key]
        
        if move.black_move and not ("+" in move.black_move or "#" in move.black_move):
            key = (False,)
            if key in perpetual_check_tracking:
                prev_last_move = perpetual_check_tracking[key].get('last_move', 0)
                if move_num > prev_last_move + 1:
                    del perpetual_check_tracking[key]
        
        context.shared_state['perpetual_check_tracking'] = perpetual_check_tracking
        
        return highlights

