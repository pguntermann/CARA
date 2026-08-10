"""Unit tests for ExchangeSequenceRule."""

import unittest

from app.services.game_highlights.rules.exchange_sequence_rule import ExchangeSequenceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_ROOKS_WHITE_STARTS = "4k3/4r3/8/4r3/4R3/8/7P/4K3 w - - 0 20"
_ROOKS_BLACK_STARTS = "4k3/7r/8/r7/R7/8/7P/R3K3 w - - 0 20"


class TestExchangeSequenceRule(unittest.TestCase):
    """Exchange sequence: mutual rook/queen trade started by either side."""

    def test_should_match_when_white_starts_rook_trade_on_same_move(self):
        moves = moves_from_pgn("h3 Kd8 Rxe5 Rxe5", starting_fen=_ROOKS_WHITE_STARTS)
        highlights = evaluate_rule(ExchangeSequenceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="exchange_sequence", side="white"
        )
        self.assertTrue(matching, "Expected rook exchange started by White")
        self.assertTrue(matching[0].is_white)

    def test_should_match_when_black_starts_rook_trade_across_moves(self):
        moves = moves_from_pgn("h3 Rxa4 Rxa4", starting_fen=_ROOKS_BLACK_STARTS)
        highlights = evaluate_rule(ExchangeSequenceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="exchange_sequence", side="black"
        )
        self.assertTrue(matching, "Expected rook exchange started by Black")
        self.assertFalse(matching[0].is_white)

    def test_should_not_match_when_only_one_side_captures_a_rook(self):
        moves = moves_from_pgn("h3 Kd8 Rxe5 Re6", starting_fen=_ROOKS_WHITE_STARTS)
        highlights = evaluate_rule(ExchangeSequenceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights, move_number=21, rule_type="exchange_sequence"
        )
        self.assertFalse(
            matching,
            "A one-sided rook capture should not count as an exchange sequence",
        )


if __name__ == "__main__":
    unittest.main()
