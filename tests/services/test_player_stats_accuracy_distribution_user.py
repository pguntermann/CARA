"""Tests for player_stats_accuracy_distribution user settings normalization."""

from app.services.player_stats_accuracy_distribution_user import (
    DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION,
    normalize_player_stats_accuracy_distribution_settings,
)


def test_normalize_defaults_when_none() -> None:
    out = normalize_player_stats_accuracy_distribution_settings(None)
    assert out == DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION


def test_normalize_accepts_valid_values() -> None:
    raw = {
        "skew_mode": "linear",
        "y_axis_mode": "percent_of_games",
        "bin_density": "more",
        "color_preset": "amber",
        "distribution_line_curve": "straight",
        "distribution_line_smooth_strength": 1.5,
    }
    out = normalize_player_stats_accuracy_distribution_settings(raw)
    assert out == {**DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION, **raw}


def test_normalize_drops_invalid_keys_uses_defaults() -> None:
    raw = {
        "skew_mode": "invalid",
        "y_axis_mode": "nope",
        "bin_density": "",
        "color_preset": "ocean_blue",
        "extra": 1,
    }
    out = normalize_player_stats_accuracy_distribution_settings(raw)
    assert out["skew_mode"] == DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION["skew_mode"]
    assert out["y_axis_mode"] == DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION["y_axis_mode"]
    assert out["bin_density"] == DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION["bin_density"]
    assert out["color_preset"] == "ocean_blue"
    assert out["distribution_line_curve"] == DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION[
        "distribution_line_curve"
    ]
    assert out["distribution_line_smooth_strength"] == DEFAULT_PLAYER_STATS_ACCURACY_DISTRIBUTION[
        "distribution_line_smooth_strength"
    ]
    assert "extra" not in out
