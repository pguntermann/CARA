"""Unit tests for TacticalResourceRule."""

import unittest

from app.services.game_highlights.rules.tactical_resource_rule import TacticalResourceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

# Mutual rook trade (equal material).
_ROOKS = "4k3/4r3/8/4r3/4R3/8/7P/4K3 w - - 0 20"


class TestTacticalResourceRule(unittest.TestCase):
    """Tactical resource: good move with lasting material/eval payoff, not a hang cash-in."""

    def test_should_match_quiet_move_with_large_eval_jump(self):
        moves = moves_from_pgn(
            "Kd8 Ra7 Ke8",
            starting_fen="4k3/8/8/8/8/8/7P/R3K3 b - - 0 19",
            analysis={
                19: {"black": {"cpl": "40", "eval": "+0.5"}},
                20: {
                    "white": {"cpl": "5", "eval": "+4.0"},
                    "black": {"cpl": "40", "eval": "+4.0"},
                },
            },
        )
        highlights = evaluate_rule(TacticalResourceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="tactical_resource", side="white"
        )
        self.assertTrue(matching, "Expected tactical resource on quiet Ra7 eval jump")
        self.assertIn("tactical resource", matching[0].description.lower())

    def test_should_match_when_capture_wins_net_material_on_defended_unit(self):
        # d5 is defended by e6; Rxd5 still nets a pawn when Black does not recapture.
        moves = moves_from_pgn(
            "Kd7 Rxd5 Kc6",
            starting_fen="4k3/8/4p3/3p4/8/8/3R3P/4K3 b - - 0 19",
            analysis={
                19: {"black": {"cpl": "20"}},
                20: {"white": {"cpl": "5"}, "black": {"cpl": "40"}},
            },
        )
        highlights = evaluate_rule(TacticalResourceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="tactical_resource", side="white"
        )
        self.assertTrue(
            matching,
            "Expected tactical resource when capturing a defended unit for net gain",
        )

    def test_should_not_match_when_capture_is_an_equal_trade(self):
        moves = moves_from_pgn(
            "h3 Kd8 Rxe5 Rxe5",
            starting_fen=_ROOKS,
            analysis={
                20: {"black": {"cpl": "40"}},
                21: {"white": {"cpl": "5"}, "black": {"cpl": "5"}},
            },
        )
        highlights = evaluate_rule(TacticalResourceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="tactical_resource", side="white"
        )
        self.assertFalse(
            matching,
            "An equal rook trade should not count as a tactical resource",
        )

    def test_should_not_match_when_taking_undefended_hanging_knight(self):
        moves = moves_from_pgn(
            "h3 Ke7 Qxe3 Kd8",
            starting_fen="4k3/8/7Q/8/8/4n3/7P/4K3 w - - 0 20",
            analysis={
                20: {"black": {"cpl": "40"}},
                21: {"white": {"cpl": "5"}, "black": {"cpl": "30"}},
            },
        )
        highlights = evaluate_rule(TacticalResourceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="tactical_resource", side="white"
        )
        self.assertFalse(
            matching,
            "Taking an undefended hanging knight is not a tactical resource",
        )

    def test_should_not_match_when_taking_piece_hung_by_opponent_blunder(self):
        # 12...Rg8 hangs the queen on b2; 13.Qxb2 only cashes in that blunder.
        moves = moves_from_pgn(
            "Qb1 Rg8 Qxb2",
            starting_fen="r3kb1r/p1p2p2/2ppbp1p/4p3/P2PP3/5N2/1qP1NPPP/R2Q1RK1 w kq - 0 12",
            analysis={
                12: {
                    "white": {"cpl": "205", "eval": "-1.0"},
                    "black": {"cpl": "813", "assess": "Miss", "eval": "+7.2"},
                },
                13: {"white": {"cpl": "0", "eval": "+7.2"}},
            },
        )
        highlights = evaluate_rule(TacticalResourceRule({}), moves, move_number=13)
        matching = find_highlights(
            highlights, move_number=13, rule_type="tactical_resource", side="white"
        )
        self.assertFalse(
            matching,
            "Capturing a queen hung by the opponent's blunder is not a tactical resource",
        )

    def test_should_not_match_when_taking_rook_left_hanging_by_mistake(self):
        # After 10.Bxb4 the f8-rook is hanging; 10...Qh4 (Mistake) ignores it;
        # 11.Bxf8 only cashes in — not a newly found tactical resource.
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
                11: {"white": {"cpl": "0", "eval": "+5.2"}},
            },
        )
        highlights = evaluate_rule(TacticalResourceRule({}), moves, move_number=11)
        matching = find_highlights(
            highlights, move_number=11, rule_type="tactical_resource", side="white"
        )
        self.assertFalse(
            matching,
            "Capturing a rook left hanging by a mistake is not a tactical resource",
        )


if __name__ == "__main__":
    unittest.main()
