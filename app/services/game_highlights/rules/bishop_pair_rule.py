"""Rule for detecting when a side secures the bishop pair."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import bishops_opposite_colors


class BishopPairRule(HighlightRule):
    """Detects when a side secures the (opposite-color) bishop pair against the opponent."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for bishop pair highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        board_after = half.board_after()
        if board_after is None:
            return []

        my_bishops = len(board_after.pieces(chess.BISHOP, half.color))
        opp_bishops = len(board_after.pieces(chess.BISHOP, not half.color))
        if my_bishops != 2 or opp_bishops >= 2:
            return []

        board_before = half.board_before()
        if board_before is None:
            return []
        prev_mine = len(board_before.pieces(chess.BISHOP, half.color))
        prev_opp = len(board_before.pieces(chess.BISHOP, not half.color))

        captured_bishop = (half.capture or "").lower() == "b"
        # Newly completed the pair, or destroyed the opponent's pair by taking a bishop.
        if not (prev_mine < 2 or (prev_opp >= 2 and captured_bishop)):
            return []

        if not bishops_opposite_colors(board_after, half.color):
            return []

        if self._pair_equalized_on_reply(half):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} secured the bishop pair",
                priority=28,
                rule_type="bishop_pair",
            )
        ]

    def _pair_equalized_on_reply(self, half: HalfMoveContext) -> bool:
        """True if the opponent immediately recaptures a bishop, canceling the pair advantage."""
        reply = half.reply()
        return bool(reply and (reply.capture or "").lower() == "b")
