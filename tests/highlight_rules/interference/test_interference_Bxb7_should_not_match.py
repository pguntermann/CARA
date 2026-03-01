"""Test case: Interference Bxb7 - should NOT detect interference on move 18."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestInterferenceBxb7ShouldNotMatch(unittest.TestCase):
    """Move 18.Bxb7 is not an interference tactic and must not be flagged."""

    def test_interference_Bxb7_should_not_match(self):
        game_data = load_test_game("interference_Bxb7_shoud_not_match.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=18, rule_type="interference", side="white")
        if matching:
            explain_failure(18, "interference", "white", game_data, highlights)
        self.assertFalse(matching, "Interference should not be detected for move 18.Bxb7")


if __name__ == "__main__":
    unittest.main()
