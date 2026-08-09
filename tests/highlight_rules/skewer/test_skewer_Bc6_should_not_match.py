"""Skewer rule: equal-trade x-ray should not match; winning interposed cash-in should."""

import sys
import os
import unittest

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
)

import chess

from app.models.moveslist_model import MoveData
from app.services.game_highlights.base_rule import RuleContext
from app.services.game_highlights.rules.skewer_rule import SkewerRule
from tests.highlight_rules.helpers import find_highlights


def _ctx(moves, move_index, **kwargs) -> RuleContext:
    defaults = dict(
        total_moves=len(moves),
        opening_end=15,
        middlegame_end=40,
        prev_move=moves[move_index - 1] if move_index > 0 else None,
        next_move=moves[move_index + 1] if move_index + 1 < len(moves) else None,
        prev_white_bishops=0,
        prev_black_bishops=0,
        prev_white_knights=0,
        prev_black_knights=0,
        prev_white_queens=0,
        prev_black_queens=0,
        prev_white_rooks=0,
        prev_black_rooks=0,
        prev_white_pawns=0,
        prev_black_pawns=0,
        prev_white_material=0,
        prev_black_material=0,
        last_book_move_number=0,
        theory_departed=True,
        good_move_max_cpl=50,
        inaccuracy_max_cpl=100,
        mistake_max_cpl=200,
        shared_state={},
        moves=moves,
        move_index=move_index,
    )
    defaults.update(kwargs)
    return RuleContext(**defaults)


def _play(sans):
    board = chess.Board()
    moves = []
    n = 1
    i = 0
    while i < len(sans):
        w = sans[i]
        i += 1
        m = board.parse_san(w)
        capt = board.piece_at(m.to_square)
        board.push(m)
        fw = board.fen()
        wc = capt.symbol().lower() if capt else ""
        bk = ""
        bc = ""
        fb = ""
        if i < len(sans):
            bk = sans[i]
            i += 1
            m = board.parse_san(bk)
            capt = board.piece_at(m.to_square)
            board.push(m)
            fb = board.fen()
            bc = capt.symbol().lower() if capt else ""
        moves.append(
            MoveData(
                move_number=n,
                white_move=w,
                black_move=bk,
                white_capture=wc,
                black_capture=bc,
                fen_white=fw,
                fen_black=fb,
                cpl_white="0",
                cpl_black="0",
                assess_white="Best Move",
                assess_black="Best Move",
            )
        )
        n += 1
    return moves


class TestSkewerBc6ShouldNotMatch(unittest.TestCase):
    """Bc6 x-rays Re4/Nf3, but Rf4 defends for an equal B↔N trade."""

    def test_skewer_Bc6_should_not_match(self):
        sans = (
            "Nf3 Nf6 e4 g6 e5 Nh5 d4 d6 h3 Qd7 g4 Ng7 Bh6 dxe5 Nxe5 Qd5 Rh2 Nf5 "
            "Qf3 Qxf3 Nxf3 Nxh6 g5 Nf5 Bd3 e5 dxe5 h5 gxh6 Rh7 Nbd2 a5 O-O-O Nd7 "
            "Re1 b5 Bxb5 Ke7 Bxd7 Bxd7 Nc4 Rxh6 h4 Bg7 Re4 Bc6 Rf4 Bxf3 Rxf3"
        ).split()
        moves = _play(sans)
        # Move 23: Re4 Bc6
        idx = 22
        highlights = SkewerRule({}).evaluate(moves[idx], _ctx(moves, idx))
        matching = find_highlights(
            highlights, move_number=23, rule_type="skewer", side="black"
        )
        self.assertFalse(
            matching,
            "Skewer should not fire on 23...Bc6 when White can flee to an equal trade",
        )


class TestSkewerBb6ShouldMatch(unittest.TestCase):
    """Interposed Bb6 cashes in the queen for a net material gain."""

    def test_skewer_Bb6_should_match(self):
        sans = (
            "Nf3 d5 d4 Nf6 e3 c6 Be2 Bf5 O-O e6 b3 Bb4 Bb2 Bd6 c4 Qc7 c5 Bxb1 "
            "Rxb1 O-O cxd6 Qd8 Ne5 Re8 Rc1 Ne4 Bd3 f5 Bxe4 dxe4 Qd2 g6 Bc3 a5 "
            "a4 g5 b4 axb4 Bxb4 Nd7 a5 h6 Rb1 Nxe5 dxe5 c5 Bxc5 h5 Rxb7 Rxa5 "
            "Rfb1 Ra8 d7 Ra5 Bb6 Ra4 Bxd8 Rxd8"
        ).split()
        moves = _play(sans)
        # Move 28: Bb6 Ra4
        idx = 27
        highlights = SkewerRule({}).evaluate(moves[idx], _ctx(moves, idx))
        matching = find_highlights(
            highlights, move_number=28, rule_type="skewer", side="white"
        )
        self.assertTrue(
            matching,
            "Skewer should fire on 28. Bb6 when the game cashes in net material (Bxd8)",
        )


class TestSkewerBb4ShouldNotMatch(unittest.TestCase):
    """Bb4 pins Nc3 to the king — not a skewer; knight is defended."""

    def test_skewer_Bb4_should_not_match(self):
        fen_before = "rnbq1rk1/ppp1bppp/5n2/3p2B1/2PP4/2N2N2/PP3PPP/R2QKB1R b KQ - 6 7"
        before = chess.Board(fen_before)
        after = before.copy()
        after.push_san("Bb4")

        cur = MoveData(
            move_number=7,
            white_move="Bg5",
            black_move="Bb4",
            fen_white=fen_before,
            fen_black=after.fen(),
            cpl_white="44",
            cpl_black="78",
            assess_black="Inaccuracy",
        )
        ctx = _ctx([cur], 0)
        highlights = SkewerRule({}).evaluate(cur, ctx)
        matching = find_highlights(
            highlights, move_number=7, rule_type="skewer", side="black"
        )
        self.assertFalse(
            matching,
            "Skewer should not fire on 7...Bb4 (pin of defended knight to king)",
        )


if __name__ == "__main__":
    unittest.main()
