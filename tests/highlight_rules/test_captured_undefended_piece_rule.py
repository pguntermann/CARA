"""Unit tests for CapturedUndefendedPieceRule."""

import unittest

from app.services.game_highlights.rules.captured_undefended_piece_rule import (
    CapturedUndefendedPieceRule,
)
from app.services.game_highlights.rules.tactical_resource_rule import TacticalResourceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

# Queen on h6 can take a hanging knight on e3.
_HANGING_KNIGHT = "4k3/8/7Q/8/8/4n3/7P/4K3 w - - 0 20"

# After 28.Rd7, Black to move (user example path to 29.Rxa7).
_BEFORE_KG8 = "8/p2R1p1k/4p3/4p1p1/8/1P2P1Pb/4BP1P/6K1 b - - 2 28"


class TestCapturedUndefendedPieceRule(unittest.TestCase):
    """Captured undefended: take a unit with no defenders."""

    def test_should_match_when_taking_hanging_knight(self):
        moves = moves_from_pgn(
            "h3 Ke7 Qxe3 Kd8",
            starting_fen=_HANGING_KNIGHT,
            analysis={
                20: {"black": {"cpl": "40"}},
                21: {"white": {"cpl": "5"}, "black": {"cpl": "30"}},
            },
        )
        highlights = evaluate_rule(CapturedUndefendedPieceRule({}), moves, move_number=21)
        matching = find_highlights(
            highlights,
            move_number=21,
            rule_type="captured_undefended_piece",
            side="white",
        )
        self.assertTrue(matching, "Expected undefended knight capture on Qxe3")
        self.assertIn("undefended knight", matching[0].description.lower())

    def test_should_match_rxa7_hanging_pawn(self):
        moves = moves_from_pgn(
            "Kg8 Rxa7 f5",
            starting_fen=_BEFORE_KG8,
            analysis={
                28: {"black": {"cpl": "38"}},
                29: {"white": {"cpl": "0", "eval": "+8.8"}, "black": {"cpl": "50"}},
            },
        )
        highlights = evaluate_rule(CapturedUndefendedPieceRule({}), moves, move_number=29)
        matching = find_highlights(
            highlights,
            move_number=29,
            rule_type="captured_undefended_piece",
            side="white",
        )
        self.assertTrue(matching, "Expected undefended pawn capture on 29.Rxa7")
        self.assertIn("undefended pawn", matching[0].description.lower())

    def test_tactical_resource_should_not_match_rxa7(self):
        moves = moves_from_pgn(
            "Kg8 Rxa7 f5",
            starting_fen=_BEFORE_KG8,
            analysis={
                28: {"black": {"cpl": "38"}},
                29: {"white": {"cpl": "0", "eval": "+8.8"}, "black": {"cpl": "50"}},
            },
        )
        highlights = evaluate_rule(TacticalResourceRule({}), moves, move_number=29)
        matching = find_highlights(
            highlights, move_number=29, rule_type="tactical_resource", side="white"
        )
        self.assertFalse(
            matching,
            "Rxa7 is a plain undefended capture, not a tactical resource",
        )

    def test_should_not_match_when_target_is_defended(self):
        # d5 is defended by e6; include a prior ply so fen_before is available.
        moves = moves_from_pgn(
            "Kd7 Rxd5 Kc6",
            starting_fen="4k3/8/4p3/3p4/8/8/3R3P/4K3 b - - 0 19",
            analysis={
                19: {"black": {"cpl": "20"}},
                20: {"white": {"cpl": "5"}, "black": {"cpl": "20"}},
            },
        )
        highlights = evaluate_rule(CapturedUndefendedPieceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="captured_undefended_piece"
        )
        self.assertFalse(
            matching,
            "Capturing a pawn-defended unit should not count as undefended",
        )


if __name__ == "__main__":
    unittest.main()
