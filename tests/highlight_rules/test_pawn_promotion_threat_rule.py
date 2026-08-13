"""Unit tests for PawnPromotionThreatRule."""

import unittest

from app.services.game_highlights.rules.pawn_promotion_threat_rule import (
    PawnPromotionThreatRule,
)
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)


class TestPawnPromotionThreatRule(unittest.TestCase):
    """Promotion threat: the moved pawn newly reaches 6th/7th (or 2nd/1st) and is supported."""

    def test_should_match_when_supported_pawn_reaches_sixth_rank(self):
        # e5→e6 with d5 supporting; need a prior ply for fen_before.
        moves = moves_from_pgn(
            "Kd2 Kd7 e6",
            starting_fen="4k3/8/8/3PP3/8/8/8/4K3 w - - 0 30",
        )
        highlights = evaluate_rule(PawnPromotionThreatRule({}), moves, move_number=31)
        matching = find_highlights(
            highlights, move_number=31, rule_type="pawn_promotion_threat", side="white"
        )
        self.assertTrue(matching, "Expected promotion threat on 31. e6")
        self.assertIn("promotion", matching[0].description.lower())

    def test_should_not_match_when_advanced_pawn_is_unsupported(self):
        moves = moves_from_pgn(
            "Kd2 Kd7 e6",
            starting_fen="4k3/8/8/4P3/8/8/8/4K3 w - - 0 30",
        )
        highlights = evaluate_rule(PawnPromotionThreatRule({}), moves, move_number=31)
        matching = find_highlights(
            highlights, move_number=31, rule_type="pawn_promotion_threat", side="white"
        )
        self.assertFalse(matching, "Unsupported e6 should not count as a promotion threat")

    def test_should_not_match_when_another_pawn_was_already_advanced(self):
        # e6 already on the 6th; e4xf5 only lands on the 5th. Must not credit e6.
        moves = moves_from_pgn(
            "Kd2 Kf8 exf5",
            starting_fen="4k3/8/4P3/3B1n2/4P3/8/8/4K3 w - - 0 30",
        )
        highlights = evaluate_rule(PawnPromotionThreatRule({}), moves, move_number=31)
        matching = find_highlights(
            highlights, move_number=31, rule_type="pawn_promotion_threat", side="white"
        )
        self.assertFalse(
            matching,
            "Capturing on the 5th while another pawn sits on the 6th is not a new promotion threat",
        )

    def test_should_not_match_when_forward_path_is_blocked(self):
        # e5→e6 is supported by d5, but a black knight on e7 blocks the path.
        moves = moves_from_pgn(
            "Kd2 Kd8 e6",
            starting_fen="4k3/4n3/8/3PP3/8/8/8/4K3 w - - 0 30",
        )
        highlights = evaluate_rule(PawnPromotionThreatRule({}), moves, move_number=31)
        matching = find_highlights(
            highlights, move_number=31, rule_type="pawn_promotion_threat", side="white"
        )
        self.assertFalse(
            matching,
            "A supported advance should not count when the queening path is blocked",
        )

    def test_should_not_match_when_pawn_actually_promotes(self):
        # Pawn already on the 7th; d8=Q is the promotion, not a threat.
        moves = moves_from_pgn(
            "Ke2 Kf8 d8=Q",
            starting_fen="4k3/3P4/8/8/8/8/8/4K3 w - - 0 39",
        )
        highlights = evaluate_rule(PawnPromotionThreatRule({}), moves, move_number=40)
        matching = find_highlights(
            highlights, move_number=40, rule_type="pawn_promotion_threat", side="white"
        )
        self.assertFalse(
            matching,
            "Promoting with d8=Q should not be labeled a promotion threat",
        )


if __name__ == "__main__":
    unittest.main()
