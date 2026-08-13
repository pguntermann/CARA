"""Unit tests for ZugzwangRule."""

import unittest

from app.services.game_highlights.rules.zugzwang_rule import ZugzwangRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/8/8/8/8/8/3P4/4K3 w - - 0 40"


class TestZugzwangRule(unittest.TestCase):
    """Simplified endgame where every top move is bad and the eval drops."""

    def test_should_match_when_all_top_moves_are_bad_and_eval_drops(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3",
            starting_fen=_FEN,
            analysis={
                40: {"black": {"eval": "+0.5"}},
                41: {
                    "white": {
                        "cpl": "160",
                        "cpl_2": "170",
                        "cpl_3": "180",
                        "eval": "-1.0",
                    },
                },
            },
        )
        highlights = evaluate_rule(ZugzwangRule({}), moves, move_number=41)
        matching = find_highlights(
            highlights, move_number=40, rule_type="zugzwang", side="black"
        )
        self.assertTrue(
            matching,
            "Expected zugzwang attached to 40...Ke7 (the ply that created it)",
        )
        self.assertIn("white is in zugzwang", matching[0].description.lower())

    def test_should_not_match_when_evaluation_does_not_worsen(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3",
            starting_fen=_FEN,
            analysis={
                40: {"black": {"eval": "+0.5"}},
                41: {
                    "white": {
                        "cpl": "160",
                        "cpl_2": "170",
                        "cpl_3": "180",
                        "eval": "+0.4",
                    },
                },
            },
        )
        highlights = evaluate_rule(ZugzwangRule({}), moves, move_number=41)
        matching = find_highlights(
            highlights, move_number=40, rule_type="zugzwang", side="black"
        )
        self.assertFalse(
            matching,
            "High CPLs alone should not count as zugzwang without an eval drop",
        )


if __name__ == "__main__":
    unittest.main()
