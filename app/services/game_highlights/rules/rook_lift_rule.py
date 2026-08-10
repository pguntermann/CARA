"""Rule for detecting rook lift (rook moves to a higher rank to create threats)."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import piece_type_from_san


class RookLiftRule(HighlightRule):
    """Detects when a rook moves up from the back ranks toward the center/opponent."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for rook lift highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if piece_type_from_san(half.san) != chess.ROOK:
            return []

        board_before = half.board_before()
        chess_move = half.parse_move()
        if board_before is None or chess_move is None:
            return []

        moved = board_before.piece_at(chess_move.from_square)
        if moved is None or moved.piece_type != chess.ROOK or moved.color != half.color:
            return []

        rank_before = chess.square_rank(chess_move.from_square)
        rank_after = chess.square_rank(chess_move.to_square)

        if half.is_white:
            # From ranks 1–2 up to rank 3+
            if not (rank_before <= 1 and rank_after >= 2):
                return []
        else:
            # From ranks 7–8 down to rank 6 or below
            if not (rank_before >= 6 and rank_after <= 5):
                return []

        # If eval data exists, require the lift not to worsen the mover's eval.
        improvement = half.eval_improvement_cp()
        if improvement is not None and improvement <= 0:
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} lifted the rook to create threats",
                priority=24,
                rule_type="rook_lift",
            )
        ]
