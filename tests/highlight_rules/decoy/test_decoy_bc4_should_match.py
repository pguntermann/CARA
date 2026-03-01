"""Test case: Decoy Bc4 - should detect decoy on move 17."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestDecoyBc4ShouldMatch(unittest.TestCase):
    """Test that Bc4 (move 17) is detected as a decoy."""

    def test_decoy_bc4_should_match(self):
        game_data = load_test_game("decoy_bc4_should_match.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=17, rule_type="decoy", side="white")
        if not matching:
            explain_failure(17, "decoy", "white", game_data, highlights)
        self.assertTrue(matching, "Decoy should be detected for move 17.Bc4")


if __name__ == "__main__":
    unittest.main()
