"""Helper to resolve the engine best move for a Chess Log tagged position."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Optional

import chess
import chess.pgn

from app.utils.pgn_variation_path import decode_path, is_mainline_path, node_at_path

if TYPE_CHECKING:
    from app.models.database_model import GameData


def resolve_best_move_for_path(
    game: "GameData",
    path_key: str,
    played_move: Optional[chess.Move],
    pgn_game: Optional[chess.pgn.Game] = None,
) -> Optional[chess.Move]:
    """Return the engine's best move for the position preceding the tagged move.

    Returns None when:
    - the game has no analysis data,
    - path_key is not a mainline path,
    - the best-move slot in the analysis data is empty,
    - the best move is identical to played_move,
    - SAN parsing fails for any reason.

    Args:
        game: GameData with PGN and CARAAnalysisData payload.
        path_key: encoded variation path for the tagged node.
        played_move: the move the player actually made (for equality check).
        pgn_game: already-parsed chess.pgn.Game (avoids re-parsing if caller has it).
    """
    from app.services.analysis_data_storage_service import AnalysisDataStorageService

    if game is None:
        return None

    path = decode_path(path_key)
    if path is None or not path:
        return None
    if not is_mainline_path(path):
        return None

    if not AnalysisDataStorageService.has_analysis_data(game):
        return None

    analysis = AnalysisDataStorageService.load_analysis_data(game)
    if not analysis:
        return None

    ply = len(path)
    row = (ply - 1) // 2
    if row >= len(analysis):
        return None

    move_data = analysis[row]
    is_white_move = (ply - 1) % 2 == 0
    best_san: str = move_data.best_white if is_white_move else move_data.best_black
    if not best_san:
        return None

    try:
        if pgn_game is None:
            pgn_str = getattr(game, "pgn", None)
            if not pgn_str:
                return None
            pgn_game = chess.pgn.read_game(StringIO(pgn_str))
            if pgn_game is None:
                return None

        parent_path = path[:-1]
        parent_node = node_at_path(pgn_game, parent_path)
        if parent_node is None:
            return None
        board = parent_node.board()
        best_move = board.parse_san(best_san)
    except Exception:
        return None

    if best_move == played_move:
        return None

    return best_move
