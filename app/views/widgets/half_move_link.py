"""Build a linked-move popup tip from move-list data and a notation string."""

from __future__ import annotations

import html
import re
from typing import Mapping, Optional, Sequence, Tuple

import chess

from app.models.moveslist_model import MoveData
from app.services.game_summary_service import format_half_move_notation, format_half_move_tip
from app.views.widgets.move_link_popup import MoveLinkTip, uci_from_san

_NOTATION_PREFIX = re.compile(r"^(\d+\.{1,3})(\S.*)$")


def resolve_linked_ply(notation: str, *maps: Mapping[str, int]) -> Optional[int]:
    """Ply index for a notes or AI-chat move link, using the same keys as navigation."""
    text = html.unescape(str(notation or "")).strip().rstrip(".,;:!?)")
    if not text:
        return None
    candidates = [text]
    if " " in text:
        candidates.append(text.replace(" ", "", 1))
    else:
        match = _NOTATION_PREFIX.match(text)
        if match is not None:
            candidates.append(f"{match.group(1)} {match.group(2)}")
    for candidate in candidates:
        for mapping in maps:
            ply = mapping.get(candidate)
            if ply is not None:
                return int(ply)
    return None


def board_is_flipped(game_controller) -> bool:
    """Whether the main board is flipped, for miniature boards in move popups."""
    if game_controller is None:
        return False
    board_controller = getattr(game_controller, "board_controller", None)
    if board_controller is None:
        return False
    model = board_controller.get_board_model()
    return bool(getattr(model, "is_flipped", False))


def half_move_from_ply(ply: int) -> Tuple[int, bool]:
    """``(move_number, is_white)`` for a 1-based mainline ply."""
    ply = int(ply)
    return (ply + 1) // 2, ply % 2 == 1


def move_data_for_number(moves: Sequence[MoveData], move_number: int) -> Optional[MoveData]:
    for move in moves:
        if int(getattr(move, "move_number", -1)) == int(move_number):
            return move
    return None


def fen_before_half_move(moves: Sequence[MoveData], move_number: int, is_white: bool) -> str:
    """FEN of the position the half-move was played from."""
    md = move_data_for_number(moves, move_number)
    if md is None:
        return ""
    if is_white:
        if move_number <= 1:
            return chess.STARTING_FEN
        prev = move_data_for_number(moves, move_number - 1)
        return ((prev.fen_black if prev else "") or "").strip() or chess.STARTING_FEN
    return (md.fen_white or "").strip()


def fen_and_played_uci(moves: Sequence[MoveData], move_number: int, is_white: bool) -> Tuple[str, str]:
    """FEN after the half-move, and UCI of the move that was played."""
    md = move_data_for_number(moves, move_number)
    if md is None:
        return "", ""
    fen_before = fen_before_half_move(moves, move_number, is_white)
    if is_white:
        fen_after = (md.fen_white or "").strip()
        san = (md.white_move or "").strip()
    else:
        fen_after = (md.fen_black or "").strip()
        san = (md.black_move or "").strip()
    uci = uci_from_san(fen_before, san) if fen_before and san else ""
    return fen_after, uci


def build_half_move_link_tip(
    moves: Sequence[MoveData],
    move_number: int,
    is_white: bool,
    *,
    description: str = "",
) -> MoveLinkTip:
    """Popup content for one half-move in the moves list."""
    fen, uci = fen_and_played_uci(moves, move_number, is_white)
    san = ""
    assessment = ""
    cpl = ""
    best = ""
    md = move_data_for_number(moves, move_number)
    if md is not None:
        if is_white:
            san = md.white_move or ""
            assessment = md.assess_white or ""
            cpl = md.cpl_white or ""
            best = md.best_white or ""
        else:
            san = md.black_move or ""
            assessment = md.assess_black or ""
            cpl = md.cpl_black or ""
            best = md.best_black or ""
    title = format_half_move_notation(move_number, is_white, san) or f"Move {int(move_number)}"
    subtitle, details = format_half_move_tip(
        assessment=assessment,
        cpl=cpl,
        best_move=best,
        description=description,
    )
    return MoveLinkTip(
        title=title,
        subtitle=subtitle,
        details=details,
        fen=fen,
        arrow_uci=uci,
        alternative_uci=uci_from_san(fen_before_half_move(moves, move_number, is_white), best),
    )
