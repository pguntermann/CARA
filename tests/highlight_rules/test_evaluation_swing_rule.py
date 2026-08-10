"""Unit tests for EvaluationSwingRule."""

import unittest

from app.services.game_highlights.rules.evaluation_swing_rule import EvaluationSwingRule
from tests.highlight_rules.helpers import evaluate_rule_sequence, moves_from_pgn

_FEN = "4k3/8/8/8/8/8/8/4K3 w - - 0 19"


def _swing_highlights(shared_state):
    store = shared_state.get("eval_swing_highlights", {})
    return [highlight for _, highlight in store.values()]


class TestEvaluationSwingRule(unittest.TestCase):
    """Large same-sign eval swings, collected via shared_state post-processing."""

    def test_should_match_when_eval_jumps_without_crossing_zero(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kd6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+0.5"}},
                20: {
                    "white": {"cpl": "10", "eval": "+3.0"},
                    "black": {"cpl": "20", "eval": "+2.8"},
                },
            },
        )
        shared = {}
        evaluate_rule_sequence(EvaluationSwingRule({}), moves, shared_state=shared)
        matching = [
            h
            for h in _swing_highlights(shared)
            if h.move_number == 20 and h.is_white and h.rule_type == "evaluation_swing"
        ]
        self.assertTrue(matching, "Expected evaluation swing on 20. Kd3")
        self.assertIn("increased", matching[0].description.lower())

    def test_should_not_match_when_opponent_immediately_blunders(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3 Kd6",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "10", "eval": "+0.5"}},
                20: {
                    "white": {"cpl": "10", "eval": "+3.0"},
                    "black": {"cpl": "150", "eval": "+5.0"},
                },
            },
        )
        shared = {}
        evaluate_rule_sequence(EvaluationSwingRule({}), moves, shared_state=shared)
        matching = [
            h
            for h in _swing_highlights(shared)
            if h.move_number == 20 and h.is_white and h.rule_type == "evaluation_swing"
        ]
        self.assertFalse(
            matching,
            "Swings driven by an opponent blunder should not be credited",
        )


if __name__ == "__main__":
    unittest.main()
