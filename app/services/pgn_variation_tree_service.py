"""Variation-tree edits on a parsed PGN game (insert and remove sidelines)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import chess
import chess.pgn

from app.utils.pgn_variation_path import Path, node_at_path, sideline_fork


class VariationTreeError(ValueError):
    """Raised when a variation-tree edit cannot be applied."""


@dataclass(frozen=True)
class VariationInsertResult:
    """Outcome of merging a move prefix into the tree."""

    end_path: Path
    added: int
    followed: int


@dataclass(frozen=True)
class VariationRemoveResult:
    """Outcome of deleting the sideline that contains a path."""

    fork_path: Path
    removed_index: int


def parse_pv_token(board: chess.Board, token: str) -> Optional[chess.Move]:
    """Parse a PV token as SAN, then UCI. ``None`` if illegal in ``board``."""
    raw = (token or "").strip()
    if not raw:
        return None
    try:
        move = board.parse_san(raw)
        if move in board.legal_moves:
            return move
    except ValueError:
        pass
    try:
        move = chess.Move.from_uci(raw)
        if move in board.legal_moves:
            return move
    except ValueError:
        pass
    return None


def same_placement_and_turn(fen_a: str, fen_b: str) -> bool:
    """True when two FENs share placement and side to move (ignore clocks/EP)."""
    try:
        a = chess.Board(fen_a)
        b = chess.Board(fen_b)
    except ValueError:
        return False
    return a.board_fen() == b.board_fen() and a.turn == b.turn


def child_index_for_move(node: chess.pgn.GameNode, move: chess.Move) -> Optional[int]:
    """Return the variation index of ``move``, or ``None`` if it is not a child."""
    for i, child in enumerate(node.variations):
        if child.move == move:
            return i
    return None


def insert_san_prefix(
    chess_game: chess.pgn.Game,
    start_path: Sequence[int],
    tokens: Sequence[str],
) -> VariationInsertResult:
    """Follow existing children, then append remaining tokens as a new branch.

    The first unmatched move becomes a new variation at that node (or the
    mainline continuation when the node has no children). Never overwrites
    an existing child.
    """
    node = node_at_path(chess_game, start_path)
    if node is None:
        raise VariationTreeError("Current position is not in the game.")
    sans = [str(t).strip() for t in tokens if str(t).strip()]
    if not sans:
        raise VariationTreeError("No moves to add.")

    path: Path = tuple(int(i) for i in start_path)
    added = 0
    followed = 0
    board = node.board()
    for token in sans:
        move = parse_pv_token(board, token)
        if move is None:
            raise VariationTreeError(
                f"Could not play {token!r} from this position."
            )
        existing = child_index_for_move(node, move)
        if existing is not None:
            node = node.variation(existing)
            path = path + (existing,)
            followed += 1
        else:
            idx = len(node.variations)
            node = node.add_variation(move)
            path = path + (idx,)
            added += 1
        board.push(move)
    return VariationInsertResult(end_path=path, added=added, followed=followed)


def remove_variation_at_path(
    chess_game: chess.pgn.Game,
    path: Sequence[int],
) -> VariationRemoveResult:
    """Delete the innermost sideline that contains ``path``.

    The whole parenthetical is removed from its fork, including later moves
    and nested variations of that branch. Mainline paths are rejected.
    """
    fork = sideline_fork(path)
    if fork is None:
        raise VariationTreeError("That move is not in a variation.")
    parent_path, child_index = fork
    parent = node_at_path(chess_game, parent_path)
    if parent is None or child_index >= len(parent.variations):
        raise VariationTreeError("Current position is not in the game.")
    parent.remove_variation(child_index)
    return VariationRemoveResult(fork_path=parent_path, removed_index=child_index)
