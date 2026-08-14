"""Rank missed tactics for the game summary.

A miss is the engine PV1 on the position *before* the played ply, scored with
the same allowlisted board-tactic rules used for best-move ranking (fork,
skewer, pin, discovered attack). Mate, capture, and check on PV1 are a fast
accept and a rank boost — they do not gate the tactic pass, so a quiet fork
with no ``x`` / ``+`` / ``#`` still counts.

This scans analyzed error plies (Miss / Mistake / Blunder). It does not use
the Game Highlights composer or reply-dependent rules.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import chess

from app.models.moveslist_model import MoveData
from app.services.best_move_ranking import ParseEval, display_eval_gain_cp, eval_before_cp
from app.services.game_highlights.base_rule import HighlightRule
from app.services.game_highlights.half_move import make_rule_context
from app.utils.material_tracker import get_captured_piece_letter

ERROR_ASSESSMENTS = frozenset({"Miss", "Mistake", "Blunder"})
ALREADY_LOST_CP = 500.0
KIND_RANK_MATE = 0
KIND_RANK_TACTIC = 1
KIND_RANK_CAPTURE = 2
KIND_RANK_CHECK = 3

_KIND_LABELS = {
    "mate": "mate",
    "fork": "fork",
    "skewer": "skewer",
    "pin": "pin",
    "discovered_attack": "discovered attack",
    "capture": "capture",
    "check": "check",
}


@dataclass(frozen=True)
class RankedMissedTactic:
    """One scored miss ready to map onto a summary CriticalMove."""

    move_number: int
    move_notation: str
    cpl: float
    assessment: str
    evaluation: str
    best_move: str
    tactic_type: str
    selection_reason: str
    eval_drop: float = 0.0


def missed_kind_label(kind: str) -> str:
    """Short display label for a miss kind (tooltip, subline parens)."""
    text = str(kind or "").strip()
    if not text:
        return ""
    return _KIND_LABELS.get(text, text.replace("_", " "))


def format_missed_tactic_line(move: object) -> str:
    """Subline matching the summary UI: ``Missed: Nc7+ (fork)``."""
    pv1 = str(getattr(move, "best_move", "") or "").strip()
    if not pv1:
        return ""
    label = missed_kind_label(str(getattr(move, "tactic_type", "") or ""))
    if label:
        return f"Missed: {pv1} ({label})"
    return f"Missed: {pv1}"


def format_missed_tactic_selection_reason(
    *,
    played: str,
    pv1: str,
    assessment: str,
    cpl: float,
    kind: str,
) -> str:
    """Plain-text tooltip explaining why this ply made the missed-tactics list."""
    label = missed_kind_label(kind) or "tactic"
    lines = [
        f"Missed {label}",
        f"Engine line: {pv1}",
        f"Played {played} ({assessment})",
        f"CPL {float(cpl):.0f}",
    ]
    return "\n".join(lines)


def load_missed_tactic_rules(
    rules_config: Optional[Dict] = None,
) -> List[HighlightRule]:
    """Instantiate the allowlisted board-tactic rules used for missed PV1 checks."""
    from app.services.game_highlights.rules.discovered_attack_rule import DiscoveredAttackRule
    from app.services.game_highlights.rules.fork_rule import ForkRule
    from app.services.game_highlights.rules.pin_rule import PinRule
    from app.services.game_highlights.rules.skewer_rule import SkewerRule

    cfg = rules_config if isinstance(rules_config, dict) else {}
    loaded: List[HighlightRule] = []
    for rule_id, cls in (
        ("fork", ForkRule),
        ("skewer", SkewerRule),
        ("pin", PinRule),
        ("discovered_attack", DiscoveredAttackRule),
    ):
        rule_cfg = cfg.get(rule_id, {})
        if not isinstance(rule_cfg, dict):
            rule_cfg = {}
        rule = cls(rule_cfg)
        if rule.is_enabled():
            loaded.append(rule)
    return loaded


def _same_board_position(left: chess.Board, right: chess.Board) -> bool:
    """Piece placement, side to move, and castling — not EP, which FEN may omit."""
    return (
        left.board_fen() == right.board_fen()
        and left.turn == right.turn
        and left.castling_rights == right.castling_rights
    )


def _parse_board(fen: str) -> Optional[chess.Board]:
    if not fen:
        return None
    try:
        return chess.Board(fen)
    except ValueError:
        return None


def _parse_move(board: chess.Board, san: str) -> Optional[chess.Move]:
    if not san:
        return None
    try:
        return board.parse_san(san)
    except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError, chess.InvalidMoveError):
        return None


def fen_before_for_ply(
    moves: List[MoveData], index: int, is_white: bool
) -> Optional[str]:
    """FEN of the position the mover faced, or None if it cannot be recovered.

    White uses the previous row's ``fen_black``. Index-0 White only uses the
    standard starting position when pushing the played SAN from
    ``chess.STARTING_FEN`` matches ``fen_white``. Black uses this row's
    ``fen_white``.
    """
    if index < 0 or index >= len(moves):
        return None
    move = moves[index]
    if is_white:
        if index > 0:
            fen = str(getattr(moves[index - 1], "fen_black", "") or "").strip()
            return fen or None
        played = str(move.white_move or "").strip()
        after_fen = str(move.fen_white or "").strip()
        if not played or not after_fen:
            return None
        start = chess.Board()
        played_move = _parse_move(start, played)
        after = _parse_board(after_fen)
        if played_move is None or after is None:
            return None
        start.push(played_move)
        if not _same_board_position(start, after):
            return None
        return chess.STARTING_FEN
    fen = str(move.fen_white or "").strip()
    return fen or None


def mover_already_lost(eval_before: Optional[float], is_white: bool) -> bool:
    """True when the mover is already lost by ``ALREADY_LOST_CP`` (desperation)."""
    if eval_before is None:
        return False
    if is_white:
        return eval_before <= -ALREADY_LOST_CP
    return eval_before >= ALREADY_LOST_CP


def _synthetic_pv1_move(
    original: MoveData,
    *,
    is_white: bool,
    pv1: str,
    fen_after: str,
    capture: str,
) -> MoveData:
    """Copy of this row with PV1 as the played move so tactic rules can score it."""
    synth = copy.copy(original)
    if is_white:
        synth.white_move = pv1
        synth.black_move = ""
        synth.cpl_white = "0"
        synth.assess_white = "Best Move"
        synth.fen_white = fen_after
        synth.white_capture = capture
        synth.white_is_top3 = True
    else:
        synth.black_move = pv1
        synth.white_move = ""
        synth.cpl_black = "0"
        synth.assess_black = "Best Move"
        synth.fen_black = fen_after
        synth.black_capture = capture
        synth.black_is_top3 = True
    return synth


def detect_pv1_tactic(
    moves: List[MoveData],
    index: int,
    *,
    is_white: bool,
    synth: MoveData,
    fen_before: str,
    tactic_rules: Sequence[HighlightRule],
    opening_end: int,
    middlegame_end: int,
    good_move_max_cpl: int,
    inaccuracy_max_cpl: int,
    mistake_max_cpl: int,
) -> str:
    """Allowlisted tactic ``rule_type`` for PV1 on this side, or empty if none fires."""
    if not tactic_rules:
        return ""
    synth_moves = list(moves)
    synth_moves[index] = synth
    overrides = dict(
        opening_end=opening_end,
        middlegame_end=middlegame_end,
        good_move_max_cpl=good_move_max_cpl,
        inaccuracy_max_cpl=inaccuracy_max_cpl,
        mistake_max_cpl=mistake_max_cpl,
    )
    if is_white:
        prev = synth_moves[index - 1] if index > 0 else None
        if prev is None or not str(getattr(prev, "fen_black", "") or "").strip():
            dummy = copy.copy(prev) if prev is not None else MoveData(move_number=0)
            dummy.fen_black = fen_before
            overrides["prev_move"] = dummy
    context = make_rule_context(synth_moves, index, **overrides)
    for rule in tactic_rules:
        try:
            highlights = rule.evaluate(synth, context)
        except Exception:
            continue
        for highlight in highlights:
            if highlight.is_white == is_white:
                return str(highlight.rule_type or "")
    return ""


def _classify_miss(
    *,
    board_before: chess.Board,
    pv_move: chess.Move,
    pv1_san: str,
    tactic_type: str,
) -> Optional[Tuple[str, int]]:
    """Kind + sort rank, or None if PV1 is not a tactic / mate / capture / check."""
    after = board_before.copy()
    after.push(pv_move)
    is_mate = after.is_checkmate() or "#" in pv1_san
    is_capture = board_before.is_capture(pv_move) or "x" in pv1_san
    is_check = (not is_mate) and (after.is_check() or "+" in pv1_san)
    if is_mate:
        return "mate", KIND_RANK_MATE
    if tactic_type:
        return tactic_type, KIND_RANK_TACTIC
    if is_capture:
        return "capture", KIND_RANK_CAPTURE
    if is_check:
        return "check", KIND_RANK_CHECK
    return None


def select_top_missed_tactics(
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
) -> List[RankedMissedTactic]:
    """Return up to ``count`` missed tactics in display order."""
    if is_white:
        cpl_field = "cpl_white"
        assess_field = "assess_white"
        eval_field = "eval_white"
        move_field = "white_move"
        best_field = "best_white"
    else:
        cpl_field = "cpl_black"
        assess_field = "assess_black"
        eval_field = "eval_black"
        move_field = "black_move"
        best_field = "best_black"

    ranked: List[Tuple[int, float, float, int, RankedMissedTactic]] = []
    for index, move in enumerate(moves):
        played = str(getattr(move, move_field, "") or "").strip()
        if not played:
            continue
        assessment = str(getattr(move, assess_field, "") or "").strip()
        if assessment == "Book Move" or assessment not in ERROR_ASSESSMENTS:
            continue
        pv1 = str(getattr(move, best_field, "") or "").strip()
        if not pv1:
            continue
        cpl_str = getattr(move, cpl_field)
        if not cpl_str:
            continue
        try:
            cpl = float(cpl_str)
        except (ValueError, TypeError):
            continue

        fen_before = fen_before_for_ply(moves, index, is_white)
        if not fen_before:
            continue
        eval_before = eval_before_cp(moves, index, is_white, parse_eval)
        if mover_already_lost(eval_before, is_white):
            continue

        board_before = _parse_board(fen_before)
        if board_before is None:
            continue
        pv_move = _parse_move(board_before, pv1)
        if pv_move is None:
            continue
        played_move = _parse_move(board_before, played)
        if played_move is not None and played_move == pv_move:
            continue

        after = board_before.copy()
        after.push(pv_move)
        capture = get_captured_piece_letter(board_before, pv_move)
        synth = _synthetic_pv1_move(
            move,
            is_white=is_white,
            pv1=pv1,
            fen_after=after.fen(),
            capture=capture,
        )
        tactic_type = detect_pv1_tactic(
            moves,
            index,
            is_white=is_white,
            synth=synth,
            fen_before=fen_before,
            tactic_rules=tactic_rules,
            opening_end=opening_end,
            middlegame_end=middlegame_end,
            good_move_max_cpl=good_move_max_cpl,
            inaccuracy_max_cpl=inaccuracy_max_cpl,
            mistake_max_cpl=mistake_max_cpl,
        )
        classified = _classify_miss(
            board_before=board_before,
            pv_move=pv_move,
            pv1_san=pv1,
            tactic_type=tactic_type,
        )
        if classified is None:
            continue
        kind, kind_rank = classified
        gain = display_eval_gain_cp(moves, index, is_white, parse_eval)
        eval_drop = max(0.0, -gain)
        notation = f"{move.move_number}. {played}"
        ranked.append(
            (
                kind_rank,
                -cpl,
                -eval_drop,
                index,
                RankedMissedTactic(
                    move_number=move.move_number,
                    move_notation=notation,
                    cpl=cpl,
                    assessment=assessment,
                    evaluation=getattr(move, eval_field) or "",
                    best_move=pv1,
                    tactic_type=kind,
                    selection_reason=format_missed_tactic_selection_reason(
                        played=played,
                        pv1=pv1,
                        assessment=assessment,
                        cpl=cpl,
                        kind=kind,
                    ),
                    eval_drop=eval_drop,
                ),
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [item[4] for item in ranked[: max(0, int(count))]]
