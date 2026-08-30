"""Tests for variation-path SAN matching helpers."""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.pgn_formatter_service import PgnFormatterService
from app.utils.pgn_variation_path import (
    canonicalize_san_for_match,
    encode_path,
    sans_match,
    strip_san_suffixes,
)


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


class TestSansMatch(unittest.TestCase):
    def test_exact_and_nag_suffixes(self) -> None:
        self.assertTrue(sans_match("Nxe5", "Nxe5"))
        self.assertTrue(sans_match("Nxe5!", "Nxe5"))
        self.assertTrue(sans_match("O-O", "O-O"))
        self.assertFalse(sans_match("Nxe5", "Nxe4"))

    def test_over_disambiguated_piece_captures(self) -> None:
        self.assertTrue(sans_match("Ngxe5", "Nxe5"))
        self.assertTrue(sans_match("Nfxe5", "Nxe5"))
        self.assertTrue(sans_match("N5xe5", "Nxe5"))
        self.assertTrue(sans_match("Ng5xe5", "Nxe5"))
        self.assertEqual(canonicalize_san_for_match("Ngxe5!"), "Nxe5")

    def test_over_disambiguated_non_captures(self) -> None:
        self.assertTrue(sans_match("Nbd7", "Nd7"))
        self.assertTrue(sans_match("Rae1", "Re1"))
        self.assertTrue(sans_match("R1e1", "Re1"))

    def test_pawns_and_castling_unchanged(self) -> None:
        self.assertEqual(canonicalize_san_for_match("exd5"), "exd5")
        self.assertEqual(canonicalize_san_for_match("e4"), "e4")
        self.assertEqual(canonicalize_san_for_match("O-O-O"), "O-O-O")
        self.assertFalse(sans_match("exd5", "xd5"))

    def test_strip_san_suffixes(self) -> None:
        self.assertEqual(strip_san_suffixes("Qh5+!!"), "Qh5+")


class TestOverDisambiguatedPathAnchors(unittest.TestCase):
    def test_over_disambiguation_keeps_path_queue_aligned(self) -> None:
        # Tree SAN for 3.Nxe5 is Nxe5; PGN text uses ChessBase-style Nfxe5.
        # A later sibling sideline (6.d3) must still get a cara-path anchor.
        pgn = """[Event "Test"]
[Result "*"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 (3. Nfxe5 Nxe5 4. d4) a6 4. Ba4 Nf6 5. O-O Be7
6. Re1 (6. d3) b5 *
"""
        html, _ = PgnFormatterService.format_pgn_to_html(
            pgn,
            _MIN_CFG,
            0,
            pgn_notation_settings={
                "use_symbols_for_nags": True,
                "show_nag_text": False,
            },
            indent_variations=False,
        )
        nfxe5_paths = re.findall(r'href="cara-path:([^"]+)"[^>]*>Nfxe5<', html)
        self.assertEqual(nfxe5_paths, [encode_path((0, 0, 0, 0, 1))])

        # Continuation inside the same sideline (queue must advance past Nfxe5).
        self.assertRegex(html, r'href="cara-path:[^"]+"[^>]*>Nxe5<')

        d3_paths = re.findall(r'href="cara-path:([^"]+)"[^>]*>d3<', html)
        self.assertEqual(d3_paths, [encode_path((0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1))])


class TestCommentParenthesesPathAnchors(unittest.TestCase):
    def test_paren_inside_comment_does_not_break_nested_sideline_anchor(self) -> None:
        # Comment after White's move ends with ":)" — that closing paren must not
        # truncate the enclosing variation, or the nested (2... Nc6) loses cara-path.
        pgn = """[Event "Test"]
[Result "*"]

1. e4 e5 2. Nf3 (2. Nc3 {anyone :)} Nf6 (2... Nc6 3. Bc4) d6) *
"""
        html, _ = PgnFormatterService.format_pgn_to_html(
            pgn, _MIN_CFG, indent_variations=False
        )
        # Nested sideline first move must be a path anchor, not a bare span.
        self.assertRegex(html, r'href="cara-path:[^"]+"[^>]*>Nc6<')
        # Continuation after the comment stays a variation path move (not mainline ply).
        self.assertRegex(html, r'href="cara-path:[^"]+"[^>]*>Nf6<')
        self.assertNotRegex(html, r'href="cara-ply:\d+"[^>]*>Nf6<')


if __name__ == "__main__":
    unittest.main()
