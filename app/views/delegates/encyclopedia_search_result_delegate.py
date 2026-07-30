"""Delegate that paints encyclopedia search rows with themed ECO chips."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PyQt6.QtCore import QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.utils.font_utils import resolve_font_family, scale_font_size

# opening_id lives in UserRole; ECO chip label in UserRole+1.
ECO_CHIP_ROLE = int(Qt.ItemDataRole.UserRole) + 1


def _rgb(value: Any, default: Sequence[int]) -> List[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [int(value[0]), int(value[1]), int(value[2])]
    return [int(default[0]), int(default[1]), int(default[2])]


class EncyclopediaSearchResultDelegate(QStyledItemDelegate):
    """Paint opening name + optional ECO chip matching dialog tag styling."""

    def __init__(
        self,
        tags_cfg: Dict[str, Any],
        *,
        name_color: Optional[Sequence[int]] = None,
        selected_name_color: Optional[Sequence[int]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(tags_cfg, dict):
            tags_cfg = {}

        self._name_color = QColor(*_rgb(name_color, [200, 200, 205]))
        self._selected_name_color = QColor(
            *_rgb(selected_name_color, name_color or [230, 230, 236])
        )
        self._chip_bg = QColor(*_rgb(tags_cfg.get("eco_background"), [65, 55, 55]))
        self._chip_fg = QColor(*_rgb(tags_cfg.get("eco_text_color"), [210, 160, 130]))
        self._chip_radius = int(tags_cfg.get("border_radius", 4))
        pad = tags_cfg.get("padding", [2, 6, 2, 6])
        if not isinstance(pad, (list, tuple)) or len(pad) < 4:
            pad = [2, 6, 2, 6]
        self._pad_v = int(pad[0])
        self._pad_h = int(pad[1])
        self._chip_font = QFont(
            resolve_font_family("Helvetica Neue"),
            int(scale_font_size(tags_cfg.get("font_size", 8))),
        )
        self._name_gap = 8

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # Overflow / non-result rows keep the default item rendering.
        if not index.data(Qt.ItemDataRole.UserRole):
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        name = str(opt.text or "")
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        eco = index.data(ECO_CHIP_ROLE)
        eco_text = str(eco).strip() if eco else ""

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect.adjusted(8, 4, -8, -4)
        if rect.width() <= 2 or rect.height() <= 2:
            painter.restore()
            return

        name_font = QFont(option.font)
        painter.setFont(name_font)
        name_fm = QFontMetrics(name_font)

        chip_w = 0
        chip_h = 0
        chip_fm = QFontMetrics(self._chip_font)
        if eco_text:
            chip_h = max(chip_fm.height() + 2 * self._pad_v, name_fm.height())
            chip_w = int(chip_fm.horizontalAdvance(eco_text) + 2 * self._pad_h)

        name_max_w = rect.width()
        if chip_w > 0:
            name_max_w = max(40, rect.width() - chip_w - self._name_gap)

        elided = name_fm.elidedText(name, Qt.TextElideMode.ElideRight, name_max_w)
        name_w = min(int(name_fm.horizontalAdvance(elided)), name_max_w)
        name_y = rect.y() + (rect.height() - name_fm.height()) // 2

        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(self._selected_name_color)
        else:
            painter.setPen(self._name_color)
        painter.drawText(
            QRect(rect.x(), name_y, name_w, name_fm.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            elided,
        )

        if eco_text and chip_w > 0:
            chip_x = rect.x() + name_w + self._name_gap
            if chip_x + chip_w > rect.right():
                chip_x = max(rect.x(), rect.right() - chip_w + 1)
            chip_y = rect.y() + (rect.height() - chip_h) // 2
            chip_rect = QRect(chip_x, chip_y, chip_w, chip_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._chip_bg)
            painter.drawRoundedRect(chip_rect, self._chip_radius, self._chip_radius)
            painter.setPen(self._chip_fg)
            painter.setFont(self._chip_font)
            painter.drawText(
                chip_rect.adjusted(self._pad_h, 0, -self._pad_h, 0),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter),
                eco_text,
            )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        base = super().sizeHint(option, index)
        chip_fm = QFontMetrics(self._chip_font)
        chip_h = chip_fm.height() + 2 * self._pad_v
        return QSize(base.width(), max(base.height(), chip_h + 8))
