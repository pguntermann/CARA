"""Unit tests for DelayedMatingRule."""

import unittest

from app.services.game_highlights.rules.delayed_mating_rule import DelayedMatingRule
from tests.highlight_rules.helpers import (
    evaluate_rule_sequence,
    find_highlights,
    moves_from_pgn,
)

_KINGS = "4k3/8/8/8/8/8/8/4K3 w - - 0 20"


class TestDelayedMatingRule(unittest.TestCase):
    """Delayed mating: consecutive missed mates within mate-in 5."""

    def test_should_match_when_mate_is_missed_twice_in_a_row(self):
        moves = moves_from_pgn(
            "Kd2 Kd7 Kd1 Kd8",
            starting_fen=_KINGS,
            analysis={
                20: {
                    "white": {
                        "cpl": "100",
                        "best": "Qh7#",
                        "eval": "M1",
                        "assess": "Mistake",
                    },
                    "black": {"cpl": "20"},
                },
                21: {
                    "white": {
                        "cpl": "120",
                        "best": "Qh8#",
                        "eval": "M2",
                        "assess": "Mistake",
                    },
                    "black": {"cpl": "20"},
                },
            },
        )
        highlights = evaluate_rule_sequence(DelayedMatingRule({}), moves)

        misses = [
            h
            for h in highlights
            if h.rule_type == "delayed_mating" and "missed a checkmate" in h.description
        ]
        delayed = [
            h
            for h in highlights
            if h.rule_type == "delayed_mating" and "delayed mating" in h.description.lower()
        ]
        self.assertGreaterEqual(len(misses), 2, "Expected two individual missed-mate highlights")
        self.assertTrue(delayed, "Expected a delayed-mating highlight after two consecutive misses")
        self.assertEqual(delayed[0].move_number, 20)
        self.assertEqual(delayed[0].move_number_end, 21)
        self.assertTrue(delayed[0].is_white)

    def test_should_not_match_when_the_mating_move_is_played_after_one_miss(self):
        moves = moves_from_pgn(
            "Kd2 Kd7 Kd1 Kd8",
            starting_fen=_KINGS,
            analysis={
                20: {
                    "white": {
                        "cpl": "100",
                        "best": "Qh7#",
                        "eval": "M1",
                        "assess": "Mistake",
                    },
                    "black": {"cpl": "20"},
                },
                21: {
                    "white": {
                        "cpl": "0",
                        "best": "Kd1",
                        "eval": "M1",
                        "assess": "Best Move",
                    },
                    "black": {"cpl": "20"},
                },
            },
        )
        highlights = evaluate_rule_sequence(DelayedMatingRule({}), moves)
        delayed = [
            h
            for h in highlights
            if h.rule_type == "delayed_mating" and "delayed mating" in h.description.lower()
        ]
        self.assertFalse(
            delayed,
            "Playing the mating continuation after one miss should not create delayed mating",
        )
        misses = find_highlights(
            highlights, move_number=20, rule_type="delayed_mating", side="white"
        )
        self.assertTrue(
            any("missed a checkmate" in h.description for h in misses),
            "A single miss should still produce an individual missed-mate highlight",
        )


if __name__ == "__main__":
    unittest.main()
