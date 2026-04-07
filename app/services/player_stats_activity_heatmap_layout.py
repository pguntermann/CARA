"""Layout math for Player Stats activity heatmap (no Qt)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.player_stats_activity_heatmap_user import (
    normalize_player_stats_activity_heatmap_settings,
)

# strftime("%b") follows the process locale; keep heatmap month labels English like other player-stats charts.
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


def effective_ordinal_for_heatmap(
    partial_dates: str,
    full_o: Optional[int],
    trends_o: Optional[int],
) -> Optional[int]:
    """Pick per-game ordinal: full dates only, or trends stand-in when partial."""
    if partial_dates == "exclude":
        return full_o
    if full_o is not None:
        return full_o
    return trends_o


def _monday_on_or_before(ordinal: int) -> int:
    d = date.fromordinal(ordinal)
    return ordinal - d.weekday()


def _sunday_on_or_before(ordinal: int) -> int:
    d = date.fromordinal(ordinal)
    return ordinal - ((d.weekday() + 1) % 7)


def trim_range_ordinals(
    ordinals: Sequence[int],
    date_range_mode: str,
    today_ordinal: int,
) -> Tuple[int, int]:
    """Inclusive ordinal range for the heatmap window."""
    if date_range_mode == "rolling_12_months":
        end_o = today_ordinal
        return end_o - 364, end_o
    if date_range_mode == "rolling_24_months":
        end_o = today_ordinal
        return end_o - 729, end_o
    # ~12 / ~24 months ending at latest game in the analyzed set (not calendar "today")
    if date_range_mode == "games_12_months":
        if not ordinals:
            return today_ordinal, today_ordinal
        end_o = max(ordinals)
        return end_o - 364, end_o
    if date_range_mode == "games_24_months":
        if not ordinals:
            return today_ordinal, today_ordinal
        end_o = max(ordinals)
        return end_o - 729, end_o
    # trim_to_data
    if not ordinals:
        return today_ordinal, today_ordinal
    return min(ordinals), max(ordinals)


def _yearish_band_ranges(start_o: int, end_o: int) -> List[Tuple[int, int]]:
    """Split inclusive [start_o, end_o] into chunks of at most 365 days each, oldest first.

    Matches the rolling ~24 month split (first chunk 365 days, then the next, etc.).
    """
    if start_o > end_o:
        return []
    ranges: List[Tuple[int, int]] = []
    cur = start_o
    while cur <= end_o:
        hi = min(cur + 364, end_o)
        ranges.append((cur, hi))
        cur = hi + 1
    return ranges


def _week_anchor_end_cover(start_o: int, end_o: int, week_start: str) -> Tuple[int, int]:
    if week_start == "monday":
        anchor = _monday_on_or_before(start_o)
        end_cover = _monday_on_or_before(end_o) + 6
    else:
        anchor = _sunday_on_or_before(start_o)
        end_cover = _sunday_on_or_before(end_o) + 6
    return anchor, end_cover


def _build_calendar_day_grid(
    counts_by_day: Dict[int, int],
    start_o: int,
    end_o: int,
    week_start: str,
) -> Tuple[List[List[int]], List[List[str]], List[str], int, int, int, List[List[int]]]:
    """7 rows (weekday) × N columns (weeks), one cell per calendar day (GitHub-style)."""
    anchor, end_cover = _week_anchor_end_cover(start_o, end_o, week_start)
    n_cols = (end_cover - anchor + 1) // 7
    n_rows = 7
    grid = [[0] * n_cols for _ in range(n_rows)]
    labs = [[""] * n_cols for _ in range(n_rows)]
    ordinals = [[-1] * n_cols for _ in range(n_rows)]
    o = anchor
    while o <= end_cover:
        col = (o - anchor) // 7
        if week_start == "monday":
            row = date.fromordinal(o).weekday()
        else:
            row = (date.fromordinal(o).weekday() + 1) % 7
        if 0 <= col < n_cols and 0 <= row < n_rows:
            cnt = counts_by_day.get(o, 0)
            grid[row][col] = cnt
            ordinals[row][col] = int(o)
            iso = date.fromordinal(o).isoformat()
            labs[row][col] = f"{iso}\n{cnt} game(s)"
        o += 1
    if week_start == "monday":
        row_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    else:
        row_labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    return grid, labs, row_labels, n_rows, n_cols, anchor, ordinals


def _month_tick_label(prev_ym: Optional[Tuple[int, int]], d: date) -> str:
    """Short English month label; add year when calendar year changes."""
    mon = _EN_MONTH_ABBREV[d.month]
    if prev_ym is not None and d.year != prev_ym[0]:
        return f"{mon} {d.year}"
    return mon


def _month_ticks_day_calendar(anchor: int, n_cols: int) -> Tuple[Tuple[Tuple[Tuple[int, str], ...], ...], Tuple[int, ...]]:
    """One band above the grid. month_start_columns: cols where a new month begins (for stronger dividers)."""
    col_starts = [anchor + c * 7 for c in range(n_cols)]
    band: List[Tuple[int, str]] = []
    month_starts: List[int] = []
    prev_ym: Optional[Tuple[int, int]] = None
    for c, wo in enumerate(col_starts):
        wd = date.fromordinal(wo)
        ym = (wd.year, wd.month)
        if ym != prev_ym:
            band.append((c, _month_tick_label(prev_ym, wd)))
            month_starts.append(c)
        prev_ym = ym
    bands = (tuple(band),)
    return bands, tuple(month_starts)


@dataclass(frozen=True)
class ActivityHeatmapGridBand:
    """One month strip + 7 weekday rows × week columns."""

    n_rows: int
    n_cols: int
    counts: List[List[int]]
    labels: List[List[str]]
    row_labels: Tuple[str, ...]
    month_label_bands: Tuple[Tuple[Tuple[int, str], ...], ...]
    month_start_columns: Tuple[int, ...]
    cell_ordinals: Tuple[Tuple[int, ...], ...]


@dataclass(frozen=True)
class ActivityHeatmapPaintModel:
    """One or more stacked calendar bands (e.g. two years for ~24 month range)."""

    kind: str
    scale_max: float
    subcaption: str
    layout_style: str
    bands: Tuple[ActivityHeatmapGridBand, ...]


def _make_grid_band(
    counts_by_day: Dict[int, int],
    lo: int,
    hi: int,
    week_start: str,
    include_row_labels: bool,
) -> Optional[ActivityHeatmapGridBand]:
    if lo > hi:
        return None
    grid, labs, row_labels, n_rows, n_cols, anchor_dc, ordinals = _build_calendar_day_grid(
        counts_by_day, lo, hi, week_start
    )
    if n_cols <= 0:
        return None
    month_bands_t, month_cols = _month_ticks_day_calendar(anchor_dc, n_cols)
    ordinals_t = tuple(tuple(row) for row in ordinals)
    rl = tuple(row_labels) if include_row_labels else tuple()
    return ActivityHeatmapGridBand(
        n_rows=n_rows,
        n_cols=n_cols,
        counts=grid,
        labels=labs,
        row_labels=rl,
        month_label_bands=month_bands_t,
        month_start_columns=month_cols,
        cell_ordinals=ordinals_t,
    )


def _peak_across_bands(bands: Tuple[ActivityHeatmapGridBand, ...]) -> int:
    peak = 0
    for b in bands:
        for r in range(b.n_rows):
            for c in range(b.n_cols):
                peak = max(peak, b.counts[r][c])
    return peak


def build_activity_heatmap_paint_model(
    per_game_ordinals: Sequence[Tuple[Optional[int], Optional[int]]],
    user_settings: Optional[Dict[str, Any]],
    today_ordinal: int,
) -> Optional[ActivityHeatmapPaintModel]:
    """Build a paint model, or None when there is nothing to show."""
    usr = normalize_player_stats_activity_heatmap_settings(
        user_settings if isinstance(user_settings, dict) else None
    )
    partial = usr["partial_dates"]

    effective: List[int] = []
    for full_o, trends_o in per_game_ordinals:
        o = effective_ordinal_for_heatmap(partial, full_o, trends_o)
        if o is not None:
            effective.append(int(o))

    if not effective:
        return None

    start_o, end_o = trim_range_ordinals(effective, usr["date_range"], today_ordinal)
    if start_o > end_o:
        start_o, end_o = end_o, start_o
    in_window = [o for o in effective if start_o <= o <= end_o]

    counts_by_day: Dict[int, int] = {}
    for o in in_window:
        counts_by_day[o] = counts_by_day.get(o, 0) + 1

    week_start = usr["week_starts_on"]
    week_start_label = "Monday" if week_start == "monday" else "Sunday"
    sub_parts = ["Month"]
    sub_parts.append("weeks start " + week_start_label)
    dr = usr["date_range"]
    if dr == "trim_to_data":
        sub_parts.append("range: activity bounds")
    elif dr == "rolling_12_months":
        sub_parts.append("range: last ~12 months")
    elif dr == "rolling_24_months":
        sub_parts.append("range: last ~24 months")
    elif dr == "games_12_months":
        sub_parts.append("range: 1 year span to last game")
    elif dr == "games_24_months":
        sub_parts.append("range: 2 year span to last game")
    else:
        sub_parts.append("range: last ~24 months")
    if partial == "exclude":
        sub_parts.append("dates: full only")
    else:
        sub_parts.append("dates: partial stand-ins included")

    md = str(usr.get("month_divider_mode", "week_anchor")).strip().lower()
    if md == "calendar_mesh":
        sub_parts.append("month lines: calendar grid")
    elif md == "off":
        sub_parts.append("month lines: off")
    else:
        sub_parts.append("month lines: week-aligned")

    bands_t: Tuple[ActivityHeatmapGridBand, ...]
    layout_style: str

    span_days = end_o - start_o + 1

    if dr in ("rolling_24_months", "games_24_months") and span_days >= 730:
        # ~two years: split into two ~365-day bands (older on top, newer below) for larger cells.
        pivot = start_o + 364
        b0 = _make_grid_band(counts_by_day, start_o, pivot, week_start, True)
        b1 = _make_grid_band(counts_by_day, pivot + 1, end_o, week_start, False)
        if b0 is not None and b1 is not None:
            bands_t = (b0, b1)
            layout_style = "two_year_stacked"
            sub_parts.append("layout: older year above, newer below")
        else:
            b_single = _make_grid_band(counts_by_day, start_o, end_o, week_start, True)
            if b_single is None:
                return None
            bands_t = (b_single,)
            layout_style = "single_band"
    elif dr == "trim_to_data" and span_days > 365:
        # Same stacking as ~24 month mode: at most ~365 days per band for readable cell size.
        chunk_ranges = _yearish_band_ranges(start_o, end_o)
        built: List[ActivityHeatmapGridBand] = []
        for i, (lo, hi) in enumerate(chunk_ranges):
            b = _make_grid_band(counts_by_day, lo, hi, week_start, i == 0)
            if b is None:
                return None
            built.append(b)
        bands_t = tuple(built)
        if len(bands_t) == 2:
            layout_style = "two_year_stacked"
        else:
            layout_style = "multi_year_stacked"
        sub_parts.append("layout: older year above, newer below")
    else:
        b_single = _make_grid_band(counts_by_day, start_o, end_o, week_start, True)
        if b_single is None:
            return None
        bands_t = (b_single,)
        layout_style = "single_band"

    peak = _peak_across_bands(bands_t)
    if usr["color_scale_max_mode"] == "fixed":
        scale_max = float(max(1, int(usr["color_scale_max_fixed"])))
    else:
        scale_max = float(max(1, peak))

    return ActivityHeatmapPaintModel(
        kind="month",
        scale_max=scale_max,
        subcaption=" · ".join(sub_parts),
        layout_style=layout_style,
        bands=bands_t,
    )
