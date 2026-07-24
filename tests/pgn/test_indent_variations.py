"""Tests for display-only indented variation layout in PGN HTML."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.pgn_formatter_service import PgnFormatterService


_MIN_CFG = {
    "ui": {
        "panels": {
            "detail": {
                "pgn_notation": {
                    "formatting": {
                        "variations": {"color": [180, 180, 180], "italic": True},
                        "comments": {"color": [150, 150, 150]},
                        "headers": {"color": [200, 200, 200]},
                        "nags": {},
                        "move_numbers": {"color": [255, 255, 255], "bold": True},
                        "moves": {"color": [220, 220, 220]},
                    }
                }
            }
        }
    }
}

_PGN = """[Event "Test"]
[Result "*"]

1. e4 e5 (1... c5 2. Nf3 d6 (2... Nc6)) 2. Nf3 Nc6 *
"""

# Nested castling after a preceding move in the same sideline (Be7 / O-O case).
_PGN_NESTED_CASTLE = """[Event "Test"]
[Result "*"]

1. e4 c5 2. Nf3 e6 3. c4 Nc6 4. Nc3 Nf6 5. Be2 d5 (5... Be7 6. d4 (6. O-O d5) 6... cxd4 7. Nxd4 O-O) *
"""


def _path_hrefs(html: str) -> list:
    return re.findall(r'href="cara-path:([^"]+)"', html)


def _path_hrefs_for_san(html: str, san: str) -> list:
    """Return cara-path values attached specifically to the given SAN text."""
    return re.findall(
        rf'href="cara-path:([^"]+)"[^>]*>{re.escape(san)}<',
        html,
    )


class TestIndentVariations(unittest.TestCase):
    def test_off_keeps_inline_parens(self) -> None:
        html, _ = PgnFormatterService.format_pgn_to_html(
            _PGN, _MIN_CFG, indent_variations=False
        )
        # Compact layout: opening paren should not be preceded by a line break + indent.
        self.assertNotIn("<br>&nbsp;&nbsp;&nbsp;&nbsp;<span", html)

    def test_on_breaks_and_indents_by_depth(self) -> None:
        html, _ = PgnFormatterService.format_pgn_to_html(
            _PGN, _MIN_CFG, indent_variations=True
        )
        # Top-level sideline: newline + 4 nbsp before styled (
        self.assertIn("<br>&nbsp;&nbsp;&nbsp;&nbsp;<span", html)
        # Nested sideline: newline + 8 nbsp before raw (
        self.assertIn("<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(", html)
        # Mainline resumes after top-level closing paren
        self.assertRegex(html, r"\)</span><br>")

    def test_indent_preserves_path_anchors_for_nested_castling(self) -> None:
        html_off, _ = PgnFormatterService.format_pgn_to_html(
            _PGN_NESTED_CASTLE, _MIN_CFG, indent_variations=False
        )
        html_on, _ = PgnFormatterService.format_pgn_to_html(
            _PGN_NESTED_CASTLE, _MIN_CFG, indent_variations=True
        )
        self.assertEqual(_path_hrefs(html_off), _path_hrefs(html_on))

        oo_off = _path_hrefs_for_san(html_off, "O-O")
        oo_on = _path_hrefs_for_san(html_on, "O-O")
        self.assertEqual(len(oo_off), 2, "expected nested 6.O-O and later 7...O-O")
        self.assertEqual(oo_on, oo_off)
        self.assertNotEqual(oo_on[0], oo_on[1])


if __name__ == "__main__":
    unittest.main()
