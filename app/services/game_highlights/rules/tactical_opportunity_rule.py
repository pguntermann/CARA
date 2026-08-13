"""Rule for detecting missed tactical opportunities."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import san_is_tactical

_MULTIPLE_ALT_CPL_MAX = 30


class TacticalOpportunityRule(HighlightRule):
    """Detects when a mistake misses a tactical best move (capture, check, or mate)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for missed tactical opportunity highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.best or half.best == half.san:
            return []
        if not san_is_tactical(half.best):
            return []
        if not half.is_mistake():
            return []

        multiple = half.alt_cpls_below(_MULTIPLE_ALT_CPL_MAX)
        if multiple:
            description = (
                f"{half.side_name} missed multiple tactical opportunities "
                f"(best move was {half.best})"
            )
            priority = 30
        else:
            description = (
                f"{half.side_name} missed a tactical opportunity "
                f"(best move was {half.best})"
            )
            priority = 25

        return [
            make_highlight(
                half,
                description,
                priority=priority,
                rule_type="tactical_opportunity",
            )
        ]
