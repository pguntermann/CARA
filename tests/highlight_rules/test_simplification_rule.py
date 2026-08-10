"""Unit tests for SimplificationRule."""

import unittest

from app.services.game_highlights.rules.simplification_rule import SimplificationRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_ROOKS_WHITE_STARTS = "4k3/4r3/8/4r3/4R3/8/7P/4K3 w - - 0 20"
_ROOKS_BLACK_STARTS = "4k3/7r/8/r7/R7/8/7P/R3K3 w - - 0 20"


class TestSimplificationRule(unittest.TestCase):
    """Simplification: piece trade that reduces material while eval stays roughly equal."""

    def test_should_match_when_white_starts_a_quiet_rook_trade(self):
        moves = moves_from_pgn(
            "h3 Kd8 Rxe5 Rxe5",
            starting_fen=_ROOKS_WHITE_STARTS,
            analysis={
                20: {"black": {"eval": "+0.20"}},
                21: {"white": {"eval": "+0.25"}, "black": {"eval": "+0.30"}},
            },
        )
        highlights = evaluate_rule(SimplificationRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="simplification", side="white"
        )
        self.assertTrue(matching, "Expected quiet simplifying rook trade started by White")
        self.assertTrue(matching[0].is_white)

    def test_should_match_when_black_starts_a_quiet_rook_trade(self):
        moves = moves_from_pgn(
            "h3 Rxa4 Rxa4",
            starting_fen=_ROOKS_BLACK_STARTS,
            analysis={
                20: {"white": {"eval": "+0.20"}, "black": {"eval": "+0.25"}},
                21: {"white": {"eval": "+0.30"}},
            },
        )
        # Detected on Black's starting half-move (row 20), looking ahead to White's reply.
        highlights = evaluate_rule(SimplificationRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="simplification", side="black"
        )
        self.assertTrue(matching, "Expected quiet simplifying rook trade started by Black")
        self.assertFalse(matching[0].is_white)

    def test_should_not_match_when_trade_swings_the_evaluation(self):
        moves = moves_from_pgn(
            "h3 Kd8 Rxe5 Rxe5",
            starting_fen=_ROOKS_WHITE_STARTS,
            analysis={
                20: {"black": {"eval": "+0.20"}},
                21: {"white": {"eval": "+1.00"}, "black": {"eval": "+1.50"}},
            },
        )
        highlights = evaluate_rule(SimplificationRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="simplification"
        )
        self.assertFalse(
            matching,
            "A trade that swings eval by more than 50cp is an exchange, not quiet simplification",
        )

    def test_should_not_match_uneven_queen_for_bishop_recapture(self):
        # 11.Nxf3 takes the queen; 11...Nxh6 takes a bishop — not an even trade,
        # even if the eval is flat (White ends a piece down from the wider sequence).
        moves = moves_from_pgn(
            "Nxf3 Nxh6",
            starting_fen="rnb1kb1r/ppp1pp1p/6pB/4Nn2/3P2P1/5q1P/PPP2P1R/RN2KB2 w Qkq - 0 11",
            analysis={
                10: {"black": {"eval": "-4.0"}},
                11: {
                    "white": {"cpl": "0", "eval": "-4.0"},
                    "black": {"cpl": "0", "eval": "-4.0"},
                },
            },
        )
        highlights = evaluate_rule(SimplificationRule({}), moves, move_number=11)
        matching = find_highlights(
            highlights, move_number=11, rule_type="simplification", side="white"
        )
        self.assertFalse(
            matching,
            "Capturing a queen then losing a bishop is not simplification",
        )


if __name__ == "__main__":
    unittest.main()
