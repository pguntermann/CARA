"""User overrides for Chess Log Charts binning and rendering (persisted in user settings)."""

from __future__ import annotations

from typing import Any, Dict, Optional

DEFAULT_CHESS_LOG_CHARTS: Dict[str, Any] = {
    "target_progression_bins": 16,
    "ordinal_fallback_mode": "quantile",
    "progression_x_axis_mode": "uniform_bins",
    "compress_gap_max_segment_days": 28,
    "progression_line_style": "smooth",
    "progression_line_smooth_strength": 1.0,
}

CHOICES_TARGET_BINS: tuple = (8, 12, 16, 24, 32)
CHOICES_BINNING_MODE: tuple = ("quantile", "equal_width")
CHOICES_X_AXIS_LAYOUT: tuple = ("uniform_bins", "gap_compressed", "calendar_linear")
CHOICES_MAX_GAP_SEGMENT_DAYS: tuple = (14, 28, 50, 100)
CHOICES_LINE_STYLE: tuple = ("smooth", "straight")
CHOICES_SMOOTHING_STRENGTH: tuple = (0.5, 1.0, 1.5, 2.0)


def normalize_chess_log_charts_settings(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a full Chess Log Charts settings dict with invalid values dropped and defaults filled.

    Migrations (applied on first load, in order):
    - Old ``x_axis_mode`` key → ``progression_x_axis_mode`` ("game_count" → "uniform_bins", "time" → "calendar_linear").
    - Old short key names (pre-alignment) → new Player-Stats-aligned leaf names.
    """
    out = dict(DEFAULT_CHESS_LOG_CHARTS)
    if not raw or not isinstance(raw, dict):
        return out

    # --- migration: old x_axis_mode (phase 0 legacy) ---
    if "x_axis_mode" in raw and "progression_x_axis_mode" not in raw and "x_axis_layout" not in raw:
        legacy = str(raw.get("x_axis_mode", "")).strip().lower()
        if legacy == "game_count":
            out["progression_x_axis_mode"] = "uniform_bins"
        else:
            out["progression_x_axis_mode"] = "calendar_linear"

    # --- migration: old short key names → new aligned names (6 keys) ---
    _migrate_single = [
        ("target_bins", "target_progression_bins", CHOICES_TARGET_BINS),
        ("binning_mode", "ordinal_fallback_mode", CHOICES_BINNING_MODE),
        ("x_axis_layout", "progression_x_axis_mode", CHOICES_X_AXIS_LAYOUT),
        ("max_gap_segment_days", "compress_gap_max_segment_days", CHOICES_MAX_GAP_SEGMENT_DAYS),
        ("line_style", "progression_line_style", CHOICES_LINE_STYLE),
        ("smoothing_strength", "progression_line_smooth_strength", CHOICES_SMOOTHING_STRENGTH),
    ]
    for old_key, new_key, choices in _migrate_single:
        if old_key in raw and new_key not in raw:
            raw = dict(raw)
            raw[new_key] = raw[old_key]

    if raw.get("target_progression_bins") in CHOICES_TARGET_BINS:
        out["target_progression_bins"] = int(raw["target_progression_bins"])

    bm = str(raw.get("ordinal_fallback_mode", "")).strip().lower()
    if bm in CHOICES_BINNING_MODE:
        out["ordinal_fallback_mode"] = bm

    xl = str(raw.get("progression_x_axis_mode", "")).strip().lower()
    if xl in CHOICES_X_AXIS_LAYOUT:
        out["progression_x_axis_mode"] = xl

    if raw.get("compress_gap_max_segment_days") in CHOICES_MAX_GAP_SEGMENT_DAYS:
        out["compress_gap_max_segment_days"] = int(raw["compress_gap_max_segment_days"])

    ls = str(raw.get("progression_line_style", "")).strip().lower()
    if ls in CHOICES_LINE_STYLE:
        out["progression_line_style"] = ls

    if raw.get("progression_line_smooth_strength") in CHOICES_SMOOTHING_STRENGTH:
        out["progression_line_smooth_strength"] = float(raw["progression_line_smooth_strength"])

    return out


def chart_cfg_with_chess_log_charts_overrides(
    app_config: Optional[Dict[str, Any]],
    target_bins: int,
    binning_mode: str = "quantile",
) -> Dict[str, Any]:
    """Build a chart_cfg dict for chess_log_stats_service.aggregate() with user overrides applied.

    Extracts the player_stats.time_series block from app_config (for min_games_per_ordinal_bin,
    max_ordinal_bins, etc.) and overrides target_progression_bins and ordinal_fallback_mode with
    the caller's already-resolved values so player_stats_service helpers read the right values.
    """
    ts_block: Dict[str, Any] = (
        (app_config or {})
        .get("ui", {})
        .get("panels", {})
        .get("detail", {})
        .get("player_stats", {})
        .get("time_series", {})
    )
    cfg = dict(ts_block)
    cfg["target_progression_bins"] = target_bins
    cfg["ordinal_fallback_mode"] = binning_mode
    return cfg
