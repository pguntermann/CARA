"""Tests for activity heatmap layout helpers."""

from __future__ import annotations

from datetime import date

from app.services.player_stats_activity_heatmap_layout import (
    build_activity_heatmap_paint_model,
    effective_ordinal_for_heatmap,
    trim_range_ordinals,
)


def test_effective_ordinal_exclude() -> None:
    assert effective_ordinal_for_heatmap("exclude", 100, 200) == 100
    assert effective_ordinal_for_heatmap("exclude", None, 200) is None


def test_effective_ordinal_include() -> None:
    assert effective_ordinal_for_heatmap("include_stand_in", 100, 200) == 100
    assert effective_ordinal_for_heatmap("include_stand_in", None, 200) == 200


def test_trim_range() -> None:
    today = date(2020, 6, 15).toordinal()
    lo, hi = trim_range_ordinals([today - 10, today - 5], "trim_to_data", today)
    assert lo == today - 10 and hi == today - 5
    lo2, hi2 = trim_range_ordinals([today - 1000], "rolling_12_months", today)
    assert hi2 == today
    assert hi2 - lo2 == 364
    lo3, hi3 = trim_range_ordinals([today], "rolling_24_months", today)
    assert hi3 == today
    assert hi3 - lo3 == 729


def _heatmap_user(**overrides):
    base = {
        "week_starts_on": "monday",
        "partial_dates": "exclude",
        "date_range": "trim_to_data",
        "color_scale_max_mode": "auto",
        "color_scale_max_fixed": 5,
        "color_preset": "github_green",
    }
    base.update(overrides)
    return base


def test_calendar_distinct_weekday_rows() -> None:
    d_tue = date(2024, 1, 2).toordinal()  # Tuesday — one game
    pairs = [(d_tue, d_tue)]
    user = _heatmap_user()
    m = build_activity_heatmap_paint_model(pairs, user, date(2024, 2, 1).toordinal())
    assert m is not None
    assert m.kind == "month"
    b0 = m.bands[0]
    assert b0.n_rows == 7
    assert b0.n_cols >= 1
    assert len(b0.row_labels) == 7
    assert m.layout_style == "single_band"
    assert b0.counts[0][0] == 0 and b0.counts[1][0] == 1
    assert sum(b0.counts[r][c] for r in range(7) for c in range(b0.n_cols)) == 1


def test_single_game_calendar_grid() -> None:
    d0 = date(2024, 1, 2).toordinal()
    pairs = [(d0, d0)]
    user = _heatmap_user()
    m = build_activity_heatmap_paint_model(pairs, user, date(2024, 2, 1).toordinal())
    assert m is not None
    assert m.kind == "month"
    b0 = m.bands[0]
    assert b0.n_rows == 7
    assert b0.n_cols >= 1
    assert len(b0.row_labels) == 7
    assert sum(b0.counts[r][c] for r in range(b0.n_rows) for c in range(b0.n_cols)) == 1


def test_trim_range_calendar_single_band() -> None:
    d0 = date(2024, 1, 1).toordinal()
    pairs = [(d0, d0)]
    user = _heatmap_user(date_range="trim_to_data")
    m = build_activity_heatmap_paint_model(pairs, user, date(2024, 6, 1).toordinal())
    assert m is not None
    assert m.kind == "month"
    assert m.bands[0].n_rows == 7
    assert m.layout_style == "single_band"


def test_rolling_24_months_stacks_two_year_bands() -> None:
    today_o = date(2026, 4, 4).toordinal()
    o_old = today_o - 400
    o_new = today_o - 10
    pairs = [(o_old, o_old), (o_new, o_new)]
    user = _heatmap_user(date_range="rolling_24_months")
    m = build_activity_heatmap_paint_model(pairs, user, today_o)
    assert m is not None
    assert m.kind == "month"
    assert m.layout_style == "two_year_stacked"
    assert len(m.bands) == 2
    assert len(m.bands[0].row_labels) == 7
    assert len(m.bands[1].row_labels) == 0
    assert m.bands[0].n_cols >= 45
    assert m.bands[1].n_cols >= 45
    s0 = sum(
        m.bands[0].counts[r][c]
        for r in range(7)
        for c in range(m.bands[0].n_cols)
    )
    s1 = sum(
        m.bands[1].counts[r][c]
        for r in range(7)
        for c in range(m.bands[1].n_cols)
    )
    assert s0 + s1 == 2
    assert "older year above" in m.subcaption


def test_build_empty_returns_none() -> None:
    m = build_activity_heatmap_paint_model([], {}, date.today().toordinal())
    assert m is None
