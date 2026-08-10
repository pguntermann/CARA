"""Unit tests for ForcingCombinationRule."""

import unittest

from app.services.game_highlights.rules.forcing_combination_rule import ForcingCombinationRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

# White knight on e5 can take the f7-pawn; Black king recaptures.
_SAC = "4k3/5p2/8/4N3/8/8/4K3/8 w - - 0 20"

# Same idea but Black recaptures with a knight — equal knight trade.
_EQUAL = "4k3/5n2/3n4/4N3/8/8/4K3/8 w - - 0 20"

# Black knight on e5 takes the f3-pawn; White king recaptures next move.
_SAC_BLACK = "4k3/8/8/4n3/8/5P2/4K3/8 w - - 0 20"


class TestForcingCombinationRule(unittest.TestCase):
    """Forcing combination: sacrifice (not equal trade) that improves the evaluation."""

    def test_should_match_when_sacrifice_improves_eval_after_recapture(self):
        moves = moves_from_pgn(
            "Kd3 Ke7 Nxf7 Kxf7",
            starting_fen=_SAC,
            analysis={
                20: {"black": {"eval": "+0.20"}},
                21: {
                    "white": {"cpl": "5", "eval": "+0.30"},
                    "black": {"cpl": "0", "eval": "+1.50"},
                },
            },
        )
        highlights = evaluate_rule(ForcingCombinationRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="forcing_combination", side="white"
        )
        self.assertTrue(matching, "Expected forcing combination on Nxf7 / Kxf7")
        self.assertIn("forcing combination", matching[0].description.lower())

    def test_should_match_when_black_sacrifice_improves_eval_after_recapture(self):
        moves = moves_from_pgn(
            "Ke3 Nxf3 Kxf3",
            starting_fen=_SAC_BLACK,
            analysis={
                20: {
                    "white": {"eval": "+0.20"},
                    "black": {"cpl": "5", "eval": "+0.10"},
                },
                21: {"white": {"cpl": "0", "eval": "-1.20"}},
            },
        )
        highlights = evaluate_rule(ForcingCombinationRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="forcing_combination", side="black"
        )
        self.assertTrue(matching, "Expected forcing combination on ...Nxf3 / Kxf3")
        self.assertIn("black", matching[0].description.lower())

    def test_should_not_match_when_the_trade_is_an_equal_recapture(self):
        moves = moves_from_pgn(
            "Kd3 Ke7 Nxf7 Nxf7",
            starting_fen=_EQUAL,
            analysis={
                20: {"black": {"eval": "+0.20"}},
                21: {
                    "white": {"cpl": "5", "eval": "+0.30"},
                    "black": {"cpl": "0", "eval": "+1.50"},
                },
            },
        )
        highlights = evaluate_rule(ForcingCombinationRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="forcing_combination", side="white"
        )
        self.assertFalse(
            matching,
            "An equal knight trade should not count as a forcing combination",
        )


if __name__ == "__main__":
    unittest.main()
