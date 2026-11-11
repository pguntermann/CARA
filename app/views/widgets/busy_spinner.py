"""Animated circular spinner widget."""

from typing import Optional

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class BusySpinner(QWidget):
    """Animated circular spinner.

    Call ``start()`` to begin animating and show the widget.
    Call ``stop()`` to freeze the animation and hide the widget.
    The widget starts hidden; ``start()`` makes it visible.
    """

    def __init__(
        self,
        *,
        color: QColor,
        track_color: Optional[QColor] = None,
        size: int = 20,
        line_width: int = 2,
        span_degrees: int = 110,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._track_color = track_color
        self._line_width = max(2, int(line_width))
        self._span_degrees = max(60, min(270, int(span_degrees)))
        self._angle = 0
        side = max(16, int(size))
        self.setFixedSize(side, side)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setVisible(False)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self.setVisible(True)

    def stop(self) -> None:
        self._timer.stop()
        self.setVisible(False)

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inset = self._line_width / 2.0 + 1.0
        rect = QRectF(inset, inset, self.width() - 2 * inset, self.height() - 2 * inset)

        if self._track_color is not None:
            track_pen = QPen(
                self._track_color,
                float(self._line_width),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
            painter.setPen(track_pen)
            painter.drawEllipse(rect)

        pen = QPen(
            self._color,
            float(self._line_width),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.drawArc(rect, int((-self._angle) * 16), int(self._span_degrees) * 16)
