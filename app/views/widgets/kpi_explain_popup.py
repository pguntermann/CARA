"""Themed KPI explanation popup for Game Summary key statistics.

Reuses the move-link popup placement/caret styling, with a range scale that
shows where the current value sits among approximate skill bands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.style.tooltip import load_tooltip_style
from app.views.widgets.move_link_popup import place_move_link_popup

Rgb = Tuple[int, int, int]

_DEFAULT_BAND_COLORS_COOL_TO_WARM: Tuple[Rgb, ...] = (
    (90, 160, 120),
    (140, 175, 100),
    (200, 175, 90),
    (210, 140, 90),
    (200, 100, 95),
)


@dataclass(frozen=True)
class KpiBand:
    """One labeled segment on the KPI scale (``end`` is the segment's upper bound)."""

    label: str
    end: float
    description: str = ""


@dataclass(frozen=True)
class KpiTip:
    """Content for one KPI hover popup."""

    title: str
    explanation: str
    note: str
    value: float
    display_value: str
    scale_min: float
    scale_max: float
    higher_is_better: bool
    bands: Tuple[KpiBand, ...]
    unit: str = ""


@dataclass(frozen=True)
class KpiTipVisualStyle:
    """Theme values for the KPI explain popup layout and band palette."""

    wrap_width: int
    band_table_desc_wrap: int
    content_spacing: int
    scale_min_width: int
    scale_preferred_height: int
    scale_bar_height: int
    scale_bar_top: int
    scale_bar_corner_radius: int
    scale_horizontal_inset: int
    band_table_horizontal_spacing: int
    band_table_vertical_spacing: int
    band_table_swatch_size: int
    band_table_header_color_delta: int
    band_colors_cool_to_warm: Tuple[Rgb, ...]
    value_underline_style: str = "dotted"
    value_underline_style_hover: str = "solid"
    value_underline_color: Rgb = (160, 160, 160)
    value_underline_color_hover: Rgb = (200, 200, 200)


def _rgb_tuple(value: Any, fallback: Rgb) -> Rgb:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return fallback
    return fallback


def _int_value(value: Any, fallback: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return fallback


def load_kpi_tip_visual_style(config: Optional[Dict[str, Any]]) -> KpiTipVisualStyle:
    """Resolve ``ui.panels.detail.summary.key_statistics.kpi_tip`` theme values."""
    raw: Dict[str, Any] = {}
    if config:
        ui = config.get("ui", {})
        panel = ui.get("panels", {}).get("detail", {})
        tip = panel.get("summary", {}).get("key_statistics", {}).get("kpi_tip", {})
        if isinstance(tip, dict):
            raw = tip
    scale = raw.get("scale", {}) if isinstance(raw.get("scale"), dict) else {}
    table = raw.get("band_table", {}) if isinstance(raw.get("band_table"), dict) else {}
    hint = raw.get("value_hint", {}) if isinstance(raw.get("value_hint"), dict) else {}
    colors_raw = raw.get("band_colors_cool_to_warm")
    colors: List[Rgb] = []
    if isinstance(colors_raw, list):
        for i, row in enumerate(colors_raw):
            fallback = _DEFAULT_BAND_COLORS_COOL_TO_WARM[
                min(i, len(_DEFAULT_BAND_COLORS_COOL_TO_WARM) - 1)
            ]
            colors.append(_rgb_tuple(row, fallback))
    if not colors:
        colors = list(_DEFAULT_BAND_COLORS_COOL_TO_WARM)
    underline_style = str(hint.get("underline_style", "dotted") or "dotted").strip().lower()
    underline_hover = str(hint.get("underline_style_hover", "solid") or "solid").strip().lower()
    return KpiTipVisualStyle(
        wrap_width=_int_value(raw.get("wrap_width"), 340, minimum=120),
        band_table_desc_wrap=_int_value(raw.get("band_table_desc_wrap"), 170, minimum=40),
        content_spacing=_int_value(raw.get("content_spacing"), 6, minimum=0),
        scale_min_width=_int_value(scale.get("min_width"), 260, minimum=80),
        scale_preferred_height=_int_value(scale.get("preferred_height"), 54, minimum=24),
        scale_bar_height=_int_value(scale.get("bar_height"), 12, minimum=4),
        scale_bar_top=_int_value(scale.get("bar_top"), 10, minimum=0),
        scale_bar_corner_radius=_int_value(scale.get("bar_corner_radius"), 3, minimum=0),
        scale_horizontal_inset=_int_value(scale.get("horizontal_inset"), 4, minimum=0),
        band_table_horizontal_spacing=_int_value(table.get("horizontal_spacing"), 8, minimum=0),
        band_table_vertical_spacing=_int_value(table.get("vertical_spacing"), 3, minimum=0),
        band_table_swatch_size=_int_value(table.get("swatch_size"), 10, minimum=4),
        band_table_header_color_delta=_header_color_delta(table.get("header_color_delta")),
        band_colors_cool_to_warm=tuple(colors),
        value_underline_style=underline_style,
        value_underline_style_hover=underline_hover,
        value_underline_color=_rgb_tuple(hint.get("underline_color"), (160, 160, 160)),
        value_underline_color_hover=_rgb_tuple(
            hint.get("underline_color_hover"), (200, 200, 200)
        ),
    )


def _header_color_delta(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -25


def _kpi_spec_from_config(
    kpi_id: str, config: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Load one KPI tip spec from ``config.json`` (``ui.panels.detail.summary.key_statistics.kpi_tips``)."""
    if not config:
        return None
    ui = config.get("ui", {})
    panel = ui.get("panels", {}).get("detail", {})
    tips = panel.get("summary", {}).get("key_statistics", {}).get("kpi_tips", {})
    if not isinstance(tips, dict):
        return None
    spec = tips.get(kpi_id)
    if not isinstance(spec, dict):
        return None
    return dict(spec)


def build_kpi_tip(
    kpi_id: str,
    value: float,
    display_value: str,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[KpiTip]:
    """Build a tip for ``kpi_id`` from config, or None when missing/invalid."""
    spec = _kpi_spec_from_config(kpi_id, config)
    if spec is None:
        return None
    raw_bands = spec.get("bands") or []
    bands: List[KpiBand] = []
    for row in raw_bands:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", "")).strip()
        try:
            end = float(row.get("end"))
        except (TypeError, ValueError):
            continue
        if label:
            bands.append(
                KpiBand(
                    label=label,
                    end=end,
                    description=str(row.get("description", "")).strip(),
                )
            )
    if not bands:
        return None
    try:
        scale_min = float(spec.get("scale_min", 0))
        scale_max = float(spec.get("scale_max", 100))
    except (TypeError, ValueError):
        scale_min, scale_max = 0.0, 100.0
    if scale_max <= scale_min:
        scale_max = scale_min + 1.0
    return KpiTip(
        title=str(spec.get("title", kpi_id)),
        explanation=str(spec.get("explanation", "")),
        note=str(spec.get("note", "")),
        value=float(value),
        display_value=str(display_value),
        scale_min=scale_min,
        scale_max=scale_max,
        higher_is_better=bool(spec.get("higher_is_better", True)),
        bands=tuple(bands),
        unit=str(spec.get("unit", "")),
    )


def _band_colors(
    count: int,
    *,
    higher_is_better: bool,
    cool_to_warm: Sequence[Rgb],
) -> List[QColor]:
    """Muted good→bad palette along the scale (left→right)."""
    # Left = scale_min, right = scale_max.
    # If higher is better, left is weaker (warmer), right is stronger (cooler).
    # If lower is better, left is stronger (cooler), right is weaker (warmer).
    stops = list(cool_to_warm) or list(_DEFAULT_BAND_COLORS_COOL_TO_WARM)
    cool_to_warm_q = [QColor(r, g, b) for r, g, b in stops]
    if count <= 0:
        return []
    if higher_is_better:
        palette = list(reversed(cool_to_warm_q))
    else:
        palette = cool_to_warm_q
    if count == 1:
        return [palette[0]]
    colors: List[QColor] = []
    for i in range(count):
        t = i / (count - 1)
        idx = t * (len(palette) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(palette) - 1)
        frac = idx - lo
        a, b = palette[lo], palette[hi]
        colors.append(
            QColor(
                int(a.red() + (b.red() - a.red()) * frac),
                int(a.green() + (b.green() - a.green()) * frac),
                int(a.blue() + (b.blue() - a.blue()) * frac),
            )
        )
    return colors


class KpiRangeScaleWidget(QWidget):
    """Segmented range bar with a marker for the current KPI value."""

    def __init__(
        self,
        visual: Optional[KpiTipVisualStyle] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._visual = visual or load_kpi_tip_visual_style(None)
        self._tip: Optional[KpiTip] = None
        self._text_color = QColor(200, 200, 200)
        self._marker_color = QColor(240, 240, 240)
        self._font = QFont()
        self.setFixedHeight(self._visual.scale_preferred_height)
        self.setMinimumWidth(self._visual.scale_min_width)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._visual.scale_min_width, self._visual.scale_preferred_height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._visual.scale_min_width, self._visual.scale_preferred_height)

    def set_visual(self, visual: KpiTipVisualStyle) -> None:
        self._visual = visual
        self.setFixedHeight(visual.scale_preferred_height)
        self.setMinimumWidth(visual.scale_min_width)
        self.update()

    def set_tip(self, tip: KpiTip, text_color: QColor, marker_color: QColor, font: QFont) -> None:
        self._tip = tip
        self._text_color = QColor(text_color)
        self._marker_color = QColor(marker_color)
        self._font = QFont(font)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        tip = self._tip
        if tip is None:
            return
        visual = self._visual
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()
        bar_y = float(visual.scale_bar_top)
        bar_h = float(visual.scale_bar_height)
        inset = float(visual.scale_horizontal_inset)
        corner = float(visual.scale_bar_corner_radius)
        left = inset
        right = w - inset
        bar_w = max(1.0, right - left)
        span = tip.scale_max - tip.scale_min
        if span <= 0:
            return

        # Always draw left = worse → right = better. For lower-is-better KPIs
        # (e.g. Average CPL), invert the value axis so the best band is on the right.
        invert = not tip.higher_is_better

        def plot_x(value: float) -> float:
            if invert:
                return left + ((tip.scale_max - value) / span) * bar_w
            return left + ((value - tip.scale_min) / span) * bar_w

        prev = tip.scale_min
        value_segments: List[Tuple[float, float, str]] = []
        for band in tip.bands:
            end = min(tip.scale_max, max(prev, float(band.end)))
            value_segments.append((prev, end, band.label))
            prev = end
        if prev < tip.scale_max and value_segments:
            start, _end, label = value_segments[-1]
            value_segments[-1] = (start, tip.scale_max, label)

        # Visual left→right order with warm→cool colors (right is best).
        visual_segs = list(reversed(value_segments)) if invert else value_segments
        colors = _band_colors(
            len(visual_segs),
            higher_is_better=True,
            cool_to_warm=visual.band_colors_cool_to_warm,
        )

        for i, (start, end, _label) in enumerate(visual_segs):
            x0 = plot_x(start)
            x1 = plot_x(end)
            xa, xb = (x0, x1) if x0 <= x1 else (x1, x0)
            color = colors[i] if i < len(colors) else colors[-1]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(xa, bar_y, max(1.0, xb - xa), bar_h), corner, corner)

        # Marker
        value = max(tip.scale_min, min(tip.scale_max, tip.value))
        mx = plot_x(value)
        painter.setBrush(self._marker_color)
        painter.setPen(QPen(self._marker_color.darker(140), 1))
        path = QPainterPath()
        path.moveTo(mx, bar_y - 2)
        path.lineTo(mx - 5, bar_y - 10)
        path.lineTo(mx + 5, bar_y - 10)
        path.closeSubpath()
        painter.drawPath(path)
        painter.setPen(QPen(self._marker_color, 1.5))
        painter.drawLine(QPointF(mx, bar_y), QPointF(mx, bar_y + bar_h))

        # Band labels under the bar. Tight segments (e.g. GM on blunder rate)
        # omit the label — the color table below already names each band.
        painter.setFont(self._font)
        painter.setPen(self._text_color)
        fm = QFontMetrics(self._font)
        label_y = bar_y + bar_h + 4
        drawn_right = left - 4.0
        for start, end, label in visual_segs:
            x0 = plot_x(start)
            x1 = plot_x(end)
            seg_left, seg_right = (x0, x1) if x0 <= x1 else (x1, x0)
            seg_w = seg_right - seg_left
            mid = (seg_left + seg_right) / 2.0
            candidates = [label]
            short = label.split("/")[0].split()[0]
            if short != label:
                candidates.append(short)
            text = None
            tw = 0
            for candidate in candidates:
                cand_w = fm.horizontalAdvance(candidate)
                if cand_w <= seg_w + 2:
                    text = candidate
                    tw = cand_w
                    break
            if text is None:
                continue
            text_left = mid - tw / 2.0
            text_right = mid + tw / 2.0
            if text_left < drawn_right + 4:
                continue
            painter.drawText(int(text_left), int(label_y + fm.ascent()), text)
            drawn_right = text_right

        # Scale ends: left = worse, right = better
        tiny = QFont(self._font)
        tiny.setPointSize(max(7, self._font.pointSize() - 1))
        painter.setFont(tiny)
        tfm = QFontMetrics(tiny)
        left_label = f"{tip.scale_max:g}" if invert else f"{tip.scale_min:g}"
        right_label = f"{tip.scale_min:g}" if invert else f"{tip.scale_max:g}"
        painter.drawText(int(left), int(h - 2), left_label)
        painter.drawText(int(right - tfm.horizontalAdvance(right_label)), int(h - 2), right_label)


class _SwatchLabel(QLabel):
    """Tiny color chip for a band table row."""

    def __init__(
        self,
        color: QColor,
        size: int = 10,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._size = max(4, int(size))
        self.setFixedSize(self._size, self._size)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        inset = 0.5
        side = float(self._size) - 1.0
        painter.drawRoundedRect(QRectF(inset, inset, side, side), 2.0, 2.0)


class KpiBandTableWidget(QWidget):
    """Tabular band guide: swatch · level · range · short description."""

    def __init__(
        self,
        visual: Optional[KpiTipVisualStyle] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._visual = visual or load_kpi_tip_visual_style(None)
        self._rows: List[Tuple[QColor, str, str, str]] = []
        self._label_font = QFont()
        self._body_font = QFont()
        self._text_color = QColor(200, 200, 200)
        self._header_color = QColor(180, 180, 180)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._apply_table_spacing()
        self._grid.setColumnStretch(3, 1)

    def set_visual(self, visual: KpiTipVisualStyle) -> None:
        self._visual = visual
        self._apply_table_spacing()

    def _apply_table_spacing(self) -> None:
        self._grid.setHorizontalSpacing(self._visual.band_table_horizontal_spacing)
        self._grid.setVerticalSpacing(self._visual.band_table_vertical_spacing)

    def set_rows(
        self,
        rows: Sequence[Tuple[QColor, str, str, str]],
        *,
        label_font: QFont,
        body_font: QFont,
        text_color: QColor,
        header_color: QColor,
    ) -> None:
        self._rows = list(rows)
        self._label_font = QFont(label_font)
        self._label_font.setBold(True)
        self._body_font = QFont(body_font)
        self._text_color = QColor(text_color)
        self._header_color = QColor(header_color)
        self._rebuild()

    def preferred_size(self, max_width: int) -> QSize:
        """Measure table from fonts so the popup can pin a fixed height."""
        if not self._rows:
            return QSize(0, 0)
        visual = self._visual
        label_fm = QFontMetrics(self._label_font)
        body_fm = QFontMetrics(self._body_font)
        header_h = body_fm.height() + 2
        row_gap = visual.band_table_vertical_spacing
        col_gap = visual.band_table_horizontal_spacing
        swatch_w = visual.band_table_swatch_size
        level_w = max(
            (label_fm.horizontalAdvance(level) for _, level, _, _ in self._rows),
            default=0,
        )
        level_w = max(level_w, body_fm.horizontalAdvance("Level")) + 2
        range_w = max(
            (body_fm.horizontalAdvance(rng) for _, _, rng, _ in self._rows),
            default=0,
        )
        range_w = max(range_w, body_fm.horizontalAdvance("Range")) + 2
        desc_budget = max(
            80,
            int(max_width) - swatch_w - level_w - range_w - 3 * col_gap,
        )
        desc_h = 0
        for _, _, _, desc in self._rows:
            if not desc:
                desc_h += body_fm.height() + 2
                continue
            rect = body_fm.boundingRect(
                QRect(0, 0, desc_budget, 10_000),
                int(Qt.TextFlag.TextWordWrap),
                desc,
            )
            desc_h += max(body_fm.height() + 2, rect.height() + 2)
        width = min(
            int(max_width),
            swatch_w
            + level_w
            + range_w
            + min(desc_budget, visual.band_table_desc_wrap)
            + 3 * col_gap,
        )
        height = header_h + row_gap + desc_h + max(0, len(self._rows) - 1) * row_gap
        return QSize(max(1, width), max(1, height))

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._rows:
            return
        headers = ("", "Level", "Range", "Guide")
        for col, text in enumerate(headers):
            if not text:
                continue
            lab = QLabel(text)
            lab.setFont(self._body_font)
            lab.setStyleSheet(self._css(self._header_color))
            lab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            self._grid.addWidget(lab, 0, col, Qt.AlignmentFlag.AlignTop)
        swatch_size = self._visual.band_table_swatch_size
        for row_i, (color, level, rng, desc) in enumerate(self._rows, start=1):
            swatch = _SwatchLabel(color, size=swatch_size)
            self._grid.addWidget(swatch, row_i, 0, Qt.AlignmentFlag.AlignTop)

            level_lab = QLabel(level)
            level_lab.setFont(self._label_font)
            level_lab.setStyleSheet(self._css(self._text_color))
            level_lab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            self._grid.addWidget(level_lab, row_i, 1, Qt.AlignmentFlag.AlignTop)

            range_lab = QLabel(rng)
            range_lab.setFont(self._body_font)
            range_lab.setStyleSheet(self._css(self._text_color))
            range_lab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            self._grid.addWidget(range_lab, row_i, 2, Qt.AlignmentFlag.AlignTop)

            desc_lab = QLabel(desc)
            desc_lab.setFont(self._body_font)
            desc_lab.setStyleSheet(self._css(self._text_color))
            desc_lab.setWordWrap(True)
            desc_lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            self._grid.addWidget(desc_lab, row_i, 3, Qt.AlignmentFlag.AlignTop)

    @staticmethod
    def _css(color: QColor) -> str:
        return (
            f"color: rgb({color.red()}, {color.green()}, {color.blue()}); "
            "background: transparent; border: none;"
        )


def _kpi_label_at_global_pos(pos: QPoint) -> Optional["HoverableKpiValueLabel"]:
    """Return the KPI value label under ``pos``, if any."""
    widget = QApplication.widgetAt(pos)
    while widget is not None:
        if isinstance(widget, HoverableKpiValueLabel):
            return widget
        widget = widget.parentWidget()
    return None


class KpiExplainPopup(QWidget):
    """Hover popup: KPI title, explanation, range scale, optional note."""

    # Grace so leave→enter when moving between adjacent KPI values does not
    # hide the shared popup before the next label can claim it.
    _HIDE_GRACE_MS = 150

    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._style = load_tooltip_style(config)
        self._visual = load_kpi_tip_visual_style(config)
        self._config = config
        self._anchor: Optional[QWidget] = None
        self._pending_anchor: Optional[QWidget] = None
        self._caret_edge = "top"
        self._caret_x = 0
        self._content_size = QSize(0, 0)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._finish_delayed_hide)

        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        family = resolve_font_family(self._style.font_family)
        self._title_font = QFont(family, max(8, scale_font_size(self._style.title_font_size)))
        self._title_font.setBold(self._style.title_font_weight.lower() == "bold")
        self._body_font = QFont(family, max(8, scale_font_size(self._style.font_size)))
        self._small_font = QFont(family, max(7, scale_font_size(self._style.font_size) - 1))

        self._content = QWidget(self)
        self._content.setAutoFillBackground(False)
        bg = self._style.background
        sheet = f"background-color: rgb({bg[0]}, {bg[1]}, {bg[2]}); border: none;"
        self._content.setStyleSheet(sheet)

        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(
            self._style.padding,
            self._style.padding,
            self._style.padding,
            self._style.padding,
        )
        layout.setSpacing(self._visual.content_spacing)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._title = self._make_label(self._title_font, self._style.title_color)
        self._value = self._make_label(self._body_font, self._style.text)
        self._explanation = self._make_label(self._body_font, self._style.text)
        self._explanation.setWordWrap(True)
        self._scale = KpiRangeScaleWidget(self._visual)
        self._scale.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._direction = self._make_label(self._small_font, self._style.text)
        self._band_table = KpiBandTableWidget(self._visual)
        self._note = self._make_label(self._small_font, self._style.text)
        self._note.setWordWrap(True)

        layout.addWidget(self._title, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._value, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._explanation, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._scale, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._direction, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._band_table, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._note, 0, Qt.AlignmentFlag.AlignTop)

    @property
    def hover_delay_ms(self) -> int:
        return self._style.hover_delay_ms

    @property
    def visual_style(self) -> KpiTipVisualStyle:
        return self._visual

    def arm_hover(self, anchor: QWidget) -> None:
        """Mark ``anchor`` as the hover target and cancel any pending hide."""
        self._hide_timer.stop()
        self._pending_anchor = anchor

    def is_armed_for(self, anchor: QWidget) -> bool:
        return self._pending_anchor is anchor

    def owns_anchor(self, anchor: QWidget) -> bool:
        return self._anchor is anchor

    def schedule_hide_for(self, anchor: QWidget) -> None:
        """Hide after a short grace if ``anchor`` still owns the hover."""
        if self._pending_anchor is anchor:
            self._pending_anchor = None
        # Another KPI already claimed hover — do not interfere.
        if self._pending_anchor is not None:
            return
        if self._anchor is not None and self._anchor is not anchor:
            return
        if not self.isVisible() and self._anchor is None:
            return
        self._hide_timer.start(self._HIDE_GRACE_MS)

    def _finish_delayed_hide(self) -> None:
        if self._pending_anchor is not None:
            return
        # ToolTip show/hide often synthesizes leave without a matching enter on
        # the next KPI. Re-check the cursor and retarget instead of staying hidden.
        target = _kpi_label_at_global_pos(QCursor.pos())
        if target is not None and target.kpi_popup is self:
            tip = target.kpi_tip
            if tip is not None:
                self._pending_anchor = target
                # Already showing for this label — keep it (avoid present/leave loops).
                if self.isVisible() and self._anchor is target:
                    return
                self.present(target, tip)
                return
        self._anchor = None
        super().hide()

    def _make_label(self, font: QFont, color: Sequence[int]) -> QLabel:
        label = QLabel()
        label.setFont(font)
        label.setStyleSheet(
            f"color: rgb({int(color[0])}, {int(color[1])}, {int(color[2])}); "
            "background: transparent; border: none;"
        )
        # Maximum vertically so a tall fixed popup cannot stretch text blocks apart.
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        return label

    def present(self, anchor: QWidget, tip: KpiTip) -> None:
        if not anchor.isVisible():
            return
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        rect = QRect(top_left, anchor.size())
        # Value cells stretch wide with right-aligned text; aim the caret at the
        # visible KPI text, not the empty center of the cell.
        if isinstance(anchor, QLabel):
            text = anchor.text() or ""
            text_w = QFontMetrics(anchor.font()).boundingRect(text).width() + 6
            align = anchor.alignment()
            if text_w > 0 and text_w < rect.width():
                if align & Qt.AlignmentFlag.AlignRight:
                    rect = QRect(rect.right() - text_w + 1, rect.top(), text_w, rect.height())
                elif align & Qt.AlignmentFlag.AlignHCenter:
                    rect = QRect(rect.left() + (rect.width() - text_w) // 2, rect.top(), text_w, rect.height())
                else:
                    rect = QRect(rect.left(), rect.top(), text_w, rect.height())
        self.present_at(rect, tip, owner=anchor)

    def present_at(self, global_rect: QRect, tip: KpiTip, *, owner: QWidget) -> None:
        if global_rect.isEmpty() or not owner.isVisible():
            return
        self._hide_timer.stop()
        self._anchor = owner
        self._pending_anchor = owner
        self._apply_tip(tip)

        unbounded = 16777215
        self.setMinimumSize(0, 0)
        self.setMaximumSize(unbounded, unbounded)
        self._content.setMinimumSize(0, 0)
        self._content.setMaximumSize(unbounded, unbounded)

        # Measure from text metrics only. Layout sizeHint can be inflated
        # (and then stretch children), which produced the oversized gaps.
        content_size = self._preferred_content_size()
        self._content_size = content_size
        self._content.setFixedSize(content_size)

        radius = self._style.border_radius
        popup_width = max(1, content_size.width() + 2 * radius)
        popup_height = max(1, content_size.height() + self._style.caret_size + 2 * radius)
        self.setFixedSize(popup_width, popup_height)

        content_layout = self._content.layout()
        if content_layout is not None:
            content_layout.invalidate()
            content_layout.activate()

        screen = QGuiApplication.screenAt(global_rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x, y, edge, caret_x = place_move_link_popup(
            anchor_left=global_rect.left(),
            anchor_top=global_rect.top(),
            anchor_width=global_rect.width(),
            anchor_height=global_rect.height(),
            popup_width=popup_width,
            popup_height=popup_height,
            screen_left=avail.left(),
            screen_top=avail.top(),
            screen_right=avail.right(),
            screen_bottom=avail.bottom(),
            caret_size=self._style.caret_size,
            anchor_gap=self._style.anchor_gap,
            border_radius=self._style.border_radius,
            border_width=self._style.border_width,
        )
        self._caret_edge = edge
        self._caret_x = caret_x
        self._place_content()
        self.update()
        self.move(x, y)
        self.show()
        self.raise_()

    def hide_for(self, anchor: QWidget) -> None:
        """Hide immediately when ``anchor`` owns the tip (e.g. mouse press)."""
        self._hide_timer.stop()
        if self._pending_anchor is anchor:
            self._pending_anchor = None
        if self._anchor is anchor or self._anchor is None:
            self._anchor = None
            super().hide()

    def hide(self) -> None:  # noqa: A003
        self._hide_timer.stop()
        self._pending_anchor = None
        self._anchor = None
        super().hide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_content()

    def paintEvent(self, event) -> None:  # noqa: N802, ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = self._shape_path()
        bg = self._style.background
        border = self._style.border
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg[0], bg[1], bg[2]))
        painter.drawPath(path)
        if self._style.border_width > 0:
            pen = QPen(QColor(border[0], border[1], border[2]))
            pen.setWidth(self._style.border_width)
            pen.setCosmetic(True)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    def _apply_tip(self, tip: KpiTip) -> None:
        self._title.setText(tip.title)
        unit = f" {tip.unit}" if tip.unit and tip.unit not in tip.display_value else ""
        self._value.setText(f"This game: {tip.display_value}{unit}")
        self._explanation.setText(tip.explanation)
        self._explanation.setVisible(bool(tip.explanation))
        marker = QColor(*self._style.title_color)
        text = QColor(*self._style.text)
        self._scale.set_tip(tip, text, marker, self._small_font)

        # Table rows match the bar: worst → best (left → right).
        band_ranges: List[Tuple[str, float, float, str]] = []
        prev = tip.scale_min
        for band in tip.bands:
            band_ranges.append((band.label, prev, float(band.end), band.description))
            prev = float(band.end)
        if not tip.higher_is_better:
            band_ranges = list(reversed(band_ranges))
        colors = _band_colors(
            len(band_ranges),
            higher_is_better=True,
            cool_to_warm=self._visual.band_colors_cool_to_warm,
        )
        rows: List[Tuple[QColor, str, str, str]] = []
        for i, (label, lo, hi, desc) in enumerate(band_ranges):
            color = colors[i] if i < len(colors) else colors[-1]
            rows.append((color, label, f"{lo:g}–{hi:g}", desc))
        direction = "Higher is better" if tip.higher_is_better else "Lower is better"
        self._direction.setText(direction)
        # Slightly muted header vs body rows (same channel, no alpha — stylesheets ignore it).
        delta = self._visual.band_table_header_color_delta
        header = QColor(
            max(0, min(255, text.red() + delta)),
            max(0, min(255, text.green() + delta)),
            max(0, min(255, text.blue() + delta)),
        )
        self._band_table.set_rows(
            rows,
            label_font=self._small_font,
            body_font=self._small_font,
            text_color=text,
            header_color=header,
        )
        self._band_table.setVisible(bool(rows))
        self._note.setText(tip.note)
        self._note.setVisible(bool(tip.note))

    def _preferred_content_size(self) -> QSize:
        pad = self._style.padding
        visual = self._visual
        inner_w = visual.wrap_width
        title_w, title_h = self._label_line_size(self._title.text(), self._title_font)
        value_w, value_h = self._label_line_size(self._value.text(), self._body_font)
        # Do not use isVisible() here — the popup is still hidden while measuring,
        # so Qt would skip explanation/table/note and under-size the tip.
        expl = (self._explanation.text() or "").strip()
        direction = (self._direction.text() or "").strip()
        note = (self._note.text() or "").strip()

        scale_w = visual.scale_min_width
        scale_h = visual.scale_preferred_height
        content_w = max(title_w, value_w, scale_w, inner_w) + 2 * pad
        text_w = max(1, content_w - 2 * pad)

        expl_w, expl_h = self._wrapped_size(expl, self._body_font, text_w)
        dir_w, dir_h = self._label_line_size(direction, self._small_font)
        table_size = self._band_table.preferred_size(text_w)
        note_w, note_h = self._wrapped_size(note, self._small_font, text_w)

        self._pin_label(self._title, title_w, title_h, text_w)
        self._pin_label(self._value, value_w, value_h, text_w)
        if expl_h > 0:
            self._pin_label(self._explanation, max(expl_w, text_w), expl_h, text_w)
        if dir_h > 0:
            self._pin_label(self._direction, max(dir_w, text_w), dir_h, text_w)
        if table_size.height() > 0:
            self._band_table.setFixedSize(max(1, text_w), max(1, table_size.height()))
        if note_h > 0:
            self._pin_label(self._note, max(note_w, text_w), note_h, text_w)
        self._scale.setFixedSize(max(1, text_w), max(1, scale_h))

        spacing = visual.content_spacing
        blocks = [title_h, value_h]
        if expl_h > 0:
            blocks.append(expl_h)
        blocks.append(scale_h)
        if dir_h > 0:
            blocks.append(dir_h)
        if table_size.height() > 0:
            blocks.append(table_size.height())
        if note_h > 0:
            blocks.append(note_h)
        content_h = sum(blocks) + spacing * (len(blocks) - 1) + 2 * pad
        return QSize(int(content_w), int(content_h))

    @staticmethod
    def _label_line_size(text: str, font: QFont) -> Tuple[int, int]:
        if not text:
            return 0, 0
        metrics = QFontMetrics(font)
        return metrics.boundingRect(text).width() + 4, metrics.height() + 2

    @staticmethod
    def _wrapped_size(text: str, font: QFont, max_width: int) -> Tuple[int, int]:
        if not text:
            return 0, 0
        metrics = QFontMetrics(font)
        line_h = metrics.height() + 2
        width = max(1, int(max_width))
        single = metrics.boundingRect(text).width() + 4
        if single <= width:
            return single, line_h
        rect = metrics.boundingRect(
            QRect(0, 0, width, 10_000),
            int(Qt.TextFlag.TextWordWrap),
            text,
        )
        # Small slack so wrapped lines are not clipped under fixed heights.
        return width, max(line_h, rect.height() + 6)

    @staticmethod
    def _pin_label(label: QLabel, width: int, height: int, max_width: int) -> None:
        """Keep wrapping labels from expanding and creating vertical gaps."""
        w = max(1, min(int(width), int(max_width)))
        h = max(1, int(height))
        label.setMinimumSize(0, 0)
        label.setMaximumSize(16777215, 16777215)
        label.setFixedWidth(w)
        label.setFixedHeight(h)

    def _place_content(self) -> None:
        """Keep content inside the straight part of the rounded body."""
        radius = self._style.border_radius
        caret = self._style.caret_size
        if self._caret_edge == "top":
            top = caret + radius
        else:
            top = radius
        self._content.setGeometry(
            radius,
            top,
            max(0, self._content_size.width()),
            max(0, self._content_size.height()),
        )

    def _shape_path(self) -> QPainterPath:
        # Same caret/body union as MoveLinkPopup: overlap the triangle into the
        # body by 1px so the border does not draw a seam across the caret base.
        style = self._style
        caret = float(style.caret_size)
        radius = float(style.border_radius)
        inset = max(0.5, style.border_width / 2.0)
        width = float(self.width())
        height = float(self.height())
        if self._caret_edge == "top":
            body = QRectF(inset, caret + inset, width - 2 * inset, height - caret - 2 * inset)
            tip_y = inset
            base_y = caret + inset + 1.0
        else:
            body = QRectF(inset, inset, width - 2 * inset, height - caret - 2 * inset)
            tip_y = height - inset
            base_y = height - caret - inset - 1.0
        center = float(self._caret_x)
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)
        triangle = QPainterPath()
        triangle.moveTo(center - caret, base_y)
        triangle.lineTo(center, tip_y)
        triangle.lineTo(center + caret, base_y)
        triangle.closeSubpath()
        return path.united(triangle)


class HoverableKpiValueLabel(QLabel):
    """Value label that shows a KPI explanation popup on hover."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._kpi_tip: Optional[KpiTip] = None
        self._kpi_popup: Optional[KpiExplainPopup] = None
        self._hover_timer: Optional[QTimer] = None
        self._visual: Optional[KpiTipVisualStyle] = None
        self._hovering = False
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    @property
    def kpi_tip(self) -> Optional[KpiTip]:
        return self._kpi_tip

    @property
    def kpi_popup(self) -> Optional[KpiExplainPopup]:
        return self._kpi_popup

    def attach_kpi_tip(self, tip: KpiTip, popup: KpiExplainPopup) -> None:
        self._kpi_tip = tip
        self._kpi_popup = popup
        self._visual = popup.visual_style
        if self._hover_timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._show_kpi_tip)
            self._hover_timer = timer

    def event(self, event: QEvent) -> bool:  # noqa: N802
        etype = event.type()
        if etype == QEvent.Type.HoverEnter:
            self._begin_hover()
        elif etype == QEvent.Type.HoverMove:
            # Recover when ToolTip show/hide synthesizes leave without re-enter.
            self._begin_hover()
        elif etype == QEvent.Type.HoverLeave:
            self._end_hover()
        return super().event(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self._begin_hover()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._end_hover()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        super().mouseMoveEvent(event)
        self._begin_hover()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._hover_timer is not None:
            self._hover_timer.stop()
        if self._kpi_popup is not None:
            self._kpi_popup.hide_for(self)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        visual = self._visual
        if visual is None:
            return
        style_name = (
            visual.value_underline_style_hover
            if self._hovering
            else visual.value_underline_style
        )
        if style_name in ("", "none"):
            return
        text = self.text() or ""
        if not text:
            return
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(text)
        if text_w <= 0:
            return
        cr = self.contentsRect()
        align = self.alignment()
        if align & Qt.AlignmentFlag.AlignRight:
            x0 = cr.right() - text_w + 1
        elif align & Qt.AlignmentFlag.AlignHCenter:
            x0 = cr.left() + (cr.width() - text_w) // 2
        else:
            x0 = cr.left()
        # Match QLabel's vertical centering for single-line values.
        text_top = cr.top() + max(0, (cr.height() - fm.height()) // 2)
        y = text_top + fm.ascent() + 2
        rgb = (
            visual.value_underline_color_hover
            if self._hovering
            else visual.value_underline_color
        )
        pen = QPen(QColor(*rgb))
        pen.setCosmetic(True)
        pen.setWidth(1)
        if style_name == "dotted":
            pen.setStyle(Qt.PenStyle.DotLine)
        elif style_name == "dashed":
            pen.setStyle(Qt.PenStyle.DashLine)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        painter = QPainter(self)
        painter.setPen(pen)
        painter.drawLine(x0, y, x0 + text_w - 1, y)

    def _begin_hover(self) -> None:
        tip = self._kpi_tip
        popup = self._kpi_popup
        timer = self._hover_timer
        if tip is None or popup is None or timer is None:
            return
        if not self._hovering:
            self._hovering = True
            self.update()
        already_showing_here = popup.isVisible() and popup.owns_anchor(self)
        if already_showing_here and popup.is_armed_for(self):
            return
        popup.arm_hover(self)
        # Retarget immediately when a tip is already up, or when a hide is only
        # deferred — waiting another full delay is how handoffs get missed.
        if popup.isVisible() or popup.hover_delay_ms <= 0:
            self._show_kpi_tip()
        elif not timer.isActive():
            timer.start(popup.hover_delay_ms)

    def _end_hover(self) -> None:
        if self._hovering:
            self._hovering = False
            self.update()
        if self._hover_timer is not None:
            self._hover_timer.stop()
        if self._kpi_popup is not None:
            self._kpi_popup.schedule_hide_for(self)

    def _show_kpi_tip(self) -> None:
        tip = self._kpi_tip
        popup = self._kpi_popup
        if tip is None or popup is None:
            return
        if not popup.is_armed_for(self):
            return
        popup.present(self, tip)
