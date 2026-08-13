"""Unit tests for MomentumShiftRule."""

import unittest

from app.services.game_highlights.rules.momentum_shift_rule import MomentumShiftRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 19"


class TestMomentumShiftRule(unittest.TestCase):
    """Advantage flips across zero; credit the side that holds the new advantage."""

    def test_should_match_when_consolidating_after_opponent_crossing_blunder(self):
        # White blunders across zero; Black's accurate reply keeps the new sign.
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kf6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+1.0"}},
                20: {
                    "white": {"cpl": "250", "assess": "Blunder", "eval": "-1.5"},
                    "black": {"cpl": "15", "eval": "-1.8"},
                },
            },
        )
        highlights = evaluate_rule(MomentumShiftRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="momentum_shift", side="black"
        )
        self.assertTrue(matching, "Expected momentum shift on Black's consolidating Kf6")
        self.assertIn("switched sides", matching[0].description.lower())

    def test_should_not_credit_the_crossing_blunder_itself(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+1.0"}},
                20: {"white": {"cpl": "250", "assess": "Blunder", "eval": "-1.5"}},
            },
        )
        highlights = evaluate_rule(MomentumShiftRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="momentum_shift", side="white"
        )
        self.assertFalse(
            matching,
            "The side that blundered across zero should not get momentum shift",
        )

    def test_should_match_accurate_own_flip_that_holds_after_reply(self):
        # White seizes the advantage: -1.0 -> +1.5, and Black's reply stays positive.
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kf6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "-1.0"}},
                20: {
                    "white": {"cpl": "15", "eval": "+1.5"},
                    "black": {"cpl": "20", "eval": "+1.3"},
                },
            },
        )
        highlights = evaluate_rule(MomentumShiftRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="momentum_shift", side="white"
        )
        self.assertTrue(matching, "Expected momentum shift on White's accurate Kd3 flip")

    def test_should_not_match_own_flip_that_is_given_back_on_reply(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kf6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "-1.0"}},
                20: {
                    "white": {"cpl": "15", "eval": "+1.5"},
                    "black": {"cpl": "5", "eval": "-0.5"},
                },
            },
        )
        highlights = evaluate_rule(MomentumShiftRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="momentum_shift", side="white"
        )
        self.assertFalse(
            matching,
            "A flip that does not hold after the reply should not count",
        )


if __name__ == "__main__":
    unittest.main()
