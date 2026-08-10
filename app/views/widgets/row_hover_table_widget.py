"""QTableWidget with full-row hover highlighting.

Qt stylesheets only apply ``::item:hover`` to the cell under the cursor. This
widget tracks the hovered row and paints every cell in that row so hover reads
as a full row (matching selection behavior).
"""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QCursor
from PyQt6.QtWidgets import QTableWidget, QWidget


class RowHoverTableWidget(QTableWidget):
    """Table that highlights the entire hovered row, not only one cell."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._hover_row = -1
        self._hover_bg = (60, 60, 65)
        self._hover_text = (200, 200, 200)
        self._selection_bg: Optional[tuple[int, int, int]] = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self.installEventFilter(self)

    def configure_row_chrome(
        self,
        *,
        hover_bg: Sequence[int],
        hover_text: Sequence[int],
        selection_bg: Optional[Sequence[int]] = None,
    ) -> None:
        """Set colors used when painting hover / selected cell widgets."""
        self._hover_bg = (int(hover_bg[0]), int(hover_bg[1]), int(hover_bg[2]))
        self._hover_text = (int(hover_text[0]), int(hover_text[1]), int(hover_text[2]))
        if selection_bg is None:
            self._selection_bg = None
        else:
            self._selection_bg = (
                int(selection_bg[0]),
                int(selection_bg[1]),
                int(selection_bg[2]),
            )

    def clear_hover(self) -> None:
        """Reset hover highlighting (e.g. after rebuilding rows)."""
        self._set_hover_row(-1)

    def refresh_row_chrome(self) -> None:
        """Re-apply hover/selection chrome for all rows."""
        for row in range(self.rowCount()):
            self.apply_row_chrome(row)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        et = event.type()
        if et in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
            QEvent.Type.Enter,
        ):
            self._update_hover_from_cursor()
        elif et == QEvent.Type.Leave:
            # Child widgets may emit Leave; re-check after the event settles.
            QTimer.singleShot(0, self._update_hover_from_cursor)
        return super().eventFilter(watched, event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        QTimer.singleShot(0, self._update_hover_from_cursor)
        super().leaveEvent(event)

    def track_cell_widget(self, widget: QWidget) -> None:
        """Follow hover while the cursor is over embedded cell widgets."""
        widget.setMouseTracking(True)
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.setMouseTracking(True)
            child.installEventFilter(self)

    def _update_hover_from_cursor(self) -> None:
        if not self.isVisible():
            self._set_hover_row(-1)
            return
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(pos):
            self._set_hover_row(-1)
            return
        index = self.indexAt(pos)
        self._set_hover_row(index.row() if index.isValid() else -1)

    def _set_hover_row(self, row: int) -> None:
        if row == self._hover_row:
            return
        previous = self._hover_row
        self._hover_row = row
        if previous >= 0:
            self.apply_row_chrome(previous)
        if row >= 0:
            self.apply_row_chrome(row)

    def apply_row_chrome(self, row: int) -> None:
        """Paint selection / hover / default chrome for one row."""
        if row < 0 or row >= self.rowCount():
            return

        selected = False
        model = self.selectionModel()
        if model is not None:
            selected = model.isRowSelected(row, self.rootIndex())

        if selected:
            # Selection styling for items comes from the stylesheet.
            item_bg = None
            item_fg = None
            if self._selection_bg is not None:
                widget_bg = (
                    f"background-color: rgb({self._selection_bg[0]}, "
                    f"{self._selection_bg[1]}, {self._selection_bg[2]});"
                )
            else:
                widget_bg = "background-color: transparent;"
        elif row == self._hover_row:
            item_bg = QBrush(QColor(*self._hover_bg))
            item_fg = QBrush(QColor(*self._hover_text))
            widget_bg = (
                f"background-color: rgb({self._hover_bg[0]}, "
                f"{self._hover_bg[1]}, {self._hover_bg[2]});"
            )
        else:
            item_bg = QBrush()
            item_fg = QBrush()
            widget_bg = "background-color: transparent;"

        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item is not None:
                if item_bg is None:
                    item.setData(Qt.ItemDataRole.BackgroundRole, None)
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
                else:
                    item.setBackground(item_bg)
                    item.setForeground(item_fg)
            cell = self.cellWidget(row, col)
            if cell is not None:
                cell.setStyleSheet(widget_bg)
