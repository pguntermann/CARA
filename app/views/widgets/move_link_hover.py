"""Hover tracking for a move link drawn inside a text widget."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QTextCursor, QTextDocument
from PyQt6.QtWidgets import QLabel, QTextEdit, QWidget

from app.views.widgets.move_link_popup import MoveLinkPopup, MoveLinkTip


def notation_from_move_href(href: str) -> str:
    """Notation stored in a ``move:`` link, or empty when ``href`` is not one."""
    text = str(href or "")
    if not text.startswith("move:"):
        return ""
    return text.split("move:", 1)[1]


class MoveLinkHover:
    """Show one popup while the pointer rests on a move link."""

    def __init__(
        self,
        owner: QWidget,
        popup: MoveLinkPopup,
        tip_for: Callable[[str], Optional[MoveLinkTip]],
        is_flipped: Callable[[], bool],
    ) -> None:
        self._owner = owner
        self._popup = popup
        self._tip_for = tip_for
        self._is_flipped = is_flipped
        self._timer = QTimer(owner)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show)
        self._pending_notation = ""
        self._pending_rect = QRect()
        self._shown_notation = ""

    def update(self, notation: str, global_rect: QRect) -> None:
        """Aim the popup at ``global_rect`` for ``notation``, after the hover delay."""
        notation = str(notation or "")
        if not notation or global_rect.isEmpty():
            self.hide()
            return
        if notation == self._pending_notation and self._timer.isActive():
            self._pending_rect = global_rect
            return
        if notation == self._shown_notation and self._popup.isVisible():
            return
        self._timer.stop()
        if self._shown_notation and notation != self._shown_notation:
            self._popup.hide_for(self._owner)
            self._shown_notation = ""
        self._pending_notation = notation
        self._pending_rect = global_rect
        delay = self._popup.hover_delay_ms
        if delay <= 0:
            self._show()
        else:
            self._timer.start(delay)

    def hide(self) -> None:
        self._timer.stop()
        self._pending_notation = ""
        self._shown_notation = ""
        self._popup.hide_for(self._owner)

    def _show(self) -> None:
        notation = self._pending_notation
        if not notation or self._pending_rect.isEmpty():
            return
        tip = self._tip_for(notation)
        if tip is None:
            self.hide()
            return
        self._shown_notation = notation
        self._popup.present_at(
            self._pending_rect,
            tip,
            is_flipped=bool(self._is_flipped()),
            owner=self._owner,
        )


def _href_at(document: QTextDocument, index: int) -> str:
    if index < 0:
        return ""
    cursor = QTextCursor(document)
    cursor.setPosition(min(index + 1, max(0, document.characterCount() - 1)))
    return cursor.charFormat().anchorHref() or ""


def link_span_at(document: QTextDocument, point: QPointF) -> Optional[Tuple[str, int, int]]:
    """``(href, start, end)`` of the move link under a document-local point."""
    layout = document.documentLayout()
    if layout is None:
        return None
    index = layout.hitTest(point, Qt.HitTestAccuracy.ExactHit)
    if index < 0:
        return None
    href = _href_at(document, index)
    if not href.startswith("move:"):
        return None
    start = index
    while start > 0 and _href_at(document, start - 1) == href:
        start -= 1
    end = index + 1
    last = max(0, document.characterCount() - 1)
    while end < last and _href_at(document, end) == href:
        end += 1
    return href, start, end


def _cursor_origin(document: QTextDocument, position: int) -> Optional[Tuple[QPointF, float]]:
    block = document.findBlock(position)
    block_layout = block.layout()
    doc_layout = document.documentLayout()
    if block_layout is None or doc_layout is None:
        return None
    relative = max(0, position - block.position())
    line = block_layout.lineForTextPosition(relative)
    if not line.isValid():
        return None
    x = float(line.cursorToX(relative)[0])
    block_rect = doc_layout.blockBoundingRect(block)
    return QPointF(block_rect.x() + x, block_rect.y() + line.y()), float(line.height())


def span_rect(document: QTextDocument, start: int, end: int) -> QRect:
    """Document-local rectangle covering the characters in ``[start, end)``."""
    origin = _cursor_origin(document, start)
    finish = _cursor_origin(document, end)
    if origin is None:
        return QRect()
    start_point, height = origin
    if finish is None:
        return QRect(int(start_point.x()), int(start_point.y()), 1, max(1, int(height)))
    end_point, end_height = finish
    top = min(start_point.y(), end_point.y())
    bottom = max(start_point.y() + height, end_point.y() + end_height)
    left = min(start_point.x(), end_point.x())
    right = max(start_point.x(), end_point.x())
    if right <= left:
        right = left + 1
    return QRectF(left, top, right - left, max(1.0, bottom - top)).toRect()


def label_document(label: QLabel) -> Optional[QTextDocument]:
    return label.findChild(QTextDocument)


def label_document_origin(label: QLabel, document: QTextDocument) -> QPointF:
    """Top-left of the rich-text document inside ``label``."""
    contents = label.contentsRect()
    size = document.size()
    align = label.alignment()
    extra_w = max(0.0, float(contents.width()) - float(size.width()))
    extra_h = max(0.0, float(contents.height()) - float(size.height()))
    x = float(contents.x())
    y = float(contents.y())
    if align & Qt.AlignmentFlag.AlignRight:
        x += extra_w
    elif align & Qt.AlignmentFlag.AlignHCenter:
        x += extra_w / 2.0
    if align & Qt.AlignmentFlag.AlignBottom:
        y += extra_h
    elif align & Qt.AlignmentFlag.AlignVCenter:
        y += extra_h / 2.0
    return QPointF(x, y)


def label_move_link(label: QLabel, local_pos: QPoint) -> Optional[Tuple[str, QRect]]:
    """Notation and global rectangle of the move link under ``local_pos``."""
    document = label_document(label)
    if document is None:
        return None
    origin = label_document_origin(label, document)
    found = link_span_at(document, QPointF(local_pos) - origin)
    if found is None:
        return None
    href, start, end = found
    local = span_rect(document, start, end).translated(origin.toPoint())
    if local.isEmpty():
        return None
    return notation_from_move_href(href), QRect(label.mapToGlobal(local.topLeft()), local.size())


def text_edit_move_link(editor: QTextEdit, viewport_pos: QPoint) -> Optional[Tuple[str, QRect]]:
    """Notation and global rectangle of the move link under a viewport position."""
    document = editor.document()
    if document is None:
        return None
    scroll = QPoint(editor.horizontalScrollBar().value(), editor.verticalScrollBar().value())
    found = link_span_at(document, QPointF(viewport_pos + scroll))
    if found is None:
        return None
    href, start, end = found
    local = span_rect(document, start, end).translated(-scroll)
    if local.isEmpty():
        return None
    viewport = editor.viewport()
    if viewport is None:
        return None
    return notation_from_move_href(href), QRect(viewport.mapToGlobal(local.topLeft()), local.size())
