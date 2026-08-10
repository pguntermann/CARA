"""Unit tests for DefensiveFortressRule."""

import unittest

from app.services.game_highlights.rules.defensive_fortress_rule import DefensiveFortressRule
from tests.highlight_rules.helpers import evaluate_rule_sequence, moves_from_pgn

_FEN = "q3k3/8/8/8/8/8/4P3/4K3 w - - 0 19"


class TestDefensiveFortressRule(unittest.TestCase):
    """Holding a near-equal eval while down significant material."""

    def test_should_match_when_down_material_with_stable_eval(self):
        moves = moves_from_pgn(
            "Kd2 Kd7 Kc3 Kc6 Kd3 Kd6 Ke3",
            starting_fen=_FEN,
            analysis={
                20: {"white": {"eval": "+0.2"}},
                21: {"white": {"eval": "-0.1"}},
                22: {"white": {"eval": "0.0"}},
            },
        )
        highlights = evaluate_rule_sequence(DefensiveFortressRule({}), moves)
        matching = [
            h for h in highlights if h.rule_type == "defensive_fortress" and h.is_white
        ]
        self.assertTrue(matching, "Expected defensive fortress over moves 20-22")
        self.assertIn("fortress", matching[0].description.lower())

    def test_should_not_match_when_evaluation_is_not_stable(self):
        moves = moves_from_pgn(
            "Kd2 Kd7 Kc3 Kc6 Kd3 Kd6 Ke3",
            starting_fen=_FEN,
            analysis={
                20: {"white": {"eval": "+0.2"}},
                21: {"white": {"eval": "-2.0"}},
                22: {"white": {"eval": "0.0"}},
            },
        )
        highlights = evaluate_rule_sequence(DefensiveFortressRule({}), moves)
        matching = [
            h for h in highlights if h.rule_type == "defensive_fortress" and h.is_white
        ]
        self.assertFalse(
            matching,
            "A collapsing evaluation should break the fortress streak",
        )


if __name__ == "__main__":
    unittest.main()
