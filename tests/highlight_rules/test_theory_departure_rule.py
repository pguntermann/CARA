"""Unit tests for TheoryDepartureRule."""

import unittest

from app.services.game_highlights.rules.theory_departure_rule import TheoryDepartureRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestTheoryDepartureRule(unittest.TestCase):
    """Theory departure: first non-best move after the book phase."""

    def test_should_match_when_white_first_leaves_theory(self):
        moves = moves_from_pgn(
            "e4 e5 Nf3 Nc6",
            analysis={
                1: {
                    "white": {"assess": "Book Move"},
                    "black": {"assess": "Book Move"},
                },
                2: {
                    "white": {"assess": "Good Move"},
                    "black": {"assess": "Best Move"},
                },
            },
        )
        highlights = evaluate_rule(
            TheoryDepartureRule({}),
            moves,
            move_number=2,
            theory_departed=False,
            last_book_move_number=1,
        )
        matching = find_highlights(
            highlights, move_number=2, rule_type="theory_departure", side="white"
        )
        self.assertTrue(matching, "Expected theory departure on 2. Nf3")
        self.assertIn("leave theory", matching[0].description.lower())

    def test_should_not_match_when_theory_already_departed(self):
        moves = moves_from_pgn(
            "e4 e5 Nf3 Nc6",
            analysis={
                2: {
                    "white": {"assess": "Good Move"},
                    "black": {"assess": "Best Move"},
                },
            },
        )
        highlights = evaluate_rule(
            TheoryDepartureRule({}),
            moves,
            move_number=2,
            theory_departed=True,
            last_book_move_number=1,
        )
        matching = find_highlights(
            highlights, move_number=2, rule_type="theory_departure"
        )
        self.assertFalse(
            matching,
            "Theory departure should fire only once (theory_departed already set)",
        )

    def test_should_not_match_in_the_endgame(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Kd3",
            starting_fen="4k3/8/8/8/8/8/8/4K3 w - - 0 40",
            analysis={
                41: {
                    "white": {"assess": "Good Move"},
                    "black": {"assess": "Best Move"},
                },
            },
        )
        highlights = evaluate_rule(
            TheoryDepartureRule({}),
            moves,
            move_number=41,
            theory_departed=False,
            last_book_move_number=0,
            middlegame_end=40,
        )
        matching = find_highlights(
            highlights, move_number=41, rule_type="theory_departure"
        )
        self.assertFalse(
            matching,
            "Theory departure should not fire once the endgame has begun",
        )


if __name__ == "__main__":
    unittest.main()
