"""Unit tests for ZwischenzugRule."""

import unittest

from app.services.game_highlights.rules.zwischenzug_rule import ZwischenzugRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_START = "4k3/8/8/8/b7/1P6/7P/3QK3 w - - 0 20"


class TestZwischenzugRule(unittest.TestCase):
    """Zwischenzug: skip the recapture and insert a check (or other capture) instead."""

    def test_should_match_when_check_is_played_instead_of_recapture(self):
        # After ...Bxb3, White plays Qh5+ instead of taking on b3.
        moves = moves_from_pgn("h3 Bxb3 Qh5+", starting_fen=_START)
        highlights = evaluate_rule(ZwischenzugRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="zwischenzug", side="white"
        )
        self.assertTrue(matching, "Expected zwischenzug on 21. Qh5+")
        self.assertIn("zwischenzug", matching[0].description.lower())

    def test_should_not_match_when_the_captured_piece_is_recaptured(self):
        moves = moves_from_pgn("h3 Bxb3 Qxb3", starting_fen=_START)
        highlights = evaluate_rule(ZwischenzugRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="zwischenzug", side="white"
        )
        self.assertFalse(matching, "Immediate recapture Qxb3 should not be a zwischenzug")


if __name__ == "__main__":
    unittest.main()
