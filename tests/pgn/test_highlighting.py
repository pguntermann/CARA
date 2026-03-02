"""Test script for PGN highlighting functionality.

Tests that move highlighting works correctly when variations, annotations,
and results are filtered out. Uses a single shared DetailPgnView so all tests
run in sequence without Qt lifecycle issues. Skipped in CI (no display).
"""

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
from app.services.pgn_formatter_service import PgnFormatterService
from app.config.config_loader import ConfigLoader
from app.views.detail_pgn_view import DetailPgnView
from PyQt6.QtWidgets import QApplication


def _run_highlighting_test(view, config, pgn_text: str,
                           filter_variations: bool = False,
                           filter_annotations: bool = False,
                           filter_results: bool = False,
                           active_move_ply: int = 1) -> tuple:
    """Run one highlighting test using the shared view. Returns (success: bool, error_message: str or None)."""
    view._show_variations = not filter_variations
    view._show_annotations = not filter_annotations
    view._show_results = not filter_results

    pgn_text_to_format = pgn_text
    if filter_variations:
        pgn_text_to_format = PgnFormatterService._remove_variations(pgn_text_to_format)
    if filter_annotations:
        pgn_text_to_format = PgnFormatterService._remove_annotations(pgn_text_to_format)
    if filter_results:
        pgn_text_to_format = PgnFormatterService._remove_results(pgn_text_to_format)

    try:
        formatted_html, move_info = PgnFormatterService.format_pgn_to_html(
            pgn_text_to_format, config, 0
        )
        view.set_pgn_text(pgn_text)
        view._active_move_ply = active_move_ply
        app = QApplication.instance()
        app.processEvents()

        if not view._move_info:
            return False, "_move_info is empty"
        if active_move_ply > len(view._move_info):
            return False, f"active_move_ply ({active_move_ply}) > move_info length ({len(view._move_info)})"

        target_move_san, target_move_number, target_is_white = view._move_info[active_move_ply - 1]
        move_san_clean = re.sub(r'[!?]{1,2}$', '', target_move_san)
        if target_is_white:
            pattern = rf'\b{re.escape(str(target_move_number))}\.\s+{re.escape(move_san_clean)}(?:[!?]{{1,2}})?'
        else:
            pattern = rf'\b{re.escape(move_san_clean)}(?:[!?]{{1,2}})?'

        if not re.search(pattern, formatted_html):
            return False, f"Target move '{target_move_san}' not found in formatted HTML (pattern: {pattern})"
        return True, None
    except Exception as e:
        return False, str(e)


@unittest.skipIf(os.environ.get("CI") == "true", "Qt tests skipped in CI (no display)")
class TestPgnHighlighting(unittest.TestCase):
    """Unit tests for PGN highlighting (require Qt display). Uses one shared view so all tests run in sequence."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.config = ConfigLoader().load()
        except Exception as e:
            raise unittest.SkipTest(f"Config load failed: {e}") from e
        try:
            app = QApplication.instance()
            if app is None:
                app = QApplication([])
            cls._app = app
            cls._view = DetailPgnView(cls.config)
        except Exception as e:
            raise unittest.SkipTest(f"Qt/display not available: {e}") from e

    def test_basic_pgn_with_variations(self):
        pgn = '[Event "Test"]\n\n1. e4 e5 (1... c5 2. Nf3) 2. Nf3 Nc6 1-0'
        ok, err = _run_highlighting_test(self._view, self.config, pgn, active_move_ply=2)
        self.assertTrue(ok, err)

    def test_pgn_with_variations_filtered(self):
        pgn = '[Event "Test"]\n\n1. e4 e5 (1... c5 2. Nf3) 2. Nf3 Nc6 1-0'
        ok, err = _run_highlighting_test(
            self._view, self.config, pgn, filter_variations=True, active_move_ply=2
        )
        self.assertTrue(ok, err)

    def test_pgn_with_annotations(self):
        pgn = '[Event "Test"]\n\n1. e4! e5? 2. Nf3! Nc6 1-0'
        ok, err = _run_highlighting_test(self._view, self.config, pgn, active_move_ply=2)
        self.assertTrue(ok, err)

    def test_pgn_with_annotations_filtered(self):
        pgn = '[Event "Test"]\n\n1. e4! e5? 2. Nf3! Nc6 1-0'
        ok, err = _run_highlighting_test(
            self._view, self.config, pgn, filter_annotations=True, active_move_ply=2
        )
        self.assertTrue(ok, err)

    def test_pgn_with_results_filtered(self):
        pgn = '[Event "Test"]\n\n1. e4 e5 2. Nf3 Nc6 1-0'
        ok, err = _run_highlighting_test(
            self._view, self.config, pgn, filter_results=True, active_move_ply=2
        )
        self.assertTrue(ok, err)

    def test_pgn_with_variations_and_annotations_filtered(self):
        pgn = '[Event "Test"]\n\n1. e4! e5? (1... c5 2. Nf3) 2. Nf3! Nc6 1-0'
        ok, err = _run_highlighting_test(
            self._view, self.config, pgn,
            filter_variations=True, filter_annotations=True, active_move_ply=2
        )
        self.assertTrue(ok, err)


if __name__ == "__main__":
    unittest.main()
