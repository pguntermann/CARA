"""Test case: Material Imbalance Qxc5 - should NOT detect (Best Move filter)."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import unittest
from tests.highlight_rules.helpers import (
    load_test_game, run_highlight_detection,
    find_highlights, explain_failure
)


class TestMaterialImbalanceQxc5ShouldNotMatch(unittest.TestCase):
    """Qxc5 (move 30) is Best Move and must not be flagged as material imbalance."""

    def test_material_imbalance_qxc5_should_not_match(self):
        game_data = load_test_game("material_imbalance_qxc5_should_not_match.json")
        highlights = run_highlight_detection(game_data)
        matching = find_highlights(highlights, move_number=30, rule_type="material_imbalance", side="black")
        if matching:
            explain_failure(30, "material_imbalance", "black", game_data, highlights)
        self.assertFalse(matching, "Material imbalance should not be detected for move 30.Qxc5 (Best Move filter)")


if __name__ == "__main__":
    unittest.main()
