"""Test case: Pawn Storm a5 - should NOT detect pawn storm on move 11."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestPawnStormA5ShouldNotMatch(unittest.TestCase):
    """Test that a5 (move 11) is NOT detected as a pawn storm."""

    def test_pawn_storm_a5_should_not_match(self):
        game_data = load_test_game("pawn_storm_a5_should_not_match.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=11, rule_type="pawn_storm", side="black")
        if matching:
            explain_failure(11, "pawn_storm", "black", game_data, highlights)
        self.assertFalse(matching, "Pawn storm should not be detected for move 11...a5")


if __name__ == "__main__":
    unittest.main()
