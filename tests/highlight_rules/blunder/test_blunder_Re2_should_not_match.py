"""Test case: Blunder Re2 - should NOT detect blundered piece on move 35."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestBlunderRe2ShouldNotMatch(unittest.TestCase):
    """Test that Re2 (move 35) is NOT detected as a blundered piece."""

    def test_blunder_Re2_should_not_match(self):
        game_data = load_test_game("blunder_Re2_should_not_match.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=35, rule_type="blundered_piece", side="white")
        if matching:
            explain_failure(35, "blundered_piece", "white", game_data, highlights)
        self.assertFalse(matching, "Blundered piece should not be detected for move 35.Re2")


if __name__ == "__main__":
    unittest.main()
