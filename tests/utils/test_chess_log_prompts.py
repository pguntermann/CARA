"""Tests for the canonical 3x3 Why-question prompt strings."""

import unittest

from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS


class TestThreeByThreePrompts(unittest.TestCase):
    def test_has_four_keys(self):
        self.assertEqual(list(THREE_BY_THREE_PROMPTS.keys()), ["Why1", "Why2", "Why3", "Why4"])

    def test_why1_verbatim(self):
        self.assertEqual(THREE_BY_THREE_PROMPTS["Why1"], "Why did I choose that move?")

    def test_why2_verbatim(self):
        self.assertEqual(THREE_BY_THREE_PROMPTS["Why2"], "Why is my move not ideal?")

    def test_why3_verbatim(self):
        self.assertEqual(
            THREE_BY_THREE_PROMPTS["Why3"],
            "Why is the better move better than my chosen move?",
        )

    def test_why4_verbatim(self):
        self.assertEqual(
            THREE_BY_THREE_PROMPTS["Why4"],
            "What do I do in the future so this doesn't happen again?",
        )


if __name__ == "__main__":
    unittest.main()
