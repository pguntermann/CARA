"""Tests for PGN display range map (href anchors)."""

from __future__ import annotations

import os
import unittest

# Must be set before QApplication is created (CI / headless have no xcb display).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit

from app.config.config_loader import ConfigLoader
from app.services.pgn_formatter_service import (
    PgnFormatterService,
    build_pgn_range_map_from_fragments,
    parse_comment_href,
    parse_ply_href,
)
from app.views.detail_pgn_view import _range_map_from_document


_APP = None


def _ensure_app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class TestPgnRangeMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ensure_app()
        cls.config = ConfigLoader().load()

    def test_parse_hrefs(self) -> None:
        self.assertEqual(parse_ply_href("cara-ply:12"), 12)
        self.assertIsNone(parse_ply_href("cara-cmt:1"))
        self.assertEqual(parse_comment_href("cara-cmt:3"), 3)
        self.assertIsNone(parse_comment_href("cara-ply:3"))

    def test_build_from_fragments(self) -> None:
        rm = build_pgn_range_map_from_fragments(
            [
                (10, 2, "cara-ply:1"),
                (20, 5, "cara-cmt:1"),
                (30, 3, "cara-ply:2"),
            ]
        )
        self.assertEqual(rm.move_ply_at(10), 1)
        self.assertEqual(rm.move_ply_at(11), 1)
        self.assertEqual(rm.move_ply_at(12), 0)
        self.assertEqual(rm.comment_ply_at(22), 1)
        self.assertEqual(rm.move_range(2).start, 30)

    def test_formatter_emits_anchors(self) -> None:
        pgn = '1. e4 {note} e5 *'
        html, move_info = PgnFormatterService.format_pgn_to_html(pgn, self.config)
        self.assertEqual(len(move_info), 2)
        self.assertIn('href="cara-ply:1"', html)
        self.assertIn('href="cara-ply:2"', html)
        self.assertIn('href="cara-cmt:', html)
        self.assertNotIn("\u200b", html)
        self.assertNotIn("\u200c", html)
        self.assertNotIn("\u200d", html)

        edit = QTextEdit()
        edit.setHtml(html)
        rm = _range_map_from_document(edit.document())
        plain = edit.toPlainText()
        self.assertEqual(len(rm.moves), 2)
        self.assertEqual(plain[rm.moves[0].start : rm.moves[0].end], "e4")
        self.assertEqual(plain[rm.moves[1].start : rm.moves[1].end], "e5")
        self.assertEqual(len(rm.comments), 1)
        self.assertTrue(plain[rm.comments[0].start : rm.comments[0].end].startswith("{"))


if __name__ == "__main__":
    unittest.main()
