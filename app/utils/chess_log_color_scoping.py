"""Derive the color that just moved from a Chess Log path key, and scope a
player's moments to their own moves.

Path keys are dotted child-index sequences (e.g. "0", "0.0", "0.1.0").
Their length equals the ply count from the root — odd means White just moved,
even (and > 0) means Black just moved.

``own_moves_paths`` is the one own-moves filter for every player-scoped
Chess Log view (charts, Narrative Summary, report header counts, the report's
Check Logs section, and the Player list).  No view keeps its own copy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.pgn_variation_path import decode_path


def color_from_path_key(path_key: str) -> Optional[str]:
    """Return ``"white"``, ``"black"``, or ``None`` (root / invalid path)."""
    path = decode_path(path_key)
    if path is None or len(path) == 0:
        return None
    return "white" if len(path) % 2 == 1 else "black"


def player_color_in_game(game: Any, player_cf: str) -> Optional[str]:
    """Return the color *player_cf* (casefolded, stripped) played in *game*.

    ``None`` when no player is given, the player is not in the game, or the
    player is on both sides (nothing to tell apart, so nothing is filtered).
    """
    if not player_cf:
        return None
    is_white = (getattr(game, "white", "") or "").casefold().strip() == player_cf
    is_black = (getattr(game, "black", "") or "").casefold().strip() == player_cf
    if is_white and not is_black:
        return "white"
    if is_black and not is_white:
        return "black"
    return None


def own_moves_paths(
    game: Any,
    paths_data: Dict[str, List[Dict[str, Any]]],
    player_cf: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return the subset of *paths_data* logged on *player_cf*'s own moves in *game*.

    With no player (``""``), or a player on both sides, everything is kept; a
    player who is not in the game has no own moves.  Otherwise a path key is
    kept when its color is the player's (or unknown, e.g. the root).
    """
    if not paths_data:
        return {}
    if not player_cf:
        return dict(paths_data)
    player_color = player_color_in_game(game, player_cf)
    if player_color is None:
        white_cf = (getattr(game, "white", "") or "").casefold().strip()
        return dict(paths_data) if white_cf == player_cf else {}
    return {
        pk: entries
        for pk, entries in paths_data.items()
        if color_from_path_key(pk) in (None, player_color)
    }
