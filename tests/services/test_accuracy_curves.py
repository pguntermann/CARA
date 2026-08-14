"""Tests for game-summary running accuracy curves."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, List, Optional

from app.services.game_summary_service import GameSummaryService


def _move(
    number: int,
    *,
    white: str = "",
    black: str = "",
    assess_white: str = "",
    assess_black: str = "",
    cpl_white: Optional[str] = None,
    cpl_black: Optional[str] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        move_number=number,
        white_move=white,
        black_move=black,
        assess_white=assess_white,
        assess_black=assess_black,
        cpl_white=cpl_white,
        cpl_black=cpl_black,
        white_is_top3=False,
        black_is_top3=False,
    )


class AccuracyCurveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GameSummaryService(
            {
                "game_analysis": {
                    "accuracy_formula": {
                        "formula": "max(5.0, min(100.0, 100.0 - (average_cpl / 3.5)))",
                    }
                },
                "ui": {"panels": {"detail": {"summary": {}}}},
            }
        )

    def test_curves_use_ply_indices_and_drop_after_blunder(self) -> None:
        moves: List[Any] = [
            _move(1, white="e4", black="e5", assess_white="Best Move", assess_black="Best Move", cpl_white="0", cpl_black="0"),
            _move(2, white="Nf3", black="Nc6", assess_white="Best Move", assess_black="Best Move", cpl_white="5", cpl_black="5"),
            _move(
                3,
                white="Bb5",
                black="a6",
                assess_white="Best Move",
                assess_black="Blunder",
                cpl_white="0",
                cpl_black="350",
            ),
        ]
        white_curve, black_curve = self.service._extract_accuracy_curves(moves)

        self.assertEqual([ply for ply, _ in white_curve], [1, 3, 5])
        self.assertEqual([ply for ply, _ in black_curve], [2, 4, 6])

        # Early best-play accuracy stays high; black drops after the blunder.
        self.assertGreater(white_curve[-1][1], 90.0)
        self.assertLess(black_curve[-1][1], black_curve[1][1])
        self.assertLess(black_curve[-1][1], 80.0)

    def test_empty_moves_yield_empty_curves(self) -> None:
        white_curve, black_curve = self.service._extract_accuracy_curves([])
        self.assertEqual(white_curve, [])
        self.assertEqual(black_curve, [])

    def test_book_moves_keep_high_early_accuracy(self) -> None:
        moves = [
            _move(1, white="e4", black="c5", assess_white="Book Move", assess_black="Book Move"),
            _move(2, white="Nf3", black="d6", assess_white="Book Move", assess_black="Book Move"),
        ]
        white_curve, black_curve = self.service._extract_accuracy_curves(moves)
        self.assertEqual(white_curve[-1][1], 100.0)
        self.assertEqual(black_curve[-1][1], 100.0)


if __name__ == "__main__":
    unittest.main()
