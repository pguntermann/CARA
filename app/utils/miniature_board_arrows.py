"""Per-surface miniature-board arrow visibility (user settings)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

OPENING_EXPLORER = "opening_explorer"
GAME_SUMMARY_PLAYED = "game_summary_played"
GAME_SUMMARY_BEST_ALTERNATIVE = "game_summary_best_alternative"
MOVE_LINK_PLAYED = "move_link_played"
MOVE_LINK_BEST_ALTERNATIVE = "move_link_best_alternative"

# Legacy single toggle from earlier builds
_LEGACY_GAME_SUMMARY = "game_summary_highlights"

_DEFAULTS: Dict[str, bool] = {
    OPENING_EXPLORER: True,
    GAME_SUMMARY_PLAYED: True,
    GAME_SUMMARY_BEST_ALTERNATIVE: True,
    MOVE_LINK_PLAYED: True,
    MOVE_LINK_BEST_ALTERNATIVE: True,
}


def default_miniature_board_arrows() -> Dict[str, bool]:
    return dict(_DEFAULTS)


def normalize_miniature_board_arrows(
    raw: Optional[Mapping[str, Any]] = None,
) -> Dict[str, bool]:
    out = default_miniature_board_arrows()
    if not isinstance(raw, Mapping):
        return out
    # Older builds used one Game Summary flag for both arrow types.
    if _LEGACY_GAME_SUMMARY in raw and (
        GAME_SUMMARY_PLAYED not in raw or GAME_SUMMARY_BEST_ALTERNATIVE not in raw
    ):
        legacy = bool(raw.get(_LEGACY_GAME_SUMMARY))
        out[GAME_SUMMARY_PLAYED] = legacy
        out[GAME_SUMMARY_BEST_ALTERNATIVE] = legacy
    for key in _DEFAULTS:
        if key in raw:
            out[key] = bool(raw.get(key))
    return out
