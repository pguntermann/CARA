"""Test case: Interference Qd3 - should NOT be flagged as interference."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestInterferenceQd3ShouldNotMatch(unittest.TestCase):
    """Move 29.Qd3 merely improves coordination and must not be flagged."""

    def test_interference_Qd3_should_not_match(self):
        game_data = load_test_game("interference_should_not_match_Qd3.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=29, rule_type="interference", side="white")
        if matching:
            explain_failure(29, "interference", "white", game_data, highlights)
        self.assertFalse(matching, "Interference should not be detected for move 29.Qd3")


if __name__ == "__main__":
    unittest.main()
