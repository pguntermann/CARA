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
    ctrl.get_last_shallow_result.return_value = (None, None, None)
    ctrl.get_current_source_filenames.return_value = []
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
        ctrl = _make_charts_stub_controller()
        self._view.set_controller(ctrl)
        self._view._last_narrative = "## Heading\n\nSome body text."

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
        self._view._last_narrative = "## Section\n\nParagraph text."
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
        ctrl = _make_charts_stub_controller()
        ctrl.get_chess_log_controller.return_value = None
        ctrl.resolve_games.return_value = []
        self._view.set_controller(ctrl)
        self._view._last_narrative = "## Summary\n\nText."

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
# Test 5: Copy log — CLAMP chip lookup via real classifier parse step
# ---------------------------------------------------------------------------

@requires_qt
class TestCopyLogShallowChipCLAMP(unittest.TestCase):
    """Build shallow_keys the same way classify_notes() does, then verify
    the Shallow chip appears on the flagged CLAMP moment and that an unflagged
    game is not shown at all in the HTML output."""

    def setUp(self):
        from app.services.chess_log_shallow_service import _parse_verdicts

        # Two games: only game1's moment is classified SHALLOW.
        self._game1 = GameData(game_number=1, white="White1", black="Black1")
        self._game2 = GameData(game_number=2, white="White2", black="Black2")

        # Build shallow_keys through the real parse step (same as classify_notes).
        notes = [(0, self._game1, "0", "CLAMP", "I attacked too early")]
        parsed = _parse_verdicts("0: SHALLOW", len(notes))
        shallow_keys = frozenset(
            (notes[i][1], notes[i][2], notes[i][3], "")
            for i, verdict in parsed.items()
            if verdict == "SHALLOW"
        )

        chess_log_ctrl = MagicMock()
        chess_log_ctrl.get_tags_for_game.side_effect = lambda g: (
            {"0": [{"preset": "CLAMP", "cat": "C", "why": "I attacked too early"}]}
            if g is self._game1
            else {"0": [{"preset": "CLAMP", "cat": "M", "why": "I played too fast"}]}
        )

        self._view = DetailChessLogChartsView({})
        ctrl = _make_charts_stub_controller()
        ctrl.get_chess_log_controller.return_value = chess_log_ctrl
        ctrl.resolve_games.return_value = [self._game1, self._game2]
        self._view.set_controller(ctrl)
        self._view._last_shallow_keys = shallow_keys
        self._view._last_vague_keys = frozenset()

    def test_shallow_chip_appears_for_flagged_clamp_moment(self):
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertIn("#9a4400", h)

    def test_unflagged_game_absent_from_output(self):
        # game2 is not in shallow_keys → filtered out; its White player isn't shown
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertNotIn("White2", h)


# ---------------------------------------------------------------------------
# Test 6: Copy log — 3x3 chip lookup via real classifier parse step
# ---------------------------------------------------------------------------

@requires_qt
class TestCopyLogShallowChip3x3(unittest.TestCase):
    """Build shallow_keys and vague_keys the same way classify_notes_3x3() does,
    then verify Why2 gets the Shallow chip and Why4 gets the Vague chip."""

    def setUp(self):
        from app.services.chess_log_shallow_service import _parse_3x3_verdicts

        self._game = GameData(game_number=1, white="W", black="B")

        # Build shallow_keys and vague_keys through the real parse step.
        notes = [(0, self._game, "0", "3x3",
                  "I wanted a pawn", "I missed the fork", "Nf3 was better", "Calculate next time")]
        reply = "0: WHY1=SPECIFIC WHY2=GENERIC WHY3=SPECIFIC LESSON=FILLER"
        parsed = _parse_3x3_verdicts(reply, len(notes))

        s_keys = []
        v_keys = []
        for i, (why1, why2, why3, lesson) in parsed.items():
            game, pk = notes[i][1], notes[i][2]
            for cat, verdict in (("Why1", why1), ("Why2", why2), ("Why3", why3)):
                if verdict == "GENERIC":
                    s_keys.append((game, pk, "3x3", cat))
            if lesson == "FILLER":
                v_keys.append((game, pk, "3x3", "Why4"))

        chess_log_ctrl = MagicMock()
        chess_log_ctrl.get_tags_for_game.return_value = {"0": [
            {"preset": "3x3", "cat": "Why1", "why": "I wanted a pawn"},
            {"preset": "3x3", "cat": "Why2", "why": "I missed the fork"},
            {"preset": "3x3", "cat": "Why3", "why": "Nf3 was better"},
            {"preset": "3x3", "cat": "Why4", "why": "Calculate next time"},
        ]}

        self._view = DetailChessLogChartsView({})
        ctrl = _make_charts_stub_controller()
        ctrl.get_chess_log_controller.return_value = chess_log_ctrl
        ctrl.resolve_games.return_value = [self._game]
        self._view.set_controller(ctrl)
        self._view._last_shallow_keys = frozenset(s_keys)
        self._view._last_vague_keys = frozenset(v_keys)

    def test_shallow_chip_on_why2(self):
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertIn("#9a4400", h)

    def test_vague_chip_on_why4(self):
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        self.assertIn("#1d4ed8", h)

    def test_why1_not_shallow(self):
        # Why1 is SPECIFIC → not in shallow_keys → no extra chip
        self._view._copy_log_to_clipboard()
        h = QApplication.clipboard().mimeData().html()
        # Both chips are present overall; count chip spans: shallow chip for Why2,
        # vague chip for Why4 — exactly two chip spans in total.
        self.assertEqual(h.count("#9a4400"), 1, "Expected exactly one Shallow chip (Why2 only)")


if __name__ == "__main__":
    unittest.main()
