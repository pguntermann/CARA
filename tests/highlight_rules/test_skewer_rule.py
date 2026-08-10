"""Unit tests for SkewerRule."""

import unittest

from app.services.game_highlights.rules.skewer_rule import SkewerRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestSkewerRule(unittest.TestCase):
    """Skewer: slider aligns two enemies and forces / realizes material gain."""

    def test_should_match_when_rook_skewers_queen_and_king(self):
        # Ra5: queen on a7 and king on a8; b4 defends the rook so Qxa5 loses the queen.
        moves = moves_from_pgn(
            "Ra5",
            starting_fen="k7/q7/8/8/1P6/8/8/R3K3 w - - 0 10",
        )
        highlights = evaluate_rule(SkewerRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="skewer", side="white"
        )
        self.assertTrue(matching, "Expected skewer on 10. Ra5")
        self.assertIn("skewer", matching[0].description.lower())

    def test_should_not_match_when_line_is_a_pin_not_a_skewer(self):
        # Bb4 → Nc3 → Ke1: lesser piece in front of the king is a pin, not a skewer.
        moves = moves_from_pgn(
            "Bb4",
            starting_fen="4k3/8/8/8/8/B1n5/8/4K3 w - - 0 10",
        )
        highlights = evaluate_rule(SkewerRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="skewer", side="white"
        )
        self.assertFalse(
            matching,
            "Pin geometry (knight in front of king) should not count as a skewer",
        )


if __name__ == "__main__":
    unittest.main()
