"""Helpers for PGN variation paths (child-index sequences from the game root)."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import chess
import chess.pgn

Path = Tuple[int, ...]


def encode_path(path: Sequence[int]) -> str:
    """Encode a path as ``0.1.0`` (empty path → empty string)."""
    return ".".join(str(int(i)) for i in path)


def decode_path(text: str) -> Optional[Path]:
    """Decode ``0.1.0`` to a path tuple; empty/whitespace → ``()``."""
    raw = (text or "").strip()
    if not raw:
        return ()
    parts: List[int] = []
    for piece in raw.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            return None
        if parts[-1] < 0:
            return None
    return tuple(parts)


def is_mainline_path(path: Sequence[int]) -> bool:
    return all(int(i) == 0 for i in path)


def consumer_ply_for_path(path: Sequence[int]) -> int:
    """Ply index for mainline-only consumers (e.g. moves list).

    On the mainline this is ``len(path)``. Off the mainline it freezes at the
    longest all-zero prefix so side-line browsing does not drag those views.
    """
    if is_mainline_path(path):
        return len(path)
    ply = 0
    for idx in path:
        if int(idx) != 0:
            break
        ply += 1
    return ply


def node_at_path(game: chess.pgn.Game, path: Sequence[int]) -> Optional[chess.pgn.GameNode]:
    """Return the game node at ``path``, or None if the path is invalid."""
    node: chess.pgn.GameNode = game
    for idx in path:
        i = int(idx)
        if i < 0 or i >= len(node.variations):
            return None
        node = node.variation(i)
    return node


def path_after_move(path: Sequence[int], child_index: int) -> Path:
    return tuple(path) + (int(child_index),)


def parent_path(path: Sequence[int]) -> Path:
    if not path:
        return ()
    return tuple(path[:-1])


def strip_san_suffixes(san: str) -> str:
    """Drop annotation glyphs so formatter SANs can match tree SANs."""
    text = (san or "").strip()
    while text and text[-1] in "!?":
        text = text[:-1]
    return text


def forward_choices(
    game: chess.pgn.Game, path: Sequence[int]
) -> List[Tuple[Path, str]]:
    """Return ``(child_path, san)`` options from the node at ``path``."""
    node = node_at_path(game, path)
    if node is None or not node.variations:
        return []
    board = node.board()
    choices: List[Tuple[Path, str]] = []
    for i, child in enumerate(node.variations):
        san = board.san(child.move)
        choices.append((path_after_move(path, i), san))
    return choices


def collect_variation_move_paths(game: chess.pgn.Game) -> List[Tuple[Path, str]]:
    """Sideline moves in PGN export order (same order as python-chess visitors).

    Used to attach ``cara-path`` anchors while formatting variation SANs.
    """
    out: List[Tuple[Path, str]] = []

    def continue_after_variation_move(node: chess.pgn.GameNode, path: Path) -> None:
        if not node.variations:
            return
        board = node.board()
        main = node.variation(0)
        main_path = path_after_move(path, 0)
        out.append((main_path, strip_san_suffixes(board.san(main.move))))
        for i in range(1, len(node.variations)):
            sib = node.variation(i)
            sib_path = path_after_move(path, i)
            out.append((sib_path, strip_san_suffixes(board.san(sib.move))))
            continue_after_variation_move(sib, sib_path)
        continue_after_variation_move(main, main_path)

    def continue_mainline(node: chess.pgn.GameNode, path: Path) -> None:
        if not node.variations:
            return
        board = node.board()
        main = node.variation(0)
        main_path = path_after_move(path, 0)
        for i in range(1, len(node.variations)):
            sib = node.variation(i)
            sib_path = path_after_move(path, i)
            out.append((sib_path, strip_san_suffixes(board.san(sib.move))))
            continue_after_variation_move(sib, sib_path)
        continue_mainline(main, main_path)

    continue_mainline(game, ())
    return out


def mainline_path_for_ply(ply: int) -> Path:
    """Mainline path of length ``ply`` (all child indices 0)."""
    if ply <= 0:
        return ()
    return tuple(0 for _ in range(int(ply)))


def mainline_rejoin_path(path: Sequence[int]) -> Optional[Path]:
    """Mainline path one ply past the divergence point of a sideline.

    For ``(0, 1, 0)`` (branched after ply 1) this is ``(0, 0)``. Returns
    ``None`` when ``path`` is already on the mainline.
    """
    if is_mainline_path(path):
        return None
    return mainline_path_for_ply(consumer_ply_for_path(path) + 1)
