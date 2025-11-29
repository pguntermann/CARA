"""Rule for detecting zwischenzug (in-between move)."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class ZwischenzugRule(HighlightRule):
    """Detects zwischenzug: unexpected move inserted in a sequence, often a check or capture."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for zwischenzug highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if not context.prev_move:
            return highlights
        
        # White's zwischenzug
        # Detect when opponent captured, but instead of recapturing, white makes a different move
        if move.white_move and context.prev_move.black_capture:
            # Check if white didn't recapture (no capture in white's move)
            is_recapture = move.white_capture == context.prev_move.black_capture or (
                move.white_capture and move.white_move and "x" in move.white_move
            )
            
            if not is_recapture and move.cpl_white:
                try:
                    cpl = float(move.cpl_white)
                    # Zwischenzug should be a good move (CPL < 30)
                    if cpl < 30:
                        # Check if move is a check or creates a threat
                        is_check = "+" in move.white_move or "#" in move.white_move
                        is_capture = move.white_capture != ""
                        
                        if is_check or is_capture:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description="White played an in-between move (zwischenzug)",
                                priority=42,
                                rule_type="zwischenzug"
                            ))
                except (ValueError, TypeError):
                    pass
        
        # Black's zwischenzug
        if move.black_move and context.prev_move.white_capture:
            is_recapture = move.black_capture == context.prev_move.white_capture or (
                move.black_capture and move.black_move and "x" in move.black_move
            )
            
            if not is_recapture and move.cpl_black:
                try:
                    cpl = float(move.cpl_black)
                    if cpl < 30:
                        is_check = "+" in move.black_move or "#" in move.black_move
                        is_capture = move.black_capture != ""
                        
                        if is_check or is_capture:
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black played an in-between move (zwischenzug)",
                                priority=42,
                                rule_type="zwischenzug"
                            ))
                except (ValueError, TypeError):
                    pass
        
        return highlights

