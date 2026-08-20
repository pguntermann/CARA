"""Custom scrollbar with an enlarged grab zone and visual hover feedback.

The scrollbar keeps the configured ``width`` for layout.  An event filter
installed on the parent ``QAbstractScrollArea`` intercepts mouse presses
that land within ``grab_margin`` pixels of the scrollbar edge and forwards
them as if they hit the scrollbar, making the narrow handle much easier to
grab.

On hover the painted handle widens by ``hover_handle_width_extra`` pixels
and switches to ``hover_handle_color``, giving visual confirmation that
the user is in the grab zone.

All tunables live under ``ui.styles.scrollbar`` in the theme config.
"""

from typing import Dict, Any, List, Optional

from PyQt6.QtCore import Qt, QRect, QEvent, QPoint, QSize, QObject
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QMouseEvent, QBrush
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QScrollBar,
    QStyle,
    QStyleOptionSlider,
)


def _scrollbar_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return (config or {}).get("ui", {}).get("styles", {}).get("scrollbar", {})


def _resolve_color(raw, fallback: List[int]) -> List[int]:
    if isinstance(raw, list) and len(raw) >= 3:
        return raw[:3]
    return fallback


class _GrabZoneFilter(QObject):
    """Event filter that widens the effective grab area of a scrollbar.

    Installed on the :class:`QAbstractScrollArea`.  When a mouse press
    lands within *grab_margin* pixels of the scrollbar (but outside it),
    the event is re-posted to the scrollbar so the drag starts
    immediately.
    """

    def __init__(
        self,
        scroll_area: QAbstractScrollArea,
        bar: "GrabFriendlyScrollBar",
        grab_margin: int,
    ) -> None:
        super().__init__(scroll_area)
        self._scroll_area = scroll_area
        self._bar = bar
        self._grab_margin = grab_margin

    def set_grab_margin(self, margin: int) -> None:
        self._grab_margin = max(0, margin)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        ):
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if not self._bar.isVisible():
            return False

        bar_geo = self._bar.geometry()
        pos = event.position().toPoint()

        if self._bar.orientation() == Qt.Orientation.Vertical:
            expanded = QRect(
                bar_geo.left() - self._grab_margin,
                bar_geo.top(),
                bar_geo.width() + self._grab_margin,
                bar_geo.height(),
            )
        else:
            expanded = QRect(
                bar_geo.left(),
                bar_geo.top() - self._grab_margin,
                bar_geo.width(),
                bar_geo.height() + self._grab_margin,
            )

        if not expanded.contains(pos) or bar_geo.contains(pos):
            return False

        local = self._bar.mapFromParent(pos)
        redirected = QMouseEvent(
            event.type(),
            local.toPointF(),
            event.globalPosition(),
            event.button(),
            event.buttons(),
            event.modifiers(),
        )
        self._bar._enter_via_grab_zone()
        self._bar.mousePressEvent(redirected)
        return True


