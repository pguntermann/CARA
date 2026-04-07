"""Tests for activity heatmap user settings normalization."""

from __future__ import annotations

from app.services.player_stats_activity_heatmap_user import (
    DEFAULT_PLAYER_STATS_ACTIVITY_HEATMAP,
    normalize_player_stats_activity_heatmap_settings,
)


def test_default_includes_show_day_numbers() -> None:
    assert DEFAULT_PLAYER_STATS_ACTIVITY_HEATMAP["show_day_numbers_in_cells"] is True


def test_legacy_missing_key_follows_trim_to_data() -> None:
    n = normalize_player_stats_activity_heatmap_settings(
        {"date_range": "rolling_12_months"}
    )
    assert n["show_day_numbers_in_cells"] is False
    y = normalize_player_stats_activity_heatmap_settings({"date_range": "trim_to_data"})
    assert y["show_day_numbers_in_cells"] is True


def test_explicit_show_day_numbers_overrides_legacy() -> None:
    n = normalize_player_stats_activity_heatmap_settings(
        {"date_range": "rolling_12_months", "show_day_numbers_in_cells": True}
    )
    assert n["show_day_numbers_in_cells"] is True
    y = normalize_player_stats_activity_heatmap_settings(
        {"date_range": "trim_to_data", "show_day_numbers_in_cells": False}
    )
    assert y["show_day_numbers_in_cells"] is False
