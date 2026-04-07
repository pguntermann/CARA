"""User overrides for Player Stats activity heatmap (persisted in user settings)."""

from __future__ import annotations

from typing import Any, Dict, Optional

DEFAULT_PLAYER_STATS_ACTIVITY_HEATMAP: Dict[str, Any] = {
    "week_starts_on": "monday",
    "color_preset": "github_green",
    "color_scale_max_mode": "auto",
    "color_scale_max_fixed": 5,
    "partial_dates": "include_stand_in",
    "date_range": "trim_to_data",
    "show_day_numbers_in_cells": True,
    # month dividers: week_anchor = legacy verticals; calendar_mesh = edges along cell grid;
    # off = no month emphasis (week dividers only).
    "month_divider_mode": "week_anchor",
}

VALID_WEEK_START: frozenset = frozenset({"monday", "sunday"})
VALID_COLOR_PRESET: frozenset = frozenset({"github_green", "ocean_blue", "amber"})
VALID_SCALE_MAX_MODE: frozenset = frozenset({"auto", "fixed"})
VALID_PARTIAL_DATES: frozenset = frozenset({"exclude", "include_stand_in"})
VALID_DATE_RANGE: frozenset = frozenset(
    {
        "trim_to_data",
        "rolling_12_months",
        "rolling_24_months",
        "games_12_months",
        "games_24_months",
    }
)
VALID_MONTH_DIVIDER_MODE: frozenset = frozenset(
    {"week_anchor", "calendar_mesh", "off"}
)

CHOICES_COLOR_SCALE_MAX_FIXED: tuple = (3, 5, 8, 10, 15, 20)


def normalize_player_stats_activity_heatmap_settings(
    raw: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a full activity-heatmap user settings dict with invalid keys dropped."""
    out = dict(DEFAULT_PLAYER_STATS_ACTIVITY_HEATMAP)
    if not raw or not isinstance(raw, dict):
        return out
    ws = str(raw.get("week_starts_on", "")).strip().lower()
    if ws in VALID_WEEK_START:
        out["week_starts_on"] = ws
    cp = str(raw.get("color_preset", "")).strip().lower()
    if cp in VALID_COLOR_PRESET:
        out["color_preset"] = cp
    sm = str(raw.get("color_scale_max_mode", "")).strip().lower()
    if sm in VALID_SCALE_MAX_MODE:
        out["color_scale_max_mode"] = sm
    if raw.get("color_scale_max_fixed") in CHOICES_COLOR_SCALE_MAX_FIXED:
        out["color_scale_max_fixed"] = int(raw["color_scale_max_fixed"])
    else:
        try:
            v = int(raw.get("color_scale_max_fixed", out["color_scale_max_fixed"]))
            if 1 <= v <= 500:
                out["color_scale_max_fixed"] = v
        except (TypeError, ValueError):
            pass
    pd = str(raw.get("partial_dates", "")).strip().lower()
    if pd in VALID_PARTIAL_DATES:
        out["partial_dates"] = pd
    dr = str(raw.get("date_range", "")).strip().lower()
    if dr in VALID_DATE_RANGE:
        out["date_range"] = dr
    if "show_day_numbers_in_cells" in raw:
        v = raw["show_day_numbers_in_cells"]
        if isinstance(v, bool):
            out["show_day_numbers_in_cells"] = v
        elif isinstance(v, (int, float)):
            out["show_day_numbers_in_cells"] = bool(int(v))
        elif isinstance(v, str):
            sl = v.strip().lower()
            if sl in ("true", "1", "yes", "on"):
                out["show_day_numbers_in_cells"] = True
            elif sl in ("false", "0", "no", "off"):
                out["show_day_numbers_in_cells"] = False
    else:
        out["show_day_numbers_in_cells"] = out["date_range"] == "trim_to_data"
    md = str(raw.get("month_divider_mode", "")).strip().lower()
    if md in VALID_MONTH_DIVIDER_MODE:
        out["month_divider_mode"] = md
    return out
