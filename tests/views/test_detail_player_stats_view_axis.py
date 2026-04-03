"""Axis helper tests for player stats trend charts."""

from datetime import date

from app.views.detail_player_stats_view import (
    _build_gap_compressed_time_layout,
    _coerce_progression_x_axis_mode,
    _plot_x_uniform_bin_index,
    _x_axis_week_minors_in_month_mode,
)


def test_x_axis_week_minors_in_month_mode_respects_span() -> None:
    assert _x_axis_week_minors_in_month_mode({}, 50, True) is True
    assert _x_axis_week_minors_in_month_mode({}, 200, True) is False
    assert _x_axis_week_minors_in_month_mode({}, 50, False) is False


def test_x_axis_week_minors_in_month_mode_config_overrides() -> None:
    assert _x_axis_week_minors_in_month_mode({"x_axis_week_minor_max_calendar_span_days": 0}, 10, True) is False
    assert _x_axis_week_minors_in_month_mode({"x_axis_week_minor_max_calendar_span_days": 300}, 200, True) is True


def test_gap_compressed_layout_uses_less_width_for_long_calendar_gaps() -> None:
    """Long spans without bins get capped weight vs. linear calendar X."""
    o0 = date(2024, 1, 1).toordinal()
    c1 = o0 + 5
    c2 = o0 + 95
    o1 = o0 + 100
    layout = _build_gap_compressed_time_layout(o0, o1, [c1, c2], max_segment_calendar_days=15)
    assert layout is not None
    cal_gap_frac = (c2 - c1) / (o1 - o0)
    disp_gap_frac = layout.ordinal_to_frac(c2) - layout.ordinal_to_frac(c1)
    assert disp_gap_frac < cal_gap_frac


def test_coerce_progression_x_axis_mode_defaults() -> None:
    assert _coerce_progression_x_axis_mode({}) == "uniform_bins"
    assert _coerce_progression_x_axis_mode({"compress_time_axis_gaps": False}) == "calendar_linear"
    assert _coerce_progression_x_axis_mode({"progression_x_axis_mode": "gap_compressed"}) == "gap_compressed"


def test_plot_x_uniform_bin_index_even_spacing() -> None:
    assert _plot_x_uniform_bin_index(0, 5, 100.0, 400.0) == 100.0
    assert _plot_x_uniform_bin_index(4, 5, 100.0, 400.0) == 500.0
    assert abs(_plot_x_uniform_bin_index(2, 5, 0.0, 100.0) - 50.0) < 1e-9


def test_gap_compressed_frac_round_trip() -> None:
    o0 = date(2025, 6, 1).toordinal()
    layout = _build_gap_compressed_time_layout(
        o0,
        o0 + 60,
        [o0 + 10, o0 + 50],
        max_segment_calendar_days=20,
    )
    assert layout is not None
    for o in range(o0, o0 + 61, 7):
        f = layout.ordinal_to_frac(o)
        o2 = layout.frac_to_ordinal(f)
        assert abs(o2 - o) <= 1
