"""Rule for detecting piece centralization."""

from typing import List, Optional

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import (
    is_central_square,
    piece_name,
    piece_type_from_san,
)

_CENTRALIZABLE = {chess.KNIGHT, chess.BISHOP, chess.QUEEN}


class CentralizationRule(HighlightRule):
    """Detects when a piece is centralized (moves to center from non-central square)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for centralization highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        piece_type = piece_type_from_san(half.san)
        if piece_type not in _CENTRALIZABLE:
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        if board_before is None or board_after is None:
            return []

        dest_square = half.destination_square()
        if dest_square is None or not is_central_square(dest_square):
            return []

        source_square = self._source_square(
            board_before, board_after, piece_type, half.color
        )
        if source_square is None or is_central_square(source_square):
            return []

        if not self._centralization_meaningful(half):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} centralized the {piece_name(piece_type)}",
                priority=15,
                rule_type="centralization",
            )
        ]

    def _source_square(
        self,
        board_before: chess.Board,
        board_after: chess.Board,
        piece_type: chess.PieceType,
        color: chess.Color,
    ) -> Optional[chess.Square]:
        pieces_before = list(board_before.pieces(piece_type, color))
        pieces_after = list(board_after.pieces(piece_type, color))
        for sq in pieces_before:
            if sq not in pieces_after:
                return sq
        return None

    def _centralization_meaningful(self, half: HalfMoveContext) -> bool:
        """Require a good move (CPL < 30) or a clear eval gain for the mover (> 50cp)."""
        if half.is_good_move(max_cpl=30):
            return True
        improvement = half.eval_improvement_cp()
        return improvement is not None and improvement > 50
