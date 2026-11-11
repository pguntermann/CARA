"""Tests for chess_log_color_scoping.color_from_path_key.

The path key encodes a dotted child-index sequence. Its length equals the ply
count from the root (one element per half-move), so:
  - odd length  → White just moved  → "white"
  - even length (> 0) → Black just moved → "black"
  - empty       → root position, no move made → None
"""

import unittest

from app.utils.chess_log_color_scoping import color_from_path_key


class TestColorFromPathKey(unittest.TestCase):

    # ------------------------------------------------------------------
    # Mainline cases
    # ------------------------------------------------------------------

    def test_first_white_move(self):
        # "0" = after White's first move (ply 1)
        self.assertEqual(color_from_path_key("0"), "white")

    def test_first_black_move(self):
        # "0.0" = after Black's first move (ply 2)
        self.assertEqual(color_from_path_key("0.0"), "black")

    def test_second_white_move(self):
        self.assertEqual(color_from_path_key("0.0.0"), "white")

    def test_second_black_move(self):
        self.assertEqual(color_from_path_key("0.0.0.0"), "black")

    def test_tenth_ply_white(self):
        key = ".".join(["0"] * 9)  # 9 elements = ply 9 = White
        self.assertEqual(color_from_path_key(key), "white")

    def test_tenth_ply_black(self):
        key = ".".join(["0"] * 10)  # 10 elements = ply 10 = Black
        self.assertEqual(color_from_path_key(key), "black")

    # ------------------------------------------------------------------
    # Variation cases — path length is still the ply count
    # ------------------------------------------------------------------

    def test_variation_first_branch_white(self):
        # "0.1" = ply 2 → Black (child index 1 selects a sideline, but
        # still two nodes deep from root → Black's move)
        self.assertEqual(color_from_path_key("0.1"), "black")

    def test_variation_second_level_white(self):
        # "0.1.0" = 3 elements → White
        self.assertEqual(color_from_path_key("0.1.0"), "white")

    def test_variation_deep(self):
        # "0.0.1.0.0" = 5 elements → White
        self.assertEqual(color_from_path_key("0.0.1.0.0"), "white")

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_empty_string_returns_none(self):
        self.assertIsNone(color_from_path_key(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(color_from_path_key("   "))

    def test_invalid_path_returns_none(self):
        self.assertIsNone(color_from_path_key("notapath"))

    def test_negative_component_returns_none(self):
        self.assertIsNone(color_from_path_key("0.-1"))


if __name__ == "__main__":
    unittest.main()
