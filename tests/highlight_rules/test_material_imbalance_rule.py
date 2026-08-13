"""Unit tests for MaterialImbalanceRule."""

import unittest

from app.services.game_highlights.rules.material_imbalance_rule import MaterialImbalanceRule
from tests.highlight_rules.helpers import (
    evaluate_rule,
    find_highlights,
    moves_from_pgn,
)

_ROOK_FEN = "4k3/8/8/3n4/8/1b6/3R4/4K3 w - - 0 19"


class TestMaterialImbalanceRule(unittest.TestCase):
    """Unusual trades: rook for minor, or minor credited against multiple pawns."""

    def test_should_match_when_rook_takes_minor_and_is_recaptured(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Rxd5 Bxd5",
            starting_fen=_ROOK_FEN,
            analysis={20: {"white": {"assess": "Inaccuracy", "cpl": "40"}}},
        )
        highlights = evaluate_rule(MaterialImbalanceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="material_imbalance", side="white"
        )
        self.assertTrue(matching, "Expected rook-for-minor imbalance on 20. Rxd5")
        self.assertIn("rook", matching[0].description.lower())

    def test_should_not_match_rook_trade_when_assessed_best_move(self):
        moves = moves_from_pgn(
            "Ke2 Ke7 Rxd5 Bxd5",
            starting_fen=_ROOK_FEN,
            analysis={20: {"white": {"assess": "Best Move", "cpl": "0"}}},
        )
        highlights = evaluate_rule(MaterialImbalanceRule({}), moves, move_number=20)
        matching = find_highlights(
            highlights, move_number=20, rule_type="material_imbalance", side="white"
        )
        self.assertFalse(
            matching,
            "A best-move exchange should not be flagged as a material imbalance",
        )


if __name__ == "__main__":
    unittest.main()
