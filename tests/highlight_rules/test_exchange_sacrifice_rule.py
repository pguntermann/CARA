"""Unit tests for ExchangeSacrificeRule."""

import unittest

from app.services.game_highlights.rules.exchange_sacrifice_rule import ExchangeSacrificeRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/7p/8/3n4/2b5/8/3R4/6K1 w - - 0 19"


class TestExchangeSacrificeRule(unittest.TestCase):
    """Exchange sacrifice: rook takes minor, reply takes the rook, eval holds."""

    def test_should_match_when_rook_takes_knight_and_is_recaptured(self):
        # Rxd5 gains a knight; Bxd5 takes the rook back (~200cp). Eval holds.
        moves = moves_from_pgn(
            "Kh2 h6 Rxd5 Bxd5",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"eval": "+0.35"}},
                20: {
                    "white": {"cpl": "10", "eval": "+0.4"},
                    "black": {"cpl": "20", "eval": "+0.3"},
                },
            },
        )
        highlights = evaluate_rule(ExchangeSacrificeRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="exchange_sacrifice", side="white"
        )
        self.assertTrue(matching, "Expected exchange sacrifice on 20. Rxd5")
        self.assertIn("exchange", matching[0].description.lower())

    def test_should_not_match_when_the_evaluation_collapses(self):
        # Same material trade, but White's eval crashes after the recapture.
        moves = moves_from_pgn(
            "Kh2 h6 Rxd5 Bxd5",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"eval": "+0.5"}},
                20: {
                    "white": {"cpl": "10", "eval": "+0.4"},
                    "black": {"cpl": "20", "eval": "-2.0"},
                },
            },
        )
        highlights = evaluate_rule(ExchangeSacrificeRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="exchange_sacrifice", side="white"
        )
        self.assertFalse(
            matching,
            "An exchange that dumps the evaluation should not count as positional compensation",
        )


if __name__ == "__main__":
    unittest.main()
