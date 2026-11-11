"""Shared chart layout utilities — calendar axis, gap compression, Catmull-Rom smoothing.

Used by both ChessLogCategoryChartWidget and DetailPlayerStatsView so the
implementations stay in one place. Both surfaces use identical coordinate
systems and tick-generation logic.
"""

from __future__ import annotations

import bisect
from datetime import date, timedelta
from typing import List, Optional, Tuple

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath


# ---------------------------------------------------------------------------
# Constants — shared by both chart surfaces
# ---------------------------------------------------------------------------

_AXIS_FALLBACK_DAY_MAX_SPAN_DAYS = 31
_AXIS_FALLBACK_WEEK_MAX_SPAN_DAYS = 120
_AXIS_FALLBACK_MONTH_MAX_SPAN_DAYS = 960

# strftime("%b") follows the process locale; keep chart labels English regardless of OS language.
_EN_MONTH_ABBREV = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


# ---------------------------------------------------------------------------
# Tick label formatters
# ---------------------------------------------------------------------------

def _format_axis_tick_month_year(d: date) -> str:
    return f"{_EN_MONTH_ABBREV[d.month]} '{d.year % 100:02d}"


def _format_axis_tick_day_month(d: date) -> str:
    return f"{d.day} {_EN_MONTH_ABBREV[d.month]}"


# ---------------------------------------------------------------------------
# Standalone helpers (pure functions, no Qt dependencies)
# ---------------------------------------------------------------------------

def effective_calendar_mode(ordinal_min: int, ordinal_max: int) -> str:
    """Pick day/week/month/year tick density based on the ordinal span."""
    span = max(0, ordinal_max - ordinal_min)
    if span <= _AXIS_FALLBACK_DAY_MAX_SPAN_DAYS:
        return "day"
    if span <= _AXIS_FALLBACK_WEEK_MAX_SPAN_DAYS:
        return "week"
    if span <= _AXIS_FALLBACK_MONTH_MAX_SPAN_DAYS:
        return "month"
    return "year"


def week_start_monday_ordinal(ord_val: int) -> int:
    d = date.fromordinal(ord_val)
    return (d - timedelta(days=d.weekday())).toordinal()


