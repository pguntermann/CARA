"""Unit tests for NoveltyRule."""

import unittest

from app.services.game_highlights.rules.novelty_rule import NoveltyRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


def _seven_moves_then(extra: str = "a3", **analysis_for_extra):
    """Italian-ish line reaching move 7, then one more white move to test."""
    # 1–6 full moves, then white's 7th move is the novelty candidate.
    pgn = f"e4 e5 Nf3 Nc6 Bc4 Bc5 d3 d6 Nc3 Nf6 O-O O-O {extra}"
    analysis = {7: {"white": analysis_for_extra}} if analysis_for_extra else None
    return moves_from_pgn(pgn, analysis=analysis)


class TestNoveltyRule(unittest.TestCase):
    """Novelty: good move from move 7 on that is outside the engine top 3."""

    def test_should_match_when_good_move_is_outside_top3(self):
        moves = _seven_moves_then(
            "a3",
            cpl="10",
            is_top3=False,
        )
        highlights = evaluate_rule(NoveltyRule({}), moves, move_number=7)
        matching = find_highlights(
            highlights, move_number=7, rule_type="novelty", side="white"
        )
        self.assertTrue(matching, "Expected novelty on 7. a3")
        self.assertIn("novelty", matching[0].description.lower())

    def test_should_not_match_when_move_is_in_engine_top3(self):
        moves = _seven_moves_then(
            "a3",
            cpl="10",
            is_top3=True,
        )
        highlights = evaluate_rule(NoveltyRule({}), moves, move_number=7)
        matching = find_highlights(
            highlights, move_number=7, rule_type="novelty", side="white"
        )
        self.assertFalse(matching, "Top-3 engine moves should not count as novelties")


if __name__ == "__main__":
    unittest.main()
