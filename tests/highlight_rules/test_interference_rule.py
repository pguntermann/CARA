"""Unit tests for InterferenceRule."""

import unittest

from app.services.game_highlights.rules.interference_rule import InterferenceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestInterferenceRule(unittest.TestCase):
    """Interference: place a piece between two enemy sliders that previously saw each other."""

    def test_should_match_when_knight_blocks_two_rooks_on_a_file(self):
        # Na5 sits between Black's rooks on a8 and a1.
        moves = moves_from_pgn(
            "Kd2 h6 Na5",
            starting_fen="r3k3/7p/8/8/8/1N6/8/r3K3 w - - 0 19",
        )
        highlights = evaluate_rule(InterferenceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="interference", side="white"
        )
        self.assertTrue(matching, "Expected interference on 20. Na5")
        self.assertIn("interference", matching[0].description.lower())

    def test_should_not_match_when_the_move_is_a_capture(self):
        # Capturing on the line removes a unit; that is not interference.
        moves = moves_from_pgn(
            "Kd2 a6 Nxa1",
            starting_fen="r3k3/p7/8/8/8/1N6/8/r3K3 w - - 0 19",
        )
        highlights = evaluate_rule(InterferenceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="interference", side="white"
        )
        self.assertFalse(
            matching,
            "Capturing a rook on the line should not count as interference",
        )


if __name__ == "__main__":
    unittest.main()
