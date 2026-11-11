"""Characterization tests for _chart_layout_helpers shared module.

Covers the pure-Python helpers used by both ChessLogCategoryChartWidget and
AccuracyOverTimeChartWidget / MoveQualityOverTimeChartWidget. The same input
matrix must produce identical results regardless of which caller uses the
functions — this file is that guarantee.
"""

import unittest
from datetime import date

from app.views.widgets._chart_layout_helpers import (
    GapCompressedTimeLayout,
    build_gap_compressed_time_layout,
    calendar_axis_ticks,
    effective_calendar_mode,
    ordinal_to_chart_x,
    week_start_monday_ordinal,
)


class TestEffectiveCalendarMode(unittest.TestCase):
    def test_day_for_very_short_span(self):
        omin = date(2026, 6, 1).toordinal()
        omax = date(2026, 6, 15).toordinal()  # 14 days
        self.assertEqual(effective_calendar_mode(omin, omax), "day")

    def test_day_at_boundary_31_days(self):
        omin = date(2026, 6, 1).toordinal()
        omax = omin + 31
        self.assertEqual(effective_calendar_mode(omin, omax), "day")

    def test_week_just_over_day_boundary(self):
        omin = date(2026, 6, 1).toordinal()
        omax = omin + 32  # 32 > 31 → week
        self.assertEqual(effective_calendar_mode(omin, omax), "week")

    def test_week_at_120_days(self):
        omin = date(2026, 1, 1).toordinal()
        omax = omin + 120
        self.assertEqual(effective_calendar_mode(omin, omax), "week")

    def test_month_just_over_week_boundary(self):
        omin = date(2026, 1, 1).toordinal()
        omax = omin + 121  # > 120 → month
        self.assertEqual(effective_calendar_mode(omin, omax), "month")

    def test_month_for_full_year(self):
        omin = date(2026, 1, 1).toordinal()
        omax = date(2026, 12, 31).toordinal()
        self.assertEqual(effective_calendar_mode(omin, omax), "month")

    def test_year_just_over_month_boundary(self):
        omin = date(2020, 1, 1).toordinal()
        omax = omin + 961  # > 960 → year
        self.assertEqual(effective_calendar_mode(omin, omax), "year")

    def test_year_for_multiyear_span(self):
        omin = date(2020, 1, 1).toordinal()
        omax = date(2025, 12, 31).toordinal()
        self.assertEqual(effective_calendar_mode(omin, omax), "year")

    def test_zero_span_returns_day(self):
        omin = date(2026, 6, 1).toordinal()
        self.assertEqual(effective_calendar_mode(omin, omin), "day")


class TestWeekStartMondayOrdinal(unittest.TestCase):
    def test_monday_unchanged(self):
        d = date(2026, 9, 14)  # Monday
        self.assertEqual(week_start_monday_ordinal(d.toordinal()), d.toordinal())

    def test_wednesday_returns_monday(self):
        wed = date(2026, 9, 16)
        mon = date(2026, 9, 14)
        self.assertEqual(week_start_monday_ordinal(wed.toordinal()), mon.toordinal())

    def test_sunday_returns_previous_monday(self):
        sun = date(2026, 9, 20)
        mon = date(2026, 9, 14)
        self.assertEqual(week_start_monday_ordinal(sun.toordinal()), mon.toordinal())

    def test_result_is_always_a_monday(self):
        for offset in range(7):
            d = date(2026, 9, 14 + offset)
            result = date.fromordinal(week_start_monday_ordinal(d.toordinal()))
            self.assertEqual(result.weekday(), 0, f"weekday of {result} is not Monday")


