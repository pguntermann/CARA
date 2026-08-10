"""Unit tests for WeakSquareRule."""

import unittest

from app.services.game_highlights.rules.weak_square_rule import WeakSquareRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_START = "4k3/pp3ppp/8/8/3PP3/5N2/PPP2PPP/4K3 w - - 0 10"


class TestWeakSquareRule(unittest.TestCase):
    """Weak square: occupy an advanced square safe from enemy pawns and defended."""

    def test_should_match_when_piece_occupies_defended_weak_square(self):
        # Ne5: rank 5, defended by d4, not attackable by Black pawns.
        moves = moves_from_pgn("h3 a6 Ne5", starting_fen=_START)
        highlights = evaluate_rule(WeakSquareRule({}), moves, move_number=11)
        matching = find_highlights(
            highlights, move_number=11, rule_type="weak_square", side="white"
        )
        self.assertTrue(matching, "Expected weak-square occupation on 11. Ne5")
        self.assertIn("weak square", matching[0].description.lower())

    def test_should_not_match_when_enemy_pawn_attacks_the_square(self):
        moves = moves_from_pgn(
            "h3 a6 Ne5",
            starting_fen="4k3/pp3ppp/3p4/8/3PP3/5N2/PPP2PPP/4K3 w - - 0 10",
        )
        highlights = evaluate_rule(WeakSquareRule({}), moves, move_number=11)
        matching = find_highlights(
            highlights, move_number=11, rule_type="weak_square", side="white"
        )
        self.assertFalse(
            matching,
            "Ne5 should not count when Black's d6-pawn attacks e5",
        )


if __name__ == "__main__":
    unittest.main()
