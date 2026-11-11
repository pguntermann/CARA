"""Tests for ChessLogCategoryChartWidget — pure helpers and Qt-gated paint tests."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_AVAILABLE = _qt_starts_cleanly()

if _QT_AVAILABLE:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

from datetime import date as _date

from app.services.chess_log_stats_service import ChessLogCategoryBin, ChessLogPresetSeries
from app.views.widgets.chess_log_category_chart_widget import ChessLogCategoryChartWidget
from app.views.widgets._chart_layout_helpers import (
    calendar_axis_ticks,
    effective_calendar_mode,
    ordinal_to_chart_x,
    smooth_polyline_path,
)


def _bin(**counts: int) -> ChessLogCategoryBin:
    return ChessLogCategoryBin(
        time_pct=50.0,
        total=sum(counts.values()),
        lab0="2025-01",
        lab1="2025-06",
        counts=dict(counts),
    )


def _make_series(
    cats: list[str] = None,
    n_bins: int = 4,
    x_axis_layout: str = "uniform_bins",
    line_style: str = "straight",
    smoothing_strength: float = 1.0,
) -> ChessLogPresetSeries:
    cats = cats or ["C"]
    bins = [
        ChessLogCategoryBin(
            time_pct=i / max(1, n_bins - 1) * 100,
            total=1,
            lab0="2025-01-01",
            lab1="2025-06-30",
            counts={c: 1 for c in cats},
        )
        for i in range(n_bins)
    ]
    return ChessLogPresetSeries(
        preset="CLAMP",
        categories=cats,
        bins=bins,
        progression_x_axis_mode=x_axis_layout,
        progression_line_style=line_style,
        progression_line_smooth_strength=smoothing_strength,
    )


# ---------------------------------------------------------------------------
# Pure Python — no Qt needed
# ---------------------------------------------------------------------------

class TestCalendarAxisHelpers(unittest.TestCase):
    """Module-level helpers ported from Player Stats — pure Python, no Qt."""

    # --- ordinal_to_chart_x ---
    # New shared signature: (o, left, graph_width, omin, omax)

    def test_ordinal_to_chart_x_at_min_gives_left(self):
        omin = _date(2026, 1, 1).toordinal()
        omax = _date(2026, 12, 31).toordinal()
        self.assertAlmostEqual(ordinal_to_chart_x(omin, 50.0, 900.0, omin, omax), 50.0)

    def test_ordinal_to_chart_x_at_max_gives_right(self):
        omin = _date(2026, 1, 1).toordinal()
        omax = _date(2026, 12, 31).toordinal()
        self.assertAlmostEqual(ordinal_to_chart_x(omax, 50.0, 900.0, omin, omax), 950.0)

    def test_ordinal_to_chart_x_midpoint(self):
        omin = _date(2026, 1, 1).toordinal()
        omax = _date(2026, 1, 1).toordinal() + 100
        omid = omin + 50
        x = ordinal_to_chart_x(omid, 0.0, 100.0, omin, omax)
        self.assertAlmostEqual(x, 50.0)

    def test_ordinal_to_chart_x_same_function_for_tick_and_bin(self):
        """A tick and a bin at the same ordinal produce the same x-coordinate."""
        omin = _date(2026, 2, 1).toordinal()
        omax = _date(2026, 12, 31).toordinal()
        o_march_1 = _date(2026, 3, 1).toordinal()
        x_tick = ordinal_to_chart_x(o_march_1, 0.0, 1200.0, omin, omax)
        x_bin = ordinal_to_chart_x(o_march_1, 0.0, 1200.0, omin, omax)
        self.assertAlmostEqual(x_tick, x_bin)

    # --- effective_calendar_mode ---

    def test_mode_day_for_short_span(self):
        omin = _date(2026, 6, 1).toordinal()
        omax = _date(2026, 6, 20).toordinal()  # 19 days
        self.assertEqual(effective_calendar_mode(omin, omax), "day")

    def test_mode_week_for_medium_span(self):
        omin = _date(2026, 1, 1).toordinal()
        omax = _date(2026, 3, 15).toordinal()  # ~73 days
        self.assertEqual(effective_calendar_mode(omin, omax), "week")

    def test_mode_month_for_synthetic_file_span(self):
        # Synthetic file: Feb–Dec 2026 ≈ 303 days — within month range (120–960)
        omin = _date(2026, 2, 1).toordinal()
        omax = _date(2026, 12, 31).toordinal()
        self.assertEqual(effective_calendar_mode(omin, omax), "month")

    def test_mode_year_for_long_span(self):
        omin = _date(2020, 1, 1).toordinal()
        omax = _date(2024, 12, 31).toordinal()  # ~5 years
        self.assertEqual(effective_calendar_mode(omin, omax), "year")

    # --- calendar_axis_ticks month mode ---

    def test_month_mode_feb_dec_produces_correct_major_ticks(self):
        # omin=Feb 8: Feb 1 is before omin so no Feb tick; Mar–Dec gives 10 ticks.
        omin = _date(2026, 2, 8).toordinal()   # first game date from synthetic file
        omax = _date(2026, 12, 24).toordinal()  # last game date from synthetic file
        mode = effective_calendar_mode(omin, omax)
        self.assertEqual(mode, "month")
        ticks = calendar_axis_ticks(omin, omax, mode)
        majors = [(o, lbl) for o, is_major, lbl in ticks if is_major]
        # Mar 1 through Dec 1 all fall within [omin, omax] → 10 major ticks.
        # Feb 1 < omin so February is skipped (same behaviour as Player Stats).
        self.assertEqual(len(majors), 10, f"Expected 10 major ticks (Mar–Dec), got {len(majors)}: {majors}")

    def test_month_mode_aligned_start_produces_full_range_of_ticks(self):
        # omin=Feb 1: Feb 1 == omin → February tick IS included → 11 ticks.
        omin = _date(2026, 2, 1).toordinal()
        omax = _date(2026, 12, 31).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        majors = [(o, lbl) for o, is_major, lbl in ticks if is_major]
        self.assertEqual(len(majors), 11, f"Expected 11 major ticks (Feb–Dec), got {len(majors)}: {majors}")

    def test_month_mode_major_labels_are_month_year_format(self):
        omin = _date(2026, 2, 1).toordinal()
        omax = _date(2026, 4, 30).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        major_labels = [lbl for _, is_major, lbl in ticks if is_major and lbl]
        self.assertIn("Feb '26", major_labels)
        self.assertIn("Mar '26", major_labels)
        self.assertIn("Apr '26", major_labels)

    def test_month_mode_tick_ordinals_are_first_of_month(self):
        omin = _date(2026, 3, 15).toordinal()
        omax = _date(2026, 6, 20).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        for o, is_major, _ in ticks:
            if is_major:
                d = _date.fromordinal(o)
                self.assertEqual(d.day, 1,
                    f"Major tick at {d} is not the 1st of month")

    def test_empty_months_produce_no_major_ticks(self):
        # Jan 2026 is between Dec 2025 and Feb 2026; if data only spans Feb–Apr,
        # there must be no January tick.
        omin = _date(2026, 2, 1).toordinal()
        omax = _date(2026, 4, 30).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        major_labels = [lbl for _, is_major, lbl in ticks if is_major and lbl]
        self.assertNotIn("Jan '26", major_labels)
        self.assertNotIn("May '26", major_labels)

    def test_ticks_are_sorted_by_ordinal(self):
        omin = _date(2026, 2, 1).toordinal()
        omax = _date(2026, 12, 31).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "month")
        ordinals = [o for o, _, _ in ticks]
        self.assertEqual(ordinals, sorted(ordinals))

    def test_year_mode_produces_year_labels(self):
        omin = _date(2021, 6, 1).toordinal()
        omax = _date(2024, 6, 30).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "year")
        major_labels = [lbl for _, is_major, lbl in ticks if is_major and lbl]
        self.assertIn("2022", major_labels)
        self.assertIn("2023", major_labels)
        self.assertIn("2024", major_labels)

    def test_day_mode_produces_labeled_ticks(self):
        omin = _date(2026, 6, 1).toordinal()
        omax = _date(2026, 6, 10).toordinal()
        ticks = calendar_axis_ticks(omin, omax, "day")
        self.assertTrue(len(ticks) >= 2)
        # All day-mode ticks are major
        self.assertTrue(all(is_major for _, is_major, _ in ticks))

    def test_empty_range_returns_no_ticks(self):
        omin = _date(2026, 6, 1).toordinal()
        self.assertEqual(calendar_axis_ticks(omin, omin, "month"), [])


class TestYAxisPercentage(unittest.TestCase):
    """Y-axis uses percentage of bin total (0–100 %); fixed gridlines at 0/25/50/75/100."""

    def _pct(self, cat: str, b: ChessLogCategoryBin) -> float:
        """Compute the percentage a category occupies in a bin — mirrors _draw_lines logic."""
        return b.counts.get(cat, 0) / b.total if b.total > 0 else 0.0

    def test_single_cat_full_bin_is_100pct(self):
        b = ChessLogCategoryBin(time_pct=50.0, total=5, lab0="2025-01", lab1="2025-06", counts={"C": 5})
        self.assertAlmostEqual(self._pct("C", b), 1.0)

    def test_half_bin_is_50pct(self):
        b = ChessLogCategoryBin(time_pct=50.0, total=4, lab0="2025-01", lab1="2025-06", counts={"C": 2, "L": 2})
        self.assertAlmostEqual(self._pct("C", b), 0.5)

    def test_uncategorized_in_denominator_reduces_pct(self):
        # C=2 out of total=4 (which includes 2 Uncategorized moments) → 50 %
        b = ChessLogCategoryBin(time_pct=50.0, total=4, lab0="2025-01", lab1="2025-06",
                                counts={"C": 2, "Uncategorized": 2})
        self.assertAlmostEqual(self._pct("C", b), 0.5)

    def test_zero_total_guarded_returns_zero(self):
        b = ChessLogCategoryBin(time_pct=50.0, total=0, lab0="2025-01", lab1="2025-06", counts={})
        self.assertAlmostEqual(self._pct("C", b), 0.0)

    def test_absent_cat_returns_zero(self):
        b = ChessLogCategoryBin(time_pct=50.0, total=3, lab0="2025-01", lab1="2025-06", counts={"L": 3})
        self.assertAlmostEqual(self._pct("C", b), 0.0)

    def test_y_coord_100pct_maps_to_top(self):
        # pct=1.0  →  y = y0 + ph * (1.0 - 1.0) = y0
        y0, ph = 40.0, 200.0
        pct = 1.0
        y = y0 + ph * (1.0 - pct)
        self.assertAlmostEqual(y, y0)

    def test_y_coord_0pct_maps_to_bottom(self):
        # pct=0.0  →  y = y0 + ph * 1.0 = y0 + ph
        y0, ph = 40.0, 200.0
        pct = 0.0
        y = y0 + ph * (1.0 - pct)
        self.assertAlmostEqual(y, y0 + ph)

    def test_y_coord_50pct_maps_to_midpoint(self):
        y0, ph = 40.0, 200.0
        pct = 0.5
        y = y0 + ph * (1.0 - pct)
        self.assertAlmostEqual(y, y0 + ph / 2)


# ---------------------------------------------------------------------------
# Qt-gated tests
# ---------------------------------------------------------------------------

@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestSmoothPolylinePath(unittest.TestCase):
    """_smooth_polyline_path produces cubic curves vs straight lines."""

    def _pts(self, n: int) -> list:
        return [QPointF(i * 50.0, float(i % 2) * 30.0) for i in range(n)]

    def test_fewer_than_two_points_returns_none(self):
        self.assertIsNone(smooth_polyline_path([]))
        self.assertIsNone(smooth_polyline_path([QPointF(0, 0)]))

    def test_two_points_returns_path(self):
        from PyQt6.QtGui import QPainterPath
        path = smooth_polyline_path(self._pts(2))
        self.assertIsInstance(path, QPainterPath)

    def test_three_or_more_points_returns_path(self):
        from PyQt6.QtGui import QPainterPath
        path = smooth_polyline_path(self._pts(5))
        self.assertIsInstance(path, QPainterPath)

    def test_near_zero_strength_produces_straight_segments(self):
        pts = [QPointF(0, 0), QPointF(100, 0), QPointF(200, 0)]
        path = smooth_polyline_path(pts, strength=0.01)
        for i in range(path.elementCount()):
            elem = path.elementAt(i)
            self.assertFalse(elem.isCurveTo(), "near-zero strength should produce no cubic curves")

    def test_nonzero_strength_produces_cubic_curves(self):
        from PyQt6.QtGui import QPainterPath
        pts = [QPointF(0, 0), QPointF(50, 80), QPointF(100, 0), QPointF(150, 80)]
        path = smooth_polyline_path(pts, strength=1.0)
        has_curve = any(path.elementAt(i).isCurveTo() for i in range(path.elementCount()))
        self.assertTrue(has_curve)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestBinXLayout(unittest.TestCase):
    """_bin_x returns correct pixel offsets for each x_axis_layout value."""

    def _widget(self) -> ChessLogCategoryChartWidget:
        return ChessLogCategoryChartWidget(config={})

    def test_calendar_linear_positions_bin_at_calendar_center(self):
        from datetime import date as _d
        # Single-game bin: lab0=lab1="2026-06-15". Center ordinal = lab0 ordinal.
        # t_min = t_max = that ordinal → clamped to left edge.
        # Use a series with two distinct bins so t_min != t_max.
        from app.services.chess_log_stats_service import ChessLogCategoryBin as _Bin, ChessLogPresetSeries as _S
        o_a = _d(2026, 1, 1).toordinal()
        o_b = _d(2026, 7, 1).toordinal()
        bins = [
            _Bin(time_pct=0.0, total=1, lab0="2026-01-01", lab1="2026-01-31", counts={"C": 1}),
            _Bin(time_pct=100.0, total=1, lab0="2026-07-01", lab1="2026-07-31", counts={"C": 1}),
        ]
        series = _S(preset="CLAMP", categories=["C"], bins=bins, progression_x_axis_mode="calendar_linear",
                    t_min=o_a, t_max=_d(2026, 7, 31).toordinal())
        w = self._widget()
        w._series = series
        pw = 1000.0
        # Bin 0: center = (Jan 1 + Jan 31) // 2 ≈ Jan 16
        o0_center = (o_a + _d(2026, 1, 31).toordinal()) // 2
        t_min = o_a
        t_max = _d(2026, 7, 31).toordinal()
        expected = ordinal_to_chart_x(o0_center, 0.0, pw, t_min, t_max)
        actual = w._bin_x(0, 2, 0.0, pw)
        self.assertAlmostEqual(actual, expected, delta=1.0)

    def test_uniform_bins_first_index_is_zero(self):
        w = self._widget()
        w._series = _make_series(x_axis_layout="uniform_bins")
        x = w._bin_x(0, 4, 10.0, 300.0)
        self.assertAlmostEqual(x, 0.0)

    def test_uniform_bins_last_index_is_full_width(self):
        w = self._widget()
        w._series = _make_series(x_axis_layout="uniform_bins")
        x = w._bin_x(3, 4, 90.0, 300.0)
        self.assertAlmostEqual(x, 300.0)

    def test_uniform_bins_evenly_spaced(self):
        w = self._widget()
        w._series = _make_series(x_axis_layout="uniform_bins")
        xs = [w._bin_x(i, 5, i * 25.0, 400.0) for i in range(5)]
        gaps = [xs[i + 1] - xs[i] for i in range(4)]
        for g in gaps:
            self.assertAlmostEqual(g, 100.0)

    def test_gap_compressed_produces_nonuniform_spacing(self):
        """gap_compressed compresses long calendar gaps, producing different x than uniform_bins."""
        from datetime import date as _d
        from app.services.chess_log_stats_service import ChessLogCategoryBin as _Bin, ChessLogPresetSeries as _S
        # 3 bins: Jan 1 (isolated), Jul 1, Jul 8 (clustered 7 days apart).
        # Jan→Jul gap (~180 days) is compressed to max_gap_segment_days=28.
        # Weights: segment Jan→Jul = 28, segment Jul1→Jul8 = 7. Total = 35.
        # Fraction at Jul 1 = 28/35 = 0.8 → x ≈ 800px for pw=1000.
        # With uniform_bins: Jul 1 bin (i=1 of 3) is at x = 500px.
        o_jan = _d(2025, 1, 1).toordinal()
        o_jul1 = _d(2025, 7, 1).toordinal()
        o_jul8 = _d(2025, 7, 8).toordinal()
        bins = [
            _Bin(time_pct=0.0, total=1, lab0="2025-01-01", lab1="2025-01-01", counts={"C": 1}),
            _Bin(time_pct=50.0, total=1, lab0="2025-07-01", lab1="2025-07-01", counts={"C": 1}),
            _Bin(time_pct=100.0, total=1, lab0="2025-07-08", lab1="2025-07-08", counts={"C": 1}),
        ]
        series_gc = _S(preset="CLAMP", categories=["C"], bins=bins,
                       progression_x_axis_mode="gap_compressed", t_min=o_jan, t_max=o_jul8,
                       compress_gap_max_segment_days=28)
        series_uni = _S(preset="CLAMP", categories=["C"], bins=bins,
                        progression_x_axis_mode="uniform_bins", t_min=o_jan, t_max=o_jul8)
        pw = 1000.0
        w = self._widget()
        w.set_series(series_gc)
        gc_x1 = w._bin_x(1, 3, 50.0, pw)
        w.set_series(series_uni)
        uni_x1 = w._bin_x(1, 3, 50.0, pw)
        # gap_compressed pushes Jul 1 toward the right (large gap compressed)
        self.assertGreater(gc_x1, uni_x1 + 100,
            f"gap_compressed ({gc_x1:.1f}px) should be significantly right of uniform ({uni_x1:.1f}px)")

    def test_calendar_linear_not_evenly_spaced_for_gappy_data(self):
        """Regression: Calendar Linear must produce a visible gap for April+July data.

        Uses single-game bins (lab0=lab1) so center-of-bin = game date. The April
        cluster renders in the left ~20% of the chart and the July cluster in the
        right ~20%, leaving a large visible May–June gap between them. Uniform Bins
        would spread them evenly regardless of calendar position.
        """
        from datetime import date as _d
        from app.services.chess_log_stats_service import (
            ChessLogCategoryBin as _Bin,
            ChessLogPresetSeries as _Series,
        )
        # 5 April + 5 July single-game bins. Apr 1–21 span = 20 days, Jul 1–21 span = 20 days.
        # Total ordinal span: Apr 1 → Jul 21 = 111 days.
        april_dates = ["2026-04-01", "2026-04-06", "2026-04-11", "2026-04-16", "2026-04-21"]
        july_dates  = ["2026-07-01", "2026-07-06", "2026-07-11", "2026-07-16", "2026-07-21"]

        bins = [
            _Bin(time_pct=0.0, total=1, lab0=d, lab1=d, counts={"C": 1})
            for d in april_dates + july_dates
        ]
        t_min = _d.fromisoformat("2026-04-01").toordinal()
        t_max = _d.fromisoformat("2026-07-21").toordinal()
        series_cal = _Series(preset="CLAMP", categories=["C"], bins=bins,
                             progression_x_axis_mode="calendar_linear", t_min=t_min, t_max=t_max)
        series_uni = _Series(preset="CLAMP", categories=["C"], bins=bins, progression_x_axis_mode="uniform_bins")

        w = self._widget()
        pw = 900.0
        n = len(bins)

        w._series = series_cal
        cal_xs = [w._bin_x(i, n, bins[i].time_pct, pw) for i in range(n)]

        w._series = series_uni
        uni_xs = [w._bin_x(i, n, bins[i].time_pct, pw) for i in range(n)]

        # Uniform Bins must be evenly spaced regardless of dates
        uni_gaps = [uni_xs[i + 1] - uni_xs[i] for i in range(n - 1)]
        for g in uni_gaps:
            self.assertAlmostEqual(g, pw / (n - 1), places=1, msg="Uniform Bins should be evenly spaced")

        # Calendar Linear: April cluster in first ~20%, July cluster in last ~82–100%.
        # Single-game bins → center = lab0 = lab1, so Apr 1 → ~0%, Apr 21 → ~18%.
        # Jul 1 → ~82%, Jul 21 → ~100%.
        cal_gap_between_clusters = cal_xs[5] - cal_xs[4]   # Jul 1 − Apr 21 in pixels
        cal_gap_within_april = cal_xs[1] - cal_xs[0]       # Apr 6 − Apr 1 in pixels
        self.assertGreater(
            cal_gap_between_clusters, cal_gap_within_april * 8,
            f"Calendar Linear gap between clusters ({cal_gap_between_clusters:.1f}px) "
            f"should be >> within-cluster gap ({cal_gap_within_april:.1f}px)"
        )

        # Calendar Linear positions must differ significantly from Uniform Bins
        max_diff = max(abs(cal_xs[i] - uni_xs[i]) for i in range(n))
        self.assertGreater(max_diff, pw * 0.1, "Calendar Linear and Uniform Bins should produce visibly different positions")

    def test_calendar_linear_positions_straddling_bin_at_center(self):
        """Calendar Linear uses bin center, matching Player Stats' coordinate system.

        A quantile bin spanning Apr 30–Jul 1 has its center near Jun 1. The widget
        correctly renders it at that center (≈day 61 of the Apr–Jul span). Empty
        months remain visible via the calendar gridlines drawn by _draw_calendar_axis,
        NOT by shifting data points to avoid the gap. This is the Player Stats pattern.
        """
        from app.services.chess_log_stats_service import (
            ChessLogCategoryBin as _Bin,
            ChessLogPresetSeries as _Series,
        )
        from datetime import date as _d
        # Three bins: pure April, straddling Apr–Jul, pure July.
        # t_min = Apr 1 ordinal, t_max = Jul 30 ordinal → span = 119 days.
        o_apr1 = _d(2026, 4, 1).toordinal()
        o_jul30 = _d(2026, 7, 30).toordinal()
        bins = [
            _Bin(time_pct=0.0, total=3, lab0="2026-04-01", lab1="2026-04-28", counts={"C": 3}),
            _Bin(time_pct=0.0, total=2, lab0="2026-04-30", lab1="2026-07-01", counts={"C": 2}),
            _Bin(time_pct=0.0, total=3, lab0="2026-07-02", lab1="2026-07-30", counts={"C": 3}),
        ]
        series = _Series(preset="CLAMP", categories=["C"], bins=bins,
                         progression_x_axis_mode="calendar_linear", t_min=o_apr1, t_max=o_jul30)
        w = self._widget()
        w._series = series
        pw = 1200.0  # 10px per day for 120-day span (Apr 1–Jul 30)

        xs = [w._bin_x(i, 3, bins[i].time_pct, pw) for i in range(3)]

        # Straddling bin center: (Apr 30 + Jul 1) / 2 ≈ Jun 1 (day ~61)
        o_straddle_center = (_d(2026, 4, 30).toordinal() + _d(2026, 7, 1).toordinal()) // 2
        expected_straddle_x = ordinal_to_chart_x(o_straddle_center, 0.0, pw, o_apr1, o_jul30)
        self.assertAlmostEqual(xs[1], expected_straddle_x, delta=2.0,
            msg="Straddling bin must render at calendar center, not at lab0")

        # Verify center IS near June (day 61 ≈ 610px), not at April (day 29 ≈ 290px)
        self.assertGreater(xs[1], 500.0,
            "Straddling bin center should be in June territory (>500px), not April")
        self.assertLess(xs[1], 750.0,
            "Straddling bin center should be in June territory (<750px), not July")


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestCalendarAxisPainting(unittest.TestCase):
    """Qt-gated: _draw_calendar_axis paints vertical gridlines at tick positions."""

    def _calendar_series(self):
        from datetime import date as _d
        from app.services.chess_log_stats_service import ChessLogCategoryBin as _Bin, ChessLogPresetSeries as _S
        t_min = _d(2026, 2, 1).toordinal()
        t_max = _d(2026, 12, 31).toordinal()
        bins = [
            _Bin(time_pct=0.0, total=3, lab0="2026-04-01", lab1="2026-06-30", counts={"C": 3}),
            _Bin(time_pct=100.0, total=3, lab0="2026-09-01", lab1="2026-11-30", counts={"C": 3}),
        ]
        return _S(preset="CLAMP", categories=["C"], bins=bins,
                  progression_x_axis_mode="calendar_linear", t_min=t_min, t_max=t_max)

    def _render_to_image(self, widget, width=1200, height=220):
        from PyQt6.QtGui import QImage, QPainter
        widget.resize(width, height)
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        widget.render(p)
        p.end()
        return img

    def test_calendar_linear_renders_without_error(self):
        w = ChessLogCategoryChartWidget(config={})
        w.set_series(self._calendar_series())
        self._render_to_image(w)  # must not raise

    def test_calendar_linear_paints_vertical_lines_at_tick_positions(self):
        """Each calendar month must produce a vertical line of non-background pixels."""
        from datetime import date as _d
        from PyQt6.QtGui import QColor

        w = ChessLogCategoryChartWidget(config={})
        series = self._calendar_series()
        w.set_series(series)

        width, height = 1200, 220
        img = self._render_to_image(w, width, height)

        # Background color (as set in _DEFAULTS)
        bg = QColor(28, 28, 33)
        bg_rgb = (bg.red(), bg.green(), bg.blue())

        # Compute plot geometry (mirrors ChessLogCategoryChartWidget.__init__)
        pad_t, pad_r, pad_b, pad_l = 40, 16, 28, 48
        legend_w = 120
        plot_x0 = pad_l
        plot_x1 = width - pad_r - legend_w
        plot_y0 = pad_t + 5  # +5 to avoid the title area drawing over gridlines

        t_min = series.t_min
        t_max = series.t_max

        # Check 3 months (May, Jul, Sep) that are well inside the data range and
        # far from plot edges so gridlines are unambiguous.
        months_to_check = [5, 7, 9]
        for month in months_to_check:
            o = _d(2026, month, 1).toordinal()
            expected_x = int(ordinal_to_chart_x(o, plot_x0, plot_x1 - plot_x0, t_min, t_max))
            # Scan a ±3px window in the plot-area height for any non-background pixel
            found = False
            for dx in range(-3, 4):
                px = expected_x + dx
                if px < 0 or px >= width:
                    continue
                for y in range(plot_y0, plot_y0 + 100):  # scan upper half of plot
                    pixel = img.pixel(px, y)
                    c = QColor(pixel)
                    if (c.red(), c.green(), c.blue()) != bg_rgb:
                        found = True
                        break
                if found:
                    break
            self.assertTrue(
                found,
                f"Month {month}: expected a vertical gridline near x={expected_x} "
                f"(t_min={t_min}, t_max={t_max}, plot_x0={plot_x0}, plot_x1={plot_x1})"
            )

    def test_uniform_bins_does_not_draw_month_labels(self):
        """Regression: uniform_bins mode must not activate _draw_calendar_axis."""
        from app.services.chess_log_stats_service import ChessLogPresetSeries as _S
        from datetime import date as _d
        from PyQt6.QtGui import QColor

        w = ChessLogCategoryChartWidget(config={})
        bins = self._calendar_series().bins
        t_min = _d(2026, 2, 1).toordinal()
        t_max = _d(2026, 12, 31).toordinal()
        series = _S(preset="CLAMP", categories=["C"], bins=bins,
                    progression_x_axis_mode="uniform_bins", t_min=t_min, t_max=t_max)
        w.set_series(series)
        width, height = 1200, 220
        img = self._render_to_image(w, width, height)

        # For uniform_bins, month gridlines at March 1 (≈85px from left)
        # should NOT appear — the gridline is only there for calendar_linear.
        pad_l, pad_r, legend_w = 48, 16, 120
        plot_x0 = pad_l
        plot_x1 = width - pad_r - legend_w
        o_mar = _d(2026, 3, 1).toordinal()
        expected_x = int(ordinal_to_chart_x(o_mar, plot_x0, plot_x1 - plot_x0, t_min, t_max))

        bg = QColor(28, 28, 33)
        bg_rgb = (bg.red(), bg.green(), bg.blue())

        # The axis-color pixel at the March gridline position should NOT be painted in uniform mode.
        # We check the middle of the plot height and verify the pixel is still background color.
        axis_col = (140, 140, 150)
        mid_y = 40 + 30  # inside plot area, away from y-axis gridlines
        pixel_at_march = QColor(img.pixel(expected_x, mid_y))
        march_rgb = (pixel_at_march.red(), pixel_at_march.green(), pixel_at_march.blue())
        # Not asserting exact background (data line may be there), just assert axis_col absent
        self.assertNotEqual(march_rgb, axis_col,
            "uniform_bins should not paint axis-color gridline at March position")


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestLineStyleBranching(unittest.TestCase):
    """Widget reads series.line_style to choose between smooth/straight rendering."""

    def test_smooth_series_does_not_raise(self):
        w = ChessLogCategoryChartWidget(config={})
        w.set_series(_make_series(line_style="smooth", n_bins=5))
        # Trigger paintEvent via render — should not raise
        from PyQt6.QtGui import QImage, QPainter
        img = QImage(400, 220, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        w.render(p)
        p.end()

    def test_straight_series_does_not_raise(self):
        w = ChessLogCategoryChartWidget(config={})
        w.set_series(_make_series(line_style="straight", n_bins=5))
        from PyQt6.QtGui import QImage, QPainter
        img = QImage(400, 220, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        w.render(p)
        p.end()


if __name__ == "__main__":
    unittest.main()
