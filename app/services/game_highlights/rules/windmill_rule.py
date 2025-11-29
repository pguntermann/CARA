"""Rule for detecting windmill (series of checks and captures)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation


class WindmillRule(HighlightRule):
    """Detects windmill: series of checks and captures in sequence."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for windmill highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Track windmill sequences in shared state
        windmill_tracking = context.shared_state.get('windmill_tracking', {})
        
        # White's windmill
        if move.white_move and ("+" in move.white_move or "#" in move.white_move) and move.white_capture:
            key = (True,)
            # Check if previous move was also a windmill move (consecutive)
            is_consecutive = False
            if key in windmill_tracking:
                prev_last_move = windmill_tracking[key].get('last_move', 0)
                # Check if this is consecutive (same move number or next move number)
                if move_num == prev_last_move or move_num == prev_last_move + 1:
                    is_consecutive = True
            
            if key not in windmill_tracking or not is_consecutive:
                windmill_tracking[key] = {
                    'count': 1,
                    'first_move': move_num,
                    'last_move': move_num,
                    'captures': [move.white_capture] if move.white_capture else []
                }
            else:
                windmill_tracking[key]['count'] += 1
                windmill_tracking[key]['last_move'] = move_num
                if move.white_capture:
                    windmill_tracking[key]['captures'].append(move.white_capture)
            
            # Check if we have 3+ consecutive windmill moves
            windmill_data = windmill_tracking[key]
            if windmill_data['count'] >= 3:
                # Verify evaluation is improving
                eval_improving = True
                if context.prev_move and context.prev_move.eval_white and move.eval_white:
                    eval_before = parse_evaluation(context.prev_move.eval_white)
                    eval_after = parse_evaluation(move.eval_white)
                    if eval_before is not None and eval_after is not None:
                        eval_improving = eval_after > eval_before
                
                if eval_improving:
                    windmill_created = context.shared_state.get('windmill_created', set())
                    if key not in windmill_created:
                        windmill_created.add(key)
                        context.shared_state['windmill_created'] = windmill_created
                        
                        first_move = windmill_data['first_move']
                        last_move = windmill_data['last_move']
                        move_notation = f"{first_move}." if first_move == last_move else f"{first_move}-{last_move}."
                        
                        highlights.append(GameHighlight(
                            move_number=first_move,
                            move_number_end=last_move,
                            is_white=True,
                            move_notation=move_notation,
                            description="White executed a windmill (series of checks and captures)",
                            priority=47,
                            rule_type="windmill"
                        ))
        
        # Black's windmill
        if move.black_move and ("+" in move.black_move or "#" in move.black_move) and move.black_capture:
            key = (False,)
            is_consecutive = False
            if key in windmill_tracking:
                prev_last_move = windmill_tracking[key].get('last_move', 0)
                if move_num == prev_last_move or move_num == prev_last_move + 1:
                    is_consecutive = True
            
            if key not in windmill_tracking or not is_consecutive:
                windmill_tracking[key] = {
                    'count': 1,
                    'first_move': move_num,
                    'last_move': move_num,
                    'captures': [move.black_capture] if move.black_capture else []
                }
            else:
                windmill_tracking[key]['count'] += 1
                windmill_tracking[key]['last_move'] = move_num
                if move.black_capture:
                    windmill_tracking[key]['captures'].append(move.black_capture)
            
            windmill_data = windmill_tracking[key]
            if windmill_data['count'] >= 3:
                eval_improving = True
                if context.prev_move and context.prev_move.eval_black and move.eval_black:
                    eval_before = parse_evaluation(context.prev_move.eval_black)
                    eval_after = parse_evaluation(move.eval_black)
                    if eval_before is not None and eval_after is not None:
                        eval_improving = eval_after < eval_before  # Inverted for black
                
                if eval_improving:
                    windmill_created = context.shared_state.get('windmill_created', set())
                    if key not in windmill_created:
                        windmill_created.add(key)
                        context.shared_state['windmill_created'] = windmill_created
                        
                        first_move = windmill_data['first_move']
                        last_move = windmill_data['last_move']
                        move_notation = f"{first_move}. ..." if first_move == last_move else f"{first_move}-{last_move}. ..."
                        
                        highlights.append(GameHighlight(
                            move_number=first_move,
                            move_number_end=last_move,
                            is_white=False,
                            move_notation=move_notation,
                            description="Black executed a windmill (series of checks and captures)",
                            priority=47,
                            rule_type="windmill"
                        ))
        
        # Reset tracking if move doesn't continue windmill
        if move.white_move and not (("+" in move.white_move or "#" in move.white_move) and move.white_capture):
            key = (True,)
            if key in windmill_tracking:
                prev_last_move = windmill_tracking[key].get('last_move', 0)
                # If this move is not consecutive, reset
                if move_num > prev_last_move + 1:
                    del windmill_tracking[key]
        
        if move.black_move and not (("+" in move.black_move or "#" in move.black_move) and move.black_capture):
            key = (False,)
            if key in windmill_tracking:
                prev_last_move = windmill_tracking[key].get('last_move', 0)
                if move_num > prev_last_move + 1:
                    del windmill_tracking[key]
        
        context.shared_state['windmill_tracking'] = windmill_tracking
        
        return highlights

