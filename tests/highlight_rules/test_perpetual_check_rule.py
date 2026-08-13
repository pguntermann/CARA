"""Unit tests for PerpetualCheckRule."""

import unittest

from app.services.game_highlights.rules.perpetual_check_rule import PerpetualCheckRule
from tests.highlight_rules.helpers import (
    evaluate_rule_sequence,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/8/8/8/8/8/8/Q3K3 w - - 0 19"


class TestPerpetualCheckRule(unittest.TestCase):
    """Three consecutive checks with a near-stable evaluation."""

    def test_should_match_when_checks_repeat_with_stable_eval(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Qa5+ Ke8 Qe5+ Kf8 Qf5+",
            starting_fen=_FEN,
            analysis={
                20: {"white": {"eval": "+0.1"}},
                21: {"white": {"eval": "+0.2"}},
                22: {"white": {"eval": "+0.15"}},
            },
        )
        highlights = evaluate_rule_sequence(PerpetualCheckRule({}), moves)
        matching = find_highlights(
            highlights, move_number=20, rule_type="perpetual_check", side="white"
        )
        self.assertTrue(matching, "Expected perpetual check starting at move 20")
        self.assertIn("perpetual", matching[0].description.lower())

    def test_should_not_match_when_evaluation_swings_during_checks(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Qa5+ Ke8 Qe5+ Kf8 Qf5+",
            starting_fen=_FEN,
            analysis={
                20: {"white": {"eval": "+0.1"}},
                21: {"white": {"eval": "+2.0"}},
                22: {"white": {"eval": "+0.15"}},
            },
        )
        highlights = evaluate_rule_sequence(PerpetualCheckRule({}), moves)
        matching = [
            h for h in highlights if h.rule_type == "perpetual_check" and h.is_white
        ]
        self.assertFalse(
            matching,
            "Checks with a large eval swing should not count as perpetual",
        )


if __name__ == "__main__":
    unittest.main()
