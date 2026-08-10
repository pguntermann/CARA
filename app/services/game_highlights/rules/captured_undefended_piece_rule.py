"""Rule for capturing an undefended enemy unit."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import piece_name


class CapturedUndefendedPieceRule(HighlightRule):
    """Detects taking a unit that had no defenders (cashing in a hang)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for undefended-capture highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move():
            return []
        if not half.captures_undefended_unit():
            return []
        if half.is_equal_trade_with_neighbors():
            return []

        unit = piece_name(half.capture, default="piece")
        return [
            make_highlight(
                half,
                f"{half.side_name} captured an undefended {unit}",
                priority=26,
                rule_type="captured_undefended_piece",
            )
        ]
