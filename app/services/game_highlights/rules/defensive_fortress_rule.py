"""Rule for detecting defensive fortress (stable eval despite material disadvantage)."""

from typing import Any, Dict, List, Optional, Set

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import HalfMoveContext, iter_half_moves
from app.utils.material_tracker import calculate_material_count

_MIN_MATERIAL_DISADVANTAGE_CP = 300
_MAX_ABS_EVAL_CP = 100
_MIN_FORTRESS_MOVES = 3

# shared_state['fortress_tracking'][is_white] = {count, first_move, last_move}
_Tracking = Dict[bool, Dict[str, Any]]


class DefensiveFortressRule(HighlightRule):
    """Detects a side holding a near-equal eval while down significant material."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for defensive fortress highlights."""
        tracking: _Tracking = context.shared_state.setdefault("fortress_tracking", {})
        created: Set[bool] = context.shared_state.setdefault("fortress_created", set())

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
        eval_cp = half.eval_after_cp()
        board = half.board_after()
        if eval_cp is None or board is None:
            return None

        our_mat = calculate_material_count(board, half.is_white)
        opp_mat = calculate_material_count(board, not half.is_white)
        material_diff = our_mat - opp_mat

        if material_diff > -_MIN_MATERIAL_DISADVANTAGE_CP:
            tracking.pop(key, None)
            return None

        if not (-_MAX_ABS_EVAL_CP <= eval_cp <= _MAX_ABS_EVAL_CP):
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
            }
        else:
            prev["count"] += 1
            prev["last_move"] = half.move_number

        data = tracking[key]
        if data["count"] < _MIN_FORTRESS_MOVES or key in created:
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
            description=f"{half.side_name} maintained a defensive fortress",
            priority=29,
            rule_type="defensive_fortress",
        )
