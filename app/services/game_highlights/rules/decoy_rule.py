"""Rule for detecting decoy tactics (luring a piece onto a vulnerable square)."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import MATERIAL_SACRIFICE_THRESHOLD, PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import (
    check_tactical_pattern_on_follow_up_moves,
    piece_name as piece_display_name,
)

_OPPONENT_FORCED_CPL_MAX = 30
_MIN_LURED_PIECE_VALUE = 300


class DecoyRule(HighlightRule):
    """Detects offering a piece that lures an enemy unit onto a square used for a tactic."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for decoy highlights."""
        if move.move_number <= context.opening_end:
            return []
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        # Classic decoy: quiet offer (not a capture), taken on the destination by the reply.
        if half.capture or not half.is_good_move():
            return []

        reply = half.reply()
        if reply is None or not reply.capture:
            return []

        our_dest = half.destination_square()
        their_dest = reply.destination_square()
        if our_dest is None or their_dest is None or our_dest != their_dest:
            return []

        material_drop = half.own_material_drop_cp(reply)
        if material_drop is None or material_drop < MATERIAL_SACRIFICE_THRESHOLD:
            return []

        # Opponent was essentially forced to take (near-best capture).
        if not reply.is_good_move(max_cpl=_OPPONENT_FORCED_CPL_MAX):
            return []

        board_after_capture = reply.board_after()
        if board_after_capture is None:
            return []

        lured = board_after_capture.piece_at(their_dest)
        if lured is None or lured.color == half.color:
            return []
        lured_value = (
            900
            if lured.piece_type == chess.KING
            else PIECE_VALUES.get(lured.symbol().lower(), 0)
        )
        if lured_value < _MIN_LURED_PIECE_VALUE and lured.piece_type != chess.KING:
            return []

        follow_up_rows = self._follow_up_move_rows(reply)
        if not follow_up_rows:
            return []

        tactical_type = check_tactical_pattern_on_follow_up_moves(
            board_after_capture,
            follow_up_rows,
            their_dest,
            half.color,
            max_moves_to_check=2,
        )
        if not tactical_type:
            return []

        return [self._make_decoy_highlight(half, lured, tactical_type)]

    def _follow_up_move_rows(self, capture_half: HalfMoveContext) -> List:
        """MoveData rows for our side's follow-ups after the opponent's capture.

        Starts at the row of our next ply (same row as a White-capture reply to Black,
        or the next row after a Black-capture reply to White).
        """
        our_next = capture_half.reply()
        if our_next is None:
            return []
        moves = our_next.context.moves
        start = our_next.context.move_index
        return moves[start : start + 2]

    def _make_decoy_highlight(
        self,
        half: HalfMoveContext,
        lured: chess.Piece,
        tactical_type: str,
    ) -> GameHighlight:
        piece = piece_display_name(lured)
        tactical_desc = tactical_type.replace("_", " ").title()
        opponent = "Black" if half.is_white else "White"
        if tactical_type == "checkmate":
            description = (
                f"{half.side_name} executed a decoy, luring {opponent}'s {piece} "
                f"into {tactical_desc}"
            )
            priority = 48
        else:
            description = (
                f"{half.side_name} executed a decoy, luring {opponent}'s {piece} away, "
                f"enabling a {tactical_desc}"
            )
            priority = 45
        return make_highlight(
            half,
            description,
            priority=priority,
            rule_type="decoy",
        )
