"""Win probability bar for UCI WDL (white / draw / black)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.utils.font_utils import resolve_font_family, scale_font_size


class WinProbabilityBarWidget(QWidget):
    """Horizontal stacked White/Draw/Black bar from white-POV UCI WDL permille."""

    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._wdl: Optional[Tuple[int, int, int]] = None  # white, draw, black permille
        self._load_config()
        self._setup_ui()
        self.setVisible(False)

    def _manual_analysis_config(self) -> Dict[str, Any]:
        return (
            self.config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("manual_analysis", {})
        )

    def _load_config(self) -> None:
        ma = self._manual_analysis_config()
        # Behavior (enabled) lives in config.json; colors/geometry in style configs.
        behavior = ma.get("win_probability", {}) if isinstance(ma.get("win_probability", {}), dict) else {}
        style = ma.get("win_probability", {}) if isinstance(ma.get("win_probability", {}), dict) else {}
        # Prefer style keys; fall back to behavior defaults for shared keys.
        self._enabled = bool(behavior.get("enabled", True))
        self._show_title = bool(style.get("show_title", True))
        self._show_labels = bool(style.get("show_labels", True))
        self._title_text = str(style.get("title", "Win probability (best engine play)"))
        self._bar_height = int(style.get("bar_height", 8))
        self._segment_gap = int(style.get("segment_gap", 1))
        self._border_radius = int(style.get("border_radius", 3))
        self._border_width = int(style.get("border_width", 1))
        self._spacing = int(style.get("spacing", 6))
        padding = style.get("padding", [8, 6, 8, 6])
        self._padding = padding if isinstance(padding, list) and len(padding) >= 4 else [8, 6, 8, 6]

        def _rgb(value: Any, default: Tuple[int, int, int]) -> Tuple[int, int, int]:
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                try:
                    return (int(value[0]), int(value[1]), int(value[2]))
                except (TypeError, ValueError):
                    return default
            return default

        self._white_color = _rgb(style.get("white_color"), (245, 245, 245))
        self._draw_color = _rgb(style.get("draw_color"), (140, 140, 148))
        self._black_color = _rgb(style.get("black_color"), (28, 28, 32))
        self._border_color = _rgb(style.get("border_color"), (90, 90, 98))
        self._background_color = _rgb(style.get("background_color"), (45, 45, 50))
        self._label_color = _rgb(style.get("label_color"), (180, 180, 180))
        self._title_color = _rgb(style.get("title_color"), self._label_color)
        self._font_size = scale_font_size(style.get("font_size", 9))

        tabs = (
            self.config.get("ui", {})
            .get("panels", {})
            .get("detail", {})
            .get("tabs", {})
        )
        self._font_family = resolve_font_family(tabs.get("font_family", "Helvetica Neue"))

    def _setup_ui(self) -> None:
        # Custom QWidget subclasses need this for stylesheet backgrounds to paint.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._padding[0], self._padding[1], self._padding[2], self._padding[3]
        )
        layout.setSpacing(self._spacing)

        self._title_label = QLabel(self._title_text)
        self._title_label.setVisible(self._show_title)
        layout.addWidget(self._title_label)

        self._bar = _WdlBarCanvas(self)
        self._bar.setFixedHeight(self._bar_height)
        self._bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._bar)

        self._labels = QLabel("")
        self._labels.setVisible(self._show_labels)
        layout.addWidget(self._labels)

        self._apply_styling()

    def _apply_styling(self) -> None:
        bg = self._background_color
        self.setStyleSheet(
            f"WinProbabilityBarWidget {{ background-color: rgb({bg[0]}, {bg[1]}, {bg[2]}); border: none; }}"
        )
        title_c = self._title_color
        label_c = self._label_color
        font = QFont(self._font_family, int(self._font_size))
        self._title_label.setFont(font)
        self._labels.setFont(font)
        self._title_label.setStyleSheet(
            f"QLabel {{ color: rgb({title_c[0]}, {title_c[1]}, {title_c[2]}); background: transparent; border: none; }}"
        )
        self._labels.setStyleSheet(
            f"QLabel {{ color: rgb({label_c[0]}, {label_c[1]}, {label_c[2]}); background: transparent; border: none; }}"
        )
        # Also set palette so platform styles can't override label contrast
        for label, color in (
            (self._title_label, title_c),
            (self._labels, label_c),
        ):
            palette = label.palette()
            palette.setColor(label.foregroundRole(), QColor(color[0], color[1], color[2]))
            label.setPalette(palette)
            label.update()

    def set_wdl(self, wdl: Optional[Tuple[int, int, int]]) -> None:
        """Update bar from white-POV permille values, or hide when None."""
        if not self._enabled:
            self._wdl = None
            self.setVisible(False)
            return
        self._wdl = wdl
        if wdl is None:
            self.setVisible(False)
            self._bar.set_fractions(None)
            self._labels.setText("")
            return

        white, draw, black = wdl
        total = max(white + draw + black, 1)
        self._bar.set_fractions((white / total, draw / total, black / total))
        self._bar.set_colors(self._white_color, self._draw_color, self._black_color)
        self._bar.set_chrome(
            self._segment_gap, self._border_radius, self._border_width, self._border_color
        )

        white_pct = int(round(100.0 * white / total))
        draw_pct = int(round(100.0 * draw / total))
        black_pct = max(0, 100 - white_pct - draw_pct)
        self._labels.setText(f"White {white_pct}%    Draw {draw_pct}%    Black {black_pct}%")
        self.setVisible(True)
        self._bar.update()


class _WdlBarCanvas(QWidget):
    """Paints the three WDL segments."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._fractions: Optional[Tuple[float, float, float]] = None
        self._white = QColor(245, 245, 245)
        self._draw = QColor(140, 140, 148)
        self._black = QColor(28, 28, 32)
        self._gap = 1
        self._radius = 3
        self._border_width = 1
        self._border = QColor(90, 90, 98)

    def set_fractions(self, fractions: Optional[Tuple[float, float, float]]) -> None:
        self._fractions = fractions
        self.update()

    def set_colors(
        self,
        white: Tuple[int, int, int],
        draw: Tuple[int, int, int],
        black: Tuple[int, int, int],
    ) -> None:
        self._white = QColor(*white)
        self._draw = QColor(*draw)
        self._black = QColor(*black)

    def set_chrome(
        self,
        gap: int,
        radius: int,
        border_width: int,
        border_color: Tuple[int, int, int],
    ) -> None:
        self._gap = max(0, gap)
        self._radius = max(0, radius)
        self._border_width = max(0, border_width)
        self._border = QColor(*border_color)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        if self._fractions is None:
            painter.end()
            return

        white_f, draw_f, black_f = self._fractions
        gaps = self._gap * 2
        usable = max(0.0, rect.width() - gaps)
        white_w = usable * white_f
        draw_w = usable * draw_f
        black_w = max(0.0, usable - white_w - draw_w)

        x = rect.x()
        y = rect.y()
        h = rect.height()

        def _draw_seg(color: QColor, width: float) -> None:
            nonlocal x
            if width <= 0.05:
                return
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y, width, h), self._radius, self._radius)
            x += width + self._gap

        _draw_seg(self._white, white_w)
        _draw_seg(self._draw, draw_w)
        _draw_seg(self._black, black_w)

        if self._border_width > 0:
            pen = QPen(self._border)
            pen.setWidth(self._border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, self._radius, self._radius)

        painter.end()
