"""Tests for miniature board scale helpers."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.miniature_board_scales import (
    MANUAL_ANALYSIS,
    OPENING_EXPLORER,
    default_miniature_board_scales,
    get_miniature_board_scale_from_settings,
    normalize_miniature_board_scales,
)


class TestMiniatureBoardScales(unittest.TestCase):
    def test_defaults(self) -> None:
        scales = default_miniature_board_scales()
        self.assertEqual(scales[MANUAL_ANALYSIS], 1.25)
        self.assertEqual(scales[OPENING_EXPLORER], 1.0)

    def test_snap_to_preset(self) -> None:
        scales = normalize_miniature_board_scales({"opening_explorer": 1.3})
        self.assertEqual(scales[OPENING_EXPLORER], 1.25)

    def test_settings_reader_uses_miniature_boards(self) -> None:
        settings = {
            "miniature_boards": {"manual_analysis": 1.0},
        }
        self.assertEqual(
            get_miniature_board_scale_from_settings(settings, MANUAL_ANALYSIS), 1.0
        )


if __name__ == "__main__":
    unittest.main()
