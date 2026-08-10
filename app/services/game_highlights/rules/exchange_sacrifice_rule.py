"""Rule for detecting exchange sacrifice (rook for minor piece with positional compensation)."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
    paired_move_notation,
)

_MINOR = frozenset({"n", "b"})
_MATERIAL_LOSS_MIN = 150
_MATERIAL_LOSS_MAX = 250
_EVAL_DROP_MAX_CP = 100


class ExchangeSacrificeRule(HighlightRule):
    """Detects giving a rook for a knight/bishop when the evaluation holds up."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for exchange sacrifice highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        """Starter takes a minor; opponent's reply takes the rook (exchange sac)."""
        our_cap = (half.capture or "").lower()
        if our_cap not in _MINOR:
            return []

        reply = half.reply()
        if reply is None or (reply.capture or "").lower() != "r":
            return []

        # Net: we gain a minor, they take our rook → ~200cp.
        material_loss = PIECE_VALUES.get("r", 500) - PIECE_VALUES.get(our_cap, 0)
        if not (_MATERIAL_LOSS_MIN <= material_loss <= _MATERIAL_LOSS_MAX):
            return []

        # Positional compensation: sacrificer's eval must not collapse across the trade.
        eval_change = half.eval_change_through(reply)
        if eval_change is not None and eval_change <= -_EVAL_DROP_MAX_CP:
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} sacrificed the exchange for positional compensation",
                priority=36,
                rule_type="exchange_sacrifice",
                move_number_end=reply.move_number,
                move_notation=paired_move_notation(half, reply),
            )
        ]
