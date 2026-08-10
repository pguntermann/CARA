"""Unit tests for IsolatedPawnRule."""

import unittest

from app.services.game_highlights.rules.isolated_pawn_rule import IsolatedPawnRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_START = "4k3/8/8/8/8/1p6/2PP3P/4K3 w - - 0 20"


class TestIsolatedPawnRule(unittest.TestCase):
    """Isolated pawn: a pawn move that leaves a friendly pawn without adjacent-file support."""

    def test_should_match_when_pawn_capture_splits_neighbors(self):
        # c2/d2 were connected; cxb3 leaves d2 (and b3) without adjacent-file partners.
        moves = moves_from_pgn("h3 Kd7 cxb3", starting_fen=_START)
        highlights = evaluate_rule(IsolatedPawnRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="isolated_pawn", side="white"
        )
        self.assertTrue(matching, "Expected isolated pawn on 21. cxb3")
        self.assertIn("isolated", matching[0].description.lower())

    def test_should_not_match_when_structure_stays_connected(self):
        moves = moves_from_pgn("h3 Kd7", starting_fen=_START)
        highlights = evaluate_rule(IsolatedPawnRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="isolated_pawn", side="white"
        )
        self.assertFalse(matching, "h3 should not create a new isolated pawn")


if __name__ == "__main__":
    unittest.main()
