"""Rule for detecting positional improvements."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.utils.material_tracker import calculate_material_count

_MIN_EVAL_GAIN_CP = 50
_MAX_MATERIAL_SWING_CP = 50
_MAX_OWN_CPL = 30
_OPPONENT_MISTAKE_CPL = 100


class PositionalImprovementRule(HighlightRule):
    """Detects eval gains from a good quiet move (little/no material change)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for positional improvement highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        improvement = half.eval_improvement_cp()
        if improvement is None or improvement <= _MIN_EVAL_GAIN_CP:
            return []

        before = half.board_before()
        after = half.board_after()
        if before is None or after is None:
            return []
        material_swing = abs(
            calculate_material_count(after, half.is_white)
            - calculate_material_count(before, half.is_white)
        )
        if material_swing >= _MAX_MATERIAL_SWING_CP:
            return []

        cpl = half.cpl_float()
        if cpl is None or cpl >= _MAX_OWN_CPL:
            return []

        # If the opponent immediately blunders, the eval jump is not "positional".
        reply = half.reply()
        if reply is not None:
            opp_cpl = reply.cpl_float()
            if opp_cpl is not None and opp_cpl > _OPPONENT_MISTAKE_CPL:
                return []

        return [
            make_highlight(
                half,
                f"{half.side_name} gained a positional advantage",
                priority=25,
                rule_type="positional_improvement",
            )
        ]
