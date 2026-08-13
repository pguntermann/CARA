"""Rule for detecting first departure from opening theory."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    iter_half_moves,
    make_highlight,
)


class TheoryDepartureRule(HighlightRule):
    """Detects the first move that leaves opening theory."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for theory departure highlights."""
        # Book exit belongs to opening/middlegame, not the endgame.
        if move.move_number >= context.middlegame_end:
            return []

        # Skip while either side is still marked as a book move on this row.
        if move.assess_white == "Book Move" or move.assess_black == "Book Move":
            return []

        if context.theory_departed or move.move_number <= context.last_book_move_number:
            return []

        # Only "Best Move" stays within theory; anything else is a departure.
        # Prefer White if both deviate on the same full-move row.
        for half in iter_half_moves(move, context):
            if half.assess != "Best Move":
                return [
                    make_highlight(
                        half,
                        f"{half.side_name} was first to leave theory",
                        priority=20,
                        rule_type="theory_departure",
                    )
                ]
        return []
