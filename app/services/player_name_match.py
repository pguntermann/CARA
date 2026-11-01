"""Match a PGN player name exactly, or with a case-insensitive regular expression."""

from __future__ import annotations

import re
from typing import Dict, Optional

_compiled: Dict[str, Optional[re.Pattern]] = {}


def compiled_player_regex(pattern: str) -> Optional[re.Pattern]:
    """Compile a player-name pattern once. ``None`` when it is not valid."""
    if pattern in _compiled:
        return _compiled[pattern]
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error:
        compiled = None
    _compiled[pattern] = compiled
    return compiled


def player_name_matches(name: Optional[str], selector: str, *, name_is_regex: bool) -> bool:
    """Whether ``name`` is the selected player.

    Exact mode keeps whitespace, matching the existing player list. Regex mode
    searches anywhere in the name and ignores case.
    """
    text = name or ""
    if not text or not str(selector or "").strip():
        return False
    if not name_is_regex:
        return text == selector
    compiled = compiled_player_regex(selector)
    if compiled is None:
        return False
    return compiled.search(text) is not None


def game_includes_player(
    white: Optional[str],
    black: Optional[str],
    selector: str,
    *,
    name_is_regex: bool,
) -> bool:
    """True when White or Black is the selected player."""
    return player_name_matches(white, selector, name_is_regex=name_is_regex) or player_name_matches(
        black, selector, name_is_regex=name_is_regex
    )


def player_is_white(
    white: Optional[str],
    black: Optional[str],
    selector: str,
    *,
    name_is_regex: bool,
) -> bool:
    """True when the selected player is White.

    If a pattern matches both names, White is used so the game is counted once.
    """
    return player_name_matches(white, selector, name_is_regex=name_is_regex)
