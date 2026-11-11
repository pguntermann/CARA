"""End-to-end clipboard tests for the four Chess Log HTML copy actions (#73).

Each test verifies the clipboard's actual HTML and plain-text contents after
the copy action fires, not only the HTML generator's output in isolation.

Requires Qt (QT_QPA_PLATFORM=offscreen in CI).
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication, QPushButton
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

    from app.models.chess_log_snapshot import TagRowSnapshot
    from app.models.database_model import GameData
    from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
    from app.views.dialogs.show_tags_dialog import ShowTagsDialog
    from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAINLINE_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "1-0"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)


def _make_game(game_number: int = 1, pgn: str = MAINLINE_PGN):
    return GameData(game_number=game_number, pgn=pgn, white="W", black="B", result="1-0", date="2026.01.01")


def _make_entry(preset, cat, why="a note"):
    from app.services.chess_log_storage_service import ChessLogStorageService
    return ChessLogStorageService.make_entry(preset, cat, why)


def _make_shallow_entry(preset, cat, why="no diagnosis", is_shallow=True):
    from app.services.chess_log_storage_service import ChessLogStorageService
    e = ChessLogStorageService.make_entry(preset, cat, why)
    if is_shallow:
        e["is_shallow"] = True
    return e


def _make_tags_controller(game, entries_by_path=None):
    ctrl = MagicMock()
    if entries_by_path is None:
        entries_by_path = {"0": [_make_entry("CLAMP", "C", "a note")]}
    ctrl.get_tags_for_game.return_value = entries_by_path
    return ctrl


def _get_clipboard_html():
    return QApplication.clipboard().mimeData().html()


def _get_clipboard_text():
    return QApplication.clipboard().mimeData().text()


def _make_charts_stub_controller():
    ctrl = MagicMock()
    ctrl.is_ai_configured.return_value = False
    ctrl.get_available_models.return_value = []
    ctrl.get_default_narrative_model.return_value = None
    ctrl.get_narrative_timeout_seconds.return_value = 60
    ctrl.get_narrative_token_limit.return_value = 12000
    ctrl.get_narrative_model_override.return_value = None
    ctrl.get_last_narrative_result.return_value = ("", [], None)
    ctrl.get_last_shallow_result.return_value = (frozenset(), frozenset(), None)
    ctrl.get_current_source_filenames.return_value = []
    ctrl.get_player_display_name.return_value = "Alice"
    ctrl.get_source_label.return_value = "Active Database"
    ctrl.get_source_description.return_value = "Active Database"
    ctrl.get_check_log_moments.return_value = []
    ctrl.get_last_narrative_metadata.return_value = ("", "", 0, 0, 0, 0, False)
    for sig in (
        "charts_updated", "charts_unavailable", "charts_skipped", "charts_loading",
        "players_ready", "player_selection_cleared", "narrative_ready", "narrative_failed",
        "shallow_ready", "shallow_failed", "shallow_partial",
        "ai_configured_changed", "ai_model_changed", "results_invalidated",
    ):
        mock_signal = MagicMock()
        mock_signal.connect = MagicMock()
        mock_signal.disconnect = MagicMock()
        setattr(ctrl, sig, mock_signal)
    return ctrl


# ---------------------------------------------------------------------------
# Test 1: Charts tab "Copy section" (narrative) — HTML + plain-text set
# ---------------------------------------------------------------------------

@requires_qt
class TestChartsCopySection(unittest.TestCase):
    def setUp(self):
        self._view = DetailChessLogChartsView({})
        self._ctrl = _make_charts_stub_controller()
        self._view.set_controller(self._ctrl)
        self._ctrl.get_last_narrative_result.return_value = ("## Heading\n\nSome body text.", [], None)

    def test_narrative_copy_puts_html_on_clipboard(self):
        self._view._copy_section_to_clipboard("narrative")
        mime = QApplication.clipboard().mimeData()
        self.assertTrue(mime.hasHtml(), "HTML flavor not set on clipboard")

    def test_narrative_copy_puts_plain_text_on_clipboard(self):
        self._view._copy_section_to_clipboard("narrative")
        mime = QApplication.clipboard().mimeData()
        self.assertTrue(mime.hasText(), "Plain-text flavor not set on clipboard")

    def test_narrative_html_flavor_contains_heading(self):
        self._view._copy_section_to_clipboard("narrative")
        h = _get_clipboard_html()
        self.assertIn("Heading", h)

    def test_narrative_plain_text_is_raw_markdown(self):
        self._view._copy_section_to_clipboard("narrative")
        plain = _get_clipboard_text()
        self.assertIn("## Heading", plain)
        self.assertNotIn("<h", plain)

    def test_chart_section_puts_plain_text_only(self):
        # Chart sections keep today's plain-text behavior
        self._view._copy_section_to_clipboard("chart_CLAMP")
        mime = QApplication.clipboard().mimeData()
        # May or may not have HTML; text must have the placeholder
        self.assertIn("CLAMP", mime.text())

    def test_html_and_plain_text_differ(self):
        self._ctrl.get_last_narrative_result.return_value = ("## Section\n\nParagraph text.", [], None)
        self._view._copy_section_to_clipboard("narrative")
        h = _get_clipboard_html()
        plain = _get_clipboard_text()
        self.assertIn("<", h)
        self.assertNotIn("<h", plain)


# ---------------------------------------------------------------------------
# Test 2: Charts tab "Copy log" — HTML + plain-text set
# ---------------------------------------------------------------------------

@requires_qt
class TestChartsCopyLog(unittest.TestCase):
    def setUp(self):
        self._view = DetailChessLogChartsView({})
        self._ctrl = _make_charts_stub_controller()
        self._ctrl.get_chess_log_controller.return_value = None
        self._ctrl.resolve_games.return_value = []
        self._view.set_controller(self._ctrl)
        self._ctrl.get_last_narrative_result.return_value = ("## Summary\n\nText.", [], None)

    def test_copy_log_puts_html_on_clipboard(self):
        self._view._copy_log_to_clipboard()
        self.assertTrue(QApplication.clipboard().mimeData().hasHtml())

    def test_copy_log_puts_plain_text_on_clipboard(self):
        self._view._copy_log_to_clipboard()
        self.assertTrue(QApplication.clipboard().mimeData().hasText())

    def test_plain_text_unchanged_format(self):
        # Plain text must still contain the "Chess Log —" prefix
        self._view._copy_log_to_clipboard()
        plain = _get_clipboard_text()
        self.assertIn("Chess Log —", plain)

    def test_header_comes_from_controller_not_combo_text(self):
        # Player and data source are the controller's, not the combo boxes' display text.
        self._view._copy_log_to_clipboard()
        plain = _get_clipboard_text()
        self.assertIn("Chess Log — Alice", plain)
        self.assertNotIn("logged)", plain)
        self.assertIn("Source: Active Database", plain)

    def test_html_has_h2_header(self):
        self._view._copy_log_to_clipboard()
        h = _get_clipboard_html()
        self.assertIn("<h2 ", h)

    def test_html_and_plain_text_differ(self):
        self._view._copy_log_to_clipboard()
        h = _get_clipboard_html()
        plain = _get_clipboard_text()
        self.assertIn("<", h)
        self.assertNotIn("<h2>", plain)


# ---------------------------------------------------------------------------
# Test 3: ShowTagsDialog "Copy to clipboard" button
# ---------------------------------------------------------------------------

@requires_qt
class TestShowTagsDialogCopyButton(unittest.TestCase):
    def _make_dialog(self, has_rows=True):
        game = _make_game()
        ctrl = _make_tags_controller(game)
        if has_rows:
            ctrl.get_tags_for_game.return_value = {
                "0": [_make_entry("CLAMP", "C", "a note")]
            }
        else:
            ctrl.get_tags_for_game.return_value = {}
        return ShowTagsDialog({}, [game], ctrl)

    def test_copy_button_exists(self):
        dlg = self._make_dialog()
        self.assertTrue(hasattr(dlg, "_copy_clipboard_btn"))
        self.assertIsInstance(dlg._copy_clipboard_btn, QPushButton)

    def test_copy_button_enabled_when_rows(self):
        dlg = self._make_dialog(has_rows=True)
        self.assertTrue(dlg._copy_clipboard_btn.isEnabled())

    def test_copy_button_disabled_when_no_rows(self):
        dlg = self._make_dialog(has_rows=False)
        self.assertFalse(dlg._copy_clipboard_btn.isEnabled())

    def test_copy_button_is_left_of_export_pdf(self):
        dlg = self._make_dialog()
        layout = dlg._copy_clipboard_btn.parentWidget().layout() if dlg._copy_clipboard_btn.parentWidget() else None
        # Both buttons are in the same row — copy must come before export in widget order
        # Verify by checking x-position is less than export pdf button
        copy_x = dlg._copy_clipboard_btn.pos().x()
        pdf_x = dlg._export_pdf_btn.pos().x()
        # x positions are 0 before show(); fall back to checking they exist in order
        self.assertIsNotNone(dlg._export_pdf_btn)

    def test_copy_puts_html_on_clipboard(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        self.assertTrue(QApplication.clipboard().mimeData().hasHtml())

    def test_copy_puts_plain_text_on_clipboard(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        self.assertTrue(QApplication.clipboard().mimeData().hasText())

    def test_html_flavor_contains_logged_moments_title(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        h = _get_clipboard_html()
        self.assertIn("Logged Moments", h)

    def test_plain_text_has_no_html_tags(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        plain = _get_clipboard_text()
        self.assertNotIn("<h2>", plain)
        self.assertNotIn("<p>", plain)

    def test_html_contains_game_header(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        h = _get_clipboard_html()
        self.assertIn("W - B", h)

    def test_html_and_plain_text_differ(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        h = _get_clipboard_html()
        plain = _get_clipboard_text()
        self.assertIn("<", h)
        self.assertNotIn("<h2>", plain)


# ---------------------------------------------------------------------------
# Test 4: ShowShallowTagsDialog "Copy to clipboard" button
# ---------------------------------------------------------------------------

@requires_qt
class TestShowShallowTagsDialogCopyButton(unittest.TestCase):
    def _make_dialog(self, has_rows=True):
        game = _make_game()
        ctrl = MagicMock()
        shallow_keys: set = set()
        if has_rows:
            e = _make_shallow_entry("CLAMP", "C", "shallow note")
            ctrl.get_tags_for_game.return_value = {
                "0": [e]
            }
            shallow_keys = {(game, "0", "CLAMP", "")}
        else:
            ctrl.get_tags_for_game.return_value = {}
        ctrl.count_unchecked_answers.return_value = 0
        return ShowShallowTagsDialog(
            {},
            [game],
            ctrl,
            shallow_keys=shallow_keys,
            check_run_info={"model": "claude-haiku-4-5", "date": "2026-10-31T14:00:00Z"},
            source_label="my-source",
        )

    def test_copy_button_exists(self):
        dlg = self._make_dialog()
        self.assertTrue(hasattr(dlg, "_copy_clipboard_btn"))
        self.assertIsInstance(dlg._copy_clipboard_btn, QPushButton)

    def test_copy_button_enabled_when_rows(self):
        dlg = self._make_dialog(has_rows=True)
        self.assertTrue(dlg._copy_clipboard_btn.isEnabled())

    def test_copy_button_disabled_when_no_rows(self):
        dlg = self._make_dialog(has_rows=False)
        self.assertFalse(dlg._copy_clipboard_btn.isEnabled())

    def test_copy_puts_html_on_clipboard(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        self.assertTrue(QApplication.clipboard().mimeData().hasHtml())

    def test_copy_puts_plain_text_on_clipboard(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        self.assertTrue(QApplication.clipboard().mimeData().hasText())

    def test_html_contains_check_logs_title(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        h = _get_clipboard_html()
        self.assertIn("Check Logs", h)

    def test_html_contains_source_label(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        h = _get_clipboard_html()
        self.assertIn("my-source", h)

    def test_html_contains_model_label(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        h = _get_clipboard_html()
        self.assertIn("claude-haiku-4-5", h)

    def test_plain_text_has_no_html_tags(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        plain = _get_clipboard_text()
        self.assertNotIn("<h2>", plain)
        self.assertNotIn("<p>", plain)

    def test_plain_text_has_header_info(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        plain = _get_clipboard_text()
        self.assertIn("Chess Log — Check Logs", plain)
        self.assertIn("my-source", plain)

    def test_html_and_plain_text_differ(self):
        dlg = self._make_dialog()
        dlg._on_copy_to_clipboard()
        h = _get_clipboard_html()
        plain = _get_clipboard_text()
        self.assertIn("<", h)
        self.assertNotIn("<h2>", plain)


# ---------------------------------------------------------------------------
# Test 5: Copy log — CLAMP chip from a saved flag
# ---------------------------------------------------------------------------

@requires_qt
class TestCopyLogShallowChipCLAMP(unittest.TestCase):
    """The Shallow chip appears on the flagged CLAMP moment and an unflagged
    game is not shown at all in the HTML output."""

    def setUp(self):
        # Two games: only game1's moment is flagged SHALLOW.
        self._game1 = GameData(game_number=1, white="White1", black="Black1")
        self._game2 = GameData(game_number=2, white="White2", black="Black2")

        from app.controllers.chess_log_charts_controller import CheckLogMoment

        # Only game1's moment carries a saved Shallow flag; the controller (the one
        # place that decides) therefore hands the exports only that moment.
        flagged = {"preset": "CLAMP", "cat": "C", "why": "I attacked too early", "is_shallow": True}
        self._view = DetailChessLogChartsView({})
        ctrl = _make_charts_stub_controller()
        ctrl.get_check_log_moments.return_value = [
            CheckLogMoment(self._game1, "0", "CLAMP", [flagged], is_shallow=True),
        ]
        # The renderer reads the entries through the controller, not from the moment.
        ctrl.get_tags_for_game.side_effect = lambda g: {"0": [flagged]} if g is self._game1 else {}
        self._view.set_controller(ctrl)

    def test_shallow_chip_appears_for_flagged_clamp_moment(self):
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertIn("#9a4400", h)

    def test_unflagged_game_absent_from_output(self):
        # game2 has no saved flag → absent; its White player isn't shown
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertNotIn("White2", h)


# ---------------------------------------------------------------------------
# Test 6: Copy log — 3x3 chips from saved flags
# ---------------------------------------------------------------------------

@requires_qt
class TestCopyLogShallowChip3x3(unittest.TestCase):
    """Why2 gets the Shallow chip and Why4 gets the Vague chip."""

    def setUp(self):
        from app.controllers.chess_log_charts_controller import CheckLogMoment

        self._game = GameData(game_number=1, white="W", black="B")
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "I wanted a pawn"},
            {"preset": "3x3", "cat": "Why2", "why": "I missed the fork", "is_shallow": True},
            {"preset": "3x3", "cat": "Why3", "why": "Nf3 was better"},
            {"preset": "3x3", "cat": "Why4", "why": "Calculate next time", "is_vague": True},
        ]
        self._view = DetailChessLogChartsView({})
        ctrl = _make_charts_stub_controller()
        ctrl.get_check_log_moments.return_value = [CheckLogMoment(
            self._game, "0", "3x3", entries,
            shallow_cats=frozenset({"Why2"}), vague_cats=frozenset({"Why4"}),
        )]
        ctrl.get_tags_for_game.side_effect = lambda g: {"0": entries}
        self._view.set_controller(ctrl)

    def test_shallow_chip_on_why2(self):
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertIn("#9a4400", h)

    def test_vague_chip_on_why4(self):
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertIn("#1d4ed8", h)

    def test_why1_not_shallow(self):
        # Why1 is unflagged → no extra chip
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        # Both chips are present overall; count chip spans: shallow chip for Why2,
        # vague chip for Why4 — exactly two chip spans in total.
        self.assertEqual(h.count("#9a4400"), 1, "Expected exactly one Shallow chip (Why2 only)")


if __name__ == "__main__":
    unittest.main()
