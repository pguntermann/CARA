"""Rank top-best-move candidates for the game summary.

Order: classification, tactic hit, only-move, CPL, then discounted eval gain.
The displayed CP gain stays the capped mover-perspective change; ranking uses
a stricter gain that ignores recaptures, search-noise jumps, and already-won
positions. Tactic detection is a dedicated allowlisted pass on candidates,
not a boost from the Game Highlights story list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from app.models.moveslist_model import MoveData
from app.services.game_highlights.base_rule import HighlightRule
from app.services.game_highlights.half_move import make_rule_context

EVAL_IMPROVEMENT_CAP_CP = 500.0
SEARCH_NOISE_GAIN_CP = 250.0
ALREADY_WINNING_CP = 500.0
MATERIAL_GRAB_CP = 100.0
PREFERRED_MAX_RANK = 1  # Brilliant, Best Move
FILLER_MAX_RANK = 2  # Good Move

ParseEval = Callable[[str], Optional[float]]


_TACTIC_LABELS = {
    "fork": "fork",
    "skewer": "skewer",
    "pin": "pin",
    "discovered_attack": "discovered attack",
    "zwischenzug": "zwischenzug",
    "decoy": "decoy",
    "exchange_sacrifice": "exchange sacrifice",
    "forcing_combination": "forcing combination",
}


@dataclass(frozen=True)
class RankedBestMove:
    """One scored candidate ready to map onto a summary CriticalMove."""

    move_number: int
    move_notation: str
    cpl: float
    assessment: str
    evaluation: str
    best_move: str
    display_gain: float
    selection_reason: str = ""


def assessment_rank(assessment: str) -> int:
    """Lower is better: Brilliant, Best Move, Good Move, then everything else."""
    text = str(assessment or "")
    if text.startswith("Brilliant"):
        return 0
    if text == "Best Move":
        return 1
    if text == "Good Move":
        return 2
    return 3


def eval_before_cp(
    moves: List[MoveData], index: int, is_white: bool, parse_eval: ParseEval
) -> Optional[float]:
    """White-relative eval of the position immediately before this half-move."""
    move = moves[index]
    if is_white:
        if index <= 0:
            return 0.0
        prev = moves[index - 1]
        if prev.eval_black:
            return parse_eval(prev.eval_black)
        if prev.eval_white:
            return parse_eval(prev.eval_white)
        return 0.0
    if move.eval_white:
        return parse_eval(move.eval_white)
    if index > 0:
        prev = moves[index - 1]
        if prev.eval_black:
            return parse_eval(prev.eval_black)
    return None


def display_eval_gain_cp(
    moves: List[MoveData], index: int, is_white: bool, parse_eval: ParseEval
) -> float:
    """Mover-perspective eval change in centipawns, capped for display and ranking input."""
    move = moves[index]
    after_str = move.eval_white if is_white else move.eval_black
    after = parse_eval(after_str) if after_str else None
    before = eval_before_cp(moves, index, is_white, parse_eval)
    if after is None or before is None:
        return 0.0
    raw = (after - before) if is_white else (before - after)
    return max(-EVAL_IMPROVEMENT_CAP_CP, min(EVAL_IMPROVEMENT_CAP_CP, raw))


def _parse_optional_float(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def is_capture_or_material_grab(
    move: MoveData, *, is_white: bool, prev: Optional[MoveData]
) -> bool:
    """True if this half-move takes material (capture SAN/field or material jump)."""
    san = (move.white_move if is_white else move.black_move) or ""
    if "x" in san:
        return True
    capture = (move.white_capture if is_white else move.black_capture) or ""
    if capture:
        return True
    after = move.white_material if is_white else move.black_material
    if is_white:
        before = prev.white_material if prev is not None else 0
    else:
        before = prev.black_material if prev is not None else 0
    if before > 0 and after > 0 and (after - before) >= MATERIAL_GRAB_CP:
        return True
    return False


def is_only_move(move: MoveData, *, is_white: bool, good_move_max_cpl: float) -> bool:
    """True when PV2 is already outside the good-move window (a unique engine find)."""
    raw = move.cpl_white_2 if is_white else move.cpl_black_2
    cpl_2 = _parse_optional_float(raw or "")
    if cpl_2 is None:
        return False
    return cpl_2 >= float(good_move_max_cpl)


def gain_discount_reason(
    display_gain: float,
    *,
    cpl: float,
    eval_before: Optional[float],
    is_material_grab: bool,
) -> Optional[str]:
    """Why ranking gain was zeroed, or None if the displayed gain is trusted."""
    if is_material_grab:
        return "capture"
    if eval_before is not None and abs(eval_before) >= ALREADY_WINNING_CP:
        return "already winning"
    if cpl <= 10.0 and abs(display_gain) > SEARCH_NOISE_GAIN_CP:
        return "search noise"
    return None


def ranking_eval_gain(
    display_gain: float,
    *,
    cpl: float,
    eval_before: Optional[float],
    is_material_grab: bool,
) -> float:
    """Eval gain used only as a sort key after class / tactic / only-move / CPL."""
    if gain_discount_reason(
        display_gain,
        cpl=cpl,
        eval_before=eval_before,
        is_material_grab=is_material_grab,
    ):
        return 0.0
    return max(0.0, display_gain)


def format_best_move_selection_reason(
    *,
    assessment: str,
    tactic_type: str = "",
    only_move: bool = False,
    only_move_cpl2: Optional[float] = None,
    display_gain: float = 0.0,
    gain_ignored: Optional[str] = None,
    is_filler: bool = False,
) -> str:
    """Plain-text tooltip explaining why this ply made the top-best list."""
    lines: List[str] = []
    text = str(assessment or "")
    if text.startswith("Brilliant"):
        lines.append("Chosen as a Brilliant move")
    elif text == "Best Move":
        lines.append("Chosen as a Best Move")
    elif is_filler or text == "Good Move":
        lines.append("Good Move included to fill the top 3")
    elif text:
        lines.append(f"Chosen as {text}")

    if tactic_type:
        label = _TACTIC_LABELS.get(tactic_type, tactic_type.replace("_", " "))
        lines.append(f"Tactic: {label}")

    if only_move:
        if only_move_cpl2 is not None:
            lines.append(f"Only engine move (next-best CPL {only_move_cpl2:.0f})")
        else:
            lines.append("Only engine move")

    if gain_ignored:
        lines.append(f"Eval jump ignored: {gain_ignored}")
    elif text.startswith("Brilliant") or text == "Best Move":
        n = max(0, int(round(float(display_gain or 0.0))))
        if n == 0:
            lines.append("CP gain 0 counted in ranking")
        else:
            lines.append(f"CP gain {n:+d} counted in ranking")

    return "\n".join(lines)


def load_best_move_tactic_rules(
    rules_config: Optional[Dict] = None,
) -> List[HighlightRule]:
    """Instantiate the allowlisted tactic rules used for best-move ranking."""
    from app.services.game_highlights.rules.decoy_rule import DecoyRule
    from app.services.game_highlights.rules.discovered_attack_rule import DiscoveredAttackRule
    from app.services.game_highlights.rules.exchange_sacrifice_rule import ExchangeSacrificeRule
    from app.services.game_highlights.rules.forcing_combination_rule import ForcingCombinationRule
    from app.services.game_highlights.rules.fork_rule import ForkRule
    from app.services.game_highlights.rules.pin_rule import PinRule
    from app.services.game_highlights.rules.skewer_rule import SkewerRule
    from app.services.game_highlights.rules.zwischenzug_rule import ZwischenzugRule

    cfg = rules_config if isinstance(rules_config, dict) else {}
    loaded: List[HighlightRule] = []
    for rule_id, cls in (
        ("fork", ForkRule),
        ("skewer", SkewerRule),
        ("pin", PinRule),
        ("discovered_attack", DiscoveredAttackRule),
        ("zwischenzug", ZwischenzugRule),
        ("decoy", DecoyRule),
        ("exchange_sacrifice", ExchangeSacrificeRule),
        ("forcing_combination", ForcingCombinationRule),
    ):
        rule_cfg = cfg.get(rule_id, {})
        if not isinstance(rule_cfg, dict):
            rule_cfg = {}
        rule = cls(rule_cfg)
        if rule.is_enabled():
            loaded.append(rule)
    return loaded


def detect_best_tactic(
    moves: List[MoveData],
    index: int,
    *,
    is_white: bool,
    tactic_rules: Sequence[HighlightRule],
    opening_end: int,
    middlegame_end: int,
    good_move_max_cpl: int,
    inaccuracy_max_cpl: int,
    mistake_max_cpl: int,
) -> str:
    """Allowlisted tactic ``rule_type`` for this side, or empty if none fires."""
    if not tactic_rules:
        return ""
    context = make_rule_context(
        moves,
        index,
        opening_end=opening_end,
        middlegame_end=middlegame_end,
        good_move_max_cpl=good_move_max_cpl,
        inaccuracy_max_cpl=inaccuracy_max_cpl,
        mistake_max_cpl=mistake_max_cpl,
    )
    move = moves[index]
    for rule in tactic_rules:
        try:
            highlights = rule.evaluate(move, context)
        except Exception:
            continue
        for highlight in highlights:
            if highlight.is_white == is_white:
                return str(highlight.rule_type or "")
    return ""


@dataclass
class _Candidate:
    move_number: int
    move_notation: str
    cpl: float
    assessment: str
    evaluation: str
    best_move: str
    class_rank: int
    index: int
    display_gain: float
    eval_before: Optional[float]
    is_material_grab: bool
    only_move: bool
    only_move_cpl2: Optional[float]
    tactic_type: str = ""
    ranking_gain: float = 0.0
    gain_ignored: Optional[str] = None


def select_top_best_moves(
    moves: List[MoveData],
    *,
    is_white: bool,
    count: int,
    parse_eval: ParseEval,
    good_move_max_cpl: int,
    inaccuracy_max_cpl: int,
    mistake_max_cpl: int,
    opening_end: int,
    middlegame_end: int,
    tactic_rules: Sequence[HighlightRule],
) -> List[RankedBestMove]:
    """Return up to ``count`` best-move candidates in display order."""
    if is_white:
        cpl_field = "cpl_white"
        assess_field = "assess_white"
        eval_field = "eval_white"
        move_field = "white_move"
        best_field = "best_white"
        cpl2_field = "cpl_white_2"
    else:
        cpl_field = "cpl_black"
        assess_field = "assess_black"
        eval_field = "eval_black"
        move_field = "black_move"
        best_field = "best_black"
        cpl2_field = "cpl_black_2"

    candidates: List[_Candidate] = []
    for index, move in enumerate(moves):
        move_str = getattr(move, move_field)
        if not move_str:
            continue
        assessment = getattr(move, assess_field)
        if assessment == "Book Move":
            continue
        class_rank = assessment_rank(assessment)
        if class_rank > FILLER_MAX_RANK:
            continue
        cpl_str = getattr(move, cpl_field)
        if not cpl_str:
            continue
        try:
            cpl = float(cpl_str)
        except (ValueError, TypeError):
            continue
        display_gain = display_eval_gain_cp(moves, index, is_white, parse_eval)
        prev = moves[index - 1] if index > 0 else None
        cpl2 = _parse_optional_float(getattr(move, cpl2_field, "") or "")
        candidates.append(
            _Candidate(
                move_number=move.move_number,
                move_notation=f"{move.move_number}. {move_str}",
                cpl=cpl,
                assessment=assessment or "",
                evaluation=getattr(move, eval_field),
                best_move=getattr(move, best_field, "") or "",
                class_rank=class_rank,
                index=index,
                display_gain=display_gain,
                eval_before=eval_before_cp(moves, index, is_white, parse_eval),
                is_material_grab=is_capture_or_material_grab(
                    move, is_white=is_white, prev=prev
                ),
                only_move=is_only_move(
                    move, is_white=is_white, good_move_max_cpl=good_move_max_cpl
                ),
                only_move_cpl2=cpl2,
            )
        )

    preferred = [c for c in candidates if c.class_rank <= PREFERRED_MAX_RANK]
    pool = preferred if len(preferred) >= count else candidates

    for candidate in pool:
        candidate.tactic_type = detect_best_tactic(
            moves,
            candidate.index,
            is_white=is_white,
            tactic_rules=tactic_rules,
            opening_end=opening_end,
            middlegame_end=middlegame_end,
            good_move_max_cpl=good_move_max_cpl,
            inaccuracy_max_cpl=inaccuracy_max_cpl,
            mistake_max_cpl=mistake_max_cpl,
        )
        candidate.gain_ignored = gain_discount_reason(
            candidate.display_gain,
            cpl=candidate.cpl,
            eval_before=candidate.eval_before,
            is_material_grab=candidate.is_material_grab,
        )
        candidate.ranking_gain = ranking_eval_gain(
            candidate.display_gain,
            cpl=candidate.cpl,
            eval_before=candidate.eval_before,
            is_material_grab=candidate.is_material_grab,
        )

    pool.sort(
        key=lambda c: (
            c.class_rank,
            0 if c.tactic_type else 1,
            0 if c.only_move else 1,
            c.cpl,
            -c.ranking_gain,
        )
    )
    ranked: List[RankedBestMove] = []
    for candidate in pool[:count]:
        ranked.append(
            RankedBestMove(
                move_number=candidate.move_number,
                move_notation=candidate.move_notation,
                cpl=candidate.cpl,
                assessment=candidate.assessment,
                evaluation=candidate.evaluation,
                best_move=candidate.best_move,
                display_gain=candidate.display_gain,
                selection_reason=format_best_move_selection_reason(
                    assessment=candidate.assessment,
                    tactic_type=candidate.tactic_type,
                    only_move=candidate.only_move,
                    only_move_cpl2=candidate.only_move_cpl2 if candidate.only_move else None,
                    display_gain=candidate.display_gain,
                    gain_ignored=candidate.gain_ignored,
                    is_filler=candidate.class_rank == FILLER_MAX_RANK,
                ),
            )
        )
    return ranked
