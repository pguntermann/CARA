"""Unit tests for BreakthroughSacrificeRule."""

import unittest

from app.services.game_highlights.rules.breakthrough_sacrifice_rule import (
    BreakthroughSacrificeRule,
)
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/5p2/8/3B4/8/8/8/4K3 w - - 0 19"
_BXB1_FEN = "rn2k2r/ppq2ppp/2pbpn2/2Pp1b2/3P4/1P2PN2/PB2BPPP/RN1Q1RK1 b kq - 0 9"


class TestBreakthroughSacrificeRule(unittest.TestCase):
    """Breakthrough sacrifice: give a piece, eval jumps after the reply, no regain."""

    def test_should_match_when_piece_sac_improves_eval_after_reply(self):
        # Bxf7+ gives the bishop for a pawn; Kxf7 takes it back. Eval jumps for White.
        moves = moves_from_pgn(
            "Ke2 Ke7 Bxf7+ Kxf7",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"eval": "+0.4"}},
                20: {
                    "white": {"cpl": "20", "eval": "+0.5"},
                    "black": {"cpl": "50", "eval": "+3.0"},
                },
            },
        )
        highlights = evaluate_rule(BreakthroughSacrificeRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="breakthrough_sacrifice", side="white"
        )
        self.assertTrue(matching, "Expected breakthrough sacrifice on 20. Bxf7+")
        self.assertIn("break through", matching[0].description.lower())

    def test_should_not_match_when_evaluation_barely_moves(self):
        # Same material sacrifice, but the eval barely improves after the reply.
        moves = moves_from_pgn(
            "Ke2 Ke7 Bxf7+ Kxf7",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"eval": "+0.4"}},
                20: {
                    "white": {"cpl": "20", "eval": "+0.5"},
                    "black": {"cpl": "50", "eval": "+0.6"},
                },
            },
        )
        highlights = evaluate_rule(BreakthroughSacrificeRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="breakthrough_sacrifice", side="white"
        )
        self.assertFalse(
            matching,
            "A sacrifice without a clear eval breakthrough should not match",
        )

    def test_should_not_match_equal_minor_trade_recaptured_by_rook(self):
        # 9...Bxb1 takes the knight; 10.Rxb1 recaptures. Own material drops 300cp,
        # but relative material is unchanged — not a sacrifice. Eval can still
        # "improve" for Black if White's reply is inaccurate.
        moves = moves_from_pgn(
            "Bxb1 Rxb1 O-O",
            starting_fen=_BXB1_FEN,
            analysis={
                9: {
                    "black": {
                        "cpl": "422",
                        "eval": "+4.7",
                    },
                },
                10: {
                    "white": {"cpl": "363", "eval": "+1.1"},
                    "black": {"cpl": "352", "eval": "+4.6"},
                },
            },
        )
        self.assertEqual(moves[0].black_move, "Bxb1")
        self.assertEqual(moves[0].black_capture, "n")
        self.assertEqual(moves[1].white_move, "Rxb1")

        highlights = evaluate_rule(BreakthroughSacrificeRule({}), moves, move_number=9)
        matching = find_highlights(
            highlights, move_number=9, rule_type="breakthrough_sacrifice", side="black"
        )
        self.assertFalse(
            matching,
            "B×N followed by R×B is an equal trade, not a breakthrough sacrifice",
        )


if __name__ == "__main__":
    unittest.main()
