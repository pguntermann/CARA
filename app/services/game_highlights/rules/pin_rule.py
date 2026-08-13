"""Rule for detecting pins."""

from typing import List, Optional

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)


class PinRule(HighlightRule):
    """Detects when a move creates a meaningful pin (piece pinned to something heavier)."""

    MIN_PINNED_PIECE_VALUE = 300
    MIN_TARGET_VALUE = 500

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pin highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move():
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        attacker_square = half.destination_square()
        if board_before is None or board_after is None or attacker_square is None:
            return []

        if self._find_new_pin(board_before, board_after, attacker_square, half.color) is None:
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} created a pin",
                priority=38,
                rule_type="pin",
            )
        ]

    def _find_new_pin(
        self,
        board_before: chess.Board,
        board_after: chess.Board,
        attacker_square: chess.Square,
        attacker_color: chess.Color,
    ) -> Optional[chess.Square]:
        """Find a pin created by this move that did not already exist before it.

        Skips cases where the opponent walked into an existing ray (e.g. Ke4 into
        Bc6's diagonal) and the mover only slides along the same pin line (Bb7).
        """
        pinned_square = self._find_pinned_piece(
            board_after, attacker_square, attacker_color
        )
        if pinned_square is None:
            return None
        opponent_color = not attacker_color
        if board_before.piece_at(pinned_square) is not None and board_before.is_pinned(
            opponent_color, pinned_square
        ):
            return None
        return pinned_square

    def _find_pinned_piece(
        self,
        board: chess.Board,
        attacker_square: chess.Square,
        attacker_color: chess.Color,
    ) -> Optional[chess.Square]:
        """Return the square of an enemy piece newly pinned by the moved slider."""
        opponent_color = not attacker_color
        attacker_piece = board.piece_at(attacker_square)
        if attacker_piece is None or attacker_piece.color != attacker_color:
            return None
        if attacker_piece.piece_type not in (chess.ROOK, chess.BISHOP, chess.QUEEN):
            return None

        for piece_type in (
            chess.PAWN,
            chess.KNIGHT,
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
        ):
            for sq in board.pieces(piece_type, opponent_color):
                if not board.is_pinned(opponent_color, sq):
                    continue
                pinned_piece = board.piece_at(sq)
                if pinned_piece is None:
                    continue
                pinned_value = PIECE_VALUES.get(pinned_piece.symbol().lower(), 0)
                if pinned_value < self.MIN_PINNED_PIECE_VALUE:
                    continue
                if not self._is_on_same_line(
                    attacker_square, sq, attacker_piece.piece_type
                ):
                    continue
                if not self._attacker_creates_pin(
                    board, attacker_square, sq, opponent_color
                ):
                    continue
                target_value = self._get_target_piece_value(
                    board, attacker_square, sq, opponent_color
                )
                if target_value < self.MIN_TARGET_VALUE:
                    continue
                if self._is_truly_pinned(board, sq, attacker_square, opponent_color):
                    return sq
        return None

    def _attacker_creates_pin(
        self,
        board: chess.Board,
        attacker_square: chess.Square,
        pinned_square: chess.Square,
        opponent_color: chess.Color,
    ) -> bool:
        """True if an enemy unit sits on the ray past the pinned piece."""
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        pinned_file = chess.square_file(pinned_square)
        pinned_rank = chess.square_rank(pinned_square)

        df = pinned_file - attacker_file
        dr = pinned_rank - attacker_rank
        if df == 0 and dr == 0:
            return False
        if df != 0:
            df = df // abs(df)
        if dr != 0:
            dr = dr // abs(dr)

        for dist in range(1, 8):
            file = pinned_file + df * dist
            rank = pinned_rank + dr * dist
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            sq = chess.square(file, rank)
            sq_piece = board.piece_at(sq)
            if sq_piece is None:
                continue
            if sq_piece.color == opponent_color:
                return True
            break
        return False

    def _is_truly_pinned(
        self,
        board: chess.Board,
        pinned_square: chess.Square,
        attacker_square: chess.Square,
        opponent_color: chess.Color,
    ) -> bool:
        """True if the pinned unit cannot leave the pin line without exposing the king.

        Also rejects cases where the opponent can already capture the pinning piece
        (treated as a plain attack rather than a lasting pin).
        """
        if board.piece_at(pinned_square) is None:
            return False

        if board.is_attacked_by(opponent_color, attacker_square):
            return False

        pinned_file = chess.square_file(pinned_square)
        pinned_rank = chess.square_rank(pinned_square)
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)

        df = pinned_file - attacker_file
        dr = pinned_rank - attacker_rank
        df_norm = 0 if df == 0 else df // abs(df)
        dr_norm = 0 if dr == 0 else dr // abs(dr)

        for move in board.legal_moves:
            if move.from_square != pinned_square:
                continue
            to_file = chess.square_file(move.to_square)
            to_rank = chess.square_rank(move.to_square)
            to_df = to_file - attacker_file
            to_dr = to_rank - attacker_rank
            to_df_norm = 0 if to_df == 0 else to_df // abs(to_df)
            to_dr_norm = 0 if to_dr == 0 else to_dr // abs(to_dr)
            if to_df_norm == df_norm and to_dr_norm == dr_norm:
                continue
            board_copy = board.copy()
            board_copy.push(move)
            if not board_copy.is_check():
                return False
        return True

    def _is_on_same_line(
        self,
        square1: chess.Square,
        square2: chess.Square,
        piece_type: chess.PieceType,
    ) -> bool:
        """True if the slider type can travel between the two squares."""
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)

        if piece_type == chess.ROOK:
            return file1 == file2 or rank1 == rank2
        if piece_type == chess.BISHOP:
            return abs(file1 - file2) == abs(rank1 - rank2)
        if piece_type == chess.QUEEN:
            return (
                file1 == file2
                or rank1 == rank2
                or abs(file1 - file2) == abs(rank1 - rank2)
            )
        return False

    def _get_target_piece_value(
        self,
        board: chess.Board,
        attacker_square: chess.Square,
        pinned_square: chess.Square,
        opponent_color: chess.Color,
    ) -> int:
        """Value of the enemy unit beyond the pinned piece (king counts as 900)."""
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        pinned_file = chess.square_file(pinned_square)
        pinned_rank = chess.square_rank(pinned_square)

        df = pinned_file - attacker_file
        dr = pinned_rank - attacker_rank
        if df == 0 and dr == 0:
            return 0
        if df != 0:
            df = df // abs(df)
        if dr != 0:
            dr = dr // abs(dr)

        for dist in range(1, 8):
            file = pinned_file + df * dist
            rank = pinned_rank + dr * dist
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            sq = chess.square(file, rank)
            sq_piece = board.piece_at(sq)
            if sq_piece is None:
                continue
            if sq_piece.color == opponent_color:
                if sq_piece.piece_type == chess.KING:
                    return 900
                return PIECE_VALUES.get(sq_piece.symbol().lower(), 0)
            break
        return 0
