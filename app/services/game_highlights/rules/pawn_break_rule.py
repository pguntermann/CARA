"""Rule for detecting pawn breaks."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import (
    is_central_square,
    is_file_open,
    is_passed_pawn,
    piece_type_from_san,
)


class PawnBreakRule(HighlightRule):
    """Detects a central pawn capture that opens a file or creates a passed pawn."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pawn break highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if piece_type_from_san(half.san) != chess.PAWN:
            return []
        if (half.capture or "").lower() != "p":
            return []
        # Skip simple pawn-for-pawn trades with a neighbor ply.
        if half.is_equal_trade_with_neighbors():
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        if board_before is None or board_after is None:
            return []

        parsed = half.parse_move()
        if parsed is None:
            return []
        source_square, dest_square = parsed.from_square, parsed.to_square
        if not is_central_square(dest_square):
            return []

        source_rank = chess.square_rank(source_square)
        dest_rank = chess.square_rank(dest_square)
        advanced = dest_rank > source_rank if half.is_white else dest_rank < source_rank
        if not advanced:
            return []

        dest_file = chess.square_file(dest_square)
        if not (
            is_file_open(board_after, dest_file)
            or is_passed_pawn(board_after, dest_square, half.color)
        ):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} executed a central pawn break",
                priority=25,
                rule_type="pawn_break",
            )
        ]
