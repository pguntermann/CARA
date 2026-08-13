"""Rule for detecting novelties."""

from typing import List, Optional

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)


class NoveltyRule(HighlightRule):
    """Detects strong moves that are outside the engine's top-3 choices."""

    MIN_MOVE_NUMBER = 7

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for novelty highlights."""
        if move.move_number < self.MIN_MOVE_NUMBER:
            return []
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        # Deduplication (once per side per phase) is handled in highlight_detector.py
        if half.is_top3 or not half.is_good_move():
            return []

        cpl = half.cpl_float()
        near_top = self._is_near_top_novelty(half, cpl)
        if near_top:
            description = (
                f"{half.side_name} played a creative move close to engine recommendations"
            )
            priority = 18
        else:
            description = (
                f"{half.side_name} played a novelty (not in top 3 engine moves)"
            )
            priority = 15

        return [
            make_highlight(
                half,
                description,
                priority=priority,
                rule_type="novelty",
            )
        ]

    def _is_near_top_novelty(self, half: HalfMoveContext, cpl: Optional[float]) -> bool:
        """True if the move is within 20cp of the 2nd-best engine line."""
        if cpl is None:
            return False
        cpl_2 = half.cpl_2_float()
        if cpl_2 is None:
            return False
        return cpl < cpl_2 + 20
