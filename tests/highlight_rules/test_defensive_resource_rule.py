"""Unit tests for DefensiveResourceRule."""

import unittest

from app.services.game_highlights.rules.defensive_resource_rule import DefensiveResourceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "q3k3/8/8/8/8/8/8/4K3 w - - 0 19"


class TestDefensiveResourceRule(unittest.TestCase):
    """Only good defense against a real check / tactical threat."""

    def test_should_match_when_only_good_move_resolves_check(self):
        moves = moves_from_pgn(
            "Ke2 Qe4+ Kf2",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "200", "eval": "-2.5"}},
                20: {
                    "white": {
                        "cpl": "5",
                        "cpl_2": "120",
                        "cpl_3": "130",
                        "eval": "-2.4",
                        "best": "Kf2",
                        "is_top3": True,
                    },
                },
            },
        )
        highlights = evaluate_rule(DefensiveResourceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="defensive_resource", side="white"
        )
        self.assertTrue(matching, "Expected only defensive resource on 20. Kf2")
        self.assertIn("defensive", matching[0].description.lower())

    def test_should_not_match_when_other_defenses_are_also_acceptable(self):
        moves = moves_from_pgn(
            "Ke2 Qe4+ Kf2",
            starting_fen=_FEN,
            analysis={
                19: {"black": {"cpl": "200", "eval": "-2.5"}},
                20: {
                    "white": {
                        "cpl": "5",
                        "cpl_2": "40",
                        "cpl_3": "50",
                        "eval": "-2.4",
                        "best": "Kf2",
                        "is_top3": True,
                    },
                },
            },
        )
        highlights = evaluate_rule(DefensiveResourceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="defensive_resource", side="white"
        )
        self.assertFalse(
            matching,
            "When PV2/PV3 are also decent, it is not the only defensive resource",
        )


if __name__ == "__main__":
    unittest.main()
