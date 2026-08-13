"""Rule for detecting forcing combinations (sacrifices that improve the evaluation)."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import (
    EVALUATION_IMPROVEMENT_THRESHOLD,
    MATERIAL_SACRIFICE_THRESHOLD,
)
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)


class ForcingCombinationRule(HighlightRule):
    """Detects a material sacrifice that is not a quiet equal trade and improves the eval."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for forcing combination highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.capture or not half.is_good_move():
            return []

        reply = half.reply()
        if reply is None:
            return []

        sacrificed = half.own_material_drop_cp(reply)
        if sacrificed is None or sacrificed < MATERIAL_SACRIFICE_THRESHOLD:
            return []

        if half.is_equal_trade_with_neighbors(with_prior=False, with_reply=True):
            return []

        if not self._evaluation_improved(half, reply):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} initiated a forcing combination",
                priority=45,
                rule_type="forcing_combination",
            )
        ]

    def _evaluation_improved(
        self, half: HalfMoveContext, reply: HalfMoveContext
    ) -> bool:
        """True if the sacrificer gains enough eval immediately or after the reply."""
        immediate = half.eval_improvement_cp()
        if immediate is not None and immediate > EVALUATION_IMPROVEMENT_THRESHOLD:
            return True

        gain = half.mover_eval_gain_cp(reply.eval_after_cp())
        return gain is not None and gain > EVALUATION_IMPROVEMENT_THRESHOLD
