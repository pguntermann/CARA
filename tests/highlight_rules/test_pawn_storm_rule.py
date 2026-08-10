"""Unit tests for PawnStormRule."""

import unittest

from app.services.game_highlights.rules.pawn_storm_rule import PawnStormRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_FEN = "4k3/8/8/5PP1/8/8/8/4K3 w - - 0 19"
_ENDGAME_FEN = "4k3/8/8/5PP1/8/8/8/4K3 w - - 0 40"


class TestPawnStormRule(unittest.TestCase):
    """Coordinated flank pawn advances in the middlegame or endgame."""

    def test_should_match_when_adjacent_flank_pawns_advance_together(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 f6 Ke8 g6",
            starting_fen=_FEN,
        )
        highlights = evaluate_rule(PawnStormRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="pawn_storm", side="white"
        )
        self.assertTrue(matching, "Expected kingside pawn storm completing on 21. g6")
        self.assertIn("pawn storm", matching[0].description.lower())

    def test_should_match_in_the_endgame(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 f6 Ke8 g6",
            starting_fen=_ENDGAME_FEN,
        )
        highlights = evaluate_rule(PawnStormRule({}), moves, move_number=42)
        matching = find_highlights(
            highlights, move_number=42, rule_type="pawn_storm", side="white"
        )
        self.assertTrue(matching, "Expected kingside pawn storm in the endgame on 42. g6")

    def test_should_not_match_when_only_one_file_advances(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 f6 Ke8 f7",
            starting_fen=_FEN,
        )
        highlights = evaluate_rule(PawnStormRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="pawn_storm", side="white"
        )
        self.assertFalse(
            matching,
            "A single-file pawn advance should not count as a pawn storm",
        )


if __name__ == "__main__":
    unittest.main()
