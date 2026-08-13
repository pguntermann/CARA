"""Unit tests for DoubledOnOpenFileRule."""

import unittest

from app.services.game_highlights.rules.doubled_on_open_file_rule import (
    DoubledOnOpenFileRule,
)
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestDoubledOnOpenFileRule(unittest.TestCase):
    """Doubled on open file: newly align two heavy pieces on a pawnless file."""

    def test_should_match_when_rook_doubles_with_queen_on_open_file(self):
        moves = moves_from_pgn(
            "Ke2 Kf7 Rd2",
            starting_fen="4k3/8/8/8/3Q4/8/R7/4K3 w - - 0 19",
        )
        highlights = evaluate_rule(DoubledOnOpenFileRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="doubled_on_open_file", side="white"
        )
        self.assertTrue(matching, "Expected doubled on open file on 20. Rd2")
        self.assertIn("doubled", matching[0].description.lower())
        self.assertIn("d-file", matching[0].description.lower())

    def test_should_not_match_when_file_has_a_pawn(self):
        # Black pawn on d7 — file is not open.
        moves = moves_from_pgn(
            "Ke2 Kf8 Rd2",
            starting_fen="4k3/3p4/8/8/3Q4/8/R7/4K3 w - - 0 19",
        )
        highlights = evaluate_rule(DoubledOnOpenFileRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="doubled_on_open_file", side="white"
        )
        self.assertFalse(
            matching,
            "Doubling on a file with a pawn should not match",
        )


if __name__ == "__main__":
    unittest.main()
