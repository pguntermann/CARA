"""Rule for detecting initiative seized."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)

_MIN_EVAL_GAIN_CP = 50
_MAX_OWN_CPL = 30
_MIN_OPPONENT_CPL = 50


class InitiativeRule(HighlightRule):
    """Detects seizing the initiative: a strong move that forces a poor reply."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for initiative highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        improvement = half.eval_improvement_cp()
        if improvement is None or improvement < _MIN_EVAL_GAIN_CP:
            return []

        cpl = half.cpl_float()
        if cpl is None or cpl >= _MAX_OWN_CPL:
            return []

        reply = half.reply()
        if reply is None:
            return []
        opp_cpl = reply.cpl_float()
        if opp_cpl is None or opp_cpl <= _MIN_OPPONENT_CPL:
            return []

        # Advantage must still hold after the forced reply.
        through = half.eval_change_through(reply)
        if through is None or through < _MIN_EVAL_GAIN_CP:
            return []

        # Higher priority when the opponent had few decent alternatives.
        priority = 30 if reply.alt_cpls_above(_MIN_OPPONENT_CPL) else 28
        return [
            make_highlight(
                half,
                f"{half.side_name} seized the initiative",
                priority=priority,
                rule_type="initiative",
            )
        ]
