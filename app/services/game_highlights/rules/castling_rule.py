"""Rule for detecting castling."""

from typing import List, Optional, Tuple

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)


class CastlingRule(HighlightRule):
    """Detects castling moves."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for castling highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        castle = self._castle_side(half)
        if castle is None:
            return []
        side_label, rights_mask = castle

        board_before = half.board_before()
        board_after = half.board_after()
        if board_before is None or board_after is None:
            return []

        had_right = bool(board_before.castling_rights & rights_mask)
        lost_right = not bool(board_after.castling_rights & rights_mask)
        if not (had_right and lost_right):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} castled {side_label}",
                priority=15,
                rule_type="castling",
            )
        ]

    def _castle_side(self, half: HalfMoveContext) -> Optional[Tuple[str, int]]:
        """Return (side label, castling-rights bit) for a castling SAN, else None."""
        if half.san == "O-O":
            mask = chess.BB_H1 if half.is_white else chess.BB_H8
            return ("kingside", mask)
        if half.san == "O-O-O":
            mask = chess.BB_A1 if half.is_white else chess.BB_A8
            return ("queenside", mask)
        return None
