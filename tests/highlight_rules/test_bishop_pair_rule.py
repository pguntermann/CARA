"""Unit tests for BishopPairRule."""

import unittest

from app.services.game_highlights.rules.bishop_pair_rule import BishopPairRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestBishopPairRule(unittest.TestCase):
    """Bishop pair: keep both opposite-colored bishops while the opponent no longer has two."""

    def test_should_match_when_capture_destroys_opponent_bishop_pair(self):
        # White already has the pair; Bxe6 leaves Black with only one bishop.
        moves = moves_from_pgn(
            "h3 Ke7 Bxe6 Kf8",
            starting_fen="4k3/3b4/4b3/8/2B5/8/7P/2B1K3 w - - 0 20",
        )
        highlights = evaluate_rule(BishopPairRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="bishop_pair", side="white"
        )
        self.assertTrue(matching, "Expected bishop pair on 21. Bxe6")
        self.assertIn("bishop pair", matching[0].description.lower())

    def test_should_not_match_when_opponent_immediately_recaptures_a_bishop(self):
        moves = moves_from_pgn(
            "h3 Ke7 Bxe6 Bxe6",
            starting_fen="4k3/3b4/4b3/8/2B5/8/7P/2B1K3 w - - 0 20",
        )
        highlights = evaluate_rule(BishopPairRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="bishop_pair", side="white"
        )
        self.assertFalse(
            matching,
            "Bishop pair should not fire when Black immediately recaptures with Bxe6",
        )


if __name__ == "__main__":
    unittest.main()
