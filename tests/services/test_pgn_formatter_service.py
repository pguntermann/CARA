"""Unit tests for PGN formatter helpers used when copying from the UI."""

import unittest

from app.services.pgn_formatter_service import clean_pgn_text


def _lf(s: str) -> str:
    """Normalize CRLF from clipboard output to LF for assertions."""
    return s.replace("\r\n", "\n")


class TestCleanPgnTextHeaderLines(unittest.TestCase):
    """Headers copied from the pane should be one tag per line for other PGN tools."""

    def test_splits_concatenated_tags_before_moves(self) -> None:
        pgn = '[Event "T"][Site "?"][Date "2024.01.01"] 1. e4 e5 *'
        out = _lf(clean_pgn_text(pgn))
        self.assertIn("\n\n", out)
        head, moves = out.split("\n\n", 1)
        lines = [ln for ln in head.split("\n") if ln.strip()]
        self.assertEqual(
            lines,
            ['[Event "T"]', '[Site "?"]', '[Date "2024.01.01"]'],
        )
        self.assertTrue(moves.strip().startswith("1. e4"))

    def test_preserves_already_multiline_headers(self) -> None:
        pgn = '[Event "T"]\n[Site "?"]\n\n1. d4 d5 *\n'
        out = _lf(clean_pgn_text(pgn))
        head, moves = out.split("\n\n", 1)
        self.assertIn('[Event "T"]', head)
        self.assertIn('[Site "?"]', head)
        self.assertIn("1. d4", moves)
