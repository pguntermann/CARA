"""Rule for detecting pawn promotion threats."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import piece_type_from_san


class PawnPromotionThreatRule(HighlightRule):
    """Detects when a pawn advances onto a near-promotion rank and is supported."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pawn promotion threat highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if piece_type_from_san(half.san) != chess.PAWN:
            return []

        parsed = half.parse_move()
        board_after = half.board_after()
        if parsed is None or board_after is None:
            return []

        # Actual promotions are the payoff, not the threat.
        if parsed.promotion is not None:
            return []

        dest = parsed.to_square
        if not self._is_near_promotion_rank(dest, half.color):
            return []

        # Only the pawn that just moved can create the threat.
        if board_after.piece_type_at(dest) != chess.PAWN:
            return []
        if not board_after.is_attacked_by(half.color, dest):
            return []

        # Must still be able to walk forward on its file toward promotion.
        if not self._forward_path_clear(board_after, dest, half.color):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} created a pawn promotion threat",
                priority=40,
                rule_type="pawn_promotion_threat",
            )
        ]

    def _is_near_promotion_rank(self, square: chess.Square, color: chess.Color) -> bool:
        rank = chess.square_rank(square)
        if color == chess.WHITE:
            return rank in (5, 6)  # 6th or 7th — not the promotion rank
        return rank in (1, 2)  # 2nd or 3rd — not the promotion rank

    def _forward_path_clear(
        self,
        board: chess.Board,
        pawn_square: chess.Square,
        color: chess.Color,
    ) -> bool:
        """True if no piece sits further ahead on this file toward promotion.

        A pawn cannot jump; an enemy (or friendly) unit on the queening path
        means this is not a clean promotion threat yet.
        """
        file = chess.square_file(pawn_square)
        rank = chess.square_rank(pawn_square)
        ahead = (
            range(rank + 1, 8) if color == chess.WHITE else range(rank - 1, -1, -1)
        )
        for ahead_rank in ahead:
            if board.piece_at(chess.square(file, ahead_rank)) is not None:
                return False
        return True
