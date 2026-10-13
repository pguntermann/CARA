"""Evaluation display string formatting."""

import unittest

from app.models.evaluation_model import EvaluationModel, format_evaluation_display


class TestFormatEvaluationDisplay(unittest.TestCase):
    def test_positive_pawns(self) -> None:
        self.assertEqual(format_evaluation_display(123, False, 0, decimals=2), "+1.23")

    def test_negative_pawns(self) -> None:
        self.assertEqual(format_evaluation_display(-75, False, 0, decimals=2), "-0.75")

    def test_mate_white(self) -> None:
        self.assertEqual(format_evaluation_display(0, True, 3), "M3")

    def test_mate_black(self) -> None:
        self.assertEqual(format_evaluation_display(0, True, -2), "-M2")

    def test_mate_zero_from_sign(self) -> None:
        self.assertEqual(format_evaluation_display(100, True, 0), "M0")
        self.assertEqual(format_evaluation_display(-100, True, 0), "-M0")

    def test_model_format_display(self) -> None:
        model = EvaluationModel()
        model.centipawns = 250
        self.assertEqual(model.format_display(decimals=2), "+2.50")


if __name__ == "__main__":
    unittest.main()
