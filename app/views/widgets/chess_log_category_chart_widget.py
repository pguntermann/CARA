"""Category-frequency-over-time chart widget for Chess Log Charts tab.

Draws a multi-line chart where each line is one category from a single preset.
X-axis: time (bin.time_pct, 0-100) derived from game dates, or uniform bin index
        depending on the series' x_axis_layout field.
Y-axis: percentage of bin total (0–100 %).

Data entry point: set_series(series, colors)
  series: ChessLogPresetSeries from chess_log_stats_service
  colors: Dict[str, QColor] mapping category → color; falls back to palette
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from app.services.chess_log_stats_service import ChessLogCategoryBin, ChessLogPresetSeries
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.widgets._chart_layout_helpers import (
    GapCompressedTimeLayout,
    build_gap_compressed_time_layout,
    calendar_axis_ticks,
    effective_calendar_mode,
    ordinal_to_chart_x,
    smooth_polyline_path,
)


# Built-in rotating palette used when no config color is supplied.
_FALLBACK_PALETTE: List[Tuple[int, int, int]] = [
    (100, 180, 255),   # blue
    (100, 220, 140),   # green
    (255, 180, 70),    # amber
    (220, 110, 110),   # rose
    (180, 130, 220),   # lavender
    (80,  200, 210),   # teal
    (255, 140, 60),    # orange
    (200, 200, 100),   # yellow-green
]
# Uncategorized always gets this neutral grey so it visually separates from named cats.
_UNCATEGORIZED_COLOR: Tuple[int, int, int] = (130, 130, 140)

# Default inline config used when no config dict is supplied.
_DEFAULTS: Dict[str, Any] = {
    "height": 220,
    "background_color": [28, 28, 33],
    "grid_color": [55, 55, 62],
    "axis_color": [140, 140, 150],
    "text_color": [200, 200, 210],
    "title_color": [210, 210, 220],
    "line_width": 2,
    "legend_width": 120,
    "padding": [40, 16, 28, 48],  # top, right, bottom, left
    "font_family": "Helvetica Neue",
    "font_size": 9,
}


class ChessLogCategoryChartWidget(QWidget):
    """Line chart: one line per Chess Log category within a single preset."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        cfg = self._resolve_cfg(config or {})

        self._height = int(cfg.get("height", _DEFAULTS["height"]))
        self._bg = QColor(*cfg.get("background_color", _DEFAULTS["background_color"]))
        self._grid_color = QColor(*cfg.get("grid_color", _DEFAULTS["grid_color"]))
        self._axis_color = QColor(*cfg.get("axis_color", _DEFAULTS["axis_color"]))
        self._text_color = QColor(*cfg.get("text_color", _DEFAULTS["text_color"]))
        self._title_color = QColor(*cfg.get("title_color", _DEFAULTS["title_color"]))
        self._line_width = int(cfg.get("line_width", _DEFAULTS["line_width"]))
        self._legend_width = int(cfg.get("legend_width", _DEFAULTS["legend_width"]))
        self._padding = cfg.get("padding", _DEFAULTS["padding"])  # [top, right, bottom, left]
        font_family = resolve_font_family(cfg.get("font_family", _DEFAULTS["font_family"]))
        self._font_size = int(scale_font_size(cfg.get("font_size", _DEFAULTS["font_size"])))
        self._font = QFont(font_family, self._font_size)

        self._series: Optional[ChessLogPresetSeries] = None
        self._colors: Dict[str, QColor] = {}
        self._gap_layout: Optional[GapCompressedTimeLayout] = None

        self.setFixedHeight(self._height)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    @staticmethod
    def _resolve_cfg(top_config: Dict[str, Any]) -> Dict[str, Any]:
        return (
            top_config
            .get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("chess_log_charts", {})
            .get("chart", {})
        ) or {}

    def set_series(
        self,
        series: ChessLogPresetSeries,
        colors: Optional[Dict[str, QColor]] = None,
    ) -> None:
        """Load a new preset series and repaint."""
        self._series = series
        self._colors = colors or {}
        self._gap_layout = self._build_gap_layout(series)
        self.update()

    def clear(self) -> None:
        self._series = None
        self._colors = {}
        self._gap_layout = None
        self.update()

    def _build_gap_layout(self, series: ChessLogPresetSeries) -> Optional[GapCompressedTimeLayout]:
        t_min = series.t_min
        t_max = series.t_max
        if t_min is None or t_max is None or not series.bins:
            return None
        centers = []
        for b in series.bins:
            try:
                o0 = date.fromisoformat(b.lab0).toordinal()
                o1 = date.fromisoformat(b.lab1).toordinal()
                centers.append((o0 + o1) // 2)
            except (ValueError, TypeError):
                pass
        if not centers:
            return None
        return build_gap_compressed_time_layout(
            t_min, t_max, centers, series.compress_gap_max_segment_days
        )

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self._bg)

        if not self._series or not self._series.bins:
            painter.setPen(self._text_color)
            painter.setFont(self._font)
            painter.drawText(
                QRectF(0, 0, self.width(), self.height()),
                Qt.AlignmentFlag.AlignCenter,
                "No data",
            )
            return

        pad_t, pad_r, pad_b, pad_l = self._padding
        legend_w = self._legend_width
        plot_x0 = pad_l
        plot_x1 = self.width() - pad_r - legend_w
        plot_y0 = pad_t
        plot_y1 = self.height() - pad_b
        plot_w = max(1, plot_x1 - plot_x0)
        plot_h = max(1, plot_y1 - plot_y0)

        categories = self._series.categories
        bins = self._series.bins
        totals: Dict[str, int] = {
            cat: sum(b.counts.get(cat, 0) for b in bins) for cat in categories
        }
        self._draw_grid(painter, plot_x0, plot_y0, plot_x1, plot_y1, plot_w, plot_h)
        self._draw_axes(painter, plot_x0, plot_y0, plot_x1, plot_y1)
        if self._series.progression_x_axis_mode == "calendar_linear":
            self._draw_calendar_axis(painter, plot_x0, plot_y0, plot_x1, plot_y1)
        else:
            self._draw_x_labels(painter, bins, plot_x0, plot_y1, plot_w)
        self._draw_y_labels(painter, plot_x0, plot_y0, plot_y1, plot_h)
        self._draw_title(painter, plot_x0, plot_x1)
        self._draw_lines(painter, categories, bins, plot_x0, plot_y0, plot_w, plot_h, totals)
        self._draw_legend(painter, categories, plot_x1 + 8, plot_y0, legend_w - 8, totals)

    def _draw_grid(self, p, x0, y0, x1, y1, pw, ph) -> None:
        grid_pen = QPen(self._grid_color)
        grid_pen.setWidth(1)
        p.setPen(grid_pen)
        for i in range(5):  # 0%, 25%, 50%, 75%, 100%
            y = y1 - (i / 4) * ph
            p.drawLine(int(x0), int(y), int(x1), int(y))

    def _draw_axes(self, p, x0, y0, x1, y1) -> None:
        ax_pen = QPen(self._axis_color)
        ax_pen.setWidth(1)
        p.setPen(ax_pen)
        p.drawLine(int(x0), int(y0), int(x0), int(y1))  # Y axis
        p.drawLine(int(x0), int(y1), int(x1), int(y1))  # X axis

    def _draw_calendar_axis(self, p, x0: float, y0: float, x1: float, y1: float) -> None:
        """Draw vertical calendar gridlines and month labels for calendar_linear mode.

        Ported from detail_player_stats_view paintEvent axis block (lines 1460–1567).
        Uses _ordinal_to_chart_x and _calendar_axis_ticks so ticks and data points
        share an identical coordinate system by construction.
        """
        if not self._series or not self._series.bins:
            return
        t_min = self._series.t_min
        t_max = self._series.t_max
        if t_min is None:
            try:
                t_min = date.fromisoformat(self._series.bins[0].lab0).toordinal()
            except (ValueError, TypeError):
                return
        if t_max is None:
            try:
                t_max = date.fromisoformat(self._series.bins[-1].lab1).toordinal()
            except (ValueError, TypeError):
                return
        if t_max <= t_min:
            return

        mode = effective_calendar_mode(t_min, t_max)
        ticks = calendar_axis_ticks(t_min, t_max, mode)

        major_pen = QPen(self._axis_color, 1)
        minor_pen = QPen(self._grid_color, 1)

        for o, is_major, _lbl in ticks:
            x = ordinal_to_chart_x(o, x0, x1 - x0, t_min, t_max)
            p.setPen(major_pen if is_major else minor_pen)
            p.drawLine(int(x), int(y0), int(x), int(y1))

        p.setPen(self._text_color)
        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        min_spacing = fm.horizontalAdvance("MMM '00") + 4
        last_label_x = -1e9
        for o, is_major, lbl in ticks:
            if not lbl or not is_major:
                continue
            x = ordinal_to_chart_x(o, x0, x1 - x0, t_min, t_max)
            if x - last_label_x < min_spacing:
                continue
            tw = fm.horizontalAdvance(lbl)
            p.drawText(int(x - tw / 2), int(y1 + self._font_size + 2), lbl)
            last_label_x = x

    def _draw_x_labels(self, p, bins, x0, y_base, pw) -> None:
        p.setPen(self._text_color)
        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        prev_right = -999
        n = len(bins)
        for i, b in enumerate(bins):
            label = b.lab0[:7] if b.lab0 else ""  # "YYYY-MM" for all layout modes
            x = self._bin_x(i, n, b.time_pct, pw) + x0
            tw = fm.horizontalAdvance(label)
            lx = x - tw / 2
            if lx > prev_right + 4:
                p.drawText(int(lx), int(y_base + self._font_size + 2), label)
                prev_right = lx + tw

    def _bin_x(
        self,
        bin_index: int,
        n_bins: int,
        time_pct: float,
        pw: float,
    ) -> float:
        """Return the X pixel offset (from plot origin) for a given bin.

        Layout modes (from series.progression_x_axis_mode):
          - "uniform_bins":    evenly spaced by bin index, ignoring calendar gaps.
          - "calendar_linear": each bin at its calendar center via ordinal_to_chart_x.
          - "gap_compressed":  calendar position via GapCompressedTimeLayout built in
                               set_series; long game-free spans compressed. Falls back
                               to uniform spacing if the gap layout could not be built.
        """
        if not self._series:
            return (time_pct / 100.0) * pw
        layout = self._series.progression_x_axis_mode
        if layout == "calendar_linear":
            bins = self._series.bins
            if bin_index < len(bins):
                b = bins[bin_index]
                try:
                    o0 = date.fromisoformat(b.lab0).toordinal()
                    o1 = date.fromisoformat(b.lab1).toordinal()
                    center = (o0 + o1) // 2
                    t_min = self._series.t_min
                    t_max = self._series.t_max
                    if t_min is None:
                        t_min = date.fromisoformat(bins[0].lab0).toordinal()
                    if t_max is None:
                        t_max = date.fromisoformat(bins[-1].lab1).toordinal()
                    return ordinal_to_chart_x(center, 0.0, pw, t_min, t_max)
                except (ValueError, TypeError):
                    pass
            return (time_pct / 100.0) * pw
        if layout == "gap_compressed" and self._gap_layout is not None:
            bins = self._series.bins
            t_min = self._series.t_min
            t_max = self._series.t_max
            if t_min is not None and t_max is not None and bin_index < len(bins):
                b = bins[bin_index]
                try:
                    o0 = date.fromisoformat(b.lab0).toordinal()
                    o1 = date.fromisoformat(b.lab1).toordinal()
                    center = (o0 + o1) // 2
                    return ordinal_to_chart_x(center, 0.0, pw, t_min, t_max, self._gap_layout)
                except (ValueError, TypeError):
                    pass
        # uniform_bins (or gap_compressed fallback when layout unavailable): equal spacing
        if n_bins <= 1:
            return pw / 2
        return (bin_index / (n_bins - 1)) * pw

    def _draw_y_labels(self, p, x0, y0, y1, ph) -> None:
        p.setPen(self._text_color)
        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        for pct in (0, 25, 50, 75, 100):
            label = f"{pct}%"
            tw = fm.horizontalAdvance(label)
            y = y1 - (pct / 100.0) * ph
            p.drawText(int(x0 - tw - 4), int(y + self._font_size / 2), label)

    def _draw_title(self, p, x0, x1) -> None:
        if not self._series:
            return
        p.setPen(self._title_color)
        font = QFont(self._font)
        font.setBold(True)
        p.setFont(font)
        title = self._series.preset
        p.drawText(
            QRectF(x0, 4, x1 - x0, self._padding[0] - 4),
            Qt.AlignmentFlag.AlignCenter,
            title,
        )
        p.setFont(self._font)

    def _draw_lines(self, p, categories, bins, x0, y0, pw, ph, totals: Dict[str, int]) -> None:
        use_smooth = self._series and self._series.progression_line_style == "smooth"
        strength = self._series.progression_line_smooth_strength if self._series else 1.0
        n = len(bins)

        for idx, cat in enumerate(categories):
            if totals.get(cat, 0) == 0:
                continue
            color = self._cat_color(cat, idx)
            pen = QPen(color)
            pen.setWidth(self._line_width)
            p.setPen(pen)

            pts: List[QPointF] = []
            for i, b in enumerate(bins):
                x = x0 + self._bin_x(i, n, b.time_pct, pw)
                pct = b.counts.get(cat, 0) / b.total if b.total > 0 else 0.0
                y = y0 + ph * (1.0 - pct)
                pts.append(QPointF(x, y))

            if use_smooth and len(pts) >= 2:
                path = smooth_polyline_path(pts, strength=strength)
                if path:
                    p.drawPath(path)
            else:
                for i in range(1, len(pts)):
                    p.drawLine(int(pts[i - 1].x()), int(pts[i - 1].y()),
                               int(pts[i].x()), int(pts[i].y()))

            # Dot at each bin (drawn on top of whichever line style was used)
            p.setBrush(color)
            for pt in pts:
                p.drawEllipse(QRectF(pt.x() - 3, pt.y() - 3, 6, 6))

    def _draw_legend(self, p, categories, lx, ly, lw, totals: Dict[str, int]) -> None:
        p.setFont(self._font)
        fm = QFontMetrics(self._font)
        row_h = self._font_size + 6
        for idx, cat in enumerate(categories):
            has_data = totals.get(cat, 0) > 0
            color = self._cat_color(cat, idx)
            y = ly + idx * row_h
            swatch_color = QColor(color)
            if not has_data:
                swatch_color.setAlphaF(0.4)
            p.setBrush(swatch_color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(int(lx), int(y + 2), 10, self._font_size)
            p.setPen(self._axis_color if not has_data else self._text_color)
            label = "Uncategorized" if not cat else cat
            p.drawText(int(lx + 14), int(y + self._font_size), label[:24])

    def _cat_color(self, cat: str, idx: int) -> QColor:
        if cat in self._colors:
            return self._colors[cat]
        if not cat:
            return QColor(*_UNCATEGORIZED_COLOR)
        rgb = _FALLBACK_PALETTE[idx % len(_FALLBACK_PALETTE)]
        return QColor(*rgb)
