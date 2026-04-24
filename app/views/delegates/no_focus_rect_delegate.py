"""Delegates that suppress the Qt 'current cell' focus rectangle.

Qt styles often draw a focus/active-rect border around the current index even when
QSS tries to disable it. Clearing State_HasFocus at paint-time is the most robust
cross-platform way to remove that border without affecting selection colors.
"""

from __future__ import annotations

from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem


class NoFocusRectItemDelegate(QStyledItemDelegate):
    """Item delegate that prevents drawing the focus rectangle."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:  # type: ignore[override]
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, opt, index)

