"""Test case: Fork Nxc7+ - royal fork winning an undefended pawn."""

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
from app.services.game_highlights.rules.fork_rule import ForkRule
from tests.highlight_rules.helpers import find_highlights


FEN_BEFORE = "4k1r1/2p1bn2/p1p1N1p1/1pP2p1p/8/1P2P2P/PB3PP1/3R2K1 w - - 6 21"


class TestForkNxc7ShouldMatch(unittest.TestCase):
    """Nxc7+ takes a free pawn with check — royal fork with net material."""

    def test_fork_Nxc7_should_match(self):
        before = chess.Board(FEN_BEFORE)
        after = before.copy()
        after.push_san("Nxc7+")

        prev = MoveData(
            move_number=20,
            white_move="Ne6",
            black_move="Be7",
            fen_black=FEN_BEFORE,
            cpl_white="0",
            cpl_black="0",
        )
        cur = MoveData(
            move_number=21,
            white_move="Nxc7+",
            black_move="Kf8",
            fen_white=after.fen(),
            cpl_white="0",
            assess_white="Best Move",
        )
        ctx = RuleContext(
            move_index=1,
            total_moves=2,
            opening_end=10,
            middlegame_end=40,
            prev_move=prev,
            next_move=None,
            prev_white_bishops=1,
            prev_black_bishops=1,
            prev_white_knights=1,
            prev_black_knights=1,
            prev_white_queens=0,
            prev_black_queens=0,
            prev_white_rooks=1,
            prev_black_rooks=1,
            prev_white_pawns=6,
            prev_black_pawns=6,
            prev_white_material=0,
            prev_black_material=0,
            last_book_move_number=0,
            theory_departed=True,
            good_move_max_cpl=50,
            inaccuracy_max_cpl=100,
            mistake_max_cpl=200,
            shared_state={},
            moves=[prev, cur],
        )

        highlights = ForkRule({}).evaluate(cur, ctx)
        matching = find_highlights(
            highlights, move_number=21, rule_type="fork", side="white"
        )
        self.assertTrue(
            matching,
            "Fork should be detected for 21. Nxc7+ (check + undefended pawn)",
        )


if __name__ == "__main__":
    unittest.main()
