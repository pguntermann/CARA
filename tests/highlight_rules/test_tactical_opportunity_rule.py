"""Unit tests for TacticalOpportunityRule."""

import unittest

from app.services.game_highlights.rules.tactical_opportunity_rule import TacticalOpportunityRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

# Queen on h6 can take a hanging knight on e3; White can also play a quiet king move.
_HANGING_KNIGHT = "4k3/8/7Q/8/8/4n3/7P/4K3 w - - 0 20"


class TestTacticalOpportunityRule(unittest.TestCase):
    """Missed tactical opportunity: mistake that skips a tactical best move."""

    def test_should_match_when_mistake_skips_a_winning_capture(self):
        moves = moves_from_pgn(
            "h3 Ke7 Kd2 Kd8",
            starting_fen=_HANGING_KNIGHT,
            analysis={
                20: {"black": {"cpl": "20"}},
                21: {
                    "white": {
                        "cpl": "250",
                        "best": "Qxe3",
                        "assess": "Mistake",
                    },
                    "black": {"cpl": "20"},
                },
            },
        )
        highlights = evaluate_rule(TacticalOpportunityRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="tactical_opportunity", side="white"
        )
        self.assertTrue(matching, "Expected missed tactical opportunity on Kd2 instead of Qxe3")
        self.assertIn("qxe3", matching[0].description.lower())

    def test_should_not_match_when_the_tactical_capture_is_played(self):
        moves = moves_from_pgn(
            "h3 Ke7 Qxe3 Kd8",
            starting_fen=_HANGING_KNIGHT,
            analysis={
                20: {"black": {"cpl": "20"}},
                21: {
                    "white": {"cpl": "5", "best": "Qxe3", "assess": "Best Move"},
                    "black": {"cpl": "20"},
                },
            },
        )
        highlights = evaluate_rule(TacticalOpportunityRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="tactical_opportunity", side="white"
        )
        self.assertFalse(
            matching,
            "Playing the tactical capture should not count as a missed opportunity",
        )


if __name__ == "__main__":
    unittest.main()
