"""Unit tests for KingActivityRule."""

import unittest

from app.services.game_highlights.rules.king_activity_rule import KingActivityRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_START = "8/4k3/8/8/8/8/4K3/8 w - - 0 40"


class TestKingActivityRule(unittest.TestCase):
    """King activity: endgame king advances toward the center ranks."""

    def test_should_match_when_king_advances_in_endgame(self):
        # 41. Ke4: king steps from e3 (rank 3) onto e4 (rank 4).
        moves = moves_from_pgn("Ke3 Kf7 Ke4", starting_fen=_START)
        highlights = evaluate_rule(KingActivityRule({}), moves, move_number=41)
        matching = find_highlights(
            highlights, move_number=41, rule_type="king_activity", side="white"
        )
        self.assertTrue(matching, "Expected king activity on 41. Ke4")
        self.assertIn("king", matching[0].description.lower())

    def test_should_not_match_when_king_has_not_reached_active_ranks(self):
        # 40. Ke3 only reaches rank 3 (0-based 2), below the activity band.
        moves = moves_from_pgn("Ke3 Kf7", starting_fen=_START)
        highlights = evaluate_rule(KingActivityRule({}), moves, move_number=40)
        matching = find_highlights(
            highlights, move_number=40, rule_type="king_activity", side="white"
        )
        self.assertFalse(matching, "Ke3 should not count as endgame king activity")


if __name__ == "__main__":
    unittest.main()