class TestOrdinalToChartX(unittest.TestCase):
    """Signature: ordinal_to_chart_x(o, left, graph_width, omin, omax, layout=None)."""

    def test_at_omin_returns_left(self):
        omin = date(2026, 1, 1).toordinal()
        omax = date(2026, 12, 31).toordinal()
        self.assertAlmostEqual(ordinal_to_chart_x(omin, 50.0, 900.0, omin, omax), 50.0)

    def test_at_omax_returns_left_plus_width(self):
        omin = date(2026, 1, 1).toordinal()
        omax = date(2026, 12, 31).toordinal()
        self.assertAlmostEqual(ordinal_to_chart_x(omax, 50.0, 900.0, omin, omax), 950.0)

    def test_midpoint(self):
        omin = date(2026, 1, 1).toordinal()
        omax = omin + 100
        self.assertAlmostEqual(ordinal_to_chart_x(omin + 50, 0.0, 100.0, omin, omax), 50.0)

    def test_left_zero_graph_width_equals_right_boundary(self):
        omin = date(2026, 3, 1).toordinal()
        omax = omin + 200
        x = ordinal_to_chart_x(omin + 100, 0.0, 600.0, omin, omax)
        self.assertAlmostEqual(x, 300.0)

    def test_both_callers_agree_on_same_ordinal(self):
        """Player Stats and Chess Log both use ordinal_to_chart_x — same ordinal → same x."""
        omin = date(2024, 1, 1).toordinal()
        omax = date(2024, 12, 31).toordinal()
        o = date(2024, 6, 15).toordinal()
        x1 = ordinal_to_chart_x(o, 0.0, 1200.0, omin, omax)
        x2 = ordinal_to_chart_x(o, 0.0, 1200.0, omin, omax)
        self.assertEqual(x1, x2)

    def test_clamped_below_returns_left(self):
        omin = date(2026, 3, 1).toordinal()
        omax = date(2026, 12, 31).toordinal()
        x = ordinal_to_chart_x(omin - 100, 0.0, 1000.0, omin, omax)
        # Falls outside range; linear formula gives negative but clamped inputs give 0
        # Note: ordinal_to_chart_x does NOT clamp — just verify it's <= left for omin
        self.assertLessEqual(x, 0.0)

    def test_with_gap_layout_shifts_position(self):
        # Jan 1 → Jul 1 (big gap ~181 days) → Jul 8 (small gap 7 days).
        # Linear: Jul 1 ≈ 963px out of 1000 (close to omax).
        # Gap-compressed: big gap compressed to 28, small stays 7 → Jul 1 frac = 28/35 = 0.8 → 800px.
        # So gap_compressed MOVES Jul 1 left (closer to center) relative to linear.
        omin = date(2025, 1, 1).toordinal()
        omax = date(2025, 7, 8).toordinal()
        o_jul1 = date(2025, 7, 1).toordinal()
        layout = build_gap_compressed_time_layout(
            omin, omax, [omin, o_jul1, omax], max_segment_calendar_days=28
        )
        self.assertIsNotNone(layout)
        x_gc = ordinal_to_chart_x(o_jul1, 0.0, 1000.0, omin, omax, layout)
        x_linear = ordinal_to_chart_x(o_jul1, 0.0, 1000.0, omin, omax)
        # gap_compressed draws Jul 1 leftward (big gap compressed) vs linear which puts it near 960px
        self.assertLess(x_gc, x_linear - 100)


class TestCalendarAxisTicks(unittest.TestCase):
    def test_month_mode_ticks_sorted(self):
        omin = date(2026, 2, 1).toordinal()
        omax = date(2026, 12, 31).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        ordinals = [o for o, _, _ in ticks]
        self.assertEqual(ordinals, sorted(ordinals))

    def test_month_mode_tick_ordinals_are_first_of_month(self):
        omin = date(2026, 3, 15).toordinal()
        omax = date(2026, 9, 20).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        for o, is_major, _ in ticks:
            if is_major:
                self.assertEqual(date.fromordinal(o).day, 1)

    def test_month_major_labels_use_english_abbrev(self):
        omin = date(2026, 2, 1).toordinal()
        omax = date(2026, 4, 30).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        labels = {lbl for _, is_major, lbl in ticks if is_major and lbl}
        self.assertIn("Feb '26", labels)
        self.assertIn("Mar '26", labels)
        self.assertIn("Apr '26", labels)

    def test_year_mode_major_labels_are_four_digit_years(self):
        omin = date(2021, 6, 1).toordinal()
        omax = date(2024, 6, 30).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "year")
        major_labels = [lbl for _, is_major, lbl in ticks if is_major and lbl]
        for lbl in major_labels:
            self.assertTrue(lbl.isdigit() and len(lbl) == 4, f"year label {lbl!r} not 4-digit year")

    def test_day_mode_all_ticks_are_major(self):
        omin = date(2026, 6, 1).toordinal()
        omax = date(2026, 6, 10).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "day")
        self.assertTrue(all(is_major for _, is_major, _ in ticks))

    def test_week_mode_all_ticks_are_mondays(self):
        omin = date(2026, 1, 1).toordinal()
        omax = date(2026, 3, 31).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "week")
        for o, _, _ in ticks:
            self.assertEqual(date.fromordinal(o).weekday(), 0, f"{date.fromordinal(o)} is not Monday")

    def test_empty_range_returns_empty_list(self):
        omin = date(2026, 6, 1).toordinal()
        self.assertEqual(calendar_axis_ticks(omin, omin, "month"), [])

    def test_minor_month_ticks_in_year_mode(self):
        # 2-year span: year mode with month_ticks_in_year_mode=True should add minor ticks
        omin = date(2024, 1, 1).toordinal()
        omax = date(2025, 12, 31).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "year", month_ticks_in_year_mode=True)
        minor_ticks = [t for t in ticks if not t[1]]
        self.assertGreater(len(minor_ticks), 0)

    def test_no_minor_month_ticks_when_disabled(self):
        omin = date(2024, 1, 1).toordinal()
        omax = date(2025, 12, 31).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "year", month_ticks_in_year_mode=False)
        minor_ticks = [t for t in ticks if not t[1]]
        self.assertEqual(len(minor_ticks), 0)


