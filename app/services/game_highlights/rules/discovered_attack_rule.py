"""Rule for detecting discovered attacks."""

from typing import List, Optional, Tuple

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import piece_name


class DiscoveredAttackRule(HighlightRule):
    """Detects when a move uncovers a friendly slider's attack on a valuable target."""

    MIN_TARGET_PIECE_VALUE = 300

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for discovered attack highlights."""
        if move.move_number <= context.opening_end:
            return []
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move():
            return []
        if half.is_equal_trade_with_neighbors():
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        chess_move = half.parse_move()
        if board_before is None or board_after is None or chess_move is None:
            return []

        discovered = self._has_discovered_attack(
            board_before,
            board_after,
            chess_move.from_square,
            half.color,
        )
        if discovered is None:
            return []

        target_piece, is_check, target_value, is_undefended = discovered
        if target_value < self.MIN_TARGET_PIECE_VALUE and not is_check:
            return []
        if not (is_undefended or is_check):
            return []

        opponent = "Black" if half.is_white else "White"
        if is_check:
            description = (
                f"{half.side_name} performed a discovered attack on {opponent}'s king"
            )
            priority = 45
        else:
            target_name = piece_name(target_piece, default=target_piece)
            description = (
                f"{half.side_name} performed a discovered attack on {opponent}'s {target_name}"
            )
            priority = 40

        return [
            make_highlight(
                half,
                description,
                priority=priority,
                rule_type="discovered_attack",
            )
        ]

    def _has_discovered_attack(
        self,
        board_before: chess.Board,
        board_after: chess.Board,
        source_square: chess.Square,
        color: chess.Color,
    ) -> Optional[Tuple[str, bool, int, bool]]:
        """Check if leaving ``source_square`` reveals a friendly slider attack.

        Returns ``(target_letter, is_check, target_value, is_undefended)`` or None.
        """
        opponent_color = not color
        directions = (
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        )

        for df, dr in directions:
            slider_piece, slider_sq = self._first_piece_on_ray(
                board_before, source_square, df, dr
            )
            if (
                slider_piece is None
                or slider_sq is None
                or slider_piece.color != color
                or not self._slider_can_use_direction(slider_piece.piece_type, df, dr)
            ):
                continue

            target_piece, target_sq = self._first_piece_on_ray(
                board_before, source_square, -df, -dr
            )
            if (
                target_piece is None
                or target_sq is None
                or target_piece.color != opponent_color
            ):
                continue

            target_letter = target_piece.symbol().lower()
            is_check = target_piece.piece_type == chess.KING
            target_value = 900 if is_check else PIECE_VALUES.get(target_letter, 0)
            if target_value < self.MIN_TARGET_PIECE_VALUE and not is_check:
                continue

            target_after = board_after.piece_at(target_sq)
            if (
                target_after is None
                or target_after.color != opponent_color
                or target_after.piece_type != target_piece.piece_type
            ):
                continue
            if not self._ray_clear_between(board_after, slider_sq, target_sq):
                continue

            is_undefended = not board_after.is_attacked_by(opponent_color, target_sq)
            if self._is_meaningful_discovered_attack(
                board_after, slider_sq, target_letter, opponent_color, is_check
            ):
                return (target_letter, is_check, target_value, is_undefended)

        return None

    @staticmethod
    def _slider_can_use_direction(piece_type: chess.PieceType, df: int, dr: int) -> bool:
        if piece_type == chess.QUEEN:
            return True
        if piece_type == chess.ROOK:
            return df == 0 or dr == 0
        if piece_type == chess.BISHOP:
            return df != 0 and dr != 0
        return False

    @staticmethod
    def _first_piece_on_ray(
        board: chess.Board,
        start: chess.Square,
        df: int,
        dr: int,
    ) -> Tuple[Optional[chess.Piece], Optional[chess.Square]]:
        """Return the first piece along a ray from start (exclusive)."""
        file0 = chess.square_file(start)
        rank0 = chess.square_rank(start)
        for dist in range(1, 8):
            file = file0 + df * dist
            rank = rank0 + dr * dist
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            if piece is not None:
                return piece, sq
        return None, None

    @staticmethod
    def _ray_clear_between(
        board: chess.Board, from_sq: chess.Square, to_sq: chess.Square
    ) -> bool:
        """True if every square strictly between from_sq and to_sq is empty."""
        f0, r0 = chess.square_file(from_sq), chess.square_rank(from_sq)
        f1, r1 = chess.square_file(to_sq), chess.square_rank(to_sq)
        df, dr = f1 - f0, r1 - r0
        if df == 0 and dr == 0:
            return False
        step_f = 0 if df == 0 else df // abs(df)
        step_r = 0 if dr == 0 else dr // abs(dr)
        if df != 0 and dr != 0 and abs(df) != abs(dr):
            return False
        f, r = f0 + step_f, r0 + step_r
        while (f, r) != (f1, r1):
            if board.piece_at(chess.square(f, r)) is not None:
                return False
            f += step_f
            r += step_r
        return True

    def _is_meaningful_discovered_attack(
        self,
        board: chess.Board,
        attacker_square: chess.Square,
        target_piece_letter: str,
        opponent_color: chess.Color,
        is_check: bool,
    ) -> bool:
        """True if the revealed attack is check, free material, or otherwise useful."""
        if is_check:
            return True

        target_piece_type_map = {
            "q": chess.QUEEN,
            "r": chess.ROOK,
            "b": chess.BISHOP,
            "n": chess.KNIGHT,
            "p": chess.PAWN,
        }
        target_piece_type = target_piece_type_map.get(target_piece_letter)
        if target_piece_type is None:
            return False

        attacker_piece = board.piece_at(attacker_square)
        if attacker_piece is None:
            return False

        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        directions = (
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        )

        for df, dr in directions:
            if not self._slider_can_use_direction(attacker_piece.piece_type, df, dr):
                continue
            for dist in range(1, 8):
                file = attacker_file + df * dist
                rank = attacker_rank + dr * dist
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                sq = chess.square(file, rank)
                sq_piece = board.piece_at(sq)
                if sq_piece is None:
                    continue
                if (
                    sq_piece.color == opponent_color
                    and sq_piece.piece_type == target_piece_type
                ):
                    if not board.is_attacked_by(opponent_color, sq):
                        return True
                    target_value = PIECE_VALUES.get(target_piece_letter, 0)
                    attacker_value = PIECE_VALUES.get(
                        attacker_piece.symbol().lower(), 0
                    )
                    if target_value > attacker_value:
                        return True
                    if self._is_important_square(sq, opponent_color):
                        return True
                    break
                break
        return False

    def _is_important_square(
        self, square: chess.Square, opponent_color: chess.Color
    ) -> bool:
        """True if the square is near the opponent's kingside back ranks."""
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        if opponent_color == chess.WHITE:
            return rank >= 6 and file >= 5
        return rank <= 1 and file >= 5
