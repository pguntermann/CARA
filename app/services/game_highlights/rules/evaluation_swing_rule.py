"""Rule for detecting large evaluation swings."""

from typing import Dict, List, Tuple

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import EVALUATION_SWING_THRESHOLD
from app.services.game_highlights.half_move import HalfMoveContext, iter_half_moves, make_highlight

_MAX_OWN_CPL = 30
_OPPONENT_MISTAKE_CPL = 100

# shared_state key -> (swing_cp, highlight); best swing kept per side/phase/direction
_SwingStore = Dict[Tuple[bool, str, str], Tuple[float, GameHighlight]]


class EvaluationSwingRule(HighlightRule):
    """Detects large same-sign evaluation swings (not zero-crossings).

    Candidates are stored in ``shared_state['eval_swing_highlights']`` and collected
    by the detector after the game is scanned (one best swing per side/phase/direction).
    """

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Track swing candidates; highlights are emitted in post-processing."""
        store: _SwingStore = context.shared_state.setdefault("eval_swing_highlights", {})

        for half in iter_half_moves(move, context):
            self._consider_half(half, store)

        return []

    def _consider_half(self, half: HalfMoveContext, store: _SwingStore) -> None:
        before = half.eval_before_cp()
        after = half.eval_after_cp()
        if before is None or after is None:
            return

        # White-relative swing size; exclude momentum (sign change).
        white_diff = after - before
        swing = abs(white_diff)
        sign_changed = (before > 0 and after < 0) or (before < 0 and after > 0)
        if swing <= EVALUATION_SWING_THRESHOLD or sign_changed:
            return

        cpl = half.cpl_float()
        if cpl is None or cpl >= _MAX_OWN_CPL:
            return

        reply = half.reply()
        if reply is not None:
            opp_cpl = reply.cpl_float()
            if opp_cpl is not None and opp_cpl > _OPPONENT_MISTAKE_CPL:
                return

        # Direction from the mover's perspective.
        mover_diff = white_diff if half.is_white else -white_diff
        direction = "increased" if mover_diff > 0 else "decreased"
        phase = self._phase(half)
        key = (half.is_white, phase, direction)

        if key in store and swing <= store[key][0]:
            return

        change_pawns = swing / 100.0
        store[key] = (
            swing,
            make_highlight(
                half,
                f"{half.side_name}'s evaluation {direction} by {change_pawns:.1f} pawns",
                priority=30,
                rule_type="evaluation_swing",
            ),
        )

    def _phase(self, half: HalfMoveContext) -> str:
        move_num = half.move_number
        if move_num <= half.context.opening_end:
            return "opening"
        if move_num < half.context.middlegame_end:
            return "middlegame"
        return "endgame"