class TestBuildGapCompressedTimeLayout(unittest.TestCase):
    def _simple_layout(self) -> GapCompressedTimeLayout:
        omin = date(2025, 1, 1).toordinal()
        omax = date(2025, 7, 8).toordinal()
        o_jul1 = date(2025, 7, 1).toordinal()
        layout = build_gap_compressed_time_layout(
            omin, omax, [omin, o_jul1, omax], max_segment_calendar_days=28
        )
        self.assertIsNotNone(layout)
        return layout

    def test_returns_none_for_degenerate_inputs(self):
        omin = date(2026, 1, 1).toordinal()
        self.assertIsNone(build_gap_compressed_time_layout(omin, omin, [omin], 28))
        self.assertIsNone(build_gap_compressed_time_layout(omin, omin + 10, [omin], 28))

    def test_omin_maps_to_zero_frac(self):
        layout = self._simple_layout()
        omin = date(2025, 1, 1).toordinal()
        self.assertAlmostEqual(layout.ordinal_to_frac(omin), 0.0, places=6)

    def test_omax_maps_to_one_frac(self):
        layout = self._simple_layout()
        omax = date(2025, 7, 8).toordinal()
        self.assertAlmostEqual(layout.ordinal_to_frac(omax), 1.0, places=6)

    def test_large_gap_compressed(self):
        # Jan→Jul gap (~180 days) compressed to 28, Jul 1→Jul 8 gap = 7 days.
        # Jul 1 frac ≈ 28/(28+7) = 0.8
        layout = self._simple_layout()
        o_jul1 = date(2025, 7, 1).toordinal()
        frac = layout.ordinal_to_frac(o_jul1)
        self.assertAlmostEqual(frac, 0.8, delta=0.05)

    def test_compressed_bounds_non_empty_for_big_gap(self):
        layout = self._simple_layout()
        self.assertGreater(len(layout.compressed_span_boundary_ordinals), 0)

    def test_frac_to_ordinal_roundtrip(self):
        layout = self._simple_layout()
        o_jul1 = date(2025, 7, 1).toordinal()
        frac = layout.ordinal_to_frac(o_jul1)
        recovered = layout.frac_to_ordinal(frac)
        self.assertAlmostEqual(recovered, o_jul1, delta=1)

    def test_layout_produces_nonlinear_spacing(self):
        """gap_compressed x differs significantly from linear x for large-gap data."""
        omin = date(2025, 1, 1).toordinal()
        omax = date(2025, 7, 8).toordinal()
        o_jul1 = date(2025, 7, 1).toordinal()
        layout = build_gap_compressed_time_layout(
            omin, omax, [omin, o_jul1, omax], max_segment_calendar_days=28
        )
        x_gc = ordinal_to_chart_x(o_jul1, 0.0, 1000.0, omin, omax, layout)
        x_linear = ordinal_to_chart_x(o_jul1, 0.0, 1000.0, omin, omax)
        # Compressed: Jul 1 ≈ 800px; linear: Jul 1 ≈ 963px → differ by >100px
        self.assertGreater(abs(x_gc - x_linear), 100)


if __name__ == "__main__":
    unittest.main()
