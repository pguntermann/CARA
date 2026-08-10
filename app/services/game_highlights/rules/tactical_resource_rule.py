"""Rule for detecting strong tactical resources."""

from typing import List

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    evaluate_for_each_side,
    make_highlight,
)

_FORCED_CPL_MAX = 10
_CAPTURE_EVAL_MIN_CP = 200
_QUIET_EVAL_MIN_CP = 300
_QUIET_EVAL_ENDGAME_MIN_CP = 400
_CLEARLY_BEST_ALT_CPL = 50


class TacticalResourceRule(HighlightRule):
    """Detects strong tactical resources (good moves with lasting tactical payoff)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for tactical resource highlights."""
        return evaluate_for_each_side(move, context, self._evaluate_half)

    def _evaluate_half(self, half: HalfMoveContext) -> List[GameHighlight]:
        if not half.is_good_move():
            return []

        if half.is_equal_trade_with_neighbors():
            return []

        if self._is_part_of_forced_sequence(half):
            return []

        # Taking a piece the opponent just hung on a blunder is cashing in, not
        # "finding" a resource (blundered_piece / missed tactics tell that story).
        if self._is_collecting_blundered_piece(half):
            return []

        # Plain capture of an undefended unit is covered by captured_undefended_piece.
        if half.captures_undefended_unit():
            return []

        if not self._is_tactical_resource(half):
            return []

        clearly_best = half.alt_cpls_above(_CLEARLY_BEST_ALT_CPL)
        label = "clearly best tactical resource" if clearly_best else "strong tactical resource"
        return [
            make_highlight(
                half,
                f"{half.side_name} found a {label}",
                priority=28 if clearly_best else 25,
                rule_type="tactical_resource",
            )
        ]

    def _is_collecting_blundered_piece(self, half: HalfMoveContext) -> bool:
        """True if this capture takes a unit left en prise by the opponent's blunder."""
        if not half.capture:
            return False
        prior = half.prior()
        if prior is None or not prior.is_serious_error():
            return False

        dest = half.destination_square()
        board_after_blunder = prior.board_after()
        if dest is None or board_after_blunder is None:
            return False

        target = board_after_blunder.piece_at(dest)
        if target is None or target.color != prior.color:
            return False

        # We were already attacking that square after their blunder.
        return board_after_blunder.is_attacked_by(half.color, dest)

    def _is_tactical_resource(self, half: HalfMoveContext) -> bool:
        """Capture with net gain, heavy capture with eval jump, or quiet huge eval jump."""
        if half.capture:
            net_gain = half.capture_trade_net_cp()
            if net_gain is not None and net_gain > 0:
                return True
            captured_value = PIECE_VALUES.get(half.capture.lower(), 0)
            if captured_value >= 300:
                improvement = half.eval_improvement_cp()
                if improvement is not None and improvement >= _CAPTURE_EVAL_MIN_CP:
                    return True
            return False

        improvement = half.eval_improvement_cp()
        if improvement is None:
            return False
        threshold = (
            _QUIET_EVAL_ENDGAME_MIN_CP
            if half.move_number >= half.context.middlegame_end
            else _QUIET_EVAL_MIN_CP
        )
        return improvement >= threshold

    def _is_part_of_forced_sequence(self, half: HalfMoveContext) -> bool:
        """True if the prior opponent move and this reply are both near-forced best moves."""
        prior = half.prior()
        if prior is None:
            return False
        if not prior.is_near_best(_FORCED_CPL_MAX) or not half.is_near_best(_FORCED_CPL_MAX):
            return False

        # If the forced line continues, treat as sequence; otherwise still a forced reply.
        reply = half.reply()
        if reply is not None and reply.is_near_best(_FORCED_CPL_MAX):
            our_next = reply.reply()
            if our_next is not None and our_next.is_near_best(_FORCED_CPL_MAX):
                return True
        return True
