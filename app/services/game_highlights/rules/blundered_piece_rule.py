"""Rule for detecting blundered pieces (queen/rook)."""

from typing import List, Optional

from app.models.moveslist_model import MoveData
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import (
    PIECE_VALUES,
    BLUNDERED_QUEEN_MIN_LOSS,
    BLUNDERED_ROOK_MIN_LOSS,
    BLUNDERED_QUEEN_EVAL_DROP,
    BLUNDERED_ROOK_EVAL_DROP,
)


def _is_promotion_to(move_san: Optional[str], piece: str) -> bool:
    """True if SAN is a promotion to the given piece type (q/r)."""
    if not move_san or "=" not in move_san:
        return False
    promoted = move_san.split("=", 1)[1][:1]
    return promoted.lower() == piece.lower()


class BlunderedPieceRule(HighlightRule):
    """Detects when a side blunders a queen or rook."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for blundered piece highlights.

        White captures on the current row after Black's blunder on the previous row.
        Black captures on the current row after White's blunder on the *same* row
        (White moves first, then Black takes).
        """
        highlights: List[GameHighlight] = []
        if not context.prev_move:
            return highlights

        # Same-row queen/rook trade (e.g. Qxd8+ Rxd8): both sides captured the same
        # piece type — not a free hung piece.
        equal_trade_piece = (
            move.white_capture
            if (
                move.white_capture in ("q", "r")
                and move.black_capture == move.white_capture
            )
            else None
        )

        # White captured Black's queen/rook → Black blundered on the previous full move.
        if move.white_capture in ("q", "r") and move.white_capture != equal_trade_piece:
            # Recapture of a just-promoted queen/rook is not a hung pre-existing piece
            # (e.g. ...bxa1=Q Bxa1).
            if not _is_promotion_to(context.prev_move.black_move, move.white_capture):
                # Equal rook/queen trade completing now: Black took the same piece
                # type last half-move (e.g. ...Rxd1 Rxd1), or Black recaptures later.
                if not self._equal_piece_recapture(
                    piece=move.white_capture,
                    same_move_capture=move.black_capture,
                    prior_capture=context.prev_move.black_capture,
                    next_move=context.next_move,
                    next_is_white=False,
                ):
                    baseline = self._piece_count_before_prev_move(
                        context, is_white=False, piece=move.white_capture
                    )
                    highlight = self._maybe_blundered_highlight(
                        context=context,
                        piece_lost=move.white_capture,
                        is_white_blunder=False,
                        piece_count_before=baseline,
                        piece_count_after=(
                            move.black_queens
                            if move.white_capture == "q"
                            else move.black_rooks
                        ),
                        blunder_cpl=context.prev_move.cpl_black,
                        blunder_assess=context.prev_move.assess_black,
                        blunder_move_number=context.prev_move.move_number,
                        blunder_notation=(
                            f"{context.prev_move.move_number}. "
                            f"...{context.prev_move.black_move}"
                        ),
                        # White-centric eval: before Black's blunder → after White's capture.
                        eval_before_str=context.prev_move.eval_white,
                        eval_after_str=move.eval_white,
                        # Black got worse when eval rose.
                        eval_drop_fn=lambda before, after: after - before,
                        recovery_cpl=(
                            context.next_move.cpl_black if context.next_move else None
                        ),
                        recovery_assess=(
                            context.next_move.assess_black if context.next_move else None
                        ),
                        recovery_eval_after_str=(
                            context.next_move.eval_black if context.next_move else None
                        ),
                        # Recovery for Black = eval falling back toward them.
                        recovery_eval_fn=lambda after_capture, after_recovery: (
                            after_capture - after_recovery
                        ),
                    )
                    if highlight:
                        highlights.append(highlight)

        # Black captured White's queen/rook → White blundered on this same row.
        if move.black_capture in ("q", "r") and move.black_capture != equal_trade_piece:
            # Skip recapture of a queen/rook White just promoted (this row or previous).
            if not (
                _is_promotion_to(move.white_move, move.black_capture)
                or _is_promotion_to(context.prev_move.white_move, move.black_capture)
            ):
                # Next-move equal recapture (e.g. ...Rxf2 Rxf2) — rook trade, not a blunder.
                if not self._equal_piece_recapture(
                    piece=move.black_capture,
                    same_move_capture=move.white_capture,
                    prior_capture=context.prev_move.white_capture,
                    next_move=context.next_move,
                    next_is_white=True,
                ):
                    highlight = self._maybe_blundered_highlight(
                        context=context,
                        piece_lost=move.black_capture,
                        is_white_blunder=True,
                        piece_count_before=(
                            context.prev_white_queens
                            if move.black_capture == "q"
                            else context.prev_white_rooks
                        ),
                        piece_count_after=(
                            move.white_queens
                            if move.black_capture == "q"
                            else move.white_rooks
                        ),
                        blunder_cpl=move.cpl_white,
                        blunder_assess=move.assess_white,
                        blunder_move_number=move.move_number,
                        blunder_notation=f"{move.move_number}. {move.white_move}",
                        # White-centric eval: before White's blunder → after Black's capture.
                        eval_before_str=(
                            context.prev_move.eval_black
                            if context.prev_move.black_move
                            else context.prev_move.eval_white
                        ),
                        eval_after_str=move.eval_black,
                        # White got worse when eval fell.
                        eval_drop_fn=lambda before, after: before - after,
                        recovery_cpl=(
                            context.next_move.cpl_white if context.next_move else None
                        ),
                        recovery_assess=(
                            context.next_move.assess_white if context.next_move else None
                        ),
                        recovery_eval_after_str=(
                            context.next_move.eval_white if context.next_move else None
                        ),
                        # Recovery for White = eval rising again.
                        recovery_eval_fn=lambda after_capture, after_recovery: (
                            after_recovery - after_capture
                        ),
                    )
                    if highlight:
                        highlights.append(highlight)

        return highlights

    @staticmethod
    def _equal_piece_recapture(
        *,
        piece: str,
        same_move_capture: str,
        prior_capture: str,
        next_move: Optional[MoveData],
        next_is_white: bool,
    ) -> bool:
        """True if the lost q/r is (or will be) regained in an equal trade.

        same_move_capture: opponent already took the same piece type on this row.
        prior_capture: the side now "losing" the piece already captured the same
            type on the previous half-move (e.g. ...Rxd1 then Rxd1 completes the trade).
        next_move: victim's following half-move recaptures the same piece type
            (e.g. 27...Rxf2 28.Rxf2).
        """
        if same_move_capture == piece or prior_capture == piece:
            return True
        if not next_move:
            return False
        nxt = next_move.white_capture if next_is_white else next_move.black_capture
        return nxt == piece

    def _piece_count_before_prev_move(
        self, context: RuleContext, *, is_white: bool, piece: str
    ) -> int:
        """Piece count after the move before prev_move (baseline before that half-move)."""
        if context.move_index >= 2:
            earlier = context.moves[context.move_index - 2]
            if piece == "q":
                return earlier.white_queens if is_white else earlier.black_queens
            return earlier.white_rooks if is_white else earlier.black_rooks
        return 1 if piece == "q" else 2

    def _maybe_blundered_highlight(
        self,
        *,
        context: RuleContext,
        piece_lost: str,
        is_white_blunder: bool,
        piece_count_before: int,
        piece_count_after: int,
        blunder_cpl: Optional[str],
        blunder_assess: Optional[str],
        blunder_move_number: int,
        blunder_notation: str,
        eval_before_str: Optional[str],
        eval_after_str: Optional[str],
        eval_drop_fn,
        recovery_cpl: Optional[str],
        recovery_assess: Optional[str],
        recovery_eval_after_str: Optional[str],
        recovery_eval_fn,
    ) -> Optional[GameHighlight]:
        if piece_count_after >= piece_count_before:
            return None

        material_loss = PIECE_VALUES.get(piece_lost, 0)
        min_loss = (
            BLUNDERED_QUEEN_MIN_LOSS if piece_lost == "q" else BLUNDERED_ROOK_MIN_LOSS
        )
        min_eval_drop = (
            BLUNDERED_QUEEN_EVAL_DROP if piece_lost == "q" else BLUNDERED_ROOK_EVAL_DROP
        )
        if material_loss < min_loss:
            return None

        cpl_value: Optional[float] = None
        if blunder_cpl is not None and blunder_cpl != "":
            try:
                cpl_value = float(blunder_cpl)
            except (ValueError, TypeError):
                cpl_value = None

        is_blunder = (cpl_value is not None and cpl_value > context.mistake_max_cpl) or (
            blunder_assess == "Blunder"
        )
        if not is_blunder:
            return None

        # Immediate follow-up recovery: skip the highlight.
        if context.next_move:
            next_cpl_value: Optional[float] = None
            if recovery_cpl is not None and recovery_cpl != "":
                try:
                    next_cpl_value = float(recovery_cpl)
                except (ValueError, TypeError):
                    next_cpl_value = None

            if recovery_assess == "Best Move" or (
                next_cpl_value is not None and next_cpl_value <= 20
            ):
                return None

            if recovery_eval_after_str and eval_after_str:
                eval_after_capture = parse_evaluation(eval_after_str)
                eval_after_recovery = parse_evaluation(recovery_eval_after_str)
                if eval_after_capture is not None and eval_after_recovery is not None:
                    if recovery_eval_fn(eval_after_capture, eval_after_recovery) >= min_eval_drop:
                        return None

        eval_drop = 0.0
        if eval_before_str and eval_after_str:
            eval_before = parse_evaluation(eval_before_str)
            eval_after = parse_evaluation(eval_after_str)
            if eval_before is not None and eval_after is not None:
                eval_drop = eval_drop_fn(eval_before, eval_after)

        if eval_drop < min_eval_drop:
            return None

        piece_name = "queen" if piece_lost == "q" else "rook"
        side = "White" if is_white_blunder else "Black"
        return GameHighlight(
            move_number=blunder_move_number,
            is_white=is_white_blunder,
            move_notation=blunder_notation,
            description=f"{side} blundered his {piece_name}",
            priority=50,
            rule_type="blundered_piece",
        )
