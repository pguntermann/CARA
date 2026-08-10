"""Rule for detecting rook or queen exchanges started by either side."""

from typing import List, Optional, Tuple

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
    paired_move_notation,
)


class ExchangeSequenceRule(HighlightRule):
    """Detects mutual rook or queen trades started by either side."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for exchange sequence highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        reply = half.reply()
        if reply is None:
            return []

        exchange = self._heavy_piece_exchange(half.capture, reply.capture)
        if exchange is None:
            return []

        piece_name, priority = exchange
        return [
            make_highlight(
                half,
                f"{piece_name} were exchanged",
                priority=priority,
                rule_type="exchange_sequence",
                move_number_end=reply.move_number,
                move_notation=paired_move_notation(half, reply),
            )
        ]

    def _heavy_piece_exchange(
        self, first_capture: str, second_capture: str
    ) -> Optional[Tuple[str, int]]:
        """Return (label, priority) for a mutual rook or queen trade."""
        a = (first_capture or "").lower()
        b = (second_capture or "").lower()
        if a == "r" and b == "r":
            return ("Rooks", 18)
        if a == "q" and b == "q":
            return ("Queens", 30)
        return None
