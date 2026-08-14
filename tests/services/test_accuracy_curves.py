"""Tests for game-summary running accuracy curves and opening X compression."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, List, Optional

from app.services.game_summary_service import (
    AccuracyProgressXScale,
    GameSummaryService,
    ply_to_fullmove,
)


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

    def test_book_moves_are_omitted_from_plotted_series(self) -> None:
        moves = [
            _move(1, white="e4", black="c5", assess_white="Book Move", assess_black="Book Move"),
            _move(2, white="Nf3", black="d6", assess_white="Book Move", assess_black="Book Move"),
            _move(
                3,
                white="d4",
                black="cxd4",
                assess_white="Best Move",
                assess_black="Best Move",
                cpl_white="10",
                cpl_black="12",
            ),
        ]
        white_curve, black_curve = self.service._extract_accuracy_curves(moves)
        self.assertEqual([ply for ply, _ in white_curve], [5])
        self.assertEqual([ply for ply, _ in black_curve], [6])
        self.assertGreater(white_curve[0][1], 90.0)


class AccuracyProgressXScaleTests(unittest.TestCase):
    def test_no_compression_when_first_scored_early(self) -> None:
        scale = AccuracyProgressXScale.from_move_numbers([1, 2, 10])
        self.assertFalse(scale.is_compressed)
        self.assertEqual(scale.plot_x(1), 1.0)
        self.assertEqual(scale.plot_x(10), 10.0)

    def test_compresses_opening_strip(self) -> None:
        # First scored at 6 with override width 0.28 → bookEnd 5
        scale = AccuracyProgressXScale.from_move_numbers(
            [6, 7, 8, 9, 10], compressed_units=0.28
        )
        self.assertTrue(scale.is_compressed)
        self.assertEqual(scale.book_end_move, 5)
        self.assertAlmostEqual(scale.plot_x(0), 0.0)
        self.assertAlmostEqual(scale.plot_x(5), 0.28)
        self.assertAlmostEqual(scale.plot_x(6), 1.28)
        self.assertAlmostEqual(scale.plot_x(10), 5.28)

    def test_default_units_clamped(self) -> None:
        units = AccuracyProgressXScale.default_compressed_units(8, 54)
        self.assertGreaterEqual(units, 1.2)
        self.assertLessEqual(units, 4.0)
        self.assertAlmostEqual(units, min(4.0, max(1.2, (54 - 8) * 0.12)))

    def test_axis_marks_include_compressed_label(self) -> None:
        scale = AccuracyProgressXScale.from_move_numbers([8, 20, 40, 54])
        marks = scale.axis_marks([8, 20, 40, 54], desired_count=4)
        self.assertEqual(marks[0][1], "0...7")
        self.assertAlmostEqual(marks[0][0], scale.compressed_units * 0.5)

    def test_ply_to_fullmove(self) -> None:
        self.assertEqual(ply_to_fullmove(1), 1)
        self.assertEqual(ply_to_fullmove(2), 1)
        self.assertEqual(ply_to_fullmove(3), 2)
        self.assertEqual(ply_to_fullmove(4), 2)


if __name__ == "__main__":
    unittest.main()
