"""Rule for detecting forks."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import is_exploitable_fork


class ForkRule(HighlightRule):
    """Detects when a move creates an exploitable fork."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for fork highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        # Allow inaccuracies: a real fork can still be thematic even when not
        # engine-best (e.g. CPL 60 vs a preferred quiet alternative).
        max_cpl = half.context.inaccuracy_max_cpl
        if not half.is_good_move(max_cpl=max_cpl):
            return []

        board_after = half.board_after()
        piece_square = half.destination_square()
        if board_after is None or piece_square is None:
            return []

        if not is_exploitable_fork(board_after, piece_square, half.color):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} executed a fork",
                priority=45,
                rule_type="fork",
            )
        ]
