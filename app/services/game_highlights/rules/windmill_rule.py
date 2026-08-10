"""Rule for detecting windmill (series of checks and captures)."""

from typing import Any, Dict, List, Optional, Set

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import HalfMoveContext, iter_half_moves
from app.services.game_highlights.helpers import san_is_check

_MIN_WINDMILL_HITS = 3

# shared_state['windmill_tracking'][is_white] =
#   {count, first_move, last_move, captures}
_Tracking = Dict[bool, Dict[str, Any]]


class WindmillRule(HighlightRule):
    """Detects a windmill: repeated check-and-capture hits by the same side."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for windmill highlights."""
        tracking: _Tracking = context.shared_state.setdefault("windmill_tracking", {})
        created: Set[bool] = context.shared_state.setdefault("windmill_created", set())

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

        if not self._is_windmill_ply(half):
            data = tracking.get(key)
            if data is not None and half.move_number > data["last_move"] + 1:
                del tracking[key]
            return None

        prev = tracking.get(key)
        consecutive = (
            prev is not None
            and (
                half.move_number == prev["last_move"]
                or half.move_number == prev["last_move"] + 1
            )
        )

        if prev is None or not consecutive:
            tracking[key] = {
                "count": 1,
                "first_move": half.move_number,
                "last_move": half.move_number,
                "captures": [half.capture] if half.capture else [],
            }
        else:
            prev["count"] += 1
            prev["last_move"] = half.move_number
            if half.capture:
                prev["captures"].append(half.capture)

        data = tracking[key]
        if data["count"] < _MIN_WINDMILL_HITS or key in created:
            return None

        improvement = half.eval_improvement_cp()
        if improvement is not None and improvement <= 0:
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
            description=(
                f"{half.side_name} executed a windmill "
                f"(series of checks and captures)"
            ),
            priority=47,
            rule_type="windmill",
        )

    @staticmethod
    def _is_windmill_ply(half: HalfMoveContext) -> bool:
        """True if this ply is a capturing check (or mate)."""
        return bool(half.capture) and san_is_check(half.san)
