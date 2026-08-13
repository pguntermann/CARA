"""Rule for detecting material imbalances."""

from typing import List, Optional

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)
from app.services.game_highlights.helpers import piece_type_from_san

_MINOR = frozenset({"n", "b"})
_MIN_PAWNS_FOR_PIECE = 2
_ROOK_RECAPTURE_BASE = 2
_ROOK_RECAPTURE_MAX = 10


class MaterialImbalanceRule(HighlightRule):
    """Detects unusual trades: a minor for multiple pawns, or a rook for a minor."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for material imbalance highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        highlights: List[GameHighlight] = []

        piece_for_pawns = self._piece_for_pawns(half)
        if piece_for_pawns is not None:
            highlights.append(piece_for_pawns)

        rook_for_minor = self._rook_for_minor(half)
        if rook_for_minor is not None:
            highlights.append(rook_for_minor)

        return highlights

    def _piece_for_pawns(self, half: HalfMoveContext) -> Optional[GameHighlight]:
        """Capture a minor while the opponent loses ≥2 pawns over the same full move."""
        cap = (half.capture or "").lower()
        if cap not in _MINOR:
            return None

        # Opponent pawn drop from before this ply to after the MoveData row settles.
        # White: previous row's black pawns vs current row (after black's reply if any).
        # Black: white pawns before this ply vs after this ply (fixed vs old prev-row baseline).
        if half.is_white:
            pawn_diff = half.context.prev_black_pawns - half.move.black_pawns
        else:
            before = half.board_before()
            after = half.board_after()
            if before is None or after is None:
                return None
            pawn_diff = len(before.pieces(chess.PAWN, chess.WHITE)) - len(
                after.pieces(chess.PAWN, chess.WHITE)
            )

        if pawn_diff < _MIN_PAWNS_FOR_PIECE:
            return None

        return make_highlight(
            half,
            f"{half.side_name} traded {cap.upper()} for {pawn_diff} pawns",
            priority=25,
            rule_type="material_imbalance",
        )

    def _rook_for_minor(self, half: HalfMoveContext) -> Optional[GameHighlight]:
        """Rook takes a minor and the rook is recaptured (not a best-move exchange sac)."""
        cap = (half.capture or "").lower()
        if cap not in _MINOR:
            return None
        if piece_type_from_san(half.san) != chess.ROOK:
            return None
        if (half.assess or "") == "Best Move":
            return None

        reply = half.reply()
        recaptured = reply is not None and (reply.capture or "").lower() == "r"
        if not recaptured and not self._rook_recaptured_later(half):
            return None

        return make_highlight(
            half,
            f"{half.side_name} traded rook for minor piece",
            priority=32,
            rule_type="material_imbalance",
        )

    def _rook_recaptured_later(self, half: HalfMoveContext) -> bool:
        """True if the opponent captures a rook within an adaptive capture window."""
        look_ahead = _ROOK_RECAPTURE_BASE
        plies = list(half.iter_following(limit=_ROOK_RECAPTURE_MAX))
        if not plies:
            return False

        checked = 0
        while look_ahead <= _ROOK_RECAPTURE_MAX:
            end = min(look_ahead, len(plies))
            if end <= checked:
                break
            for ply in plies[checked:end]:
                if ply.is_white == half.is_white:
                    continue
                if (ply.capture or "").lower() == "r":
                    return True
            last = plies[end - 1]
            checked = end
            if last.capture and last.is_white == half.is_white:
                look_ahead += 1
                continue
            break
        return False
