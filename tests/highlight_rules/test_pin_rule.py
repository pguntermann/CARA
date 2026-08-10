"""Unit tests for PinRule."""

import unittest

from app.services.game_highlights.rules.pin_rule import PinRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestPinRule(unittest.TestCase):
    """Pin: slider creates a new, meaningful pin of a minor/major to something heavier."""

    def test_should_match_when_bishop_pins_knight_to_king(self):
        # Bishop leaves c4 for b5, creating a new pin of Nc6 to Ke8.
        moves = moves_from_pgn(
            "Kd2 h6 Bb5",
            starting_fen="4k3/7p/2n5/8/2B5/8/8/4K3 w - - 0 9",
        )
        highlights = evaluate_rule(PinRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="pin", side="white"
        )
        self.assertTrue(matching, "Expected pin on 10. Bb5")
        self.assertIn("pin", matching[0].description.lower())

    def test_should_not_match_when_only_a_pawn_is_pinned(self):
        # Same geometry, but the front unit is a pawn (< 300cp) — not a meaningful pin.
        moves = moves_from_pgn(
            "Kd2 h6 Bb5",
            starting_fen="4k3/7p/2p5/8/2B5/8/8/4K3 w - - 0 9",
        )
        highlights = evaluate_rule(PinRule({}), moves, move_number=10)
        matching = find_highlights(
            highlights, move_number=10, rule_type="pin", side="white"
        )
        self.assertFalse(
            matching,
            "Pinning a pawn to the king should not count as a meaningful pin",
        )


if __name__ == "__main__":
    unittest.main()
