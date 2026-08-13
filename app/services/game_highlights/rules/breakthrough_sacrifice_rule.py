"""Rule for detecting breakthrough sacrifice (sacrificing a piece to break through)."""

from typing import List, Optional

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.utils.material_tracker import calculate_material_count

_MIN_SACRIFICE_CP = 300
_MIN_NET_MATERIAL_LOSS_CP = 150
_MIN_EVAL_GAIN_CP = 200
_REGAIN_CAPTURE_FRACTION = 0.8
_REGAIN_MATERIAL_SLACK_CP = 50
_FOLLOW_UP_PLIES = 8


class BreakthroughSacrificeRule(HighlightRule):
    """Detects a real piece sacrifice that improves the eval after the opponent replies."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for breakthrough sacrifice highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.capture or half.cpl_float() is None:
            return []

        reply = half.reply()
        if reply is None:
            return []

        sacrificed = half.own_material_drop_cp(reply)
        if sacrificed is None or sacrificed < _MIN_SACRIFICE_CP:
            return []

        # Own-piece drop alone is not enough: B×N / R×B leaves own count -300 but
        # relative material unchanged. Require a real net deficit after the reply.
        net_loss = self._net_material_loss_cp(half, reply)
        if net_loss is None or net_loss < _MIN_NET_MATERIAL_LOSS_CP:
            return []

        if self._material_regained(half, sacrificed):
            return []

        # Eval must jump for the sacrificer after the opponent's reply.
        gain = half.mover_eval_gain_cp(reply.eval_after_cp())
        if gain is None or gain <= _MIN_EVAL_GAIN_CP:
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} sacrificed a piece to break through",
                priority=44,
                rule_type="breakthrough_sacrifice",
            )
        ]

    def _net_material_loss_cp(
        self, half: HalfMoveContext, reply: HalfMoveContext
    ) -> Optional[int]:
        """Relative material lost from before this ply to after ``reply`` (positive = worse)."""
        before = half.board_before()
        after = reply.board_after()
        if before is None or after is None:
            return None

        def relative(board) -> int:
            return calculate_material_count(board, half.is_white) - calculate_material_count(
                board, not half.is_white
            )

        return relative(before) - relative(after)

    def _material_regained(self, half: HalfMoveContext, sacrificed: int) -> bool:
        """True if follow-ups regain the sacrificed material (tactical sequence, not sac)."""
        before_board = half.board_before()
        if before_board is None:
            return False
        material_before = calculate_material_count(before_board, half.is_white)

        for ply in half.iter_following(limit=_FOLLOW_UP_PLIES):
            if ply.is_white != half.is_white:
                continue

            if ply.capture:
                capture_value = PIECE_VALUES.get(ply.capture.lower(), 0)
                if capture_value >= sacrificed * _REGAIN_CAPTURE_FRACTION:
                    return True

            after = ply.board_after()
            if after is None:
                continue
            material_now = calculate_material_count(after, half.is_white)
            if material_now >= material_before - _REGAIN_MATERIAL_SLACK_CP:
                return True

        return False
