"""Unit tests for PGN formatter helpers used when copying from the UI."""

import unittest
from pathlib import Path

from app.services.pgn_formatter_service import PgnFormatterService, clean_pgn_text
from app.config.config_loader import ConfigLoader


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


def _load_app_config() -> dict:
    root = Path(__file__).resolve().parents[2]
    return ConfigLoader(root / "app/config/config.json").load()


class TestFormatPgnNagDisplayModes(unittest.TestCase):
    """PGN pane NAG menu: Symbols vs Text (user_settings pgn_notation)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._cfg = _load_app_config()

    def test_symbols_mode_expands_non_glyph_nag_to_text_not_dollar(self) -> None:
        html, _ = PgnFormatterService.format_pgn_to_html(
            "1. e4 $17 *",
            self._cfg,
            0,
            pgn_notation_settings={"use_symbols_for_nags": True, "show_nag_text": False},
        )
        self.assertNotIn("$17", html)
        self.assertIn("Black has a moderate advantage", html)

    def test_symbols_mode_maps_common_nag_to_glyph(self) -> None:
        html, _ = PgnFormatterService.format_pgn_to_html(
            "1. e4 $1 *",
            self._cfg,
            0,
            pgn_notation_settings={"use_symbols_for_nags": True, "show_nag_text": False},
        )
        self.assertNotIn("$1", html)
        self.assertIn(">!</span>", html)

    def test_text_mode_shows_literal_glyphs_as_descriptions(self) -> None:
        html, _ = PgnFormatterService.format_pgn_to_html(
            "1. e4!! e5 *",
            self._cfg,
            0,
            pgn_notation_settings={"use_symbols_for_nags": False, "show_nag_text": True},
        )
        self.assertNotIn("!!</span>", html)
        self.assertIn("very good move", html)

    def test_text_mode_shows_numeric_nag_as_description(self) -> None:
        html, _ = PgnFormatterService.format_pgn_to_html(
            "1. e4 $3 *",
            self._cfg,
            0,
            pgn_notation_settings={"use_symbols_for_nags": False, "show_nag_text": True},
        )
        self.assertNotIn("$3", html)
        self.assertIn("very good move", html)
