"""Axis helper tests for player stats trend charts."""

from app.views.detail_player_stats_view import _x_axis_week_minors_in_month_mode


def test_x_axis_week_minors_in_month_mode_respects_span() -> None:
    assert _x_axis_week_minors_in_month_mode({}, 50, True) is True
    assert _x_axis_week_minors_in_month_mode({}, 200, True) is False
    assert _x_axis_week_minors_in_month_mode({}, 50, False) is False


def test_x_axis_week_minors_in_month_mode_config_overrides() -> None:
    assert _x_axis_week_minors_in_month_mode({"x_axis_week_minor_max_calendar_span_days": 0}, 10, True) is False
    assert _x_axis_week_minors_in_month_mode({"x_axis_week_minor_max_calendar_span_days": 300}, 200, True) is True
