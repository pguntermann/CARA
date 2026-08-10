"""Unit tests for KnightOutpostRule."""

import unittest

from app.services.game_highlights.rules.knight_outpost_rule import KnightOutpostRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestKnightOutpostRule(unittest.TestCase):
    """Knight outpost: advanced, pawn-backed, not challengeable by enemy pawns."""

    def test_should_match_when_knight_lands_on_secure_outpost(self):
        # Nd5 supported by c4/e4; Black has no c/e pawns that can challenge.
        moves = moves_from_pgn(
            "Nd5",
            starting_fen="4k3/pp3ppp/8/8/2P1P3/2N5/PP3PPP/4K3 w - - 0 10",
        )
        highlights = evaluate_rule(KnightOutpostRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="knight_outpost", side="white"
        )
        self.assertTrue(matching, "Expected knight outpost on 10. Nd5")
        self.assertIn("outpost", matching[0].description.lower())

    def test_should_not_match_when_enemy_pawn_can_challenge(self):
        # Same idea, but Black still has a c-pawn that can advance to challenge d5.
        moves = moves_from_pgn(
            "Nd5",
            starting_fen="4k3/ppp2ppp/8/8/2P1P3/2N5/PP3PPP/4K3 w - - 0 10",
        )
        highlights = evaluate_rule(KnightOutpostRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="knight_outpost", side="white"
        )
        self.assertFalse(
            matching,
            "Nd5 should not be an outpost while Black's c-pawn can still challenge it",
        )


if __name__ == "__main__":
    unittest.main()
