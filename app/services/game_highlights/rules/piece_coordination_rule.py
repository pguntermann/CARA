"""Rule for detecting piece coordination (multiple pieces attacking one target)."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import MIN_VALUABLE_PIECE_VALUE


class PieceCoordinationRule(HighlightRule):
    """Detects when multiple pieces coordinate against the same valuable target."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for piece coordination highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move(max_cpl=30):
            return []

        board_after = half.board_after()
        if board_after is None:
            return []

        if not self._has_piece_coordination(board_after, half.color):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name}'s pieces coordinated effectively",
                priority=33,
                rule_type="piece_coordination",
            )
        ]

    def _has_piece_coordination(self, board: chess.Board, color: chess.Color) -> bool:
        """True if 2+ friendly pieces attack the same valuable enemy unit (or king)."""
        opponent = not color
        for piece_type in (
            chess.PAWN,
            chess.KNIGHT,
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
            chess.KING,
        ):
            for target_sq in board.pieces(piece_type, opponent):
                target = board.piece_at(target_sq)
                if target is None:
                    continue
                value = PIECE_VALUES.get(target.symbol().lower(), 0)
                if value < MIN_VALUABLE_PIECE_VALUE and piece_type != chess.KING:
                    continue
                if len(board.attackers(color, target_sq)) >= 2:
                    return True
        return False
