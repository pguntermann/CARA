"""Tests for PGN date handling in player stats time-series aggregation."""

from datetime import date

from app.services.player_stats_service import (
    _accuracy_series_equal_ordinal_width_bins,
    _accuracy_series_ordinal_quantile_bins,
    _game_date_ordinal_for_trends,
    _game_date_to_ordinal,
    _ordinal_target_bin_count,
    _trend_axis_ordinals_for_quantile_bins,
    merged_player_stats_time_series_chart_cfg,
)


def test_game_date_to_ordinal_requires_full_date() -> None:
    assert _game_date_to_ordinal("2024.06.15") == date(2024, 6, 15).toordinal()
    assert _game_date_to_ordinal("2024.06.??") is None
    assert _game_date_to_ordinal("2024.??.??") is None


def test_game_date_ordinal_for_trends_accepts_partial() -> None:
    assert _game_date_ordinal_for_trends("2024.06.15") == date(2024, 6, 15).toordinal()
    assert _game_date_ordinal_for_trends("2024.06.??") == date(2024, 6, 15).toordinal()
    assert _game_date_ordinal_for_trends("2024.??.??") == date(2024, 7, 1).toordinal()
    assert _game_date_ordinal_for_trends("????.??.??") is None


def test_merged_time_series_chart_cfg_precedence() -> None:
    ps = {
        "time_series": {"target_progression_bins": 10, "font_size": 11},
        "accuracy_over_time_chart": {"target_progression_bins": 22, "height": 200},
        "move_quality_over_time_chart": {"legend_width": 99},
        "top_move_over_time_chart": {"height": 210},
    }
    acc_m = merged_player_stats_time_series_chart_cfg(ps, "accuracy_over_time_chart")
    assert acc_m["target_progression_bins"] == 22
    assert acc_m["font_size"] == 11
    mq_m = merged_player_stats_time_series_chart_cfg(ps, "move_quality_over_time_chart")
    assert mq_m["target_progression_bins"] == 22
    assert mq_m["font_size"] == 11
    assert mq_m["legend_width"] == 99
    tm_m = merged_player_stats_time_series_chart_cfg(ps, "top_move_over_time_chart")
    assert tm_m["target_progression_bins"] == 22
    assert tm_m["height"] == 210


def test_ordinal_target_bin_count_respects_density_cap() -> None:
    cfg = {"target_progression_bins": 100, "max_ordinal_bins": 120, "min_games_per_ordinal_bin": 3}
    assert _ordinal_target_bin_count(cfg, 300) == 100
    assert _ordinal_target_bin_count(cfg, 20) == min(100, 20 // 3)


def test_quantile_progression_honors_target_bin_count() -> None:
    """Progression always uses ordinal bins; quantile mode yields one point per requested bin."""
    oa = date(2025, 4, 29).toordinal()
    ob = date(2025, 8, 5).toordinal()
    samples = [(oa, 68.0, True)] * 50 + [(ob, 87.0, False)] * 50
    series = _accuracy_series_ordinal_quantile_bins(samples, 16, oa, ob)
    assert len(series) == 16


def test_ordinal_quantile_bins_split_many_games_into_more_points() -> None:
    oa = date(2025, 4, 29).toordinal()
    ob = date(2025, 8, 5).toordinal()
    samples = [(oa, 68.0, True)] * 50 + [(ob, 87.0, False)] * 50
    series = _accuracy_series_ordinal_quantile_bins(samples, 12, oa, ob)
    assert len(series) == 12
    assert series[0][1] < 72.0
    assert series[-1][1] > 84.0


def test_equal_ordinal_width_bins_spread_on_calendar_not_equal_counts() -> None:
    """Bimodal play dates: quantile stacks many bins at temporal modes; equal-width does not."""
    o_lo = date(2025, 12, 1).toordinal()
    o_hi = date(2026, 3, 31).toordinal()
    span = o_hi - o_lo
    band = max(12, span // 25)
    first_band_end = o_lo + band
    last_band_start = o_hi - band
    samples = [(o_lo + (i % 4), 70.0, True) for i in range(48)] + [(o_hi - (i % 4), 85.0, False) for i in range(48)]
    t_min, t_max = min(o for o, _, __ in samples), max(o for o, _, __ in samples)
    eq = _accuracy_series_equal_ordinal_width_bins(samples, 12, t_min, t_max)
    qn = _accuracy_series_ordinal_quantile_bins(samples, 12, t_min, t_max)

    def _n_centers_in(rows, lo: int, hi: int) -> int:
        n = 0
        for r in rows:
            c = (date.fromisoformat(r[5]).toordinal() + date.fromisoformat(r[6]).toordinal()) // 2
            if lo <= c <= hi:
                n += 1
        return n

    q_end_caps = _n_centers_in(qn, t_min, first_band_end) + _n_centers_in(qn, last_band_start, t_max)
    eq_end_caps = _n_centers_in(eq, t_min, first_band_end) + _n_centers_in(eq, last_band_start, t_max)
    assert q_end_caps > eq_end_caps + 3


def test_trend_axis_tight_around_quantile_bin_centers() -> None:
    """Wide first-bin lab0–lab1 must not force the chart axis to start at the early outlier date."""
    oa = date(2024, 4, 28).toordinal()
    ob = date(2024, 8, 8).toordinal()
    pairs = [
        ("2024-04-28", "2024-08-05"),
        ("2024-08-06", "2024-08-06"),
        ("2024-08-08", "2024-08-08"),
    ]
    amin, amax = _trend_axis_ordinals_for_quantile_bins(pairs, oa, ob)
    assert amin > date(2024, 5, 20).toordinal()
    assert amax == ob
    assert amin < amax


def test_ordinal_quantile_bins_x_matches_calendar_not_rank() -> None:
    """Dense early + dense late dates: X must follow calendar axis, not list index."""
    o_early = date(2025, 12, 1).toordinal()
    o_late = date(2026, 3, 15).toordinal()
    samples = [(o_early, 70.0, True)] * 50 + [(o_late, 80.0, False)] * 50
    series = _accuracy_series_ordinal_quantile_bins(samples, 4, o_early, o_late)
    early_rows = [row for row in series if row[5].startswith("2025-12") and row[6].startswith("2025-12")]
    assert early_rows
    assert all(row[0] < 5.0 for row in early_rows)
    late_rows = [row for row in series if row[5].startswith("2026-03") and row[6].startswith("2026-03")]
    assert late_rows
    assert all(row[0] > 95.0 for row in late_rows)
