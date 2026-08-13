"""Rule for detecting tempo gain (forcing threat that elicits a poor reply)."""

from typing import List, Set

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import MIN_VALUABLE_PIECE_VALUE, san_is_check


class TempoGainRule(HighlightRule):
    """Detects when a good move creates a threat and the opponent replies poorly to it."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for tempo gain highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move():
            return []

        threatened = self._threatened_squares(half)
        if not threatened and not san_is_check(half.san):
            return []

        reply = half.reply()
        if reply is None:
            return []
        opponent_cpl = reply.cpl_float()
        if opponent_cpl is None or opponent_cpl <= 50:
            return []

        if not self._reply_addresses_threat(half, reply, threatened):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} gained a tempo",
                priority=32,
                rule_type="tempo_gain",
            )
        ]

    def _threatened_squares(self, half: HalfMoveContext) -> Set[chess.Square]:
        """Enemy pieces the moved unit newly pressures (check handled separately).

        Capturing material alone is not a tempo threat — that is winning the
        piece, not forcing the opponent to spend a move answering a threat.
        """
        board = half.board_after()
        dest = half.destination_square()
        if board is None or dest is None:
            return set()

        threatened: Set[chess.Square] = set()
        for sq in board.attacks(dest):
            piece = board.piece_at(sq)
            if piece is None or piece.color == half.color:
                continue
            if PIECE_VALUES.get(piece.symbol().lower(), 0) >= MIN_VALUABLE_PIECE_VALUE:
                threatened.add(sq)
        return threatened

    def _reply_addresses_threat(
        self,
        half: HalfMoveContext,
        reply: HalfMoveContext,
        threatened: Set[chess.Square],
    ) -> bool:
        """True if the reply reacts to the threat (not an unrelated inaccuracy)."""
        if san_is_check(half.san):
            return True

        if not threatened:
            return False

        before = half.board_after()
        after = reply.board_after()
        move = reply.parse_move()
        if before is None or after is None or move is None:
            return False

        threatener = half.destination_square()

        # Moved the threatened piece away.
        if move.from_square in threatened:
            return True

        # Captured the piece that created the threat.
        if threatener is not None and move.to_square == threatener:
            return True

        # Kicked / attacked the threatening piece with the reply.
        if threatener is not None and threatener in after.attacks(move.to_square):
            return True

        # Added a defender to a threatened square.
        for sq in threatened:
            if len(after.attackers(reply.color, sq)) > len(
                before.attackers(reply.color, sq)
            ):
                return True

        return False
