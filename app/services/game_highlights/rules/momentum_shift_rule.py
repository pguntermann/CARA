"""Rule for detecting momentum shifts (advantage switching sides)."""

from typing import List, Optional, Tuple

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import MOMENTUM_SHIFT_THRESHOLD
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    iter_half_moves,
    make_highlight,
)

# Consolidating / accurate-flip moves must be reasonably clean.
_MAX_OWN_CPL = 50
_LastShift = Tuple[int, bool]  # (move_number, is_white)


def _sign_changed(before: float, after: float) -> bool:
    return (before > 0 and after < 0) or (before < 0 and after > 0)


def _same_sign(a: float, b: float) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)


class MomentumShiftRule(HighlightRule):
    """Detects when the evaluation flips across equal and the new side holds it.

    Attribution goes to the side that ends up better on a reasonably accurate
    move — either an accurate flip of their own, or consolidating after the
    opponent's crossing error. Crossing blunders are not credited.
    """

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for momentum shift highlights."""
        last: Optional[_LastShift] = context.shared_state.get("last_momentum_shift")
        highlights: List[GameHighlight] = []

        for half in iter_half_moves(move, context):
            hit = self._evaluate_half(half, last)
            if hit is None:
                continue
            highlights.append(hit)
            last = (half.move_number, half.is_white)
            context.shared_state["last_momentum_shift"] = last

        return highlights

    def _evaluate_half(
        self, half: HalfMoveContext, last: Optional[_LastShift]
    ) -> Optional[GameHighlight]:
        # Prefer consolidating after the opponent's zero-crossing error.
        hit = self._from_held_prior_flip(half, last)
        if hit is not None:
            return hit
        # Accurate flip by this side that still holds after the reply.
        return self._from_own_accurate_flip(half, last)

    def _from_held_prior_flip(
        self, half: HalfMoveContext, last: Optional[_LastShift]
    ) -> Optional[GameHighlight]:
        """Credit a good move that keeps the advantage after the opponent flipped eval."""
        prior = half.prior()
        if prior is None:
            return None

        before = prior.eval_before_cp()
        after_prior = prior.eval_after_cp()
        after_half = half.eval_after_cp()
        if before is None or after_prior is None or after_half is None:
            return None

        if not _sign_changed(before, after_prior):
            return None
        if abs(after_prior - before) <= MOMENTUM_SHIFT_THRESHOLD:
            return None

        # Beneficiary of the flip (white-relative eval).
        beneficiary_is_white = after_prior > 0
        if half.is_white != beneficiary_is_white:
            return None
        if not _same_sign(after_prior, after_half):
            return None

        cpl = half.cpl_float()
        if cpl is None or cpl >= _MAX_OWN_CPL:
            return None

        return self._make(half, last)

    def _from_own_accurate_flip(
        self, half: HalfMoveContext, last: Optional[_LastShift]
    ) -> Optional[GameHighlight]:
        """Credit a clean move that itself flips the eval and keeps the new side."""
        before = half.eval_before_cp()
        after = half.eval_after_cp()
        if before is None or after is None:
            return None

        if not _sign_changed(before, after):
            return None
        if abs(after - before) <= MOMENTUM_SHIFT_THRESHOLD:
            return None

        # Mover must be the new beneficiary (not the blunderer who crossed the wrong way).
        beneficiary_is_white = after > 0
        if half.is_white != beneficiary_is_white:
            return None

        cpl = half.cpl_float()
        if cpl is None or cpl >= _MAX_OWN_CPL:
            return None

        reply = half.reply()
        if reply is not None:
            after_reply = reply.eval_after_cp()
            if after_reply is None or not _same_sign(after, after_reply):
                return None

        return self._make(half, last)

    def _make(
        self, half: HalfMoveContext, last: Optional[_LastShift]
    ) -> GameHighlight:
        is_again = False
        if last is not None:
            prev_num, prev_is_white = last
            if half.is_white:
                prev_row = half.context.prev_move
                is_again = prev_num == half.move_number - 1 or (
                    prev_row is not None and prev_num == prev_row.move_number
                )
            else:
                is_again = prev_num == half.move_number and prev_is_white

        description = (
            "The advantage switched sides again"
            if is_again
            else "The advantage switched sides"
        )
        return make_highlight(
            half,
            description,
            priority=45,
            rule_type="momentum_shift",
        )
