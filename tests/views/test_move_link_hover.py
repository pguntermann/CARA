"""Hover hit-testing for move links in notes and AI chat."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel, QTextEdit, QWidget

from app.views.detail_ai_chat_view import MessageLabel
from app.views.detail_notes_view import NotesTextEdit

from app.views.widgets.half_move_link import resolve_linked_ply
from app.views.widgets.move_link_hover import label_move_link, text_edit_move_link


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestResolveLinkedPly(unittest.TestCase):
    def test_matches_spaced_unspaced_and_trailing_punctuation(self) -> None:
        mapping = {"1.e4": 1, "1. e4": 1, "1...e5": 2, "13...Rb7": 26, "13... Rb7": 26}
        self.assertEqual(resolve_linked_ply("1.e4", mapping), 1)
        self.assertEqual(resolve_linked_ply("1. e4", mapping), 1)
        self.assertEqual(resolve_linked_ply("1... e5", mapping), 2)
        self.assertEqual(resolve_linked_ply("13...Rb7,", mapping), 26)
        self.assertEqual(resolve_linked_ply("13... Rb7.", mapping), 26)
        self.assertIsNone(resolve_linked_ply("2.Nf3", mapping))


class TestMoveLinkGeometry(unittest.TestCase):
    def test_text_edit_returns_each_linked_move(self) -> None:
        app = _app()
        edit = QTextEdit()
        edit.setHtml(
            'Before <a href="move:1.e4">1. e4</a> then '
            '<a href="move:1...e5">1...e5</a> after'
        )
        edit.resize(420, 160)
        edit.show()
        app.processEvents()
        found = _scan(lambda point: text_edit_move_link(edit, point), 360, 48)
        edit.hide()
        self.assertIn("1.e4", found)
        self.assertIn("1...e5", found)
        self.assertFalse(found["1.e4"].isEmpty())
        self.assertFalse(found["1...e5"].isEmpty())
        self.assertLess(found["1.e4"].center().x(), found["1...e5"].center().x())

    def test_label_returns_each_linked_move(self) -> None:
        app = _app()
        label = QLabel(
            'Before <a href="move:1.e4">1. e4</a> then '
            '<a href="move:1...e5">1...e5</a> after'
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setFixedWidth(420)
        label.show()
        app.processEvents()
        found = _scan(lambda point: label_move_link(label, point), label.width(), label.height())
        label.hide()
        self.assertIn("1.e4", found)
        self.assertIn("1...e5", found)
        self.assertFalse(found["1.e4"].isEmpty())
        self.assertLess(found["1.e4"].center().x(), found["1...e5"].center().x())

    def test_message_label_mouse_move_reports_the_link(self) -> None:
        app = _app()
        view = QWidget()
        hover = _RecordingHover()
        view._move_link_hover = hover
        label = MessageLabel(
            'Before <a href="move:1.e4">1. e4</a> after',
            parent_view=view,
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        label.set_track_move_links(True)
        label.setFixedWidth(320)
        label.show()
        app.processEvents()
        point = _first_hit(lambda pos: label_move_link(label, pos), label.width(), label.height())
        self.assertIsNotNone(point)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(point),
            QPointF(label.mapToGlobal(point)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(label, event)
        self.assertEqual(label.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        miss = QPoint(2, 2)
        miss_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(miss),
            QPointF(label.mapToGlobal(miss)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(label, miss_event)
        self.assertNotEqual(label.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        label.hide()
        view.hide()
        self.assertIn("1.e4", hover.notations)

    def test_notes_editor_mouse_move_reports_the_link(self) -> None:
        app = _app()
        edit = NotesTextEdit()
        hover = _RecordingHover()
        edit.set_move_link_hover(hover)
        edit.setHtml('Before <a href="move:12.Nf3">12. Nf3</a> after')
        edit.resize(420, 160)
        edit.show()
        app.processEvents()
        point = _first_hit(lambda pos: text_edit_move_link(edit, pos), 360, 48)
        self.assertIsNotNone(point)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(point),
            QPointF(edit.viewport().mapToGlobal(point)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(edit.viewport(), event)
        self.assertEqual(edit.viewport().cursor().shape(), Qt.CursorShape.PointingHandCursor)
        miss = QPoint(2, 2)
        miss_event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(miss),
            QPointF(edit.viewport().mapToGlobal(miss)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(edit.viewport(), miss_event)
        self.assertEqual(edit.viewport().cursor().shape(), Qt.CursorShape.IBeamCursor)
        edit.hide()
        self.assertIn("12.Nf3", hover.notations)


class _RecordingHover:
    def __init__(self) -> None:
        self.notations = []

    def update(self, notation: str, _rect) -> None:
        self.notations.append(notation)

    def hide(self) -> None:
        return None


def _first_hit(probe, width: int, height: int):
    for y in range(0, max(1, height), 2):
        for x in range(0, max(1, width), 2):
            if probe(QPoint(x, y)) is not None:
                return QPoint(x, y)
    return None


def _scan(probe, width: int, height: int):
    found = {}
    for y in range(0, max(1, height), 3):
        for x in range(0, max(1, width), 3):
            hit = probe(QPoint(x, y))
            if hit is None:
                continue
            notation, rect = hit
            found.setdefault(notation, rect)
    return found


if __name__ == "__main__":
    unittest.main()
