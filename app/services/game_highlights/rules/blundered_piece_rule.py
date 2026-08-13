"""Rule for detecting blundered pieces (queen/rook)."""

from typing import List, Optional

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import (
    BLUNDERED_QUEEN_EVAL_DROP,
    BLUNDERED_QUEEN_MIN_LOSS,
    BLUNDERED_ROOK_EVAL_DROP,
    BLUNDERED_ROOK_MIN_LOSS,
    PIECE_VALUES,
)
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)

_HEAVY = frozenset({"q", "r"})
_RECOVERY_CPL_MAX = 20
# When the engine prices a hang into the error move, the capture adds little
# further eval. Soft floors stay well above "noise" and below the full bars.
_SOFT_EVAL_DROP_ROOK_CP = 100
_SOFT_EVAL_DROP_QUEEN_CP = 200


def _is_promotion_to(san: Optional[str], piece: str) -> bool:
    """True if SAN is a promotion to the given piece type (q/r)."""
    if not san or "=" not in san:
        return False
    promoted = san.split("=", 1)[1][:1]
    return promoted.lower() == piece.lower()


def _count_heavy(board: chess.Board, color: chess.Color, piece: str) -> int:
    piece_type = chess.QUEEN if piece == "q" else chess.ROOK
    return len(board.pieces(piece_type, color))


class BlunderedPieceRule(HighlightRule):
    """Detects when a side blunders a queen or rook (taken on the next ply)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for blundered piece highlights.

        Evaluated on the capturing ply: the previous ply is the blunder.
        """
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        piece = (half.capture or "").lower()
        if piece not in _HEAVY:
            return []

        prior = half.prior()
        if prior is None:
            return []

        if _is_promotion_to(prior.san, piece):
            return []

        if self._is_equal_heavy_trade(half, piece):
            return []

        before_board = prior.board_before()
        after_board = half.board_after()
        if before_board is None or after_board is None:
            return []

        blunderer = prior.color
        count_before = _count_heavy(before_board, blunderer, piece)
        count_after = _count_heavy(after_board, blunderer, piece)
        if count_after >= count_before:
            return []

        material_loss = PIECE_VALUES.get(piece, 0)
        min_loss = BLUNDERED_QUEEN_MIN_LOSS if piece == "q" else BLUNDERED_ROOK_MIN_LOSS
        min_eval_drop = (
            BLUNDERED_QUEEN_EVAL_DROP if piece == "q" else BLUNDERED_ROOK_EVAL_DROP
        )
        if material_loss < min_loss:
            return []

        if not self._prior_is_blunder_grade(prior):
            return []

        if self._recovered_immediately(half, prior, min_eval_drop):
            return []

        eval_drop = prior.eval_drop_through(half)
        if eval_drop is None or not self._eval_drop_sufficient(piece, eval_drop, min_eval_drop):
            return []

        piece_name = "queen" if piece == "q" else "rook"
        return [
            make_highlight(
                prior,
                f"{prior.side_name} blundered his {piece_name}",
                priority=50,
                rule_type="blundered_piece",
            )
        ]

    def _prior_is_blunder_grade(self, prior: HalfMoveContext) -> bool:
        """True for labeled Mistake/Miss/Blunder or CPL past the mistake threshold.

        Deliberately narrower than ``is_serious_error()`` (which also treats
        unlabeled inaccuracy-range CPLs as serious) so blundered-piece stays
        reserved for clear errors.
        """
        if prior.assess in ("Blunder", "Miss", "Mistake"):
            return True
        return prior.is_blunder()

    def _eval_drop_sufficient(
        self, piece: str, eval_drop: float, min_eval_drop: float
    ) -> bool:
        """True if eval collapse meets the full bar, or the priced-in soft floor."""
        if eval_drop >= float(min_eval_drop):
            return True
        soft = (
            _SOFT_EVAL_DROP_ROOK_CP if piece == "r" else _SOFT_EVAL_DROP_QUEEN_CP
        )
        return eval_drop >= soft

    def _is_equal_heavy_trade(self, half: HalfMoveContext, piece: str) -> bool:
        """True if this q/r capture is (or completes) an equal heavy-piece trade."""
        prior = half.prior()
        if prior and (prior.capture or "").lower() == piece:
            return True

        reply = half.reply()
        if reply and (reply.capture or "").lower() == piece:
            return True

        if reply is not None:
            our_next = reply.reply()
            if our_next is not None:
                their_next = our_next.reply()
                if their_next and (their_next.capture or "").lower() == piece:
                    return True
        return False

    def _recovered_immediately(
        self,
        capture_half: HalfMoveContext,
        blunder_half: HalfMoveContext,
        min_eval_drop: float,
    ) -> bool:
        """True if the blunderer's next ply is a strong recovery."""
        recovery = capture_half.reply()
        if recovery is None:
            return False

        cpl = recovery.cpl_float()
        if recovery.assess == "Best Move" or (
            cpl is not None and cpl <= _RECOVERY_CPL_MAX
        ):
            return True

        after_capture = capture_half.eval_after_cp()
        after_recovery = recovery.eval_after_cp()
        if after_capture is None or after_recovery is None:
            return False
        if blunder_half.is_white:
            recovered = after_recovery - after_capture
        else:
            recovered = after_capture - after_recovery
        return recovered >= min_eval_drop