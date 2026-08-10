"""Rule for detecting perpetual check."""

from typing import Any, Dict, List, Optional, Set

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import HalfMoveContext, iter_half_moves
from app.services.game_highlights.helpers import san_is_check

_MIN_CHECKS = 3
_MAX_EVAL_RANGE_CP = 50

# shared_state['perpetual_check_tracking'][is_white] =
#   {count, first_move, last_move, eval_values}
_Tracking = Dict[bool, Dict[str, Any]]


class PerpetualCheckRule(HighlightRule):
    """Detects repeated checks whose evaluations stay near-drawish."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for perpetual check highlights."""
        tracking: _Tracking = context.shared_state.setdefault(
            "perpetual_check_tracking", {}
        )
        created: Set[bool] = context.shared_state.setdefault(
            "perpetual_check_created", set()
        )

        highlights: List[GameHighlight] = []
        for half in iter_half_moves(move, context):
            hit = self._evaluate_half(half, tracking, created)
            if hit is not None:
                highlights.append(hit)
        return highlights

    def _evaluate_half(
        self,
        half: HalfMoveContext,
        tracking: _Tracking,
        created: Set[bool],
    ) -> Optional[GameHighlight]:
        key = half.is_white

        if not san_is_check(half.san):
            data = tracking.get(key)
            if data is not None and half.move_number > data["last_move"] + 1:
                del tracking[key]
            return None

        prev = tracking.get(key)
        consecutive = prev is not None and (
            half.move_number == prev["last_move"]
            or half.move_number == prev["last_move"] + 1
        )

        if prev is None or not consecutive:
            tracking[key] = {
                "count": 1,
                "first_move": half.move_number,
                "last_move": half.move_number,
                "eval_values": [],
            }
        else:
            prev["count"] += 1
            prev["last_move"] = half.move_number

        data = tracking[key]
        eval_cp = half.eval_after_cp()
        if eval_cp is not None:
            data["eval_values"].append(eval_cp)

        if data["count"] < _MIN_CHECKS or key in created:
            return None
        evals = data["eval_values"]
        if len(evals) < _MIN_CHECKS:
            return None
        if max(evals) - min(evals) >= _MAX_EVAL_RANGE_CP:
            return None

        created.add(key)
        first_move = data["first_move"]
        last_move = data["last_move"]
        if first_move == last_move:
            notation = f"{first_move}." if half.is_white else f"{first_move}. ..."
        else:
            notation = (
                f"{first_move}-{last_move}."
                if half.is_white
                else f"{first_move}-{last_move}. ..."
            )

        return GameHighlight(
            move_number=first_move,
            move_number_end=last_move,
            is_white=half.is_white,
            move_notation=notation,
            description=f"{half.side_name} initiated perpetual check",
            priority=46,
            rule_type="perpetual_check",
        )
