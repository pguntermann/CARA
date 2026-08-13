"""Rule for detecting zwischenzug (in-between move)."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import san_is_check


class ZwischenzugRule(HighlightRule):
    """Detects an in-between check/capture instead of an expected recapture."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for zwischenzug highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        prior = half.prior()
        if prior is None or not prior.capture:
            return []

        if self._is_recapture(half, prior):
            return []

        if not half.is_good_move(max_cpl=30):
            return []

        if not (san_is_check(half.san) or half.capture):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} played an in-between move (zwischenzug)",
                priority=42,
                rule_type="zwischenzug",
            )
        ]

    def _is_recapture(self, half: HalfMoveContext, prior: HalfMoveContext) -> bool:
        """True if this move takes back on the capture square (or same piece type)."""
        if not half.capture:
            return False

        dest = half.destination_square()
        opp_square = prior.destination_square()
        if dest is not None and opp_square is not None and dest == opp_square:
            return True

        return half.capture.lower() == prior.capture.lower()
