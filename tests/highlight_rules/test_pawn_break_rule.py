"""Unit tests for PawnBreakRule."""

import unittest

from app.services.game_highlights.rules.pawn_break_rule import PawnBreakRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 19"


class TestPawnBreakRule(unittest.TestCase):
    """Central pawn capture that creates a passer / open file, not a pawn trade."""

    def test_should_match_when_central_pawn_capture_creates_passer(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 exd5",
            starting_fen=_FEN,
        )
        highlights = evaluate_rule(PawnBreakRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="pawn_break", side="white"
        )
        self.assertTrue(matching, "Expected central pawn break on 20. exd5")
        self.assertIn("pawn break", matching[0].description.lower())

    def test_should_not_match_when_pawns_are_traded_equally(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 exd5 exd5",
            starting_fen="4k3/8/4p3/3p4/4P3/8/8/4K3 w - - 0 19",
        )
        highlights = evaluate_rule(PawnBreakRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="pawn_break", side="white"
        )
        self.assertFalse(
            matching,
            "An equal pawn-for-pawn exchange should not count as a pawn break",
        )


if __name__ == "__main__":
    unittest.main()
