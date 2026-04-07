"""GitHub-style month activity heatmap for Player Stats (games per calendar day)."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from app.services.player_stats_activity_heatmap_layout import (
    ActivityHeatmapGridBand,
    ActivityHeatmapPaintModel,
    build_activity_heatmap_paint_model,
)
from app.services.player_stats_activity_heatmap_user import (
    normalize_player_stats_activity_heatmap_settings,
)
from app.services.user_settings_service import UserSettingsService


def _parse_color_stops(raw: Any) -> List[Tuple[int, int, int]]:
    out: List[Tuple[int, int, int]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            try:
                out.append((int(item[0]), int(item[1]), int(item[2])))
            except (TypeError, ValueError):
                continue
    return out


def _preset_stops(heatmap_cfg: Dict[str, Any], preset_id: str) -> List[Tuple[int, int, int]]:
    presets = heatmap_cfg.get("color_presets")
    if isinstance(presets, dict):
        raw = presets.get(preset_id) or presets.get("github_green")
        stops = _parse_color_stops(raw)
        if len(stops) >= 2:
            return stops
    return [(22, 27, 34), (0, 55, 40), (38, 130, 80), (120, 200, 120)]


def _lerp_rgb(
    a: Tuple[int, int, int], b: Tuple[int, int, int], t: float
) -> Tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _color_for_count(
    count: int,
    scale_max: float,
    heatmap_cfg: Dict[str, Any],
    preset: str,
    empty_rgb: Tuple[int, int, int],
) -> QColor:
    if count <= 0:
        return QColor(*empty_rgb)
    stops = _preset_stops(heatmap_cfg, preset)
    t = min(1.0, float(count) / max(scale_max, 1e-6))
    x = t * (len(stops) - 1)
    i = int(x)
    f = x - i
    if i >= len(stops) - 1:
        r, g, b = stops[-1]
    else:
        r, g, b = _lerp_rgb(stops[i], stops[i + 1], f)
    return QColor(r, g, b)


class PlayerActivityHeatmapWidget(QWidget):
    """Renders :class:`ActivityHeatmapPaintModel`; cells scale to use full widget width."""

    #: Emitted on double-click a cell with at least one game; ``day_ordinal`` is the calendar day.
    activity_day_double_clicked = pyqtSignal(int)

    _MARGIN_L = 8
    _MARGIN_R = 8
    _MARGIN_T = 8
    _MARGIN_B = 8

    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._per_game: List[Tuple[Optional[int], Optional[int]]] = []
        self._model: Optional[ActivityHeatmapPaintModel] = None
        self._hover_brc: Optional[Tuple[int, int, int]] = None  # band_idx, row, col
        self.setMouseTracking(True)
        self.setMinimumWidth(0)
        self.setMinimumHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def _sync_minimum_height_to_width(self) -> None:
        if not self._model:
            self.setMinimumHeight(48)
            return
        w = self.width()
        if w <= 0:
            w = 520
        self.setMinimumHeight(max(48, self.heightForWidth(w)))

    def set_per_game_ordinals(
        self, pairs: List[Tuple[Optional[int], Optional[int]]]
    ) -> None:
        self._per_game = list(pairs)
        self._rebuild_model()
        self.updateGeometry()
        QTimer.singleShot(0, self._sync_minimum_height_to_width)
        self.update()

    def refresh_from_settings(self) -> None:
        self._rebuild_model()
        self.updateGeometry()
        QTimer.singleShot(0, self._sync_minimum_height_to_width)
        self.update()

    def subcaption_text(self) -> str:
        return self._model.subcaption if self._model else ""

    def _heatmap_config(self) -> Dict[str, Any]:
        ui = self.config.get("ui", {})
        detail = ui.get("panels", {}).get("detail", {})
        ps = detail.get("player_stats", {})
        raw = ps.get("activity_heatmap")
        return raw if isinstance(raw, dict) else {}

    def _rebuild_model(self) -> None:
        from datetime import date

        cfg = self._heatmap_config()
        usr = UserSettingsService.get_instance().get_model().get_player_stats_activity_heatmap()
        today_o = date.today().toordinal()
        self._model = build_activity_heatmap_paint_model(
            self._per_game, usr, today_o
        )

    def hasHeightForWidth(self) -> bool:
        return self._model is not None

    def _layout_pack(self, width: int) -> Optional[Dict[str, Any]]:
        """Compute geometry shared by paint, hit-test, and heightForWidth."""
        m = self._model
        if not m or not m.bands:
            return None
        cfg = self._heatmap_config()
        gap = int(cfg.get("cell_gap", 2))
        mh = int(cfg.get("month_label_band_height", 14))
        band_vgap = int(cfg.get("two_band_vertical_gap", 12))
        max_cols = max(b.n_cols for b in m.bands)
        if max_cols <= 0:
            return None
        any_row_labels = any(len(b.row_labels) > 0 for b in m.bands)
        label_w = 0
        if any_row_labels:
            label_w = max(22, int(cfg.get("row_label_width", 28)))
        inner = max(0, width - self._MARGIN_L - label_w - self._MARGIN_R)
        min_cs = int(cfg.get("min_cell_size", 3))
        max_cs = int(cfg.get("max_cell_size", 24))
        total_gap = max(0, max_cols - 1) * gap
        cs = (inner - total_gap) // max_cols if max_cols else min_cs
        cs = max(min_cs, min(max_cs, cs))
        grid_ox = self._MARGIN_L + label_w

        band_packs: List[Dict[str, Any]] = []
        y = self._MARGIN_T
        for bi, b in enumerate(m.bands):
            row_month_y = y
            y += mh
            row_cell_y: List[int] = []
            for r in range(b.n_rows):
                row_cell_y.append(y)
                y += cs
                if r < b.n_rows - 1:
                    y += gap
            band_packs.append(
                {
                    "band_idx": bi,
                    "grid": b,
                    "row_month_y": row_month_y,
                    "row_cell_y": row_cell_y,
                }
            )
            if bi < len(m.bands) - 1:
                y += band_vgap
        total_h = y + self._MARGIN_B

        return {
            "cs": cs,
            "gap": gap,
            "mh": mh,
            "band_vgap": band_vgap,
            "grid_ox": grid_ox,
            "label_w": label_w,
            "band_packs": band_packs,
            "total_h": total_h,
        }

    def _hit_test_at(self, px: float, py: float) -> Optional[Tuple[int, int, int]]:
        """Return ``(band_idx, row, col)`` for a cell under the point, or ``None``."""
        m = self._model
        if not m or not m.bands:
            return None
        pack = self._layout_pack(self.width())
        if not pack:
            return None
        cs = pack["cs"]
        gap = pack["gap"]
        grid_ox = pack["grid_ox"]
        band_packs = pack["band_packs"]
        for bp in band_packs:
            gb = bp["grid"]
            bi = int(bp["band_idx"])
            row_cell_y: List[int] = bp["row_cell_y"]
            for r in range(gb.n_rows):
                if r >= len(row_cell_y):
                    break
                cy = row_cell_y[r]
                if not (cy <= py < cy + cs):
                    continue
                rel_x = px - grid_ox
                if rel_x < 0:
                    break
                col = int(rel_x // (cs + gap))
                if col < 0 or col >= gb.n_cols:
                    break
                if (rel_x % (cs + gap)) >= cs:
                    break
                return (bi, r, col)
        return None

    def heightForWidth(self, width: int) -> int:
        pack = self._layout_pack(width)
        if not pack:
            return 80
        return max(48, int(pack["total_h"]))

    def sizeHint(self) -> QSize:
        pw = 0
        parent = self.parentWidget()
        if parent is not None and parent.width() > 0:
            pw = parent.width()
        w = max(self.width(), pw, 520)
        h = self.heightForWidth(w) if self._model else 80
        return QSize(w, h)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, 48)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() > 0:
            self._sync_minimum_height_to_width()
        self.update()

    def _paint_month_band(
        self,
        p: QPainter,
        band: Tuple[Tuple[int, str], ...],
        month_y: int,
        grid_ox: int,
        cs: int,
        gap: int,
        mh: int,
        n_cols: int,
        color: QColor,
    ) -> None:
        if not band:
            return
        p.setPen(QPen(color))
        month_font = QFont(p.font())
        month_font.setPointSize(max(6, int(self._heatmap_config().get("month_label_font_size", 7))))
        p.setFont(month_font)
        band_list = list(band)
        for i, (c, lab) in enumerate(band_list):
            x0 = grid_ox + c * (cs + gap)
            if i + 1 < len(band_list):
                c_next = band_list[i + 1][0]
                w = max(1, (c_next - c) * (cs + gap) - gap)
            else:
                w = max(1, n_cols * (cs + gap) - gap - c * (cs + gap))
            rect = QRect(int(x0), int(month_y), int(w), int(mh))
            p.drawText(
                rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                lab,
            )

    def _paint_week_dividers(
        self,
        p: QPainter,
        b: ActivityHeatmapGridBand,
        grid_ox: int,
        cs: int,
        gap: int,
        y_top: int,
        y_bottom: int,
        cfg: Dict[str, Any],
    ) -> None:
        wcol = tuple(cfg.get("week_divider_color", [72, 72, 80]))
        wwid = max(0, int(cfg.get("week_divider_line_width", 1)))
        mcol = tuple(cfg.get("month_divider_color", [120, 120, 135]))
        mwid = max(wwid, int(cfg.get("month_divider_line_width", 2)))
        month_set = frozenset(b.month_start_columns)
        if wwid <= 0 and mwid <= 0:
            return
        for c in range(1, b.n_cols):
            x = grid_ox + c * (cs + gap) - gap / 2.0
            is_month = c in month_set
            if is_month and mwid > 0:
                pen = QPen(QColor(*mcol))
                pen.setWidth(mwid)
            elif wwid > 0:
                pen = QPen(QColor(*wcol))
                pen.setWidth(wwid)
            else:
                continue
            p.setPen(pen)
            p.drawLine(int(x), int(y_top), int(x), int(y_bottom))

    def paintEvent(self, event) -> None:
        del event
        cfg = self._heatmap_config()
        border = tuple(cfg.get("border_color", [55, 55, 62]))
        empty_rgb = tuple(cfg.get("empty_cell_color", [33, 38, 46]))
        month_txt = tuple(cfg.get("month_label_text_color", [150, 150, 158]))
        usr = normalize_player_stats_activity_heatmap_settings(
            UserSettingsService.get_instance()
            .get_model()
            .get_player_stats_activity_heatmap()
        )
        preset = str(usr.get("color_preset", "github_green"))
        date_range = str(usr.get("date_range", "trim_to_data"))
        show_day_numbers_in_cells = date_range == "trim_to_data"

        m = self._model
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not m:
            p.end()
            return

        pack = self._layout_pack(self.width())
        if not pack:
            p.end()
            return

        cs = pack["cs"]
        gap = pack["gap"]
        mh = pack["mh"]
        grid_ox = pack["grid_ox"]
        label_w = pack["label_w"]
        band_packs = pack["band_packs"]

        base_radius = int(cfg.get("corner_radius", 2))
        radius = min(base_radius, max(0, cs // 2))

        font = QFont()
        font.setPointSize(max(7, int(cfg.get("label_font_size", 8))))
        p.setFont(font)

        for bp in band_packs:
            gb = bp["grid"]
            row_month_y = int(bp["row_month_y"])
            row_cell_y: List[int] = bp["row_cell_y"]
            bi = int(bp["band_idx"])
            if gb.month_label_bands:
                self._paint_month_band(
                    p,
                    gb.month_label_bands[0],
                    row_month_y,
                    grid_ox,
                    cs,
                    gap,
                    mh,
                    gb.n_cols,
                    QColor(*month_txt),
                )

            if gb.row_labels:
                p.setPen(QPen(QColor(*month_txt)))
                for r, text in enumerate(gb.row_labels):
                    if r >= len(row_cell_y):
                        break
                    y0 = row_cell_y[r]
                    rect = QRect(self._MARGIN_L, int(y0), max(0, label_w - 2), cs)
                    p.drawText(
                        rect,
                        int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                        text,
                    )

            pen_empty = QPen(QColor(*border))
            pen_empty.setWidth(1)
            for r in range(gb.n_rows):
                if r >= len(row_cell_y):
                    break
                cy = row_cell_y[r]
                for c in range(gb.n_cols):
                    x = grid_ox + c * (cs + gap)
                    y = cy
                    cnt = gb.counts[r][c]
                    bg = _color_for_count(cnt, m.scale_max, cfg, preset, empty_rgb)
                    if self._hover_brc == (bi, r, c):
                        bg = bg.lighter(115)
                    p.setBrush(bg)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(x, y, cs, cs, radius, radius)
                    if cnt == 0:
                        p.setPen(pen_empty)
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(x, y, cs, cs, radius, radius)

            min_dom = int(cfg.get("day_number_min_cell_size", 10))
            if (
                show_day_numbers_in_cells
                and gb.cell_ordinals
                and len(gb.cell_ordinals) == gb.n_rows
                and cs >= min_dom
            ):
                dom_color = tuple(cfg.get("day_number_text_color", [130, 130, 138]))
                df = QFont(font)
                df.setPointSize(max(5, min(8, max(5, cs // 3))))
                p.setFont(df)
                p.setPen(QPen(QColor(*dom_color)))
                for r in range(gb.n_rows):
                    if r >= len(gb.cell_ordinals) or r >= len(row_cell_y):
                        break
                    cy = row_cell_y[r]
                    row_o = gb.cell_ordinals[r]
                    for c in range(gb.n_cols):
                        if c >= len(row_o):
                            break
                        o = row_o[c]
                        if o < 0:
                            continue
                        dom = str(date.fromordinal(int(o)).day)
                        x = grid_ox + c * (cs + gap)
                        inset = max(1, cs // 10)
                        rect = QRect(
                            int(x + inset),
                            int(cy + inset),
                            int(cs - 2 * inset),
                            int(cs - 2 * inset),
                        )
                        p.drawText(
                            rect,
                            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom),
                            dom,
                        )

            if gb.n_cols > 1 and row_cell_y:
                y0 = row_cell_y[0]
                y1 = row_cell_y[-1] + cs
                self._paint_week_dividers(p, gb, grid_ox, cs, gap, y0, y1, cfg)

        p.end()

    def mouseMoveEvent(self, event) -> None:
        m = self._model
        if not m:
            super().mouseMoveEvent(event)
            return
        px = event.position().x()
        py = event.position().y()
        h = self._hit_test_at(px, py)
        hit = h is not None
        band_i, row, col = h if h else (-1, -1, -1)

        new_hover = (band_i, row, col) if hit else None
        if new_hover != self._hover_brc:
            self._hover_brc = new_hover
            self.update()
            tip = ""
            if hit and 0 <= band_i < len(m.bands):
                tip = m.bands[band_i].labels[row][col] or ""
            self.setToolTip(tip)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        m = self._model
        if not m:
            super().mouseDoubleClickEvent(event)
            return
        h = self._hit_test_at(event.position().x(), event.position().y())
        if h is None:
            super().mouseDoubleClickEvent(event)
            return
        bi, r, c = h
        if not (0 <= bi < len(m.bands)):
            super().mouseDoubleClickEvent(event)
            return
        gb = m.bands[bi]
        if gb.counts[r][c] <= 0:
            super().mouseDoubleClickEvent(event)
            return
        row_o = gb.cell_ordinals[r] if r < len(gb.cell_ordinals) else ()
        if c >= len(row_o):
            super().mouseDoubleClickEvent(event)
            return
        o = row_o[c]
        if o < 0:
            super().mouseDoubleClickEvent(event)
            return
        self.activity_day_double_clicked.emit(int(o))
        event.accept()

    def leaveEvent(self, event) -> None:
        self._hover_brc = None
        self.setToolTip("")
        self.update()
        super().leaveEvent(event)