class GrabFriendlyScrollBar(QScrollBar):
    """QScrollBar with a wider effective grab area and hover-widened handle."""

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Vertical,
        parent=None,
        *,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(orientation, parent)
        cfg = _scrollbar_config(config or {})

        self._grab_margin: int = max(0, int(cfg.get("grab_margin", 4)))
        self._hover_extra: int = max(0, int(cfg.get("hover_handle_width_extra", 2)))

        handle_color = cfg.get("handle_color", [70, 70, 75])
        handle_hover_color = cfg.get("handle_hover_color", handle_color)
        hover_handle_color = cfg.get("hover_handle_color", None)

        self._handle_color = QColor(*_resolve_color(handle_color, [70, 70, 75]))
        self._handle_hover_color = QColor(
            *_resolve_color(hover_handle_color or handle_hover_color, self._handle_color.getRgb()[:3])
        )
        self._bg_color: Optional[QColor] = None
        bg_raw = cfg.get("background_color")
        if isinstance(bg_raw, list) and len(bg_raw) >= 3:
            self._bg_color = QColor(*bg_raw[:3])

        self._border_radius: int = int(cfg.get("border_radius", 3))
        self._track_width: int = int(cfg.get("width", 6))
        self._min_handle: int = int(cfg.get("min_height", 20))

        self._hovered = False
        self._grab_filter: Optional[_GrabZoneFilter] = None

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setMouseTracking(True)

        if orientation == Qt.Orientation.Vertical:
            self.setFixedWidth(self._track_width)
        else:
            self.setFixedHeight(self._track_width)

    # ------------------------------------------------------------------
    # Grab-zone event filter management
    # ------------------------------------------------------------------

    def install_grab_zone_filter(self, scroll_area: QAbstractScrollArea) -> None:
        """Install the grab-zone event filter on *scroll_area*."""
        if self._grab_filter is not None:
            return
        self._grab_filter = _GrabZoneFilter(scroll_area, self, self._grab_margin)
        scroll_area.installEventFilter(self._grab_filter)

    def _enter_via_grab_zone(self) -> None:
        """Activate hover state when a click arrives via the grab-zone filter."""
        if not self._hovered:
            self._hovered = True
            self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        widget_rect = self.rect()

        if self._bg_color is not None:
            painter.fillRect(widget_rect, self._bg_color)
        else:
            painter.fillRect(widget_rect, Qt.GlobalColor.transparent)

        handle = self._handle_rect()
        if handle.isNull():
            painter.end()
            return

        color = self._handle_hover_color if self._hovered else self._handle_color

        if self.orientation() == Qt.Orientation.Vertical:
            tw = widget_rect.width()
            if self._hovered:
                r = QRect(0, handle.y(), tw, handle.height())
            else:
                inset = max(1, min(self._hover_extra, (tw - 2) // 2))
                r = QRect(inset, handle.y(), tw - 2 * inset, handle.height())
        else:
            th = widget_rect.height()
            if self._hovered:
                r = QRect(handle.x(), 0, handle.width(), th)
            else:
                inset = max(1, min(self._hover_extra, (th - 2) // 2))
                r = QRect(handle.x(), inset, handle.width(), th - 2 * inset)

        radius = min(self._border_radius, r.width() // 2, r.height() // 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(r, radius, radius)
        painter.end()

    def _handle_rect(self) -> QRect:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        style = self.style()
        if style is None:
            return QRect()
        return style.subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            opt,
            QStyle.SubControl.SC_ScrollBarSlider,
            self,
        )

    # ------------------------------------------------------------------
    # Hover tracking
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    # Configuration update (theme switch)
    # ------------------------------------------------------------------

    def apply_config(self, config: Dict[str, Any]) -> None:
        """Re-read colours and dimensions from a new theme config."""
        cfg = _scrollbar_config(config)

        self._grab_margin = max(0, int(cfg.get("grab_margin", 4)))
        self._hover_extra = max(0, int(cfg.get("hover_handle_width_extra", 2)))
        self._border_radius = int(cfg.get("border_radius", 3))
        self._track_width = int(cfg.get("width", 6))
        self._min_handle = int(cfg.get("min_height", 20))

        handle_color = cfg.get("handle_color", [70, 70, 75])
        handle_hover_color = cfg.get("handle_hover_color", handle_color)
        hover_handle_color = cfg.get("hover_handle_color", None)

        self._handle_color = QColor(*_resolve_color(handle_color, [70, 70, 75]))
        self._handle_hover_color = QColor(
            *_resolve_color(hover_handle_color or handle_hover_color, self._handle_color.getRgb()[:3])
        )

        bg_raw = cfg.get("background_color")
        if isinstance(bg_raw, list) and len(bg_raw) >= 3:
            self._bg_color = QColor(*bg_raw[:3])
        else:
            self._bg_color = None

        if self.orientation() == Qt.Orientation.Vertical:
            self.setFixedWidth(self._track_width)
        else:
            self.setFixedHeight(self._track_width)

        if self._grab_filter is not None:
            self._grab_filter.set_grab_margin(self._grab_margin)

        self.update()
