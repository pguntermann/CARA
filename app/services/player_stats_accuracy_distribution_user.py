"""User overrides for Player Stats accuracy distribution chart (persisted in user settings)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.player_stats_time_series_user import CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH

# Same discrete strengths as time-series progression charts (menu + validation).
CHOICES_DISTRIBUTION_LINE_SMOOTH_STRENGTH: tuple = CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH

DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION: Dict[str, Any] = {
    "skew_mode": "high_accuracy_skew",
    "y_axis_mode": "count",
    "bin_density": "auto",
    "color_preset": "github_green",
    "distribution_line_curve": "smooth",
    "distribution_line_smooth_strength": 1.0,
}

VALID_SKEW_MODE: frozenset = frozenset(
    {"linear", "high_accuracy_skew", "very_high_accuracy_skew"}
)
VALID_Y_AXIS_MODE: frozenset = frozenset({"count", "percent_of_games"})
VALID_BIN_DENSITY: frozenset = frozenset({"auto", "fewer", "more"})
VALID_COLOR_PRESET: frozenset = frozenset({"github_green", "ocean_blue", "amber"})
VALID_DISTRIBUTION_LINE_CURVE: frozenset = frozenset({"smooth", "straight"})


def normalize_player_stats_accuracy_distribution_settings(
    raw: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a full accuracy-distribution user settings dict with invalid keys dropped."""
    out = dict(DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION)
    if not raw or not isinstance(raw, dict):
        return out
    sm = str(raw.get("skew_mode", "")).strip().lower()
    if sm in VALID_SKEW_MODE:
        out["skew_mode"] = sm
    ya = str(raw.get("y_axis_mode", "")).strip().lower()
    if ya in VALID_Y_AXIS_MODE:
        out["y_axis_mode"] = ya
    bd = str(raw.get("bin_density", "")).strip().lower()
    if bd in VALID_BIN_DENSITY:
        out["bin_density"] = bd
    cp = str(raw.get("color_preset", "")).strip().lower()
    if cp in VALID_COLOR_PRESET:
        out["color_preset"] = cp
    cv = str(raw.get("distribution_line_curve", "")).strip().lower()
    if cv in VALID_DISTRIBUTION_LINE_CURVE:
        out["distribution_line_curve"] = cv
    ss = raw.get("distribution_line_smooth_strength")
    if ss in CHOICES_DISTRIBUTION_LINE_SMOOTH_STRENGTH:
        out["distribution_line_smooth_strength"] = float(ss)
    return out
