"""Unit tests for ForkRule."""

import unittest

from app.services.game_highlights.rules.fork_rule import ForkRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestForkRule(unittest.TestCase):
    """Exploitable fork: safe multi-target attack that wins material or forces."""

    def test_should_match_when_knight_forks_king_and_rook(self):
        # Nbc7+: knight checks the king and attacks the undefended rook on a8.
        moves = moves_from_pgn(
            "Nc7+",
            starting_fen="r3k3/8/8/1N6/8/8/8/4K3 w - - 0 10",
        )
        highlights = evaluate_rule(ForkRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="fork", side="white"
        )
        self.assertTrue(matching, "Expected fork on 10. Nc7+")
        self.assertIn("fork", matching[0].description.lower())

    def test_should_not_match_when_the_forking_piece_is_hanging(self):
        # Nd6 would attack king + pawns, but the black queen on d4 takes it for free.
        moves = moves_from_pgn(
            "Nd6",
            starting_fen="4k3/1p3p2/8/5N2/3q4/8/8/4K3 w - - 0 10",
        )
        highlights = evaluate_rule(ForkRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="fork", side="white"
        )
        self.assertFalse(
            matching,
            "A hanging forker that the opponent can capture is not an exploitable fork",
        )

    def test_should_match_pawn_fork_even_when_move_is_an_inaccuracy(self):
        # bxc5 forks Qb6 and Bd6; CPL 60 is an inaccuracy vs engine-best e5.
        fen = "rnb1k1r1/3p1p2/1q1bpn2/p1pP3p/1PB1P3/2P1BN2/1PQN1PPP/R4RK1 w q - 0 15"
        moves = moves_from_pgn(
            "bxc5",
            starting_fen=fen,
            analysis={15: {"white": {"cpl": "60", "eval": "+5.3"}}},
        )
        highlights = evaluate_rule(ForkRule({}), moves, move_number=15)
        matching = find_highlights(
            highlights, move_number=15, rule_type="fork", side="white"
        )
        self.assertTrue(
            matching,
            "Expected pawn fork on 15. bxc5 even with CPL 60 (inaccuracy)",
        )

    def test_should_match_knight_fork_when_king_cannot_legally_capture(self):
        # Nxf2 forks Qd1 and undefended Rh1. The white king "attacks" f2 but
        # cannot take (Bc5 covers f2) — that illegal capture must not veto the fork.
        moves = moves_from_pgn(
            "Nxf2",
            starting_fen="rnbqk1r1/pppp1p1p/8/2b1p3/4P1n1/2NP1N1P/PPP2PP1/R1BQKB1R b KQq - 0 7",
            analysis={7: {"black": {"cpl": "0", "eval": "-2.4"}}},
        )
        highlights = evaluate_rule(ForkRule({}), moves, move_number=7)
        matching = find_highlights(
            highlights, move_number=7, rule_type="fork", side="black"
        )
        self.assertTrue(matching, "Expected fork on 7...Nxf2")


if __name__ == "__main__":
    unittest.main()
