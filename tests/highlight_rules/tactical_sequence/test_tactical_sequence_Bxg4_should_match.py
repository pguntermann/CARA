"""Test case: Tactical Sequence Bxg4 - should detect tactical sequence on move 25."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestTacticalSequenceBxg4ShouldMatch(unittest.TestCase):
    """Test that Bxg4 (move 25) is detected as a tactical sequence."""

    def test_tactical_sequence_Bxg4_should_match(self):
        game_data = load_test_game("tactical_sequence_Bxg4_should_match.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=25, rule_type="tactical_sequence", side="white")
        if not matching:
            explain_failure(25, "tactical_sequence", "white", game_data, highlights)
        self.assertTrue(matching, "Tactical sequence should be detected for move 25.Bxg4")


if __name__ == "__main__":
    unittest.main()
