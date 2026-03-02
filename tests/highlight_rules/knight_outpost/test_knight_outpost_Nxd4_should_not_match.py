"""Test case: Knight Outpost Nxd4 - should NOT detect knight outpost on move 9."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestKnightOutpostNxd4ShouldNotMatch(unittest.TestCase):
    """Test that black's Nxd4 (move 9) is NOT detected as a knight outpost."""

    def test_knight_outpost_Nxd4_should_not_match(self):
        game_data = load_test_game("knight_outpost_should_not_match_...Nxd4.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=9, rule_type="knight_outpost", side="black")
        if matching:
            explain_failure(9, "knight_outpost", "black", game_data, highlights)
        self.assertFalse(matching, "Knight outpost should not be detected for move 9...Nxd4 (black)")


if __name__ == "__main__":
    unittest.main()
