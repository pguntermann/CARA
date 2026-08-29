"""Detail-panel tab / related-menu visibility units and settings helpers.

A unit may map to a detail tab, a top-level menu, both, or (in future) menu-only.
Missing keys in persisted settings default to visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class DetailPanelVisibilityUnit:
    """One show/hide unit for the View → Show/Hide submenu."""

    id: str
    label: str
    tab_title: Optional[str] = None
    menu_title: Optional[str] = None


# Stable registry — add future tabs/menus here and in user_settings.json.template.
DETAIL_PANEL_VISIBILITY_UNITS: Tuple[DetailPanelVisibilityUnit, ...] = (
    DetailPanelVisibilityUnit(
        "moves_list", "Moves List", tab_title="Moves List", menu_title="Moves List"
    ),
    DetailPanelVisibilityUnit(
        "metadata", "PGN header tags", tab_title="PGN header tags", menu_title=None
    ),
    DetailPanelVisibilityUnit(
        "manual_analysis",
        "Manual Analysis",
        tab_title="Manual Analysis",
        menu_title="Manual Analysis",
    ),
    DetailPanelVisibilityUnit(
        "opening_explorer",
        "Opening Explorer",
        tab_title="Opening Explorer",
        menu_title=None,
    ),
    DetailPanelVisibilityUnit(
        "game_summary",
        "Game Summary",
        tab_title="Game Summary",
        menu_title=None,  # Game Analysis menu stays available for analysis
    ),
    DetailPanelVisibilityUnit(
        "player_stats",
        "Player Stats",
        tab_title="Player Stats",
        menu_title="Player Stats",
    ),
    DetailPanelVisibilityUnit(
        "annotations",
        "Annotations",
        tab_title="Annotations",
        menu_title="Annotations",
    ),
    DetailPanelVisibilityUnit(
        "ai_summary", "AI Summary", tab_title="AI Summary", menu_title="AI Summary"
    ),
    DetailPanelVisibilityUnit(
        "notes", "Notes", tab_title="Notes", menu_title="Notes"
    ),
)


def detail_panel_visibility_unit_ids() -> List[str]:
    """Return stable unit ids in registry order."""
    return [u.id for u in DETAIL_PANEL_VISIBILITY_UNITS]


def unit_by_id(unit_id: str) -> Optional[DetailPanelVisibilityUnit]:
    """Look up a registry unit by id."""
    for unit in DETAIL_PANEL_VISIBILITY_UNITS:
        if unit.id == unit_id:
            return unit
    return None


def unit_by_tab_title(tab_title: str) -> Optional[DetailPanelVisibilityUnit]:
    """Look up a registry unit by detail-tab title."""
    for unit in DETAIL_PANEL_VISIBILITY_UNITS:
        if unit.tab_title == tab_title:
            return unit
    return None


def default_detail_panel_visibility() -> Dict[str, bool]:
    """All known units visible."""
    return {u.id: True for u in DETAIL_PANEL_VISIBILITY_UNITS}


def normalize_detail_panel_visibility(
    raw: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    """Normalize a persisted visibility map; unknown ids ignored, missing ids → True."""
    defaults = default_detail_panel_visibility()
    if not isinstance(raw, dict):
        return defaults
    out = dict(defaults)
    for key, value in raw.items():
        sid = str(key)
        if sid in out and isinstance(value, bool):
            out[sid] = value
    # Never allow hiding every tab that has a tab_title.
    if not any(
        out.get(u.id, True) for u in DETAIL_PANEL_VISIBILITY_UNITS if u.tab_title
    ):
        # Restore Moves List as a safe fallback.
        out["moves_list"] = True
    return out


def visible_tab_units(
    visibility: Optional[Dict[str, bool]] = None,
) -> Sequence[DetailPanelVisibilityUnit]:
    """Units that have a tab and are currently visible."""
    vis = normalize_detail_panel_visibility(visibility)
    return tuple(
        u for u in DETAIL_PANEL_VISIBILITY_UNITS if u.tab_title and vis.get(u.id, True)
    )
