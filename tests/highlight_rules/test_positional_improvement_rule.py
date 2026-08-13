"""Unit tests for PositionalImprovementRule."""

import unittest

from app.services.game_highlights.rules.positional_improvement_rule import (
    PositionalImprovementRule,
)
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 19"


class TestPositionalImprovementRule(unittest.TestCase):
    """Quiet eval gains that are not driven by material or opponent blunders."""

    def test_should_match_when_good_quiet_move_improves_eval(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+0.2"}},
                20: {"white": {"cpl": "5", "eval": "+0.9"}},
            },
        )
        highlights = evaluate_rule(PositionalImprovementRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="positional_improvement", side="white"
        )
        self.assertTrue(matching, "Expected positional improvement on 20. Kd3")
        self.assertIn("positional", matching[0].description.lower())

    def test_should_not_match_when_opponent_immediately_blunders(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kd6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+0.2"}},
                20: {
                    "white": {"cpl": "5", "eval": "+0.9"},
                    "black": {"cpl": "150", "eval": "+2.0"},
                },
            },
        )
        highlights = evaluate_rule(PositionalImprovementRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="positional_improvement", side="white"
        )
        self.assertFalse(
            matching,
            "Eval jumps caused by the opponent's blunder should not count",
        )


if __name__ == "__main__":
    unittest.main()
