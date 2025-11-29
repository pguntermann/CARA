"""Rule for detecting first departure from theory."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext


class TheoryDepartureRule(HighlightRule):
    """Detects first departure from theory."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for theory departure highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Fact #6: First to leave theory
        # Skip if this move is a book move (cannot be a departure from theory)
        if move.assess_white == "Book Move" or move.assess_black == "Book Move":
            return highlights
        
        if not context.theory_departed and move_num > context.last_book_move_number:
            # Check if move is not the best move (theory departure)
            # Only "Best Move" counts as theory - "Good Move" is a deviation from theory
            if (move.assess_white != "Best Move" and move.white_move) or \
               (move.assess_black != "Best Move" and move.black_move):
                # Determine which side left theory first
                if move.white_move and move.assess_white != "Best Move":
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=True,
                        move_notation=f"{move_num}. {move.white_move}",
                        description="White was first to leave theory",
                        priority=20,
                        rule_type="theory_departure"
                    ))
                elif move.black_move and move.assess_black != "Best Move":
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=False,
                        move_notation=f"{move_num}. ...{move.black_move}",
                        description="Black was first to leave theory",
                        priority=20,
                        rule_type="theory_departure"
                    ))
        
        return highlights

