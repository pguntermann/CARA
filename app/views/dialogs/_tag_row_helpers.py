"""Shared helpers for computing move info from a chess.pgn.Game.

Used by ShowTagsDialog and the Tags Report panel so neither pulls in the other.
"""

from __future__ import annotations

from typing import Optional, Tuple

import chess
import chess.pgn

from app.utils.pgn_variation_path import decode_path, node_at_path


def game_header_text(game) -> str:
    """Return the canonical game-group header string used in exports and dialogs.

    Format: ``White - Black result (date - N moves)``
    Falls back to "Unknown" / "*" / "????.??.??" for missing fields.
    """
    white = str(getattr(game, "white", "") or "").strip() or "Unknown"
    black = str(getattr(game, "black", "") or "").strip() or "Unknown"
    result = str(getattr(game, "result", "") or "").strip() or "*"
    date = str(getattr(game, "date", "") or "").strip() or "????.??.??"
    try:
        moves = int(getattr(game, "moves", 0) or 0)
    except (TypeError, ValueError):
        moves = 0
    return f"{white} - {black} {result} ({date} - {moves} moves)"


def ply_for_path(pgn_game: Optional[chess.pgn.Game], path) -> int:
    """Return the ply index for *path* within *pgn_game* (0-based from root)."""
    if pgn_game is None:
        return len(path)
    node = node_at_path(pgn_game, path)
    if node is None:
        return len(path)
    try:
        return node.ply()
    except AttributeError:
        pass
    parent = getattr(node, "parent", None)
    if parent is None:
        return len(path)
    pre = parent.board()
    return (pre.fullmove_number - 1) * 2 + (0 if pre.turn == chess.WHITE else 1)


def node_info(
    pgn_game: Optional[chess.pgn.Game],
    path_key: str,
) -> Tuple[str, Optional[chess.Move], str, bool]:
    """Return (fen_after_move, played_move, move_label, mover_is_black) for display.

    mover_is_black is True when the move at this ply was played by Black.
    Returns ("", None, path_key, False) when the node cannot be located.
    """
    if pgn_game is None:
        return ("", None, path_key, False)
    path = decode_path(path_key)
    if not path:
        return ("", None, path_key, False)
    node = node_at_path(pgn_game, path)
    if node is None or node.move is None:
        return ("", None, path_key, False)
    try:
        pre_board = node.parent.board()
        san = pre_board.san(node.move)
        fullmove = pre_board.fullmove_number
        if pre_board.turn == chess.WHITE:
            move_label = f"{fullmove}. {san}"
        else:
            move_label = f"{fullmove}… {san}"
        fen = node.board().fen()
        mover_is_black = pre_board.turn == chess.BLACK
        return (fen, node.move, move_label, mover_is_black)
    except Exception:
        return ("", None, path_key, False)


def chess_log_miniboard_settings() -> Tuple[float, bool, bool]:
    """Return ``(scale, show_played, show_best)`` for Chess Log mini boards.

    Read through the settings owner's accessors; the owner's ``normalize_*``
    functions supply every default, so this module holds no fallback values of
    its own.  Falls back to the owner's defaults when settings are unavailable.
    """
    from app.utils.miniature_board_arrows import (
        CHESS_LOG_BEST_ALTERNATIVE,
        CHESS_LOG_PLAYED,
        normalize_miniature_board_arrows,
    )
    from app.utils.miniature_board_scales import (
        CHESS_LOG,
        normalize_miniature_board_scales,
    )

    try:
        from app.services.user_settings_service import UserSettingsService

        uss = UserSettingsService.get_instance()
        raw_scales = uss.get_miniature_boards()
        raw_arrows = uss.get_miniature_board_arrows()
    except Exception:
        raw_scales = None
        raw_arrows = None
    scales = normalize_miniature_board_scales(raw_scales)
    arrows = normalize_miniature_board_arrows(raw_arrows)
    return (
        float(scales[CHESS_LOG]),
        bool(arrows[CHESS_LOG_PLAYED]),
        bool(arrows[CHESS_LOG_BEST_ALTERNATIVE]),
    )
