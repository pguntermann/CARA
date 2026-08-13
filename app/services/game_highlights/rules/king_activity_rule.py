"""Rule for detecting king activity in the endgame."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import piece_type_from_san


class KingActivityRule(HighlightRule):
    """Detects when the king advances toward the center in the endgame."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for king activity highlights."""
        if move.move_number < context.middlegame_end:
            return []
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if half.san.startswith("O") or piece_type_from_san(half.san) != chess.KING:
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        if board_before is None or board_after is None:
            return []

        king_before = board_before.king(half.color)
        king_after = board_after.king(half.color)
        if king_before is None or king_after is None:
            return []

        rank_before = chess.square_rank(king_before)
        rank_after = chess.square_rank(king_after)

        if half.is_white:
            # Advance into ranks 4–7 (0-based 3–6).
            if not (3 <= rank_after <= 6 and rank_after > rank_before):
                return []
        else:
            # Advance into ranks 2–5 (0-based 1–4).
            if not (1 <= rank_after <= 4 and rank_after < rank_before):
                return []

        improvement = half.eval_improvement_cp()
        if improvement is not None and improvement <= 0:
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name}'s king became active in the endgame",
                priority=27,
                rule_type="king_activity",
            )
        ]
