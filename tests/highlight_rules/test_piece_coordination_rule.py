"""Unit tests for PieceCoordinationRule."""

import unittest

from app.services.game_highlights.rules.piece_coordination_rule import PieceCoordinationRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestPieceCoordinationRule(unittest.TestCase):
    """Piece coordination: 2+ pieces attack the same valuable enemy target."""

    def test_should_match_when_two_pieces_attack_enemy_minor(self):
        # Nb5 + Be5 both attack Nd6; default cpl=0 < 30.
        moves = moves_from_pgn(
            "Nb5",
            starting_fen="4k3/8/3n4/4B3/8/N7/8/4K3 w - - 0 20",
        )
        highlights = evaluate_rule(PieceCoordinationRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="piece_coordination", side="white"
        )
        self.assertTrue(matching, "Expected piece coordination on 20. Nb5")
        self.assertIn("coordinat", matching[0].description.lower())

    def test_should_not_match_when_only_one_attacker(self):
        moves = moves_from_pgn(
            "Nb5",
            starting_fen="4k3/8/3n4/8/8/N7/8/4K3 w - - 0 20",
        )
        highlights = evaluate_rule(PieceCoordinationRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="piece_coordination", side="white"
        )
        self.assertFalse(
            matching,
            "A single attacker on Nd6 should not count as coordination",
        )


if __name__ == "__main__":
    unittest.main()
