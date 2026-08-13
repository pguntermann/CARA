"""Rule for detecting simplification (quiet piece trades that clear the board)."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    equal_capture_values,
    evaluate_for_each_side,
    make_highlight,
    paired_move_notation,
)
from app.utils.material_tracker import calculate_material_count

# Captures that count as simplifying piece trades (not pawn-only exchanges).
_PIECE_CAPTURES = frozenset({"n", "b", "r", "q"})

# Max |eval change| (cp) for a trade to count as quiet simplification.
_EVAL_STABLE_MAX_CP = 50

# Max |relative material swing| (cp) across the two-ply trade.
_MATERIAL_BALANCE_MAX_CP = 50


class SimplificationRule(HighlightRule):
    """Detects even piece trades that reduce material while the evaluation stays quiet."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for simplification highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        """Starter captures a piece; opponent's reply also captures a piece of similar value."""
        reply = half.reply()
        if reply is None:
            return []

        first_cap = (half.capture or "").lower()
        second_cap = (reply.capture or "").lower()
        if first_cap not in _PIECE_CAPTURES or second_cap not in _PIECE_CAPTURES:
            return []
        if not equal_capture_values(first_cap, second_cap):
            return []

        before = half.board_before()
        after = reply.board_after()
        if before is None or after is None:
            return []
        if self._non_pawn_piece_count(before) - self._non_pawn_piece_count(after) < 2:
            return []

        # Relative material must stay roughly even (guards against Q-then-minor sequences).
        if self._relative_material_swing_cp(before, after) > _MATERIAL_BALANCE_MAX_CP:
            return []

        eval_before = half.eval_before_cp()
        eval_after = reply.eval_after_cp()
        if eval_before is None or eval_after is None:
            return []
        if abs(eval_after - eval_before) > _EVAL_STABLE_MAX_CP:
            return []

        return [
            make_highlight(
                half,
                self._trade_label(first_cap, second_cap),
                priority=22,
                rule_type="simplification",
                move_number_end=reply.move_number,
                move_notation=paired_move_notation(half, reply),
            )
        ]

    def _non_pawn_piece_count(self, board: chess.Board) -> int:
        """Count knights, bishops, rooks, and queens of both colors."""
        count = 0
        for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            count += len(board.pieces(piece_type, chess.WHITE))
            count += len(board.pieces(piece_type, chess.BLACK))
        return count

    def _relative_material_swing_cp(self, before: chess.Board, after: chess.Board) -> int:
        """Absolute change in White-minus-Black material across the trade."""

        def relative(board: chess.Board) -> int:
            return calculate_material_count(board, True) - calculate_material_count(
                board, False
            )

        return abs(relative(after) - relative(before))

    def _trade_label(self, first_capture: str, second_capture: str) -> str:
        if first_capture == second_capture == "q":
            return "The position was simplified by a queen trade"
        if first_capture == second_capture == "r":
            return "The position was simplified by a rook trade"
        if first_capture == second_capture:
            return "The position was simplified by a piece trade"
        return "The position was simplified by exchanging pieces"
