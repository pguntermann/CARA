"""Unit tests for BatteryRule."""

import unittest

from app.services.game_highlights.rules.battery_rule import BatteryRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestBatteryRule(unittest.TestCase):
    """Battery: newly aligned heavy pieces that attack an enemy unit on the line."""

    def test_should_match_when_rook_aligns_with_queen_attacking_enemy(self):
        # Rd2 forms a queen+rook battery on the d-file against the black rook on d8.
        moves = moves_from_pgn(
            "Ke2 Kf7 Rd2",
            starting_fen="3rk3/8/8/8/3Q4/8/R7/4K3 w - - 0 19",
        )
        highlights = evaluate_rule(BatteryRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="battery", side="white"
        )
        self.assertTrue(matching, "Expected battery on 20. Rd2")
        self.assertIn("battery", matching[0].description.lower())
        self.assertIn("d file", matching[0].description.lower())

    def test_should_not_match_when_file_has_no_enemy_piece(self):
        # Same doubling on an empty d-file — positional only, not a battery.
        moves = moves_from_pgn(
            "Ke2 Kf7 Rd2",
            starting_fen="4k3/8/8/8/3Q4/8/R7/4K3 w - - 0 19",
        )
        highlights = evaluate_rule(BatteryRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="battery", side="white"
        )
        self.assertFalse(
            matching,
            "Doubling on an empty file should not count as a battery",
        )

    def test_should_not_match_during_the_opening(self):
        moves = moves_from_pgn(
            "Ke2 Kf7 Rd2",
            starting_fen="3rk3/8/8/8/3Q4/8/R7/4K3 w - - 0 9",
        )
        highlights = evaluate_rule(BatteryRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="battery", side="white"
        )
        self.assertFalse(
            matching,
            "Batteries in the opening should not be highlighted",
        )


if __name__ == "__main__":
    unittest.main()
