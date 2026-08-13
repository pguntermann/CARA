"""Rule for detecting battery creation (two aligned pieces attacking an enemy unit)."""

from typing import Iterator, List, Optional, Tuple

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)

_HEAVY = (chess.ROOK, chess.QUEEN)
_DIAGONAL = (chess.BISHOP, chess.QUEEN)
_BATTERY_PIECES = (chess.ROOK, chess.QUEEN, chess.BISHOP)


class BatteryRule(HighlightRule):
    """Detects when a move creates a battery that attacks an enemy piece."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for battery highlights."""
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

        battery_info = self._creates_battery(
            board_before,
            board_after,
            chess_move.to_square,
            half.color,
            moved_from=chess_move.from_square,
        )
        if not battery_info:
            return []

        _, line_desc = battery_info
        return [
            make_highlight(
                half,
                f"{half.side_name} created a battery on the {line_desc}",
                priority=35,
                rule_type="battery",
            )
        ]

    def _creates_battery(
        self,
        board_before: chess.Board,
        board_after: chess.Board,
        moved_to: chess.Square,
        color: chess.Color,
        *,
        moved_from: chess.Square,
    ) -> Optional[Tuple[str, str]]:
        moved = board_after.piece_at(moved_to)
        if moved is None or moved.color != color or moved.piece_type not in _BATTERY_PIECES:
            return None

        moved_file = chess.square_file(moved_to)
        moved_rank = chess.square_rank(moved_to)

        for piece_type in _BATTERY_PIECES:
            for other_sq in board_after.pieces(piece_type, color):
                if other_sq == moved_to:
                    continue
                other = board_after.piece_at(other_sq)
                if other is None:
                    continue
                if self._is_in_starting_position(other_sq, other.piece_type, color):
                    continue

                other_file = chess.square_file(other_sq)
                other_rank = chess.square_rank(other_sq)

                # File battery: two heavy pieces
                if (
                    moved_file == other_file
                    and moved.piece_type in _HEAVY
                    and other.piece_type in _HEAVY
                ):
                    if not self._are_aligned(board_after, moved_to, other_sq, "file"):
                        continue
                    if self._battery_existed(
                        board_before, moved_to, other_sq, "file", color, moved.piece_type, moved_from
                    ):
                        continue
                    if not self._battery_attacks_enemy_piece(
                        board_after, moved_to, other_sq, "file", color
                    ):
                        continue
                    if not self._no_friendly_pawns_on_file(board_after, moved_file, color):
                        continue
                    if not self._line_points_toward_opponent(moved_to, other_sq, "file", color):
                        continue
                    return ("file", f"{chr(ord('a') + moved_file)} file")

                # Rank battery: two heavy pieces
                if (
                    moved_rank == other_rank
                    and moved.piece_type in _HEAVY
                    and other.piece_type in _HEAVY
                ):
                    if not self._are_aligned(board_after, moved_to, other_sq, "rank"):
                        continue
                    if self._battery_existed(
                        board_before, moved_to, other_sq, "rank", color, moved.piece_type, moved_from
                    ):
                        continue
                    if not self._battery_attacks_enemy_piece(
                        board_after, moved_to, other_sq, "rank", color
                    ):
                        continue
                    if not self._no_friendly_pawns_on_rank(board_after, moved_rank, color):
                        continue
                    if not self._line_points_toward_opponent(moved_to, other_sq, "rank", color):
                        continue
                    return ("rank", f"{moved_rank + 1}th rank")

                # Diagonal battery: bishop/queen
                if (
                    abs(moved_file - other_file) == abs(moved_rank - other_rank)
                    and moved_file != other_file
                    and moved.piece_type in _DIAGONAL
                    and other.piece_type in _DIAGONAL
                ):
                    if not self._are_aligned(board_after, moved_to, other_sq, "diagonal"):
                        continue
                    if self._battery_existed(
                        board_before,
                        moved_to,
                        other_sq,
                        "diagonal",
                        color,
                        moved.piece_type,
                        moved_from,
                    ):
                        continue
                    if not self._battery_attacks_enemy_piece(
                        board_after, moved_to, other_sq, "diagonal", color
                    ):
                        continue
                    return ("diagonal", self._diagonal_description(moved_to, other_sq))

        return None

    def _battery_attacks_enemy_piece(
        self,
        board: chess.Board,
        square1: chess.Square,
        square2: chess.Square,
        line_type: str,
        color: chess.Color,
    ) -> bool:
        """True if the ray beyond either battery piece first hits an enemy unit."""
        opponent = not color
        for start, other in ((square1, square2), (square2, square1)):
            for sq in self._squares_beyond(start, other, line_type):
                piece = board.piece_at(sq)
                if piece is None:
                    continue
                return piece.color == opponent
        return False

    def _squares_beyond(
        self, start: chess.Square, other: chess.Square, line_type: str
    ) -> Iterator[chess.Square]:
        """Yield squares on the line starting just beyond ``start``, away from ``other``."""
        sf, sr = chess.square_file(start), chess.square_rank(start)
        of, or_ = chess.square_file(other), chess.square_rank(other)

        if line_type == "file":
            df, dr = 0, 1 if sr > or_ else -1
        elif line_type == "rank":
            df, dr = (1 if sf > of else -1), 0
        else:
            df = 1 if sf > of else -1
            dr = 1 if sr > or_ else -1

        f, r = sf + df, sr + dr
        while 0 <= f <= 7 and 0 <= r <= 7:
            yield chess.square(f, r)
            f += df
            r += dr

    def _are_aligned(
        self, board: chess.Board, square1: chess.Square, square2: chess.Square, line_type: str
    ) -> bool:
        """True if nothing sits between the two squares on the shared line."""
        f1, r1 = chess.square_file(square1), chess.square_rank(square1)
        f2, r2 = chess.square_file(square2), chess.square_rank(square2)

        if line_type == "file":
            for rank in range(min(r1, r2) + 1, max(r1, r2)):
                if board.piece_at(chess.square(f1, rank)) is not None:
                    return False
            return True
        if line_type == "rank":
            for file in range(min(f1, f2) + 1, max(f1, f2)):
                if board.piece_at(chess.square(file, r1)) is not None:
                    return False
            return True

        df = 1 if f2 > f1 else -1
        dr = 1 if r2 > r1 else -1
        for dist in range(1, abs(f2 - f1)):
            if board.piece_at(chess.square(f1 + df * dist, r1 + dr * dist)) is not None:
                return False
        return True

    def _battery_existed(
        self,
        board: chess.Board,
        square1: chess.Square,
        square2: chess.Square,
        line_type: str,
        color: chess.Color,
        moved_piece_type: chess.PieceType,
        moved_from: chess.Square,
    ) -> bool:
        other = board.piece_at(square2)
        if other is None or other.color != color:
            return False
        if self._on_same_line(moved_from, square2, line_type) and self._are_aligned(
            board, moved_from, square2, line_type
        ):
            return True
        prior = board.piece_at(square1)
        if (
            prior is not None
            and prior.color == color
            and prior.piece_type == moved_piece_type
            and self._on_same_line(square1, square2, line_type)
            and self._are_aligned(board, square1, square2, line_type)
        ):
            return True
        return False

    def _on_same_line(self, square1: chess.Square, square2: chess.Square, line_type: str) -> bool:
        f1, r1 = chess.square_file(square1), chess.square_rank(square1)
        f2, r2 = chess.square_file(square2), chess.square_rank(square2)
        if line_type == "file":
            return f1 == f2
        if line_type == "rank":
            return r1 == r2
        return abs(f1 - f2) == abs(r1 - r2) and f1 != f2

    def _is_in_starting_position(
        self, square: chess.Square, piece_type: chess.PieceType, color: chess.Color
    ) -> bool:
        if piece_type == chess.ROOK:
            return square in (
                (chess.A1, chess.H1) if color == chess.WHITE else (chess.A8, chess.H8)
            )
        if piece_type == chess.BISHOP:
            return square in (
                (chess.C1, chess.F1) if color == chess.WHITE else (chess.C8, chess.F8)
            )
        return False

    def _no_friendly_pawns_on_file(
        self, board: chess.Board, file: int, color: chess.Color
    ) -> bool:
        return not any(
            chess.square_file(sq) == file for sq in board.pieces(chess.PAWN, color)
        )

    def _no_friendly_pawns_on_rank(
        self, board: chess.Board, rank: int, color: chess.Color
    ) -> bool:
        return not any(
            chess.square_rank(sq) == rank for sq in board.pieces(chess.PAWN, color)
        )

    def _line_points_toward_opponent(
        self, square1: chess.Square, square2: chess.Square, line_type: str, color: chess.Color
    ) -> bool:
        if line_type == "diagonal":
            return True
        r1 = chess.square_rank(square1)
        r2 = chess.square_rank(square2)
        if line_type == "file":
            if color == chess.WHITE:
                return r1 >= 3 or r2 >= 3
            return r1 <= 4 or r2 <= 4
        # rank
        if color == chess.WHITE:
            return r1 >= 3
        return r1 <= 4

    def _diagonal_description(self, square1: chess.Square, square2: chess.Square) -> str:
        f1, r1 = chess.square_file(square1), chess.square_rank(square1)
        f2, r2 = chess.square_file(square2), chess.square_rank(square2)
        df = 0 if f2 == f1 else (1 if f2 > f1 else -1)
        dr = 0 if r2 == r1 else (1 if r2 > r1 else -1)

        def extend(f: int, r: int, step_f: int, step_r: int) -> Tuple[int, int]:
            while 0 <= f + step_f <= 7 and 0 <= r + step_r <= 7:
                f += step_f
                r += step_r
            return f, r

        # Prefer the endpoint farther "back" along -df/-dr from the nearer piece.
        back1 = min(
            f1 if df > 0 else (7 - f1 if df < 0 else 0),
            r1 if dr > 0 else (7 - r1 if dr < 0 else 0),
        )
        back2 = min(
            f2 if df > 0 else (7 - f2 if df < 0 else 0),
            r2 if dr > 0 else (7 - r2 if dr < 0 else 0),
        )
        if back1 >= back2:
            start_f, start_r = f1 - df * back1, r1 - dr * back1
        else:
            start_f, start_r = f2 - df * back2, r2 - dr * back2
        end_f, end_r = extend(start_f, start_r, df, dr)
        return (
            f"{chess.square_name(chess.square(start_f, start_r))}-"
            f"{chess.square_name(chess.square(end_f, end_r))} diagonal"
        )
