"""Per-game accuracy histogram for Player Stats (config + user settings)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRect, Qt, QSize
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from app.services.player_stats_accuracy_distribution_user import (
    normalize_player_stats_accuracy_distribution_settings,
)
from app.services.user_settings_service import UserSettingsService
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.detail_player_stats_view import _draw_bin_data_x_marker, _smooth_polyline_path


def _parse_color_ranges_list(raw: Any) -> List[Tuple[float, QColor]]:
    if not isinstance(raw, list) or len(raw) < 2:
        return []
    out: List[Tuple[float, QColor]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        max_acc = entry.get("max_acc")
        color = entry.get("color")
        if max_acc is None or not isinstance(color, (list, tuple)) or len(color) < 3:
            continue
        try:
            out.append((float(max_acc), QColor(int(color[0]), int(color[1]), int(color[2]))))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out if len(out) >= 2 else []


def _bar_pixel_spans(
    plot_left: int,
    plot_w: int,
    acc_edges: List[float],
    bar_gap: int,
    x_display_min: float = 0.0,
    x_display_max: float = 100.0,
) -> List[Tuple[int, int]]:
    """Non-overlapping (x0, width) for each bin; preserves order, respects gap.

    Accuracy ``acc_edges`` are mapped linearly from ``[x_display_min, x_display_max]`` to plot width
    (defaults 0–100 for full-range x-axis).
    """
    plot_right = plot_left + plot_w
    gap = max(0, int(bar_gap))
    n = len(acc_edges) - 1
    if n <= 0 or plot_w <= 0:
        return []
    span = float(x_display_max) - float(x_display_min)
    if span <= 1e-12:
        span = 1e-12
    # Right edge (exclusive) of the previous bar's pixel span.
    prev_excl = plot_left - gap
    out: List[Tuple[int, int]] = []
    for i in range(n):
        lo_f = plot_left + ((acc_edges[i] - x_display_min) / span) * plot_w
        hi_f = plot_left + ((acc_edges[i + 1] - x_display_min) / span) * plot_w
        x0 = max(plot_left, int(math.ceil(lo_f - 1e-9)), prev_excl + gap)
        x1 = max(x0 + 1, int(math.floor(hi_f + 1e-9)))
        x1 = min(x1, plot_right)
        w0 = x1 - x0
        if w0 < 1:
            w0 = min(1, max(0, plot_right - x0))
        out.append((x0, w0))
        prev_excl = x0 + w0
    return out


def _pen_style_from_config(style: str) -> Qt.PenStyle:
    if (style or "").strip().lower() == "dashed":
        return Qt.PenStyle.DashLine
    return Qt.PenStyle.SolidLine


class AccuracyDistributionChartWidget(QWidget):
    """Histogram of per-game accuracy; styling from config, skew/y-axis/bins/colors from user settings."""

    def __init__(
        self,
        config: Dict[str, Any],
        accuracy_values: List[float],
        text_color: QColor,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._accuracy_values: List[float] = accuracy_values or []
        self._fallback_text_color = text_color

        ui_config = config.get("ui", {})
        panel_config = ui_config.get("panels", {}).get("detail", {})
        self._player_stats_config = panel_config.get("player_stats", {})
        self._dist_config = self._player_stats_config.get("accuracy_distribution", {})

        self._height = int(self._dist_config.get("height", 200))
        self._margins = self._dist_config.get("padding", self._dist_config.get("margins", [16, 14, 16, 14]))
        if not isinstance(self._margins, (list, tuple)) or len(self._margins) < 4:
            self._margins = [16, 14, 16, 14]

        self._bar_corner_radius = int(self._dist_config.get("bar_corner_radius", 2))
        self._grid_major_count = max(2, int(self._dist_config.get("grid_major_horizontal_lines", 5)))
        self._x_grid_minor = bool(self._dist_config.get("x_axis_minor_grid", True))

        self._dist_hover_ctx: Optional[Dict[str, Any]] = None
        self._hover_pixel: Optional[QPointF] = None
        self._hover_vertex_index: Optional[int] = None
        self.setMouseTracking(True)
        self.setMinimumHeight(self._height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._sync_dist_visual_settings()

    def _sync_dist_visual_settings(self) -> None:
        """Axis font and static chrome from config; distribution line pen from config only; curve/strength from user settings."""
        d = self._dist_cfg()
        usr = normalize_player_stats_accuracy_distribution_settings(self._user())
        fonts_block = self._player_stats_config.get("fonts", {})
        self._axis_font_family = resolve_font_family(
            d.get("font_family", fonts_block.get("label_font_family", "Helvetica Neue"))
        )
        self._axis_font_size = int(scale_font_size(d.get("font_size", 10)))
        self._axis_min_font_size = int(scale_font_size(d.get("min_font_size", 8)))
        self._axis_font_divisor = int(d.get("font_size_calculation_divisor", 20)) or 20
        self._y_axis_label_spacing = int(d.get("y_axis_label_spacing", 5))
        self._x_axis_label_spacing = int(d.get("x_axis_label_spacing", 5))
        self._line_color = QColor(*d.get("distribution_line_color", [120, 190, 255]))
        self._line_width = max(1, int(d.get("distribution_line_width", 2)))
        self._line_style = _pen_style_from_config(str(d.get("distribution_line_pen_style", "solid")))
        curve = str(
            usr.get("distribution_line_curve", d.get("distribution_line_curve", "smooth"))
        ).strip().lower()
        self._distribution_line_smooth = curve in ("smooth", "bezier", "curve", "curved")
        self._distribution_line_smooth_strength = max(
            0.0,
            min(
                2.0,
                float(usr.get("distribution_line_smooth_strength", d.get("distribution_line_smooth_strength", 1.0)))
                or 1.0,
            ),
        )
        self._hover_hit_threshold_px = int(d.get("hover_hit_threshold_px", 25))
        self._hover_circle_radius = int(d.get("hover_circle_radius", 6))
        self._show_bin_data_markers = bool(d.get("show_distribution_vertex_markers", True))
        self._bin_data_marker_radius = float(d.get("distribution_vertex_marker_radius", 3))

    def _dist_cfg(self) -> Dict[str, Any]:
        return self._dist_config if isinstance(self._dist_config, dict) else {}

    def _user(self) -> Dict[str, Any]:
        return UserSettingsService.get_instance().get_model().get_player_stats_accuracy_distribution()

    def _effective_colors(self) -> Tuple[QColor, List[Tuple[float, QColor]]]:
        cfg = self._dist_cfg()
        usr = normalize_player_stats_accuracy_distribution_settings(self._user())
        preset_id = str(usr.get("color_preset", "github_green"))
        presets = cfg.get("color_presets")
        ranges: List[Tuple[float, QColor]] = []
        if isinstance(presets, dict):
            raw = presets.get(preset_id) or presets.get("github_green")
            ranges = _parse_color_ranges_list(raw)
        colors_config = self._player_stats_config.get("colors", {})
        fallback = QColor(
            *cfg.get("bar_color", colors_config.get("phase_opening_color", [100, 150, 255]))
        )
        return fallback, ranges

    def _skew_exponent(self) -> float:
        usr = normalize_player_stats_accuracy_distribution_settings(self._user())
        mode = str(usr.get("skew_mode", "high_accuracy_skew"))
        ex = self._dist_cfg().get("skew_exponents")
        if isinstance(ex, dict) and mode in ex:
            try:
                v = float(ex[mode])
                return max(1.0, v)
            except (TypeError, ValueError):
                pass
        return 4.0 if mode == "high_accuracy_skew" else 6.5 if mode == "very_high_accuracy_skew" else 1.0

    def _bin_profile(self) -> Dict[str, Any]:
        usr = normalize_player_stats_accuracy_distribution_settings(self._user())
        key = str(usr.get("bin_density", "auto"))
        profiles = self._dist_cfg().get("bin_density_profiles")
        if isinstance(profiles, dict):
            p = profiles.get(key)
            if isinstance(p, dict):
                return p
        return {"min_bins": 5, "max_bins": 25, "range_divisor": 5.0}

    def _compute_bin_count(self, range_size: float) -> int:
        p = self._bin_profile()
        try:
            mn = int(p.get("min_bins", 5))
            mx = int(p.get("max_bins", 25))
            div = float(p.get("range_divisor", 5.0)) or 5.0
        except (TypeError, ValueError):
            mn, mx, div = 5, 25, 5.0
        mn = max(3, mn)
        mx = max(mn, mx)
        raw = int(round(range_size / div))
        return max(mn, min(mx, raw))

    def _color_for_accuracy(
        self, acc: float, fallback: QColor, ranges: List[Tuple[float, QColor]]
    ) -> QColor:
        if not ranges:
            return fallback
        acc = max(0.0, min(100.0, acc))
        first_max, first_color = ranges[0]
        if acc <= first_max:
            return first_color
        prev_max, prev_color = first_max, first_color
        for max_acc, color in ranges[1:]:
            if acc <= max_acc:
                t = (acc - prev_max) / (max_acc - prev_max) if max_acc > prev_max else 1.0
                return QColor(
                    int(prev_color.red() + t * (color.red() - prev_color.red())),
                    int(prev_color.green() + t * (color.green() - prev_color.green())),
                    int(prev_color.blue() + t * (color.blue() - prev_color.blue())),
                )
            prev_max, prev_color = max_acc, color
        return ranges[-1][1]

    @staticmethod
    def _closest_point_on_segment(
        p: QPointF, a: QPointF, b: QPointF
    ) -> Tuple[QPointF, float]:
        vx = b.x() - a.x()
        vy = b.y() - a.y()
        wx = p.x() - a.x()
        wy = p.y() - a.y()
        c1 = wx * vx + wy * vy
        c2 = vx * vx + vy * vy
        if c2 <= 0:
            cx, cy = a.x(), a.y()
        elif c1 <= 0:
            cx, cy = a.x(), a.y()
        elif c1 >= c2:
            cx, cy = b.x(), b.y()
        else:
            t = c1 / c2
            cx = a.x() + t * vx
            cy = a.y() + t * vy
        dx = p.x() - cx
        dy = p.y() - cy
        return QPointF(cx, cy), dx * dx + dy * dy

    def _dist_hover_tooltip(self, vertex_index: int) -> str:
        ctx = self._dist_hover_ctx
        if not ctx or vertex_index < 0 or vertex_index >= len(ctx["bins"]):
            return ""
        lo, hi, cnt = ctx["bins"][vertex_index]
        y_mode = str(ctx["y_mode"])
        total = int(ctx["total"])
        rng = f"{lo:.1f}–{hi:.1f}%"
        gw = "game" if cnt == 1 else "games"
        if y_mode == "percent_of_games" and total > 0:
            pct = 100.0 * cnt / float(total)
            return f"{rng}\n{cnt} {gw} ({pct:.1f}% of all)"
        return f"{rng}\n{cnt} {gw}"

    def set_accuracy_values(self, values: List[float]) -> None:
        self._accuracy_values = values or []
        self._dist_hover_ctx = None
        self._hover_pixel = None
        self._hover_vertex_index = None
        QToolTip.hideText()
        self.update()

    def refresh_from_settings(self) -> None:
        panel = self._config.get("ui", {}).get("panels", {}).get("detail", {})
        self._player_stats_config = panel.get("player_stats", {})
        self._dist_config = self._player_stats_config.get("accuracy_distribution", {})
        self._sync_dist_visual_settings()
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(320, self._height)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, self._height)

    def paintEvent(self, event) -> None:
        del event
        cfg = self._dist_cfg()
        usr = normalize_player_stats_accuracy_distribution_settings(self._user())
        y_mode = str(usr.get("y_axis_mode", "count"))
        x_span_mode = str(usr.get("x_axis_span", "full"))

        bg = QColor(*cfg.get("background_color", [30, 30, 35]))
        grid_major = QColor(*cfg.get("grid_major_color", [55, 55, 62]))
        grid_minor = QColor(*cfg.get("grid_minor_color", [45, 45, 50]))
        axis_col = QColor(*cfg.get("axis_color", [120, 120, 128]))
        tc_raw = cfg.get("text_color")
        if isinstance(tc_raw, (list, tuple)) and len(tc_raw) >= 3:
            txt = QColor(int(tc_raw[0]), int(tc_raw[1]), int(tc_raw[2]))
        else:
            txt = QColor(self._fallback_text_color)
        fallback_bar, color_ranges = self._effective_colors()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w_full, h_full = rect.width(), rect.height()
        painter.fillRect(0, 0, w_full, h_full, bg)

        m = self._margins
        left, top, right, bottom = int(m[0]), int(m[1]), w_full - int(m[2]), h_full - int(m[3])
        if right <= left or bottom <= top:
            self._dist_hover_ctx = None
            return

        reserve_font = QFont(self._axis_font_family, self._axis_font_size)
        fm_reserve = QFontMetrics(reserve_font)
        x_axis_band = fm_reserve.height() + self._x_axis_label_spacing + 4
        y_label_w = (
            fm_reserve.horizontalAdvance("100%")
            if y_mode == "percent_of_games"
            else fm_reserve.horizontalAdvance("9999") + 4
        )

        plot_left = left + y_label_w + self._y_axis_label_spacing
        plot_top = top
        plot_bottom = bottom - x_axis_band
        if plot_bottom <= plot_top + 8:
            plot_bottom = top + 20
        plot_h = plot_bottom - plot_top
        plot_w = right - plot_left
        if plot_w <= 0 or plot_h <= 0:
            self._dist_hover_ctx = None
            return

        adaptive_font_size = max(
            self._axis_min_font_size,
            min(self._axis_font_size, int(plot_h / self._axis_font_divisor)),
        )
        axis_font = QFont(self._axis_font_family, adaptive_font_size)
        painter.setFont(axis_font)
        fm = QFontMetrics(axis_font)

        values = [max(0.0, min(100.0, v)) for v in self._accuracy_values]
        if not values:
            self._dist_hover_ctx = None
            painter.setPen(QPen(txt))
            msg = "No analyzed games"
            tw = fm.horizontalAdvance(msg)
            painter.drawText(plot_left + (plot_w - tw) // 2, plot_top + plot_h // 2 + fm.ascent() // 2, msg)
            return

        major_n = max(2, self._grid_major_count)
        painter.setPen(QPen(grid_major, 1))
        for i in range(major_n):
            frac = i / float(major_n - 1) if major_n > 1 else 0.0
            y = int(plot_bottom - plot_h * frac)
            painter.drawLine(plot_left, y, plot_left + plot_w, y)

        if self._x_grid_minor and plot_w > 80:
            painter.setPen(QPen(grid_minor, 1, Qt.PenStyle.DotLine))
            tick_count = 5
            for i in range(1, tick_count):
                x = plot_left + int((i / float(tick_count)) * plot_w)
                painter.drawLine(x, plot_top, x, plot_bottom)

        data_min = min(values)
        data_max = max(values)
        margin = 2.5
        low = max(0.0, data_min - margin)
        high = min(100.0, data_max + margin)
        if high <= low:
            high = min(100.0, low + 5.0)
        range_size = high - low
        bin_count = self._compute_bin_count(range_size)

        k = self._skew_exponent()
        if k <= 1.0001:
            t_low = low / 100.0
            t_high = high / 100.0
        else:
            t_low = (low / 100.0) ** k
            t_high = (high / 100.0) ** k
        t_range = t_high - t_low
        if t_range <= 0:
            t_range = 1e-9
        t_edges = [t_low + (i / float(bin_count)) * t_range for i in range(bin_count + 1)]
        if k <= 1.0001:
            acc_edges = [100.0 * t for t in t_edges]
        else:
            acc_edges = [100.0 * (t ** (1.0 / k)) for t in t_edges]

        bins = [0] * bin_count
        for v in values:
            if k <= 1.0001:
                t = v / 100.0
            else:
                t = (v / 100.0) ** k
            if t <= t_low:
                idx = 0
            elif t >= t_high:
                idx = bin_count - 1
            else:
                idx = int((t - t_low) / t_range * bin_count)
                if idx >= bin_count:
                    idx = bin_count - 1
            bins[idx] += 1

        total = len(values)
        if y_mode == "percent_of_games" and total > 0:
            heights = [100.0 * c / float(total) for c in bins]
            max_y = max(heights) if heights else 1.0
        else:
            heights = [float(c) for c in bins]
            max_y = max(heights) if heights else 1.0
        if max_y <= 0:
            max_y = 1.0

        if x_span_mode == "data_bounds":
            x_display_min = float(acc_edges[0])
            x_display_max = float(acc_edges[-1])
            if x_display_max <= x_display_min:
                x_display_max = min(100.0, x_display_min + 1e-3)
        else:
            x_display_min, x_display_max = 0.0, 100.0

        bar_gap = max(0, int(cfg.get("bar_gap_px", 1)))
        spans = _bar_pixel_spans(
            plot_left, plot_w, acc_edges, bar_gap, x_display_min, x_display_max
        )
        while len(spans) < bin_count:
            spans.append((plot_left, 1))
        painter.setPen(Qt.PenStyle.NoPen)
        r_bar = min(self._bar_corner_radius, 6)

        for i in range(bin_count):
            start_acc = acc_edges[i]
            end_acc = acc_edges[i + 1]
            x0, w0 = spans[i] if i < len(spans) else (plot_left, 1)
            count = bins[i]
            h_val = heights[i]

            if count <= 0:
                continue

            center_acc = (start_acc + end_acc) / 2.0
            bar_color = self._color_for_accuracy(center_acc, fallback_bar, color_ranges)
            frac_h = h_val / max_y
            bar_h = max(2, int(plot_h * frac_h))
            y0 = plot_bottom - bar_h
            draw_w = max(1, w0)
            painter.setBrush(QBrush(bar_color))
            painter.drawRoundedRect(x0, y0, draw_w, bar_h, r_bar, r_bar)

        points_line: List[QPointF] = []
        for i in range(bin_count):
            x0, w0 = spans[i] if i < len(spans) else (plot_left, 1)
            xc = float(x0) + float(w0) / 2.0
            yi = float(plot_bottom) - plot_h * (heights[i] / max_y) if max_y > 0 else float(plot_bottom)
            yi = max(float(plot_top), min(float(plot_bottom), yi))
            points_line.append(QPointF(xc, yi))

        self._dist_hover_ctx = {
            "left": float(plot_left),
            "top": float(plot_top),
            "right": float(plot_left + plot_w),
            "bottom": float(plot_bottom),
            "points": points_line,
            "bins": [(acc_edges[i], acc_edges[i + 1], bins[i]) for i in range(bin_count)],
            "y_mode": y_mode,
            "total": total,
        }

        lw_ln = max(1, self._line_width)
        pen_ln = QPen(self._line_color, lw_ln)
        pen_ln.setStyle(self._line_style)
        painter.setPen(pen_ln)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if len(points_line) > 1:
            if self._distribution_line_smooth and self._line_style == Qt.PenStyle.SolidLine:
                spath = _smooth_polyline_path(
                    points_line, strength=self._distribution_line_smooth_strength
                )
                if spath is not None:
                    painter.drawPath(spath)
                else:
                    for k in range(len(points_line) - 1):
                        painter.drawLine(points_line[k], points_line[k + 1])
            else:
                for k in range(len(points_line) - 1):
                    painter.drawLine(points_line[k], points_line[k + 1])
        elif len(points_line) == 1:
            painter.setBrush(QBrush(self._line_color))
            r = max(3, lw_ln + 2)
            painter.drawEllipse(points_line[0], r, r)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._show_bin_data_markers and points_line:
            arm = max(2.0, self._bin_data_marker_radius)
            mpen = QPen(self._line_color, max(1, lw_ln))
            mpen.setStyle(self._line_style)
            for pt in points_line:
                _draw_bin_data_x_marker(painter, pt.x(), pt.y(), arm, mpen)

        painter.setPen(QPen(axis_col, 1))
        painter.drawLine(plot_left, plot_bottom, plot_left + plot_w, plot_bottom)

        painter.setPen(QPen(txt))
        if y_mode == "percent_of_games":
            ticks = [(0.0, 0.0), (0.5, max_y / 2.0), (1.0, max_y)]
            for frac, val in ticks:
                y = plot_bottom - int(plot_h * frac)
                lab = f"{val:.0f}%"
                lw = fm.horizontalAdvance(lab)
                painter.drawText(
                    int(plot_left - lw - self._y_axis_label_spacing),
                    int(y + fm.height() / 2),
                    lab,
                )
        else:
            if max_y <= 1:
                y_ticks = [(0.0, 0.0), (1.0, max_y)]
            else:
                y_ticks = [(0.0, 0.0), (0.5, max_y / 2.0), (1.0, max_y)]
            for frac, val in y_ticks:
                y = plot_bottom - int(plot_h * frac)
                lab = f"{int(round(val))}"
                lw = fm.horizontalAdvance(lab)
                painter.drawText(
                    int(plot_left - lw - self._y_axis_label_spacing),
                    int(y + fm.height() / 2),
                    lab,
                )

        if plot_w > 0:
            if plot_w >= 480:
                tick_count = 6
            elif plot_w >= 320:
                tick_count = 5
            elif plot_w >= 200:
                tick_count = 3
            else:
                tick_count = 2
            x_rng = x_display_max - x_display_min
            if x_rng <= 1e-12:
                x_rng = 1e-12
            for i in range(tick_count):
                if tick_count == 1:
                    t = 0.5
                else:
                    t = i / float(tick_count - 1)
                value = x_display_min + t * x_rng
                lab = f"{value:.0f}%"
                x_pos = plot_left + int(t * plot_w)
                tw = fm.horizontalAdvance(lab)
                painter.drawText(
                    int(x_pos - tw // 2),
                    int(plot_bottom + fm.height() + self._x_axis_label_spacing),
                    lab,
                )

        if self._hover_pixel is not None and self._hover_vertex_index is not None:
            hover_pen = QPen(self._line_color, 2)
            hover_pen.setStyle(self._line_style)
            painter.setPen(hover_pen)
            painter.setBrush(QBrush(bg))
            painter.drawEllipse(self._hover_pixel, self._hover_circle_radius, self._hover_circle_radius)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        ctx = self._dist_hover_ctx
        if not ctx:
            self._hover_pixel = None
            self._hover_vertex_index = None
            QToolTip.hideText()
            self.update()
            return
        left = float(ctx["left"])
        top = float(ctx["top"])
        right = float(ctx["right"])
        bottom = float(ctx["bottom"])
        points: List[QPointF] = ctx["points"]
        if len(points) == 0:
            self._hover_pixel = None
            self._hover_vertex_index = None
            QToolTip.hideText()
            self.update()
            return
        mp = event.position()
        mx, my = float(mp.x()), float(mp.y())
        if not (left <= mx <= right and top <= my <= bottom):
            self._hover_pixel = None
            self._hover_vertex_index = None
            QToolTip.hideText()
            self.update()
            return
        threshold_sq = self._hover_hit_threshold_px * self._hover_hit_threshold_px
        if len(points) == 1:
            d0 = (mx - points[0].x()) ** 2 + (my - points[0].y()) ** 2
            if d0 <= threshold_sq:
                self._hover_pixel = points[0]
                self._hover_vertex_index = 0
                tip = self._dist_hover_tooltip(0)
                QToolTip.showText(event.globalPosition().toPoint(), tip, self, QRect(), 4000)
            else:
                self._hover_pixel = None
                self._hover_vertex_index = None
                QToolTip.hideText()
            self.update()
            return
        best_dist_sq = float("inf")
        best_pixel: Optional[QPointF] = None
        best_vertex: Optional[int] = None
        for i in range(len(points) - 1):
            closest, dist_sq = self._closest_point_on_segment(mp, points[i], points[i + 1])
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_pixel = closest
                d_i = (closest.x() - points[i].x()) ** 2 + (closest.y() - points[i].y()) ** 2
                d_j = (closest.x() - points[i + 1].x()) ** 2 + (closest.y() - points[i + 1].y()) ** 2
                best_vertex = i if d_i <= d_j else i + 1
        if best_dist_sq <= threshold_sq and best_pixel is not None and best_vertex is not None:
            self._hover_pixel = best_pixel
            self._hover_vertex_index = best_vertex
            tip = self._dist_hover_tooltip(best_vertex)
            QToolTip.showText(event.globalPosition().toPoint(), tip, self, QRect(), 4000)
        else:
            self._hover_pixel = None
            self._hover_vertex_index = None
            QToolTip.hideText()
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover_pixel = None
        self._hover_vertex_index = None
        QToolTip.hideText()
        super().leaveEvent(event)
