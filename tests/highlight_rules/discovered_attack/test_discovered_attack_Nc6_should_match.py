"""Test case: Discovered attack Nc6+ - should detect discovered check on move 16."""

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
from app.services.game_highlights.rules.discovered_attack_rule import DiscoveredAttackRule
from tests.highlight_rules.helpers import find_highlights


FEN_BEFORE = "r1bqk2r/ppp2ppp/5n2/4N3/2B5/8/PPPP1PPP/R1BQR1K1 w kq - 0 16"


class TestDiscoveredAttackNc6ShouldMatch(unittest.TestCase):
    """Test that 16. Nc6+ is detected as a discovered attack on the king."""

    def test_discovered_attack_Nc6_should_match(self):
        before = chess.Board(FEN_BEFORE)
        move = before.parse_san("Nc6+")
        after = before.copy()
        after.push(move)

        prev = MoveData(
            move_number=15,
            white_move="Bb3",
            black_move="a6",
            cpl_white="10",
            cpl_black="10",
            fen_black=FEN_BEFORE,
        )
        cur = MoveData(
            move_number=16,
            white_move="Nc6+",
            cpl_white="5",
            assess_white="Best Move",
            fen_white=after.fen(),
        )
        ctx = RuleContext(
            move_index=1,
            total_moves=2,
            opening_end=15,
            middlegame_end=40,
            prev_move=prev,
            next_move=None,
            prev_white_bishops=2,
            prev_black_bishops=2,
            prev_white_knights=2,
            prev_black_knights=2,
            prev_white_queens=1,
            prev_black_queens=1,
            prev_white_rooks=2,
            prev_black_rooks=2,
            prev_white_pawns=8,
            prev_black_pawns=7,
            prev_white_material=39,
            prev_black_material=36,
            last_book_move_number=0,
            theory_departed=True,
            good_move_max_cpl=50,
            inaccuracy_max_cpl=100,
            mistake_max_cpl=200,
            shared_state={},
            moves=[prev, cur],
        )

        highlights = DiscoveredAttackRule({}).evaluate(cur, ctx)
        matching = find_highlights(
            highlights, move_number=16, rule_type="discovered_attack", side="white"
        )
        self.assertTrue(
            matching,
            "Discovered attack should be detected for 16. Nc6+",
        )
        self.assertIn("king", matching[0].description.lower())


if __name__ == "__main__":
    unittest.main()
