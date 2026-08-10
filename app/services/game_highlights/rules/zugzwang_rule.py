"""Rule for detecting zugzwang (any move worsens the position)."""

from typing import Dict, List, Optional

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    iter_half_moves,
    make_highlight,
)
from app.utils.material_tracker import calculate_material_count

_MIN_CPL = 150
_EVAL_DROP_CP = 50
_MAX_TOTAL_MATERIAL_CP = 2000
_COOLDOWN_MOVES = 2


class ZugzwangRule(HighlightRule):
    """Detects simplified endgames where every top move is bad and the eval drops."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for zugzwang highlights."""
        tracking: Dict[str, int] = context.shared_state.setdefault(
            "zugzwang_tracking", {}
        )
        highlights: List[GameHighlight] = []
        for half in iter_half_moves(move, context):
            hit = self._evaluate_half(half, tracking)
            if hit is not None:
                highlights.append(hit)
        return highlights

    def _evaluate_half(
        self, half: HalfMoveContext, tracking: Dict[str, int]
    ) -> Optional[GameHighlight]:
        if half.move_number < half.context.middlegame_end:
            return None

        cpl = half.cpl_float()
        cpl_2 = half.cpl_2_float()
        cpl_3 = half.cpl_3_float()
        if cpl is None or cpl_2 is None or cpl_3 is None:
            return None
        if cpl <= _MIN_CPL or cpl_2 <= _MIN_CPL or cpl_3 <= _MIN_CPL:
            return None

        board = half.board_after()
        if board is None:
            return None
        total = calculate_material_count(board, True) + calculate_material_count(
            board, False
        )
        if total >= _MAX_TOTAL_MATERIAL_CP:
            return None

        improvement = half.eval_improvement_cp()
        if improvement is None or improvement > -_EVAL_DROP_CP:
            return None

        # Avoid back-to-back zugzwang highlights on consecutive moves.
        other_key = "last_black_zugzwang" if half.is_white else "last_white_zugzwang"
        last_other = tracking.get(other_key, 0)
        if last_other > 0 and half.move_number - last_other <= _COOLDOWN_MOVES:
            return None

        # Attribute to the opponent ply that left this side to move in zugzwang.
        prior = half.prior()
        if prior is None:
            return None

        own_key = "last_white_zugzwang" if half.is_white else "last_black_zugzwang"
        tracking[own_key] = half.move_number

        return make_highlight(
            prior,
            f"{half.side_name} is in zugzwang (any move worsens the position)",
            priority=35,
            rule_type="zugzwang",
        )
