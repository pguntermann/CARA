"""Unit tests for DiscoveredAttackRule."""

import unittest

from app.services.game_highlights.rules.discovered_attack_rule import DiscoveredAttackRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestDiscoveredAttackRule(unittest.TestCase):
    """Discovered attack: leaving a square opens a friendly slider onto a valuable target."""

    def test_should_match_when_knight_uncovers_rook_onto_enemy_rook(self):
        # Nb6 leaves the a-file; Ra1 then attacks the undefended rook on a8.
        moves = moves_from_pgn(
            "Kd2 Ke7 Nb6",
            starting_fen="r3k3/8/8/8/N7/8/8/R3K3 w - - 0 19",
        )
        highlights = evaluate_rule(DiscoveredAttackRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="discovered_attack", side="white"
        )
        self.assertTrue(matching, "Expected discovered attack on 20. Nb6")
        self.assertIn("discovered attack", matching[0].description.lower())
        self.assertIn("rook", matching[0].description.lower())

    def test_should_not_match_during_the_opening(self):
        # Same uncovering idea, but still in the opening phase — rule intentionally skips.
        moves = moves_from_pgn(
            "Kd2 Ke7 Nb6",
            starting_fen="r3k3/8/8/8/N7/8/8/R3K3 w - - 0 9",
        )
        highlights = evaluate_rule(DiscoveredAttackRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="discovered_attack", side="white"
        )
        self.assertFalse(
            matching,
            "Discovered attacks in the opening should not be highlighted",
        )


if __name__ == "__main__":
    unittest.main()
