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
        self.assertGreaterEqual(units, 0.55)
        self.assertLessEqual(units, 1.0)
        self.assertAlmostEqual(units, min(1.0, max(0.55, (54 - 8) * 0.045)))

    def test_default_units_more_compressed_than_one_move(self) -> None:
        # Short book + typical game: strip must stay clearly narrower than two move-units.
        units = AccuracyProgressXScale.default_compressed_units(4, 40)
        self.assertLessEqual(units, 1.0)
        self.assertGreaterEqual(units, 0.55)

    def test_axis_marks_include_compressed_label(self) -> None:
        scale = AccuracyProgressXScale.from_move_numbers([8, 20, 40, 54])
        marks = scale.axis_marks([8, 20, 40, 54], desired_count=4)
        self.assertEqual(marks[0][1], "0...7")
        self.assertAlmostEqual(marks[0][0], scale.compressed_units * 0.5)

    def test_sample_move_numbers_even_step_no_irregular_gaps(self) -> None:
        # Old round-based sampling produced irregular single-move skips (e.g. 11,13,14…).
        moves = AccuracyProgressXScale._sample_move_numbers(10, 38, desired_count=24)
        self.assertEqual(moves[0], 10)
        self.assertEqual(moves[-1], 38)
        gaps = [b - a for a, b in zip(moves, moves[1:])]
        # All intermediate gaps share one step; final gap may be shorter to reach hi.
        if len(gaps) >= 2:
            self.assertTrue(all(g == gaps[0] for g in gaps[:-1]))
            self.assertLessEqual(gaps[-1], gaps[0])

    def test_sample_move_numbers_uses_nice_step_when_sparse(self) -> None:
        moves = AccuracyProgressXScale._sample_move_numbers(10, 54, desired_count=8)
        self.assertEqual(moves[0], 10)
        self.assertEqual(moves[-1], 54)
        # Prefer readable multiples (5/10/…) rather than jagged integers.
        self.assertEqual(moves[:-1], [10, 20, 30, 40])
        gaps = [b - a for a, b in zip(moves, moves[1:-1])]
        self.assertTrue(gaps and all(g == gaps[0] for g in gaps))

    def test_sample_move_numbers_dense_when_width_allows(self) -> None:
        moves = AccuracyProgressXScale._sample_move_numbers(10, 15, desired_count=20)
        self.assertEqual(moves, [10, 11, 12, 13, 14, 15])

    def test_axis_marks_keep_compressed_opening_intact(self) -> None:
        scale = AccuracyProgressXScale.from_move_numbers(
            list(range(10, 39)), compressed_units=2.0
        )
        marks = scale.axis_marks(list(range(10, 39)), desired_count=12)
        self.assertEqual(marks[0][1], "0...9")
        numeric = [int(label) for _, label in marks[1:]]
        self.assertEqual(numeric[0], 10)
        self.assertEqual(numeric[-1], 38)
        gaps = [b - a for a, b in zip(numeric, numeric[1:])]
        if len(gaps) >= 2:
            self.assertTrue(all(g == gaps[0] for g in gaps[:-1]))

    def test_filter_overlapping_skips_first_scored_beside_compressed_label(self) -> None:
        # Mimic a narrow compressed strip: "0...10" centered at 0.5, "11" at ~1.5.
        marks = [(0.5, "0...10"), (1.5, "11"), (5.0, "15"), (10.0, "20")]
        # 10 px per plot unit; "0...10" ~36px wide, "11" ~12px → collision.
        filtered = AccuracyProgressXScale.filter_overlapping_axis_marks(
            marks,
            x_to_pixel=lambda x: float(x) * 10.0,
            text_width=lambda label: 36.0 if label.startswith("0...") else 12.0,
            min_gap_px=6.0,
        )
        labels = [label for _, label in filtered]
        self.assertEqual(labels[0], "0...10")
        self.assertNotIn("11", labels)
        self.assertIn("15", labels)
        self.assertIn("20", labels)

    def test_ply_to_fullmove(self) -> None:
        self.assertEqual(ply_to_fullmove(1), 1)
        self.assertEqual(ply_to_fullmove(2), 1)
        self.assertEqual(ply_to_fullmove(3), 2)
        self.assertEqual(ply_to_fullmove(4), 2)


if __name__ == "__main__":
    unittest.main()
