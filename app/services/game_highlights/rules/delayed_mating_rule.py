"""Rule for detecting delayed mating (consecutive missed mate opportunities)."""

from typing import Dict, List, Set, Tuple

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    iter_half_moves,
    make_highlight,
)

_MAX_MATE_IN = 5

# shared_state['missed_mate_tracking'][(is_white, phase)] =
#   (count, first_move_num, last_move_num, best_san)
_Tracking = Dict[Tuple[bool, str], Tuple[int, int, int, str]]


class DelayedMatingRule(HighlightRule):
    """Detects missed mates and delayed mating when misses stack consecutively."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for missed-mate and delayed-mating highlights."""
        phase = self._phase(move.move_number, context)
        tracking: _Tracking = context.shared_state.setdefault("missed_mate_tracking", {})
        delayed_created: Set[Tuple[bool, str]] = context.shared_state.setdefault(
            "delayed_mate_created", set()
        )
        delayed_ranges: List[Tuple[int, int, bool]] = context.shared_state.setdefault(
            "delayed_mating_ranges", []
        )

        highlights: List[GameHighlight] = []
        for half in iter_half_moves(move, context):
            highlights.extend(self._evaluate_half(half, phase, tracking))

        highlights.extend(
            self._emit_delayed_highlights(tracking, delayed_created, delayed_ranges)
        )
        return highlights

    def _evaluate_half(
        self, half: HalfMoveContext, phase: str, tracking: _Tracking
    ) -> List[GameHighlight]:
        key = (half.is_white, phase)

        if not half.best:
            tracking.pop(key, None)
            return []

        best_is_mate = "#" in half.best or half.favoring_mate_in() is not None
        if not best_is_mate:
            tracking.pop(key, None)
            return []

        if half.san == half.best:
            # Played the mating move — streak ends.
            tracking.pop(key, None)
            return []

        # Missed a real mate threat: worse than a good move, mate-in ≤ 5.
        if not half.is_mistake(min_cpl=half.context.good_move_max_cpl):
            return []
        if not half.is_favoring_mate_within(_MAX_MATE_IN):
            return []

        if key in tracking:
            count, first_move, _, _ = tracking[key]
            tracking[key] = (count + 1, first_move, half.move_number, half.best)
        else:
            tracking[key] = (1, half.move_number, half.move_number, half.best)

        return [
            make_highlight(
                half,
                (
                    f"{half.side_name} missed a checkmate opportunity "
                    f"(best move was {half.best})"
                ),
                priority=50,
                rule_type="delayed_mating",
            )
        ]

    def _emit_delayed_highlights(
        self,
        tracking: _Tracking,
        delayed_created: Set[Tuple[bool, str]],
        delayed_ranges: List[Tuple[int, int, bool]],
    ) -> List[GameHighlight]:
        """Emit one delayed-mating highlight per side/phase once count reaches 2."""
        highlights: List[GameHighlight] = []
        for (is_white, phase_key), (count, first_move, last_move, best) in list(
            tracking.items()
        ):
            if count < 2 or (is_white, phase_key) in delayed_created:
                continue

            side = "White" if is_white else "Black"
            if first_move == last_move:
                notation = f"{first_move}." if is_white else f"{first_move}. ..."
            else:
                notation = (
                    f"{first_move}-{last_move}."
                    if is_white
                    else f"{first_move}-{last_move}. ..."
                )

            highlights.append(
                GameHighlight(
                    move_number=first_move,
                    move_number_end=last_move,
                    is_white=is_white,
                    move_notation=notation,
                    description=f"{side} delayed mating (best move was {best})",
                    priority=55,
                    rule_type="delayed_mating",
                )
            )
            delayed_created.add((is_white, phase_key))
            delayed_ranges.append((first_move, last_move, is_white))
        return highlights

    def _phase(self, move_number: int, context: RuleContext) -> str:
        if move_number <= context.opening_end:
            return "opening"
        if move_number < context.middlegame_end:
            return "middlegame"
        return "endgame"
