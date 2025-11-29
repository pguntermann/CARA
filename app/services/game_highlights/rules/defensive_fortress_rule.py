"""Rule for detecting defensive fortress (position difficult to break despite material disadvantage)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation


class DefensiveFortressRule(HighlightRule):
    """Detects when a side maintains a defensive fortress despite material disadvantage."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for defensive fortress highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Track fortress positions in shared state
        fortress_tracking = context.shared_state.get('fortress_tracking', {})
        
        # White's defensive fortress
        if move.white_move and move.eval_white:
            eval_val = parse_evaluation(move.eval_white)
            if eval_val is not None:
                # Check if white is down material (>=300cp)
                material_diff = move.white_material - move.black_material
                if material_diff <= -300:
                    # Check if evaluation is stable (within 100cp of equal)
                    if -100 <= eval_val <= 100:
                        key = (True,)
                        is_consecutive = False
                        if key in fortress_tracking:
                            prev_last_move = fortress_tracking[key].get('last_move', 0)
                            if move_num == prev_last_move or move_num == prev_last_move + 1:
                                is_consecutive = True
                        
                        if key not in fortress_tracking or not is_consecutive:
                            fortress_tracking[key] = {
                                'count': 1,
                                'first_move': move_num,
                                'last_move': move_num
                            }
                        else:
                            fortress_tracking[key]['count'] += 1
                            fortress_tracking[key]['last_move'] = move_num
                        
                        # Check if fortress maintained for 3+ moves
                        fortress_data = fortress_tracking[key]
                        if fortress_data['count'] >= 3:
                            fortress_created = context.shared_state.get('fortress_created', set())
                            if key not in fortress_created:
                                fortress_created.add(key)
                                context.shared_state['fortress_created'] = fortress_created
                                
                                first_move = fortress_data['first_move']
                                last_move = fortress_data['last_move']
                                move_notation = f"{first_move}." if first_move == last_move else f"{first_move}-{last_move}."
                                
                                highlights.append(GameHighlight(
                                    move_number=first_move,
                                    move_number_end=last_move,
                                    is_white=True,
                                    move_notation=move_notation,
                                    description="White maintained a defensive fortress",
                                    priority=29,
                                    rule_type="defensive_fortress"
                                ))
        
        # Black's defensive fortress
        if move.black_move and move.eval_black:
            eval_val = parse_evaluation(move.eval_black)
            if eval_val is not None:
                material_diff = move.black_material - move.white_material
                if material_diff <= -300:
                    if -100 <= eval_val <= 100:
                        key = (False,)
                        is_consecutive = False
                        if key in fortress_tracking:
                            prev_last_move = fortress_tracking[key].get('last_move', 0)
                            if move_num == prev_last_move or move_num == prev_last_move + 1:
                                is_consecutive = True
                        
                        if key not in fortress_tracking or not is_consecutive:
                            fortress_tracking[key] = {
                                'count': 1,
                                'first_move': move_num,
                                'last_move': move_num
                            }
                        else:
                            fortress_tracking[key]['count'] += 1
                            fortress_tracking[key]['last_move'] = move_num
                        
                        fortress_data = fortress_tracking[key]
                        if fortress_data['count'] >= 3:
                            fortress_created = context.shared_state.get('fortress_created', set())
                            if key not in fortress_created:
                                fortress_created.add(key)
                                context.shared_state['fortress_created'] = fortress_created
                                
                                first_move = fortress_data['first_move']
                                last_move = fortress_data['last_move']
                                move_notation = f"{first_move}. ..." if first_move == last_move else f"{first_move}-{last_move}. ..."
                                
                                highlights.append(GameHighlight(
                                    move_number=first_move,
                                    move_number_end=last_move,
                                    is_white=False,
                                    move_notation=move_notation,
                                    description="Black maintained a defensive fortress",
                                    priority=29,
                                    rule_type="defensive_fortress"
                                ))
        
        # Reset tracking if material disadvantage changes significantly
        if move.white_move:
            material_diff = move.white_material - move.black_material
            if material_diff > -300:
                key = (True,)
                if key in fortress_tracking:
                    del fortress_tracking[key]
        
        if move.black_move:
            material_diff = move.black_material - move.white_material
            if material_diff > -300:
                key = (False,)
                if key in fortress_tracking:
                    del fortress_tracking[key]
        
        context.shared_state['fortress_tracking'] = fortress_tracking
        
        return highlights

