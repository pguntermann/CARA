"""Rule for detecting defensive resources found."""

from typing import List

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import (
    DEFENSIVE_EVAL_IMPROVEMENT_THRESHOLD,
    PIECE_VALUES,
)
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import MIN_VALUABLE_PIECE_VALUE

_THREAT_CPL = 150
_ALT_DEFENSE_CPL = 100
_BAD_EVAL_CP = 150
_OPPONENT_GAIN_CP = 100


class DefensiveResourceRule(HighlightRule):
    """Detects when a side finds the only good defense against a real threat."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for defensive resource highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        prior = half.prior()
        if prior is None:
            return []

        prior_cpl = prior.cpl_float()
        curr_cpl = half.cpl_float()
        if prior_cpl is None or curr_cpl is None:
            return []

        opponent_created_threat = prior_cpl > _THREAT_CPL
        evaluation_was_bad = self._evaluation_was_bad(half, prior)
        if not (opponent_created_threat or evaluation_was_bad):
            return []

        board_before = half.board_before()
        board_after = half.board_after()
        if board_before is None or board_after is None:
            return []
        if not self._has_tactical_threat(board_before, half.color):
            return []
        if not self._move_defends_threat(board_before, board_after, half.color):
            return []

        if curr_cpl >= half.context.good_move_max_cpl:
            return []

        is_best = (
            half.is_top3
            and bool(half.best)
            and half.best.strip().lower() == half.san.strip().lower()
        )
        if not is_best:
            return []

        # When PV2/PV3 exist, require them to be clearly worse (only defense).
        if half.cpl_2 and half.cpl_3 and not half.alt_cpls_above(_ALT_DEFENSE_CPL):
            return []

        improvement = half.eval_improvement_cp()
        if (
            improvement is None
            or improvement < -DEFENSIVE_EVAL_IMPROVEMENT_THRESHOLD
        ):
            return []

        return [
            make_highlight(
                half,
                f"{half.side_name} found the only defensive resource",
                priority=20,
                rule_type="defensive_resource",
            )
        ]

    def _evaluation_was_bad(
        self, half: HalfMoveContext, prior: HalfMoveContext
    ) -> bool:
        before = half.eval_before_cp()
        if before is not None:
            if half.is_white and before < -_BAD_EVAL_CP:
                return True
            if not half.is_white and before > _BAD_EVAL_CP:
                return True

        prior_gain = prior.eval_improvement_cp()
        return prior_gain is not None and prior_gain > _OPPONENT_GAIN_CP

    def _has_tactical_threat(self, board: chess.Board, color: chess.Color) -> bool:
        if board.is_check():
            return True

        opponent = not color
        for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            for sq in board.pieces(piece_type, color):
                if not board.is_attacked_by(opponent, sq):
                    continue
                if board.is_attacked_by(color, sq):
                    continue
                piece = board.piece_at(sq)
                if piece is None:
                    continue
                if PIECE_VALUES.get(piece.symbol().lower(), 0) >= MIN_VALUABLE_PIECE_VALUE:
                    return True

        king_square = board.king(color)
        if king_square is not None and len(board.attackers(opponent, king_square)) >= 2:
            return True
        return False

    def _move_defends_threat(
        self,
        board_before: chess.Board,
        board_after: chess.Board,
        color: chess.Color,
    ) -> bool:
        opponent = not color

        if board_before.is_check() and not board_after.is_check():
            return True

        for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            for sq in board_before.pieces(piece_type, color):
                if not board_before.is_attacked_by(opponent, sq):
                    continue
                if board_before.is_attacked_by(color, sq):
                    continue
                if board_after.is_attacked_by(color, sq) or not board_after.is_attacked_by(
                    opponent, sq
                ):
                    piece = board_before.piece_at(sq)
                    if piece is None:
                        continue
                    if (
                        PIECE_VALUES.get(piece.symbol().lower(), 0)
                        >= MIN_VALUABLE_PIECE_VALUE
                    ):
                        return True

        king_square = board_before.king(color)
        if king_square is not None:
            before_n = len(board_before.attackers(opponent, king_square))
            after_n = len(board_after.attackers(opponent, king_square))
            if before_n >= 2 and after_n < before_n:
                return True
        return False
