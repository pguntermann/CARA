"""Unit tests for DecoyRule."""

import unittest

from app.services.game_highlights.rules.decoy_rule import DecoyRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestDecoyRule(unittest.TestCase):
    """Decoy: offer a piece, lure a capture, then exploit the lured unit."""

    def test_should_match_when_bishop_offer_lures_queen_into_knight_fork(self):
        # Bc4 hangs to the queen; Qxc4; Nd6 forks king and queen.
        moves = moves_from_pgn(
            "Kd2 h6 Bc4 Qxc4 Nd6",
            starting_fen="4k3/7p/8/1q6/4N3/8/4B3/4K3 w - - 0 19",
            analysis={
                20: {"white": {"cpl": "5"}, "black": {"cpl": "10"}},
                21: {"white": {"cpl": "0"}},
            },
        )
        highlights = evaluate_rule(DecoyRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="decoy", side="white"
        )
        self.assertTrue(matching, "Expected decoy on 20. Bc4")
        self.assertIn("decoy", matching[0].description.lower())
        self.assertIn("queen", matching[0].description.lower())

    def test_should_not_match_when_there_is_no_tactical_follow_up(self):
        # Same offer and capture, but White never exploits the queen on c4.
        moves = moves_from_pgn(
            "Kd2 h6 Bc4 Qxc4 Ke1",
            starting_fen="4k3/7p/8/1q6/4N3/8/4B3/4K3 w - - 0 19",
            analysis={
                20: {"white": {"cpl": "5"}, "black": {"cpl": "10"}},
                21: {"white": {"cpl": "0"}},
            },
        )
        highlights = evaluate_rule(DecoyRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="decoy", side="white"
        )
        self.assertFalse(
            matching,
            "Without a tactical follow-up, the hanging bishop is not a decoy",
        )


if __name__ == "__main__":
    unittest.main()
