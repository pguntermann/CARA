"""Rule for detecting exchange sequences."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext


class ExchangeSequenceRule(HighlightRule):
    """Detects exchange sequences (rooks, queens)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for exchange sequence highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Fact #4: Exchange sequence (rooks)
        if move.white_capture == "r" and move.black_capture == "r" and move.black_move:
            highlights.append(GameHighlight(
                move_number=move_num,
                move_number_end=move_num,
                is_white=True,
                move_notation=f"{move_num}. {move.white_move} ... {move.black_move}",
                    description="Rooks were exchanged",
                    priority=18,
                    rule_type="exchange_sequence"
            ))
        
        # Fact #5: Exchange sequence (queens)
        if move.white_capture == "q" and move.black_capture == "q" and move.black_move:
            highlights.append(GameHighlight(
                move_number=move_num,
                move_number_end=move_num,
                is_white=True,
                move_notation=f"{move_num}. {move.white_move} ... {move.black_move}",
                    description="Queens were exchanged",
                    priority=30,
                    rule_type="exchange_sequence"
            ))
        
        return highlights

