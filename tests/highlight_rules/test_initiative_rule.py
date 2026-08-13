"""Unit tests for InitiativeRule."""

import unittest

from app.services.game_highlights.rules.initiative_rule import InitiativeRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 19"


class TestInitiativeRule(unittest.TestCase):
    """Strong move that improves the eval and forces a poor reply."""

    def test_should_match_when_good_move_forces_poor_reply(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kd6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+0.2"}},
                20: {
                    "white": {"cpl": "5", "eval": "+0.8"},
                    "black": {
                        "cpl": "80",
                        "cpl_2": "90",
                        "cpl_3": "100",
                        "eval": "+1.2",
                    },
                },
            },
        )
        highlights = evaluate_rule(InitiativeRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="initiative", side="white"
        )
        self.assertTrue(matching, "Expected initiative on 20. Kd3")
        self.assertIn("initiative", matching[0].description.lower())
        self.assertEqual(matching[0].priority, 30)

    def test_should_not_match_when_opponent_replies_well(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kd6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+0.2"}},
                20: {
                    "white": {"cpl": "5", "eval": "+0.8"},
                    "black": {"cpl": "20", "eval": "+0.75"},
                },
            },
        )
        highlights = evaluate_rule(InitiativeRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="initiative", side="white"
        )
        self.assertFalse(
            matching,
            "A well-answered move should not count as seizing the initiative",
        )


if __name__ == "__main__":
    unittest.main()
