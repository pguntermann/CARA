"""Tests for miniature board arrow helpers."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.miniature_board_arrows import (
    CHESS_LOG_BEST_ALTERNATIVE,
    CHESS_LOG_PLAYED,
    GAME_SUMMARY_BEST_ALTERNATIVE,
    GAME_SUMMARY_PLAYED,
    default_miniature_board_arrows,
    normalize_miniature_board_arrows,
)


class TestChessLogArrows(unittest.TestCase):
    def test_chess_log_played_default_true(self):
        arrows = default_miniature_board_arrows()
        self.assertTrue(arrows[CHESS_LOG_PLAYED])

    def test_chess_log_best_default_true(self):
        arrows = default_miniature_board_arrows()
        self.assertTrue(arrows[CHESS_LOG_BEST_ALTERNATIVE])

    def test_missing_chess_log_keys_yield_defaults(self):
        arrows = normalize_miniature_board_arrows({})
        self.assertTrue(arrows[CHESS_LOG_PLAYED])
        self.assertTrue(arrows[CHESS_LOG_BEST_ALTERNATIVE])

    def test_chess_log_played_can_be_set_false(self):
        arrows = normalize_miniature_board_arrows({CHESS_LOG_PLAYED: False})
        self.assertFalse(arrows[CHESS_LOG_PLAYED])

    def test_chess_log_best_can_be_set_false(self):
        arrows = normalize_miniature_board_arrows({CHESS_LOG_BEST_ALTERNATIVE: False})
        self.assertFalse(arrows[CHESS_LOG_BEST_ALTERNATIVE])

    def test_other_keys_unaffected(self):
        arrows = normalize_miniature_board_arrows({
            CHESS_LOG_PLAYED: False,
            CHESS_LOG_BEST_ALTERNATIVE: False,
        })
        self.assertTrue(arrows[GAME_SUMMARY_PLAYED])
        self.assertTrue(arrows[GAME_SUMMARY_BEST_ALTERNATIVE])


if __name__ == "__main__":
    unittest.main()
