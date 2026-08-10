"""Unit tests for BlunderedPieceRule."""

import unittest

from app.services.game_highlights.rules.blundered_piece_rule import BlunderedPieceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

# White can hang the queen on a4; Black's rook on a5 takes it.
_HANG_QUEEN = "4k3/8/8/r7/8/8/Q6P/4K3 w - - 0 20"

# Mutual rook trade on the e-file.
_ROOK_TRADE = "4k3/4r3/8/4r3/4R3/8/7P/4K3 w - - 0 20"


class TestBlunderedPieceRule(unittest.TestCase):
    """Blundered piece: hung queen/rook taken on the next ply, with a lasting eval drop."""

    def test_should_match_when_hung_queen_is_taken(self):
        moves = moves_from_pgn(
            "h3 Kd7 Qa4 Rxa4",
            starting_fen=_HANG_QUEEN,
            analysis={
                20: {"black": {"cpl": "20", "eval": "+0.20"}},
                21: {
                    "white": {
                        "cpl": "300",
                        "assess": "Blunder",
                        "eval": "-1.00",
                    },
                    "black": {"cpl": "5", "eval": "-9.00"},
                },
            },
        )
        # Detected on Black's capturing ply; highlight attributed to White's blunder.
        highlights = evaluate_rule(BlunderedPieceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="blundered_piece", side="white"
        )
        self.assertTrue(matching, "Expected White blundered queen after Rxa4")
        self.assertIn("queen", matching[0].description.lower())

    def test_should_not_match_when_rooks_are_traded_equally(self):
        moves = moves_from_pgn(
            "h3 Kd8 Rxe5 Rxe5",
            starting_fen=_ROOK_TRADE,
            analysis={
                20: {"black": {"cpl": "20", "eval": "+0.20"}},
                21: {
                    "white": {"cpl": "300", "assess": "Blunder", "eval": "+0.25"},
                    "black": {"cpl": "5", "eval": "+0.30"},
                },
            },
        )
        highlights = evaluate_rule(BlunderedPieceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="blundered_piece"
        )
        self.assertFalse(
            matching,
            "An equal rook trade should not count as a blundered piece",
        )

    def test_should_match_when_mistake_leaves_rook_hanging(self):
        # 10.Bxb4 attacks Rf8; 10...Qh4 (Mistake) leaves it; 11.Bxf8 takes.
        moves = moves_from_pgn(
            "Bxb4 Qh4 Bxf8",
            starting_fen="r1bq1rk1/p1p2ppp/8/3p4/1b1P4/8/PPPB1PPP/R2QKB1R w KQ - 0 10",
            analysis={
                10: {
                    "white": {"cpl": "0", "eval": "+3.9"},
                    "black": {
                        "cpl": "133",
                        "assess": "Mistake",
                        "eval": "+5.2",
                    },
                },
                11: {"white": {"cpl": "0", "eval": "+5.2"}, "black": {"cpl": "68", "eval": "+5.9"}},
            },
        )
        highlights = evaluate_rule(BlunderedPieceRule({}), moves, move_number=11)
        matching = find_highlights(
            highlights, move_number=10, rule_type="blundered_piece", side="black"
        )
        self.assertTrue(matching, "Expected Black blundered rook on 10...Qh4")
        self.assertIn("rook", matching[0].description.lower())

    def test_should_not_match_when_prior_is_only_an_inaccuracy(self):
        # Same hang pattern, but prior is a mild inaccuracy — not blunder-grade.
        moves = moves_from_pgn(
            "Bxb4 Qh4 Bxf8",
            starting_fen="r1bq1rk1/p1p2ppp/8/3p4/1b1P4/8/PPPB1PPP/R2QKB1R w KQ - 0 10",
            analysis={
                10: {
                    "white": {"cpl": "0", "eval": "+3.9"},
                    "black": {
                        "cpl": "80",
                        "assess": "Inaccuracy",
                        "eval": "+5.2",
                    },
                },
                11: {"white": {"cpl": "0", "eval": "+5.2"}},
            },
        )
        highlights = evaluate_rule(BlunderedPieceRule({}), moves, move_number=11)
        matching = find_highlights(
            highlights, move_number=10, rule_type="blundered_piece", side="black"
        )
        self.assertFalse(
            matching,
            "An inaccuracy that leaves a rook hanging should not be labeled blundered piece",
        )

    def test_should_not_match_queen_with_only_soft_rook_eval_drop(self):
        # Queen loss with ~130cp eval drop passes a 100 soft floor but must not
        # pass the queen soft floor (200).
        moves = moves_from_pgn(
            "h3 Kd7 Qa4 Rxa4",
            starting_fen=_HANG_QUEEN,
            analysis={
                20: {"black": {"cpl": "20", "eval": "+0.20"}},
                21: {
                    "white": {
                        "cpl": "150",
                        "assess": "Mistake",
                        "eval": "-0.50",
                    },
                    "black": {"cpl": "5", "eval": "-1.50"},
                },
            },
        )
        highlights = evaluate_rule(BlunderedPieceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="blundered_piece", side="white"
        )
        self.assertFalse(
            matching,
            "Queen hang with only ~130cp eval drop should not use the rook soft floor",
        )


if __name__ == "__main__":
    unittest.main()
