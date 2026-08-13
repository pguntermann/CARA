"""Rule for detecting doubled heavy pieces on an open file."""

from typing import List, Optional

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import is_file_open

_HEAVY = (chess.ROOK, chess.QUEEN)


class DoubledOnOpenFileRule(HighlightRule):
    """Detects newly doubling a rook/queen with another heavy piece on an open file."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for doubled-on-open-file highlights."""
        if move.move_number <= context.opening_end:
            return []
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move():
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        chess_move = half.parse_move()
        if board_before is None or board_after is None or chess_move is None:
            return []

        moved = board_after.piece_at(chess_move.to_square)
        if moved is None or moved.color != half.color or moved.piece_type not in _HEAVY:
            return []

        file_idx = chess.square_file(chess_move.to_square)
        if not is_file_open(board_after, file_idx):
            return []

        partner = self._find_new_partner(
            board_before,
            board_after,
            chess_move.to_square,
            chess_move.from_square,
            half.color,
            file_idx,
        )
        if partner is None:
            return []

        file_name = chr(ord("a") + file_idx)
        return [
            make_highlight(
                half,
                f"{half.side_name} doubled on the open {file_name}-file",
                priority=28,
                rule_type="doubled_on_open_file",
            )
        ]

    def _find_new_partner(
        self,
        board_before: chess.Board,
        board_after: chess.Board,
        moved_to: chess.Square,
        moved_from: chess.Square,
        color: chess.Color,
        file_idx: int,
    ) -> Optional[chess.Square]:
        """Return another heavy piece on this open file that was not already doubled with us."""
        for piece_type in _HEAVY:
            for other_sq in board_after.pieces(piece_type, color):
                if other_sq == moved_to:
                    continue
                if chess.square_file(other_sq) != file_idx:
                    continue
                if self._is_undeveloped_rook(other_sq, board_after.piece_type_at(other_sq), color):
                    continue
                if not self._clear_between(board_after, moved_to, other_sq):
                    continue
                # Already doubled before this move?
                if (
                    chess.square_file(moved_from) == file_idx
                    and self._clear_between(board_before, moved_from, other_sq)
                    and board_before.piece_at(other_sq) is not None
                ):
                    continue
                return other_sq
        return None

    def _clear_between(
        self, board: chess.Board, square1: chess.Square, square2: chess.Square
    ) -> bool:
        file = chess.square_file(square1)
        r1 = chess.square_rank(square1)
        r2 = chess.square_rank(square2)
        for rank in range(min(r1, r2) + 1, max(r1, r2)):
            if board.piece_at(chess.square(file, rank)) is not None:
                return False
        return True

    def _is_undeveloped_rook(
        self, square: chess.Square, piece_type: Optional[chess.PieceType], color: chess.Color
    ) -> bool:
        if piece_type != chess.ROOK:
            return False
        if color == chess.WHITE:
            return square in (chess.A1, chess.H1)
        return square in (chess.A8, chess.H8)
