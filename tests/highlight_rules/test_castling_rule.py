"""Unit tests for CastlingRule."""

import unittest

from app.services.game_highlights.rules.castling_rule import CastlingRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestCastlingRule(unittest.TestCase):
    """Castling: SAN is O-O / O-O-O and the matching castling right is lost."""

    def test_should_match_when_white_castles_kingside(self):
        # Need a prior full move so white's half-move has fen_before (prev.fen_black).
        moves = moves_from_pgn("e4 e5 Nf3 Nc6 Bc4 Bc5 O-O")
        highlights = evaluate_rule(CastlingRule({}), moves, move_number=4)
        matching = find_highlights(
            highlights, move_number=4, rule_type="castling", side="white"
        )
        self.assertTrue(matching, "Expected castling highlight on 4. O-O")
        self.assertIn("kingside", matching[0].description.lower())

    def test_should_not_match_when_move_is_not_castling(self):
        moves = moves_from_pgn("e4 e5 Nf3 Nc6 Bc4 Bc5 h3")
        highlights = evaluate_rule(CastlingRule({}), moves, move_number=4)
        matching = find_highlights(
            highlights, move_number=4, rule_type="castling", side="white"
        )
        self.assertFalse(matching, "Non-castling move should not match castling rule")


if __name__ == "__main__":
    unittest.main()
