"""Item delegate that paints themed separators in a QComboBox dropdown.

Normal items are drawn with ``QItemDelegate`` (same base Qt uses for combo
popups), so appearance stays aligned with other styled comboboxes. Only rows
created by ``QComboBox.insertSeparator()`` are customized.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QModelIndex, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox, QItemDelegate, QStyleOptionViewItem


def _rgb(value: Any, default: Sequence[int]) -> Tuple[int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    return (int(default[0]), int(default[1]), int(default[2]))


def _is_separator(index: QModelIndex) -> bool:
    return (
        index.data(Qt.ItemDataRole.AccessibleDescriptionRole) == "separator"
    )


class ComboBoxSeparatorDelegate(QItemDelegate):
    """Paint ``insertSeparator`` rows as a horizontal theme-colored line."""

    def __init__(
        self,
        separator_color: Sequence[int],
        *,
        row_height: int = 8,
        line_thickness: int = 1,
        horizontal_margin: int = 8,
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(
            int(separator_color[0]),
            int(separator_color[1]),
            int(separator_color[2]),
        )
        self._row_height = max(3, int(row_height))
        self._line_thickness = max(1, int(line_thickness))
        self._horizontal_margin = max(0, int(horizontal_margin))

    def paint(  # type: ignore[override]
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        if not _is_separator(index):
            super().paint(painter, option, index)
            return

        painter.save()
        bg = option.palette.color(option.palette.ColorRole.Base)
        if not bg.isValid():
            bg = option.palette.color(option.palette.ColorRole.Window)
        painter.fillRect(option.rect, bg)

        pen = QPen(self._color)
        pen.setWidth(self._line_thickness)
        painter.setPen(pen)
        y = option.rect.center().y()
        left = option.rect.left() + self._horizontal_margin
        right = option.rect.right() - self._horizontal_margin
        if right > left:
            painter.drawLine(left, y, right, y)
        painter.restore()

    def sizeHint(  # type: ignore[override]
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        if _is_separator(index):
            return QSize(-1, self._row_height)
        return super().sizeHint(option, index)


def apply_combobox_separator_delegate(
    combobox: QComboBox,
    config: Dict[str, Any],
) -> ComboBoxSeparatorDelegate:
    """Attach a separator-aware delegate without changing normal item painting.

    Colors come from ``ui.styles.combobox.separator_*``, falling back to the
    shared menu separator background token.
    """
    styles = (config.get("ui") or {}).get("styles") or {}
    combo_cfg = styles.get("combobox") or {}
    if not isinstance(combo_cfg, dict):
        combo_cfg = {}

    menu_sep = ((config.get("ui") or {}).get("menu") or {}).get("separator") or {}
    default_color: List[int] = [60, 60, 65]
    if isinstance(menu_sep, dict):
        default_color = list(
            _rgb(menu_sep.get("background_color"), default_color)
        )

    color = _rgb(combo_cfg.get("separator_color"), default_color)
    try:
        row_height = int(combo_cfg.get("separator_row_height", 8))
    except (TypeError, ValueError):
        row_height = 8
    try:
        thickness = int(combo_cfg.get("separator_thickness", 1))
    except (TypeError, ValueError):
        thickness = 1
    try:
        h_margin = int(combo_cfg.get("separator_horizontal_margin", 8))
    except (TypeError, ValueError):
        h_margin = 8

    delegate = ComboBoxSeparatorDelegate(
        color,
        row_height=row_height,
        line_thickness=thickness,
        horizontal_margin=h_margin,
        parent=combobox,
    )
    combobox.setItemDelegate(delegate)
    return delegate
