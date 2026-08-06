"""Horizontal separator that paints at a stable device-pixel thickness.

A themed logical height (typically 1) is rounded to whole device pixels and drawn
without antialiasing, so fractional OS scale factors do not make sibling lines
appear 1px vs 2px thick after layout reflow.
"""

from __future__ import annotations

import math
from typing import Sequence, Union

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QPainter, QPaintEvent, QShowEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget


class PixelAlignedHLine(QWidget):
    """Theme-height horizontal rule with HiDPI-stable stroke thickness."""

    def __init__(
        self,
        color: Union[QColor, Sequence[int]],
        height: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = self._as_color(color)
        self._logical_height = max(1, int(height))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._apply_layout_height()

    @staticmethod
    def _as_color(color: Union[QColor, Sequence[int]]) -> QColor:
        if isinstance(color, QColor):
            return QColor(color)
        return QColor(int(color[0]), int(color[1]), int(color[2]))

    def set_line_color(self, color: Union[QColor, Sequence[int]]) -> None:
        self._color = self._as_color(color)
        self.update()

    def set_logical_height(self, height: int) -> None:
        self._logical_height = max(1, int(height))
        self._apply_layout_height()
        self.update()

    def _dpr(self) -> float:
        win = self.window()
        if win is not None:
            try:
                return max(1.0, float(win.devicePixelRatioF()))
            except Exception:
                pass
        return max(1.0, float(self.devicePixelRatioF()))

    def _device_height(self) -> int:
        return max(1, int(round(self._logical_height * self._dpr())))

    def _apply_layout_height(self) -> None:
        """Reserve enough logical height for the snapped device-pixel stroke."""
        logical = self._device_height() / self._dpr()
        self.setFixedHeight(max(self._logical_height, int(math.ceil(logical - 1e-9))))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        dpr = self._dpr()
        device_h = self._device_height()
        # Paint in device pixels so every instance of the same logical height
        # resolves to the same physical thickness.
        painter.scale(1.0 / dpr, 1.0 / dpr)
        width_px = max(1, int(round(self.width() * dpr)))
        painter.fillRect(0, 0, width_px, device_h, self._color)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_layout_height()

    def event(self, event: QEvent) -> bool:  # noqa: N802
        # Keep stroke snap correct when moving between differently scaled screens.
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            self._apply_layout_height()
            self.update()
        return super().event(event)
