"""Rule for detecting isolated pawns."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import piece_type_from_san


class IsolatedPawnRule(HighlightRule):
    """Detects when a pawn move creates a newly isolated friendly pawn."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for isolated pawn highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        # Isolation from this rule is attributed to a pawn move by that side.
        if piece_type_from_san(half.san) != chess.PAWN:
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        if board_before is None or board_after is None:
            return []

        if not self._find_new_isolated_pawns(board_before, board_after, half.color):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} created an isolated pawn",
                priority=21,
                rule_type="isolated_pawn",
            )
        ]

    def _find_new_isolated_pawns(
        self,
        board_before: chess.Board,
        board_after: chess.Board,
        color: chess.Color,
    ) -> List[chess.Square]:
        """Find friendly pawns that became isolated after the move."""
        pawns_before = list(board_before.pieces(chess.PAWN, color))
        pawns_after = list(board_after.pieces(chess.PAWN, color))
        new_isolated: List[chess.Square] = []

        for pawn_sq in pawns_after:
            pawn_file = chess.square_file(pawn_sq)
            was_isolated = self._is_isolated(pawns_before, pawn_file)
            is_isolated = self._is_isolated(pawns_after, pawn_file)
            if not was_isolated and is_isolated:
                new_isolated.append(pawn_sq)

        # A pawn that left its file may isolate neighbors on adjacent files.
        for pawn_sq_before in pawns_before:
            if pawn_sq_before in pawns_after:
                continue
            removed_file = chess.square_file(pawn_sq_before)
            for pawn_sq_after in pawns_after:
                pawn_file = chess.square_file(pawn_sq_after)
                if abs(pawn_file - removed_file) != 1:
                    continue
                if self._is_isolated(pawns_after, pawn_file) and pawn_sq_after not in new_isolated:
                    new_isolated.append(pawn_sq_after)

        return new_isolated

    def _is_isolated(self, pawns: List[chess.Square], file: int) -> bool:
        """True if ``file`` has no friendly pawns on either adjacent file."""
        for adj_file in (file - 1, file + 1):
            if not 0 <= adj_file <= 7:
                continue
            for pawn_sq in pawns:
                if chess.square_file(pawn_sq) == adj_file:
                    return False
        return True
