"""User overrides for Player Stats time-series binning and presentation (persisted in user settings)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

# Default values align with app/config/config.json time_series where applicable.
# min_games_with_full_date / min_span_days / min_games_per_ordinal_bin are config-only.
DEFAULT_PLAYER_STATS_TIME_SERIES: Dict[str, Any] = {
    "target_progression_bins": 16,
    "ordinal_fallback_mode": "quantile",
    "progression_x_axis_mode": "uniform_bins",
    "compress_gap_max_segment_days": 28,
    "progression_line_style": "smooth",
    "progression_line_smooth_strength": 1.0,
}

CHOICES_TARGET_PROGRESSION_BINS: tuple = (8, 12, 16, 24, 32)
CHOICES_COMPRESS_GAP_MAX_SEGMENT_DAYS: tuple = (14, 28, 50, 100)
CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH: tuple = (0.5, 1.0, 1.5, 2.0)

VALID_ORDINAL_MODES: frozenset = frozenset({"quantile", "equal_width"})
VALID_X_AXIS_MODES: frozenset = frozenset({"uniform_bins", "gap_compressed", "calendar_linear"})


def normalize_player_stats_time_series_settings(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a full time-series user settings dict with invalid keys dropped and defaults filled."""
    out = dict(DEFAULT_PLAYER_STATS_TIME_SERIES)
    if not raw or not isinstance(raw, dict):
        return out
    if raw.get("target_progression_bins") in CHOICES_TARGET_PROGRESSION_BINS:
        out["target_progression_bins"] = int(raw["target_progression_bins"])
    m = str(raw.get("ordinal_fallback_mode", "")).strip().lower()
    if m in VALID_ORDINAL_MODES:
        out["ordinal_fallback_mode"] = m
    xm = str(raw.get("progression_x_axis_mode", "")).strip().lower()
    if xm in VALID_X_AXIS_MODES:
        out["progression_x_axis_mode"] = xm
    if raw.get("compress_gap_max_segment_days") in CHOICES_COMPRESS_GAP_MAX_SEGMENT_DAYS:
        out["compress_gap_max_segment_days"] = int(raw["compress_gap_max_segment_days"])
    st = str(raw.get("progression_line_style", "")).strip().lower()
    if st in ("smooth", "straight"):
        out["progression_line_style"] = st
    if raw.get("progression_line_smooth_strength") in CHOICES_PROGRESSION_LINE_SMOOTH_STRENGTH:
        out["progression_line_smooth_strength"] = float(raw["progression_line_smooth_strength"])
    return out


def player_stats_block_with_time_series_overrides(
    player_stats_config: Dict[str, Any],
    user_ts: Dict[str, Any],
) -> Dict[str, Any]:
    """Deep-copy ``player_stats`` block and merge normalized user time_series keys into ``time_series``."""
    base = deepcopy(player_stats_config)
    ts = dict(base.get("time_series") or {})
    norm = normalize_player_stats_time_series_settings(user_ts)
    ts.update(
        {
            "target_progression_bins": norm["target_progression_bins"],
            "ordinal_fallback_mode": norm["ordinal_fallback_mode"],
            "progression_x_axis_mode": norm["progression_x_axis_mode"],
            "compress_gap_max_segment_days": norm["compress_gap_max_segment_days"],
            "progression_line_style": (
                "smooth" if norm["progression_line_style"] == "smooth" else "solid"
            ),
            "progression_line_smooth_strength": norm["progression_line_smooth_strength"],
        }
    )
    base["time_series"] = ts
    return base
