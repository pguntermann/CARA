"""Rule for detecting occupation of weak squares."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import is_attacked_by_pawn


class WeakSquareRule(HighlightRule):
    """Detects when a piece moves onto a weak square (safe from enemy pawns and defended)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for weak square highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move():
            return []

        board_after = half.board_after()
        dest = half.destination_square()
        if board_after is None or dest is None:
            return []

        piece = board_after.piece_at(dest)
        if piece is None or piece.color != half.color:
            return []

        if not self._is_weak_square(board_after, dest, half.color):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} occupied a weak square",
                priority=23,
                rule_type="weak_square",
            )
        ]

    def _is_weak_square(
        self, board: chess.Board, square: chess.Square, color: chess.Color
    ) -> bool:
        """Opponent's half, not attackable by enemy pawns, defended by us."""
        opponent = not color
        rank = chess.square_rank(square)

        if color == chess.WHITE:
            if rank < 4:
                return False
        elif rank > 3:
            return False

        if is_attacked_by_pawn(board, square, opponent):
            return False
        return board.is_attacked_by(color, square)
