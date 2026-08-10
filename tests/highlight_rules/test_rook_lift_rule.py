"""Unit tests for RookLiftRule."""

import unittest

from app.services.game_highlights.rules.rook_lift_rule import RookLiftRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestRookLiftRule(unittest.TestCase):
    """Rook lift: rook leaves the back ranks toward the opponent's side."""

    def test_should_match_when_rook_lifts_to_third_rank(self):
        # 2. Ra3: rook a1 → a3 (rank 1 → 3).
        moves = moves_from_pgn("a4 a5 Ra3")
        highlights = evaluate_rule(RookLiftRule({}), moves, move_number=2)
        matching = find_highlights(
            highlights, move_number=2, rule_type="rook_lift", side="white"
        )
        self.assertTrue(matching, "Expected rook lift on 2. Ra3")
        self.assertIn("rook", matching[0].description.lower())

    def test_should_not_match_when_rook_stays_on_second_rank(self):
        # 2. Ra2: only reaches rank 2 — not a lift under this rule.
        moves = moves_from_pgn("a4 a5 Ra2")
        highlights = evaluate_rule(RookLiftRule({}), moves, move_number=2)
        matching = find_highlights(
            highlights, move_number=2, rule_type="rook_lift", side="white"
        )
        self.assertFalse(matching, "Ra2 should not count as a rook lift")


if __name__ == "__main__":
    unittest.main()
