"""Rule for detecting tempo gain (move that creates threat forcing opponent response)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import PIECE_VALUES


class TempoGainRule(HighlightRule):
    """Detects when a move gains a tempo by creating a threat."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for tempo gain highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if not context.next_move:
            return highlights
        
        # White's tempo gain
        if move.white_move and move.cpl_white:
            try:
                cpl = float(move.cpl_white)
                if cpl < context.good_move_max_cpl:
                    # Check if move creates a threat (check or attack on >=300cp piece)
                    creates_threat = False
                    if "+" in move.white_move or "#" in move.white_move:
                        creates_threat = True
                    elif move.white_capture:
                        captured_value = PIECE_VALUES.get(move.white_capture.lower(), 0)
                        if captured_value >= 300:
                            creates_threat = True
                    
                    if creates_threat:
                        # Check if opponent's response has CPL > 50 (poor response)
                        opponent_cpl = None
                        if context.next_move.cpl_black:
                            try:
                                opponent_cpl = float(context.next_move.cpl_black)
                            except (ValueError, TypeError):
                                pass
                        
                        if opponent_cpl is not None and opponent_cpl > 50:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description="White gained a tempo",
                                priority=32,
                                rule_type="tempo_gain"
                            ))
            except (ValueError, TypeError):
                pass
        
        # Black's tempo gain
        if move.black_move and move.cpl_black:
            try:
                cpl = float(move.cpl_black)
                if cpl < context.good_move_max_cpl:
                    creates_threat = False
                    if "+" in move.black_move or "#" in move.black_move:
                        creates_threat = True
                    elif move.black_capture:
                        captured_value = PIECE_VALUES.get(move.black_capture.lower(), 0)
                        if captured_value >= 300:
                            creates_threat = True
                    
                    if creates_threat:
                        opponent_cpl = None
                        if context.next_move.cpl_white:
                            try:
                                opponent_cpl = float(context.next_move.cpl_white)
                            except (ValueError, TypeError):
                                pass
                        
                        if opponent_cpl is not None and opponent_cpl > 50:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black gained a tempo",
                                priority=32,
                                rule_type="tempo_gain"
                            ))
            except (ValueError, TypeError):
                pass
        
        return highlights