def calendar_axis_ticks(
    ordinal_min: int,
    ordinal_max: int,
    mode: str,
    max_labels: int = 8,
    *,
    month_ticks_in_year_mode: bool = True,
    week_minors_in_month_mode: bool = False,
) -> List[Tuple[int, bool, str]]:
    """Generate calendar tick positions as (ordinal, is_major, label) tuples.

    Args:
        ordinal_min:               First day ordinal of the axis range.
        ordinal_max:               Last day ordinal of the axis range.
        mode:                      One of "day", "week", "month", "year".
        max_labels:                Maximum number of labelled ticks.
        month_ticks_in_year_mode:  Add minor month ticks when year span ≤ 3.
        week_minors_in_month_mode: Add minor week ticks in month mode.
    """
    omin, omax = ordinal_min, ordinal_max
    if omax <= omin:
        return []
    max_l = max(4, max_labels)
    ticks: List[Tuple[int, bool, str]] = []
    majors: set = set()

    if mode == "year":
        y0 = date.fromordinal(omin).year
        y1 = date.fromordinal(omax).year
        for y in range(y0, y1 + 1):
            o = date(y, 1, 1).toordinal()
            if omin <= o <= omax:
                ticks.append((o, True, str(y)))
                majors.add(o)
        if month_ticks_in_year_mode and (y1 - y0) <= 3:
            cur = date(y0, 1, 1)
            end_d = date(y1, 12, 1)
            while cur <= end_d:
                o = cur.toordinal()
                if omin <= o <= omax and o not in majors:
                    ticks.append((o, False, ""))
                if cur.month == 12:
                    cur = date(cur.year + 1, 1, 1)
                else:
                    cur = date(cur.year, cur.month + 1, 1)

    elif mode == "month":
        d0 = date.fromordinal(omin)
        d1 = date.fromordinal(omax)
        cur = date(d0.year, d0.month, 1)
        end_m = date(d1.year, d1.month, 1)
        while cur <= end_m:
            o = cur.toordinal()
            if omin <= o <= omax:
                ticks.append((o, True, _format_axis_tick_month_year(cur)))
                majors.add(o)
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        if week_minors_in_month_mode:
            w = week_start_monday_ordinal(omin)
            while w < omin:
                w += 7
            while w <= omax:
                if w not in majors:
                    ticks.append((w, False, ""))
                w += 7

    elif mode == "week":
        w = week_start_monday_ordinal(omin)
        while w < omin:
            w += 7
        idx = 0
        label_every = max(1, int(max(1, (omax - omin) // 7) // max_l) + 1)
        while w <= omax:
            lbl = _format_axis_tick_day_month(date.fromordinal(w)) if idx % label_every == 0 else ""
            ticks.append((w, True, lbl))
            idx += 1
            w += 7

    else:  # day
        span_days = omax - omin
        step = max(1, (span_days + max_l - 1) // max_l)
        o = omin
        while o <= omax:
            ticks.append((o, True, _format_axis_tick_day_month(date.fromordinal(o))))
            o += step
        if ticks and ticks[-1][0] < omax:
            ticks.append((omax, True, _format_axis_tick_day_month(date.fromordinal(omax))))

    ticks.sort(key=lambda t: t[0])
    return ticks


# ---------------------------------------------------------------------------
# Gap-compressed time layout
# ---------------------------------------------------------------------------

class GapCompressedTimeLayout:
    """Non-linear map calendar ordinal → horizontal fraction.

    Long game-free spans use less horizontal width. Used by both Chess Log
    charts and Player Stats charts for the 'gap_compressed' x-axis mode.
    """

    __slots__ = ("_knots", "_cum", "_compressed_bounds")

    def __init__(
        self,
        knots: List[int],
        cum_display: List[float],
        compressed_span_boundary_ordinals: frozenset,
    ) -> None:
        self._knots = tuple(knots)
        self._cum = tuple(cum_display)
        self._compressed_bounds = compressed_span_boundary_ordinals

    @property
    def compressed_span_boundary_ordinals(self) -> frozenset:
        """Knot ordinals at ends of segments where calendar span exceeded the cap."""
        return self._compressed_bounds

    def ordinal_to_frac(self, o: int) -> float:
        if not self._knots:
            return 0.0
        o = max(self._knots[0], min(self._knots[-1], o))
        for i in range(len(self._knots) - 1):
            lo, hi = self._knots[i], self._knots[i + 1]
            if lo <= o <= hi:
                span = hi - lo
                f0, f1 = self._cum[i], self._cum[i + 1]
                if span <= 0:
                    return f1
                t = (o - lo) / span
                return f0 + t * (f1 - f0)
        return self._cum[-1]

    def frac_to_ordinal(self, frac: float) -> int:
        """Inverse of ``ordinal_to_frac`` for hover / crosshair date hints."""
        if not self._knots:
            return 0
        frac = max(0.0, min(1.0, frac))
        cum = self._cum
        knots = self._knots
        i = bisect.bisect_right(cum, frac) - 1
        i = max(0, min(i, len(cum) - 2))
        f0, f1 = cum[i], cum[i + 1]
        lo, hi = knots[i], knots[i + 1]
        denom = f1 - f0
        if denom <= 1e-15:
            return int(hi)
        t = (frac - f0) / denom
        return int(round(lo + t * (hi - lo)))


def build_gap_compressed_time_layout(
    omin: int,
    omax: int,
    bin_center_ordinals: List[int],
    max_segment_calendar_days: int,
) -> Optional[GapCompressedTimeLayout]:
    """Build a GapCompressedTimeLayout from bin center ordinals.

    Each segment's horizontal weight is capped at max_segment_calendar_days so
    long stretches with no bins don't dominate the axis.
    """
    if omax <= omin or max_segment_calendar_days < 1:
        return None
    uniq = sorted({int(c) for c in bin_center_ordinals})
    if len(uniq) < 2:
        return None
    k0 = min(omin, uniq[0])
    kn = max(omax, uniq[-1])
    if kn <= k0:
        return None
    knots: List[int] = [k0]
    for c in uniq:
        if c <= k0:
            continue
        if c >= kn:
            break
        if c > knots[-1]:
            knots.append(c)
    if kn > knots[-1]:
        knots.append(kn)
    fixed: List[int] = [knots[0]]
    for k in knots[1:]:
        if k > fixed[-1]:
            fixed.append(k)
    knots = fixed
    if len(knots) < 2:
        return None
    weights: List[float] = []
    compressed_bounds: set = set()
    for i in range(len(knots) - 1):
        d = knots[i + 1] - knots[i]
        weights.append(max(1.0, float(min(d, max_segment_calendar_days))))
        if d > max_segment_calendar_days:
            compressed_bounds.add(int(knots[i]))
            compressed_bounds.add(int(knots[i + 1]))
    total = sum(weights)
    if total <= 0:
        return None
    cum: List[float] = [0.0]
    for w in weights:
        cum.append(cum[-1] + w / total)
    cum[-1] = 1.0
    return GapCompressedTimeLayout(knots, cum, frozenset(compressed_bounds))


def ordinal_to_chart_x(
    o: int,
    left: float,
    graph_width: float,
    omin: int,
    omax: int,
    layout: Optional[GapCompressedTimeLayout] = None,
) -> float:
    """Convert a day ordinal to a pixel x-coordinate.

    Args:
        o:            The ordinal to convert.
        left:         Left edge of the chart plot area in pixels.
        graph_width:  Width of the chart plot area in pixels.
        omin:         Ordinal of the left axis boundary.
        omax:         Ordinal of the right axis boundary.
        layout:       Optional gap-compressed layout; None → linear.
    """
    if layout is not None and omax > omin:
        o = max(omin, min(omax, o))
        f = layout.ordinal_to_frac(o)
        f0 = layout.ordinal_to_frac(omin)
        f1 = layout.ordinal_to_frac(omax)
        span_f = f1 - f0
        if span_f > 1e-15:
            return left + (f - f0) / span_f * graph_width
    span = max(1, omax - omin)
    return left + (o - omin) / span * graph_width


# ---------------------------------------------------------------------------
# Catmull-Rom smooth polyline
# ---------------------------------------------------------------------------

def smooth_polyline_path(
    run: List[QPointF], *, strength: float = 1.0
) -> Optional[QPainterPath]:
    """Cubic Bézier chain (Catmull-Rom style) through ``run`` for a flowing line.

    Vertices are preserved as segment endpoints; the curve may bulge slightly
    past straight chords at sharp turns. ``strength`` scales handle tension:
    0 ≈ straight segments, ~1 default, >1 more wavy.
    """
    n = len(run)
    if n < 2:
        return None
    path = QPainterPath(run[0])
    if n == 2:
        path.lineTo(run[1])
        return path
    if strength < 0.05:
        for k in range(n - 1):
            path.lineTo(run[k + 1])
        return path
    k = strength / 6.0

    def _pt(i: int) -> QPointF:
        return run[max(0, min(n - 1, i))]

    for i in range(n - 1):
        p_im1 = _pt(i - 1) if i > 0 else QPointF(2 * run[0].x() - run[1].x(), 2 * run[0].y() - run[1].y())
        p_i = run[i]
        p_ip1 = run[i + 1]
        p_ip2 = (
            run[i + 2]
            if i + 2 < n
            else QPointF(2 * run[n - 1].x() - run[n - 2].x(), 2 * run[n - 1].y() - run[n - 2].y())
        )
        c1 = QPointF(
            p_i.x() + (p_ip1.x() - p_im1.x()) * k,
            p_i.y() + (p_ip1.y() - p_im1.y()) * k,
        )
        c2 = QPointF(
            p_ip1.x() - (p_ip2.x() - p_i.x()) * k,
            p_ip1.y() - (p_ip2.y() - p_i.y()) * k,
        )
        path.cubicTo(c1, c2, p_ip1)
    return path
