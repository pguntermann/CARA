"""Helpers for game highlight rule unit tests.

Build a moves list from PGN (FENs, captures, piece counts, material) and
optionally overlay fake engine/analysis fields that rules consume.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import chess

from app.models.moveslist_model import MoveData
from app.services.game_highlights.base_rule import GameHighlight, HighlightRule
from app.services.game_highlights.half_move import make_rule_context
from app.utils.material_tracker import (
    calculate_material_count,
    count_pieces,
    get_captured_piece_letter,
)

# analysis[move_number]["white"|"black"] -> field overrides for that half-move
AnalysisMap = Dict[int, Dict[str, Dict[str, Any]]]

_DEFAULT_ANALYSIS = {
    "cpl": "0",
    "assess": "Best Move",
}


def _tokenize_pgn(pgn: str) -> List[str]:
    """Extract SAN tokens from a PGN fragment or move list."""
    text = pgn.strip()
    text = re.sub(r"\{[^}]*\}", " ", text)
    text = re.sub(r";[^\n]*", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    for result in ("1-0", "0-1", "1/2-1/2", "*"):
        text = text.replace(result, " ")
    text = re.sub(r"\d+\.(\.\.)?", " ", text)
    return [t for t in text.split() if t]


def _apply_side_analysis(move: MoveData, side: str, fields: Dict[str, Any]) -> None:
    """Map short analysis keys onto MoveData white_/black_ fields."""
    prefix = "white" if side == "white" else "black"
    mapping = {
        "cpl": f"cpl_{prefix}",
        "cpl_2": f"cpl_{prefix}_2",
        "cpl_3": f"cpl_{prefix}_3",
        "assess": f"assess_{prefix}",
        "eval": f"eval_{prefix}",
        "best": f"best_{prefix}",
        "best_2": f"best_{prefix}_2",
        "best_3": f"best_{prefix}_3",
        "is_top3": f"{prefix}_is_top3",
        "depth": f"{prefix}_depth",
        "seldepth": f"{prefix}_seldepth",
    }
    for key, value in fields.items():
        attr = mapping.get(key, key)
        if hasattr(move, attr):
            setattr(move, attr, value)


def _fill_board_stats(move: MoveData, board: chess.Board) -> None:
    """Write material / piece counts for both sides onto MoveData."""
    counts = count_pieces(board, is_white=True)
    move.white_queens = counts[chess.QUEEN]
    move.white_rooks = counts[chess.ROOK]
    move.white_bishops = counts[chess.BISHOP]
    move.white_knights = counts[chess.KNIGHT]
    move.white_pawns = counts[chess.PAWN]
    move.white_material = calculate_material_count(board, is_white=True)

    counts = count_pieces(board, is_white=False)
    move.black_queens = counts[chess.QUEEN]
    move.black_rooks = counts[chess.ROOK]
    move.black_bishops = counts[chess.BISHOP]
    move.black_knights = counts[chess.KNIGHT]
    move.black_pawns = counts[chess.PAWN]
    move.black_material = calculate_material_count(board, is_white=False)


def moves_from_pgn(
    pgn: str,
    *,
    starting_fen: Optional[str] = None,
    analysis: Optional[AnalysisMap] = None,
) -> List[MoveData]:
    """Build a MoveData list from PGN / SAN text.

    Always fills board-derived fields: ``fen_*``, ``*_capture``, piece counts,
    and material. Analysis fields default to a clean good move (``cpl="0"``,
    ``assess="Best Move"``) so quality-gated rules work without boilerplate.

    Override per half-move via ``analysis``::

        analysis = {
            21: {
                "white": {"cpl": "0", "assess": "Best Move", "eval": "+3.7", "best": "Nxc7+"},
                "black": {"cpl": "251", "assess": "Blunder", "eval": "+1.2"},
            }
        }

    Short keys (``cpl``, ``assess``, ``eval``, ``best``, ``best_2``, ``best_3``,
    ``cpl_2``, ``cpl_3``, ``is_top3``, ``depth``) map onto the matching
    ``MoveData`` attributes. Full attribute names are also accepted.
    """
    analysis = analysis or {}
    board = chess.Board(starting_fen) if starting_fen else chess.Board()
    sans = _tokenize_pgn(pgn)
    moves: List[MoveData] = []
    i = 0
    move_number = board.fullmove_number

    while i < len(sans):
        md = MoveData(move_number=move_number)

        if board.turn == chess.WHITE:
            wsan = sans[i]
            i += 1
            wmove = board.parse_san(wsan)
            wcap = get_captured_piece_letter(board, wmove)
            board.push(wmove)
            md.white_move = wsan
            md.white_capture = wcap
            md.fen_white = board.fen()
            md.cpl_white = _DEFAULT_ANALYSIS["cpl"]
            md.assess_white = _DEFAULT_ANALYSIS["assess"]
            _fill_board_stats(md, board)
        else:
            # Black to move at the start of this full-move row (e.g. mid-game FEN).
            # ``fen_white`` is the before-board for Black's half-move.
            md.fen_white = board.fen()
            _fill_board_stats(md, board)

        if i < len(sans) and board.turn == chess.BLACK:
            bsan = sans[i]
            i += 1
            bmove = board.parse_san(bsan)
            bcap = get_captured_piece_letter(board, bmove)
            board.push(bmove)
            md.black_move = bsan
            md.black_capture = bcap
            md.fen_black = board.fen()
            md.cpl_black = _DEFAULT_ANALYSIS["cpl"]
            md.assess_black = _DEFAULT_ANALYSIS["assess"]
            _fill_board_stats(md, board)

        side_analysis = analysis.get(move_number, {})
        if md.white_move and "white" in side_analysis:
            _apply_side_analysis(md, "white", side_analysis["white"])
        if md.black_move and "black" in side_analysis:
            _apply_side_analysis(md, "black", side_analysis["black"])

        moves.append(md)
        move_number += 1

    return moves


def evaluate_rule(
    rule: HighlightRule,
    moves: List[MoveData],
    move_number: int,
    **context_overrides: Any,
) -> List[GameHighlight]:
    """Evaluate ``rule`` on the row with the given move number."""
    move_index = next(
        (i for i, m in enumerate(moves) if m.move_number == move_number),
        None,
    )
    if move_index is None:
        raise ValueError(f"move_number {move_number} not found in moves list")
    context = make_rule_context(moves, move_index, **context_overrides)
    return rule.evaluate(moves[move_index], context)


def evaluate_rule_sequence(
    rule: HighlightRule,
    moves: List[MoveData],
    **context_overrides: Any,
) -> List[GameHighlight]:
    """Evaluate ``rule`` on every row, reusing one ``shared_state`` dict.

    Needed for rules that accumulate streaks across moves (e.g. delayed mating).
    """
    shared_state = context_overrides.pop("shared_state", {})
    highlights: List[GameHighlight] = []
    for move_index, move in enumerate(moves):
        context = make_rule_context(
            moves, move_index, shared_state=shared_state, **context_overrides
        )
        highlights.extend(rule.evaluate(move, context))
    return highlights


def find_highlights(
    highlights: List[GameHighlight],
    move_number: int,
    rule_type: str,
    side: Optional[str] = None,
) -> List[GameHighlight]:
    """Filter highlights by move number, rule type, and optional side."""
    matching = []
    for h in highlights:
        if h.move_number != move_number or h.rule_type != rule_type:
            continue
        if side is None:
            matching.append(h)
        elif side == "white" and h.is_white:
            matching.append(h)
        elif side == "black" and not h.is_white:
            matching.append(h)
    return matching
