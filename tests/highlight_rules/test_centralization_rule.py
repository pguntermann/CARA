"""Unit tests for CentralizationRule."""

import unittest

from app.services.game_highlights.rules.centralization_rule import CentralizationRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestCentralizationRule(unittest.TestCase):
    """Centralization: N/B/Q from a non-central square onto a central one."""

    def test_should_match_when_knight_moves_into_the_center(self):
        # 3. Nd4: knight leaves f3 (not central) for d4 (central); default cpl=0 < 30.
        moves = moves_from_pgn("e4 e5 Nf3 Nc6 Nd4")
        highlights = evaluate_rule(CentralizationRule({}), moves, move_number=3)
        matching = find_highlights(
            highlights, move_number=3, rule_type="centralization", side="white"
        )
        self.assertTrue(matching, "Expected centralization on 3. Nd4")
        self.assertIn("knight", matching[0].description.lower())

    def test_should_not_match_when_cpl_is_too_high(self):
        # Same geometry for either side: quality gate rejects CPL >= 30 without eval gain.
        moves = moves_from_pgn(
            "e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Nd4",
            analysis={4: {"black": {"cpl": "50"}}},
        )
        highlights = evaluate_rule(CentralizationRule({}), moves, move_number=4)
        matching = find_highlights(
            highlights, move_number=4, rule_type="centralization", side="black"
        )
        self.assertFalse(
            matching,
            "Centralization should not fire when CPL is 50 and eval does not improve",
        )


if __name__ == "__main__":
    unittest.main()
