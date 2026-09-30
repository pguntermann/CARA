"""Per-surface miniature-board scale factors (user settings)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

# Stable keys used in user_settings.json → miniature_boards
MANUAL_ANALYSIS = "manual_analysis"
OPENING_EXPLORER = "opening_explorer"
GAME_SUMMARY_HIGHLIGHTS = "game_summary_highlights"
OPENING_ENCYCLOPEDIA = "opening_encyclopedia"
MOVE_LINK_POPUPS = "move_link_popups"

MINIATURE_BOARD_SCALE_KEYS: Tuple[str, ...] = (
    MANUAL_ANALYSIS,
    OPENING_EXPLORER,
    GAME_SUMMARY_HIGHLIGHTS,
    OPENING_ENCYCLOPEDIA,
    MOVE_LINK_POPUPS,
)

# Menu labels for View → Miniature Boards
MINIATURE_BOARD_SCALE_MENU_ITEMS: Tuple[Tuple[str, str], ...] = (
    (MANUAL_ANALYSIS, "Manual Analysis"),
    (OPENING_EXPLORER, "Opening Explorer"),
    (GAME_SUMMARY_HIGHLIGHTS, "Game Summary Highlight Cards"),
    (OPENING_ENCYCLOPEDIA, "Opening Encyclopedia"),
    (MOVE_LINK_POPUPS, "Move Link Tooltips"),
)

MINIATURE_BOARD_SCALE_PRESETS: Tuple[float, ...] = (1.0, 1.25, 1.5, 1.75, 2.0)

_DEFAULTS: Dict[str, float] = {
    MANUAL_ANALYSIS: 1.25,
    OPENING_EXPLORER: 1.0,
    GAME_SUMMARY_HIGHLIGHTS: 1.0,
    OPENING_ENCYCLOPEDIA: 1.0,
    MOVE_LINK_POPUPS: 1.0,
}


def default_miniature_board_scales() -> Dict[str, float]:
    return dict(_DEFAULTS)


def _snap_preset(value: Any, fallback: float) -> float:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    best = float(fallback)
    best_dist = abs(raw - best)
    for preset in MINIATURE_BOARD_SCALE_PRESETS:
        dist = abs(raw - preset)
        if dist < best_dist:
            best = float(preset)
            best_dist = dist
    return best


def normalize_miniature_board_scales(
    raw: Optional[Mapping[str, Any]] = None,
) -> Dict[str, float]:
    """Return a complete scales map; snap unknown values to the nearest preset."""
    out = default_miniature_board_scales()
    if not isinstance(raw, Mapping):
        return out
    for key in MINIATURE_BOARD_SCALE_KEYS:
        if key in raw:
            out[key] = _snap_preset(raw.get(key), out[key])
    return out


def get_miniature_board_scale_from_settings(
    settings: Optional[Mapping[str, Any]], key: str
) -> float:
    """Read one surface scale from a full user-settings dict."""
    settings = settings if isinstance(settings, Mapping) else {}
    scales = normalize_miniature_board_scales(
        settings.get("miniature_boards")
        if isinstance(settings.get("miniature_boards"), Mapping)
        else None,
    )
    return float(scales.get(key, _DEFAULTS.get(key, 1.0)))
