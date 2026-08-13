"""Rule for detecting tactical sequences (forcing multi-move material wins)."""

from typing import List, Optional

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)

# Reply and follow-ups: near-forced, but reachable in human games (not engine-perfect).
_FORCED_CPL_MAX = 20
_FOLLOW_CPL_MAX = 30
_OUR_CONTINUE_CPL_MAX = 30
_MIN_FORCING_PAIRS = 1
_EVAL_IMPROVEMENT_MIN_CP = 200
_MAX_SEQUENCE_PAIRS = 6


class TacticalSequenceRule(HighlightRule):
    """Detects a forcing multi-move sequence that improves the evaluation significantly."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for tactical sequence highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.capture or not half.is_good_move():
            return []
        if half.eval_before_cp() is None:
            return []

        if not self._is_sequence_forcing(half):
            return []

        end_half = self._find_sequence_end(half)
        if end_half is None:
            return []

        if not self._has_material_change(half, end_half):
            return []

        improvement = half.eval_change_through(end_half)
        if improvement is None or improvement < _EVAL_IMPROVEMENT_MIN_CP:
            return []

        end_num = end_half.move_number
        if end_num != half.move_number:
            if half.is_white:
                notation = f"{half.move_number}-{end_num}. {half.san}"
            else:
                notation = f"{half.move_number}-{end_num}. ...{half.san}"
        else:
            notation = half.move_notation()

        return [
            make_highlight(
                half,
                f"{half.side_name} used a tactical sequence to win material",
                priority=42,
                rule_type="tactical_sequence",
                move_number_end=end_num,
                move_notation=notation,
            )
        ]

    def _is_sequence_forcing(self, half: HalfMoveContext) -> bool:
        """True if the reply is forced and at least one later (our, their) pair stays near-best."""
        initial_reply = half.reply()
        if initial_reply is None or not initial_reply.is_near_best(_FORCED_CPL_MAX):
            return False
        return (
            half.count_near_best_continuation_pairs(
                cpl_max=_FOLLOW_CPL_MAX, limit=_MAX_SEQUENCE_PAIRS
            )
            >= _MIN_FORCING_PAIRS
        )

    def _find_sequence_end(self, half: HalfMoveContext) -> Optional[HalfMoveContext]:
        """Last ply still inside the forcing continuation (usually the opponent's reply)."""
        last: Optional[HalfMoveContext] = None
        for our, their in half.iter_continuation_pairs(limit=_MAX_SEQUENCE_PAIRS):
            if not our.is_good_move(max_cpl=_OUR_CONTINUE_CPL_MAX):
                break
            if their is not None and their.is_near_best(_FOLLOW_CPL_MAX):
                last = their
                continue
            last = our
            break
        return last

    def _has_material_change(
        self, start: HalfMoveContext, end: HalfMoveContext
    ) -> bool:
        """True if any capture occurs from the starter through the end ply."""
        if start.capture:
            return True
        for ply in start.iter_following(limit=_MAX_SEQUENCE_PAIRS * 2 + 2):
            if ply.capture:
                return True
            if ply.same_ply(end):
                break
        return False
