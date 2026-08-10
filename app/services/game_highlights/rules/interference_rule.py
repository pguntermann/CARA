"""Rule for detecting interference (blocking opponent's piece coordination)."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)

_SLIDERS = frozenset({chess.ROOK, chess.BISHOP, chess.QUEEN})
_MIN_VALUE = 300


class InterferenceRule(HighlightRule):
    """Detects placing a piece between two enemy sliders that previously saw each other."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for interference highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        # Interference is about placing a piece, not capturing.
        if half.capture or not half.is_good_move():
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        moved_square = half.destination_square()
        if board_before is None or board_after is None or moved_square is None:
            return []

        if not self._creates_interference(board_before, moved_square, half.color):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} created interference",
                priority=38,
                rule_type="interference",
            )
        ]

    def _creates_interference(
        self,
        board_before: chess.Board,
        moved_square: chess.Square,
        color: chess.Color,
    ) -> bool:
        """True if the moved piece sits between two enemy sliders that had a clear path."""
        opponent_color = not color

        piece_before_on_square = board_before.piece_at(moved_square)
        if piece_before_on_square and piece_before_on_square.color == opponent_color:
            return False

        moved_file = chess.square_file(moved_square)
        moved_rank = chess.square_rank(moved_square)
        directions = (
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        )

        for df, dr in directions:
            opponent_pieces_before = []

            for dist in range(1, 8):
                file = moved_file + df * dist
                rank = moved_rank + dr * dist
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                sq = chess.square(file, rank)
                piece_before = board_before.piece_at(sq)
                if piece_before and piece_before.color == opponent_color:
                    opponent_pieces_before.append(sq)
                elif piece_before:
                    break

            for dist in range(1, 8):
                file = moved_file - df * dist
                rank = moved_rank - dr * dist
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                sq = chess.square(file, rank)
                piece_before = board_before.piece_at(sq)
                if piece_before and piece_before.color == opponent_color:
                    opponent_pieces_before.append(sq)
                elif piece_before:
                    break

            if len(opponent_pieces_before) < 2:
                continue

            for i, piece1 in enumerate(opponent_pieces_before):
                for piece2 in opponent_pieces_before[i + 1 :]:
                    piece1_obj = board_before.piece_at(piece1)
                    piece2_obj = board_before.piece_at(piece2)
                    if not piece1_obj or not piece2_obj:
                        continue
                    if piece1_obj.piece_type not in _SLIDERS:
                        continue
                    if piece2_obj.piece_type not in _SLIDERS:
                        continue

                    piece1_value = PIECE_VALUES.get(piece1_obj.symbol().lower(), 0)
                    piece2_value = PIECE_VALUES.get(piece2_obj.symbol().lower(), 0)
                    if piece1_value < _MIN_VALUE and piece2_value < _MIN_VALUE:
                        continue

                    if not self._has_clear_path_before(
                        board_before, piece1, piece2, moved_square, df, dr
                    ):
                        continue
                    if self._is_between_on_line(moved_square, piece1, piece2, df, dr):
                        return True

        return False

    def _has_clear_path_before(
        self,
        board_before: chess.Board,
        piece1: chess.Square,
        piece2: chess.Square,
        moved_square: chess.Square,
        df: int,
        dr: int,
    ) -> bool:
        """True if the two pieces could see each other before the interference move."""
        p1_file = chess.square_file(piece1)
        p1_rank = chess.square_rank(piece1)
        p2_file = chess.square_file(piece2)
        p2_rank = chess.square_rank(piece2)

        if df == 0:
            if p1_file != p2_file:
                return False
            start_rank = min(p1_rank, p2_rank)
            end_rank = max(p1_rank, p2_rank)
            for rank in range(start_rank + 1, end_rank):
                sq = chess.square(p1_file, rank)
                if sq != moved_square and board_before.piece_at(sq) is not None:
                    return False
            return True

        if dr == 0:
            if p1_rank != p2_rank:
                return False
            start_file = min(p1_file, p2_file)
            end_file = max(p1_file, p2_file)
            for file in range(start_file + 1, end_file):
                sq = chess.square(file, p1_rank)
                if sq != moved_square and board_before.piece_at(sq) is not None:
                    return False
            return True

        if abs(p1_file - p2_file) != abs(p1_rank - p2_rank):
            return False

        file_step = 1 if p2_file > p1_file else -1
        rank_step = 1 if p2_rank > p1_rank else -1
        file = p1_file + file_step
        rank = p1_rank + rank_step
        while file != p2_file and rank != p2_rank:
            sq = chess.square(file, rank)
            if sq != moved_square and board_before.piece_at(sq) is not None:
                return False
            file += file_step
            rank += rank_step
        return True

    def _is_between_on_line(
        self,
        square: chess.Square,
        piece1: chess.Square,
        piece2: chess.Square,
        df: int,
        dr: int,
    ) -> bool:
        """True if ``square`` lies strictly between the two pieces on the line."""
        sq_file = chess.square_file(square)
        sq_rank = chess.square_rank(square)
        p1_file = chess.square_file(piece1)
        p1_rank = chess.square_rank(piece1)
        p2_file = chess.square_file(piece2)
        p2_rank = chess.square_rank(piece2)

        if df == 0:
            if sq_file == p1_file == p2_file:
                return min(p1_rank, p2_rank) < sq_rank < max(p1_rank, p2_rank)
        elif dr == 0:
            if sq_rank == p1_rank == p2_rank:
                return min(p1_file, p2_file) < sq_file < max(p1_file, p2_file)
        elif abs(sq_file - p1_file) == abs(sq_rank - p1_rank) and abs(
            sq_file - p2_file
        ) == abs(sq_rank - p2_rank):
            return min(p1_file, p2_file) < sq_file < max(p1_file, p2_file) and min(
                p1_rank, p2_rank
            ) < sq_rank < max(p1_rank, p2_rank)
        return False
