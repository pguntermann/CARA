"""Unit tests for BackRankWeaknessRule."""

import unittest

from app.services.game_highlights.rules.back_rank_weakness_rule import BackRankWeaknessRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestBackRankWeaknessRule(unittest.TestCase):
    """Back-rank weakness: king on back rank, escapes blocked, enemy heavy piece there."""

    def test_should_match_when_king_trapped_on_back_rank(self):
        # White rook on c1 blocks Ra1 so Kg1 is legal. After: Kg1, Pf2/g2/h2, Ra1.
        moves = moves_from_pgn(
            "Kg1",
            starting_fen="6k1/5ppp/8/8/8/8/5PPP/r1R2K2 w - - 0 40",
        )
        highlights = evaluate_rule(BackRankWeaknessRule({}), moves, move_number=40)
        matching = find_highlights(
            highlights, move_number=40, rule_type="back_rank_weakness", side="white"
        )
        self.assertTrue(matching, "Expected back-rank weakness on 40. Kg1")
        self.assertIn("back rank", matching[0].description.lower())

    def test_should_not_match_when_escape_square_is_open(self):
        # Same setup, but g2 is empty so the king has a flight square.
        moves = moves_from_pgn(
            "Kg1",
            starting_fen="6k1/5ppp/8/8/8/8/5P1P/r1R2K2 w - - 0 40",
        )
        highlights = evaluate_rule(BackRankWeaknessRule({}), moves, move_number=40)
        matching = find_highlights(
            highlights, move_number=40, rule_type="back_rank_weakness", side="white"
        )
        self.assertFalse(
            matching,
            "Back-rank weakness should not fire when g2 is an escape square",
        )


if __name__ == "__main__":
    unittest.main()
