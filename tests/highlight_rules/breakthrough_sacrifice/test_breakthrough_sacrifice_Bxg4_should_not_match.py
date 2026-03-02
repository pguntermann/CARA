"""Test case: Breakthrough Sacrifice Bxg4 - should NOT detect sacrifice on move 25."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestBreakthroughSacrificeBxg4ShouldNotMatch(unittest.TestCase):
    """Bxg4 (move 25) is a tactical sequence, not a sacrifice; must not be flagged."""

    def test_breakthrough_sacrifice_Bxg4_should_not_match(self):
        game_data = load_test_game("sacrifice_breakthrough_should_not_match_Bxg4.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=25, rule_type="breakthrough_sacrifice", side="white")
        if matching:
            explain_failure(25, "breakthrough_sacrifice", "white", game_data, highlights)
        self.assertFalse(matching, "Breakthrough sacrifice should not be detected for move 25.Bxg4")


if __name__ == "__main__":
    unittest.main()
