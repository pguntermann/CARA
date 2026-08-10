"""Unit tests for TacticalSequenceRule."""

import unittest

from app.services.game_highlights.rules.tactical_sequence_rule import TacticalSequenceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

# Queen can take a hanging knight; quiet king walks provide a multi-ply forcing window.
_WHITE_START = "4k3/8/7Q/8/8/4n3/7P/4K3 w - - 0 20"

# Black knight can take the f3-pawn; White recaptures on the next row.
_BLACK_START = "4k3/8/8/4n3/8/5P2/4K3/8 w - - 0 20"


class TestTacticalSequenceRule(unittest.TestCase):
    """Tactical sequence: forcing ply continuation with a large lasting eval gain."""

    def test_should_match_when_white_forcing_sequence_improves_eval(self):
        moves = moves_from_pgn(
            "h3 Ke7 Qxe3 Kd8 Kd2 Kc8",
            starting_fen=_WHITE_START,
            analysis={
                20: {"black": {"cpl": "5", "eval": "+0.20"}},
                21: {
                    "white": {"cpl": "5", "eval": "+3.20"},
                    "black": {"cpl": "15", "eval": "+3.10"},
                },
                # One (our, their) continuation pair is enough after the loosened gate.
                22: {
                    "white": {"cpl": "20", "eval": "+3.30"},
                    "black": {"cpl": "25", "eval": "+3.20"},
                },
            },
        )
        highlights = evaluate_rule(TacticalSequenceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="tactical_sequence", side="white"
        )
        self.assertTrue(matching, "Expected tactical sequence starting on Qxe3")
        self.assertIn("tactical sequence", matching[0].description.lower())

    def test_should_match_when_black_forcing_sequence_improves_eval(self):
        # Black captures on move 20; White's reply is on move 21 (next MoveData row).
        moves = moves_from_pgn(
            "Ke3 Nxf3 Kxf3 Ke7 Ke2 Kd7",
            starting_fen=_BLACK_START,
            analysis={
                20: {
                    "white": {"cpl": "20", "eval": "+0.20"},
                    "black": {"cpl": "5", "eval": "-0.50"},
                },
                21: {
                    "white": {"cpl": "15", "eval": "-1.20"},
                    "black": {"cpl": "20", "eval": "-1.50"},
                },
                22: {
                    "white": {"cpl": "20", "eval": "-2.00"},
                    "black": {"cpl": "25", "eval": "-2.30"},
                },
            },
        )
        highlights = evaluate_rule(TacticalSequenceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="tactical_sequence", side="black"
        )
        self.assertTrue(
            matching,
            "Expected Black tactical sequence whose reply starts on the next MoveData row",
        )
        self.assertFalse(matching[0].is_white)

    def test_should_not_match_when_follow_up_is_not_forcing(self):
        moves = moves_from_pgn(
            "h3 Ke7 Qxe3 Kd8 Kd2 Kc8",
            starting_fen=_WHITE_START,
            analysis={
                20: {"black": {"cpl": "5", "eval": "+0.20"}},
                21: {
                    "white": {"cpl": "5", "eval": "+3.20"},
                    "black": {"cpl": "5", "eval": "+3.10"},
                },
                22: {
                    "white": {"cpl": "80", "eval": "+3.00"},
                    "black": {"cpl": "80", "eval": "+2.90"},
                },
            },
        )
        highlights = evaluate_rule(TacticalSequenceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="tactical_sequence", side="white"
        )
        self.assertFalse(
            matching,
            "Without a near-best continuation pair this should not be a tactical sequence",
        )


if __name__ == "__main__":
    unittest.main()
