"""Rule for detecting knight outposts."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import is_attacked_by_pawn, piece_type_from_san


class KnightOutpostRule(HighlightRule):
    """Detects when a knight moves to an outpost (pawn-supported, unchallengeable by enemy pawns)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for knight outpost highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        # Outposts are positional — skip captures and non-knight moves.
        if half.capture or piece_type_from_san(half.san) != chess.KNIGHT:
            return []

        board_after = half.board_after()
        if board_after is None:
            return []

        knight_square = half.destination_square()
        if knight_square is None:
            return []

        piece = board_after.piece_at(knight_square)
        if piece is None or piece.piece_type != chess.KNIGHT or piece.color != half.color:
            return []

        if not self._is_knight_outpost(board_after, knight_square, half.color):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} established a knight outpost",
                priority=26,
                rule_type="knight_outpost",
            )
        ]

    def _is_knight_outpost(
        self, board: chess.Board, knight_square: chess.Square, color: chess.Color
    ) -> bool:
        """Outpost: advanced, not on a/h, pawn-supported, safe from enemy pawns now and later."""
        opponent = not color
        knight_file = chess.square_file(knight_square)
        knight_rank = chess.square_rank(knight_square)

        if knight_file in (0, 7):
            return False

        # White: ranks 4–7; Black: ranks 1–4 (0-based 3–6 / 0–3).
        if color == chess.WHITE:
            if knight_rank < 3:
                return False
        elif knight_rank > 3:
            return False

        if not is_attacked_by_pawn(board, knight_square, color):
            return False
        if is_attacked_by_pawn(board, knight_square, opponent):
            return False
        if self._can_be_challenged_by_enemy_pawns(board, knight_square, color):
            return False
        return True

    def _can_be_challenged_by_enemy_pawns(
        self, board: chess.Board, square: chess.Square, color: chess.Color
    ) -> bool:
        """True if an enemy pawn on an adjacent file can still advance to attack ``square``.

        Same-file pawns never attack by advancing straight, so only neighboring files count.
        """
        opponent = not color
        file = chess.square_file(square)
        rank = chess.square_rank(square)

        for df in (-1, 1):
            adj = file + df
            if not 0 <= adj <= 7:
                continue
            for pawn_sq in board.pieces(chess.PAWN, opponent):
                if chess.square_file(pawn_sq) != adj:
                    continue
                pawn_rank = chess.square_rank(pawn_sq)
                if opponent == chess.BLACK:
                    # Black advances down — must still be above the outpost.
                    if pawn_rank > rank:
                        return True
                elif pawn_rank < rank:
                    # White advances up — must still be below the outpost.
                    return True
        return False
