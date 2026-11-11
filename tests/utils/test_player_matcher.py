"""Tests for player_matcher utilities."""

import unittest
from unittest.mock import MagicMock

from app.utils.player_matcher import game_matches_player_color


def _game(white="Alice", black="Bob"):
    g = MagicMock()
    g.white = white
    g.black = black
    return g


class TestGameMatchesPlayerColor(unittest.TestCase):
    def test_empty_player_matches_all(self):
        """Empty player string means no player filter — all games pass."""
        self.assertTrue(game_matches_player_color(_game(), "", "both"))
        self.assertTrue(game_matches_player_color(_game(), "", "white"))
        self.assertTrue(game_matches_player_color(_game(), "", "black"))

    def test_exact_match_white(self):
        self.assertTrue(game_matches_player_color(_game("Alice", "Bob"), "alice", "both"))

    def test_exact_match_black(self):
        self.assertTrue(game_matches_player_color(_game("Alice", "Bob"), "bob", "both"))

    def test_no_match(self):
        self.assertFalse(game_matches_player_color(_game("Alice", "Bob"), "charlie", "both"))

    def test_case_insensitive(self):
        self.assertTrue(game_matches_player_color(_game("Alice Smith", "Bob"), "alice smith", "both"))

    def test_color_filter_white_matches_white_player(self):
        self.assertTrue(game_matches_player_color(_game("Alice", "Bob"), "alice", "white"))

    def test_color_filter_white_rejects_black_player(self):
        self.assertFalse(game_matches_player_color(_game("Alice", "Bob"), "bob", "white"))

    def test_color_filter_black_matches_black_player(self):
        self.assertTrue(game_matches_player_color(_game("Alice", "Bob"), "bob", "black"))

    def test_color_filter_black_rejects_white_player(self):
        self.assertFalse(game_matches_player_color(_game("Alice", "Bob"), "alice", "black"))

    def test_none_white_header(self):
        self.assertFalse(game_matches_player_color(_game(None, "Bob"), "alice", "both"))

    def test_none_black_header(self):
        self.assertFalse(game_matches_player_color(_game("Alice", None), "bob", "both"))

    def test_both_none_no_match(self):
        self.assertFalse(game_matches_player_color(_game(None, None), "alice", "both"))

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace in game headers is stripped."""
        self.assertTrue(game_matches_player_color(_game("  Alice  ", "Bob"), "alice", "both"))


if __name__ == "__main__":
    unittest.main()
