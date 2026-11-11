"""Tests for DetailChessLogChartsView freshness-cache and invalidation."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

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
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])
    from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
    from app.controllers.chess_log_charts_controller import ChessLogChartsController
    from app.models.database_model import GameData

_MINIMAL_CONFIG: dict = {}
# Use GameData objects as keys (identity-keyed, not game_number-keyed)
_GAME_1 = GameData(game_number=1) if _QT_OK else None
_GAME_2 = GameData(game_number=2) if _QT_OK else None
_SHALLOW_KEYS = frozenset({(_GAME_1, "k1", "CLAMP", ""), (_GAME_2, "k2", "CCT", "")}) if _QT_OK else frozenset()
_GAME_3 = GameData(game_number=3) if _QT_OK else None
_VAGUE_KEYS = frozenset({(_GAME_3, "v1", "3x3", "Why4")}) if _QT_OK else frozenset()


@requires_qt
class TestViewKeepsNoResultCopies(unittest.TestCase):
    """#91: the view holds no copy of the narrative or Check Logs result; the
    controller is the only store, so the two can never disagree."""

    def test_view_has_no_result_copy_attributes(self):
        view = DetailChessLogChartsView(_MINIMAL_CONFIG)
        for attr in ("_last_shallow_keys", "_last_vague_keys", "_last_narrative"):
            self.assertFalse(hasattr(view, attr), f"view must not keep {attr}")

    def test_shallow_ready_does_not_store_on_view(self):
        view = DetailChessLogChartsView(_MINIMAL_CONFIG)
        view._on_shallow_ready(frozenset(), frozenset(), frozenset(), None)
        self.assertFalse(hasattr(view, "_last_shallow_keys"))

    def test_narrative_ready_does_not_store_on_view(self):
        view = DetailChessLogChartsView(_MINIMAL_CONFIG)
        view._on_narrative_ready("some narrative", [], None)
        self.assertFalse(hasattr(view, "_last_narrative"))


def _make_ctrl():
    """Minimal controller that won't start any threads or need real data."""
    db_ctrl = MagicMock()
    db_ctrl.get_panel_model.return_value = None
    db_ctrl.get_active_database.return_value = MagicMock(get_all_games=MagicMock(return_value=[]))
    return ChessLogChartsController(config={}, database_controller=db_ctrl)


@requires_qt
class TestThemeRebuildPreservesResults(unittest.TestCase):
    """Result cache in the controller survives view destruction (theme change)."""

    def _simulate_theme_rebuild(self, ctrl):
        """Return a fresh view wired to ctrl — the same as apply_theme's _setup_ui does."""
        view = DetailChessLogChartsView(_MINIMAL_CONFIG)
        with patch.object(ctrl, "_start_dropdown_worker"):
            view.set_controller(ctrl)
        return view

    def test_narrative_survives_theme_rebuild(self):
        ctrl = _make_ctrl()
        ctrl._on_narrative_thread_ready("Deep pawn structure issues.", [], None)

        view = self._simulate_theme_rebuild(ctrl)

        self.assertEqual(view._narrative_text(), "Deep pawn structure issues.")
        # Token label is empty (None usage) but narrative text is present.
        self.assertNotEqual(view._narrative_edit.toPlainText().strip(), "")

    def test_narrative_token_counts_survive_theme_rebuild(self):
        from app.services.ai_service import TokenUsage
        ctrl = _make_ctrl()
        usage = TokenUsage(input_tokens=100, output_tokens=50, reasoning_tokens=None, reported=True)
        ctrl._on_narrative_thread_ready("Good endgame technique.", [], usage)

        view = self._simulate_theme_rebuild(ctrl)

        self.assertIn("50", view._narrative_token_label.text())

    def test_shallow_keys_survive_theme_rebuild(self):
        ctrl = _make_ctrl()
        ctrl._on_shallow_thread_ready(_SHALLOW_KEYS, frozenset(), frozenset(), None)

        self._simulate_theme_rebuild(ctrl)

        self.assertEqual(ctrl.get_last_shallow_result()[0], _SHALLOW_KEYS)

    def test_shallow_token_counts_survive_theme_rebuild(self):
        from app.services.ai_service import TokenUsage
        ctrl = _make_ctrl()
        usage = TokenUsage(input_tokens=80, output_tokens=30, reasoning_tokens=None, reported=True)
        ctrl._on_shallow_thread_ready(_SHALLOW_KEYS, frozenset(), frozenset(), usage)

        view = self._simulate_theme_rebuild(ctrl)

        self.assertIn("30", view._shallow_token_label.text())

    def test_vague_keys_survive_theme_rebuild(self):
        ctrl = _make_ctrl()
        ctrl._on_shallow_thread_ready(frozenset(), _VAGUE_KEYS, frozenset(), None)

        self._simulate_theme_rebuild(ctrl)

        # A vague-only result is stored as such (shallow is an empty set, not None).
        self.assertEqual(ctrl.get_last_shallow_result()[:2], (frozenset(), _VAGUE_KEYS))

    def test_vague_only_token_label_survives_theme_rebuild(self):
        from app.services.ai_service import TokenUsage
        ctrl = _make_ctrl()
        usage = TokenUsage(input_tokens=80, output_tokens=31, reasoning_tokens=None, reported=True)
        ctrl._on_shallow_thread_ready(frozenset(), _VAGUE_KEYS, frozenset(), usage)

        view = self._simulate_theme_rebuild(ctrl)

        self.assertIn("31", view._shallow_token_label.text())

    def test_rebuilt_view_reads_the_same_results_from_the_controller(self):
        from app.services.ai_service import TokenUsage
        ctrl = _make_ctrl()
        usage = TokenUsage(input_tokens=10, output_tokens=7, reasoning_tokens=None, reported=True)
        ctrl._on_narrative_thread_ready("Narrative text.", [], usage)
        ctrl._on_shallow_thread_ready(_SHALLOW_KEYS, _VAGUE_KEYS, frozenset(), usage)
        first = self._simulate_theme_rebuild(ctrl)
        second = self._simulate_theme_rebuild(ctrl)

        for view in (first, second):
            self.assertEqual(view._narrative_text(), "Narrative text.")
            self.assertEqual(view._narrative_edit.toPlainText(), first._narrative_edit.toPlainText())
            self.assertEqual(view._shallow_token_label.text(), first._shallow_token_label.text())
            self.assertIn("7", view._shallow_token_label.text())
        self.assertEqual(ctrl.get_last_shallow_result()[:2], (_SHALLOW_KEYS, _VAGUE_KEYS))

    def test_database_switch_clears_narrative_before_rebuild(self):
        ctrl = _make_ctrl()
        ctrl._on_narrative_thread_ready("Stale narrative.", [], None)
        ctrl._source_selection = 1  # needed so _on_active_database_changed acts

        with patch.object(ctrl, "_start_dropdown_worker"), \
             patch.object(ctrl, "_cancel_agg_worker"), \
             patch.object(ctrl, "_cancel_shallow_thread"):
            ctrl._on_active_database_changed(MagicMock())

        view = self._simulate_theme_rebuild(ctrl)

        self.assertEqual(view._narrative_text(), "")
        self.assertEqual(view._narrative_edit.toPlainText().strip(), "")

    def test_database_switch_clears_shallow_before_rebuild(self):
        ctrl = _make_ctrl()
        ctrl._on_shallow_thread_ready(_SHALLOW_KEYS, frozenset(), frozenset(), None)
        ctrl._source_selection = 1

        with patch.object(ctrl, "_start_dropdown_worker"), \
             patch.object(ctrl, "_cancel_agg_worker"), \
             patch.object(ctrl, "_cancel_shallow_thread"):
            ctrl._on_active_database_changed(MagicMock())

        self._simulate_theme_rebuild(ctrl)

        self.assertEqual(ctrl.get_last_shallow_result()[:2], (frozenset(), frozenset()))

    def test_player_change_clears_both_before_rebuild(self):
        ctrl = _make_ctrl()
        ctrl._on_narrative_thread_ready("Player A narrative.", [], None)
        ctrl._on_shallow_thread_ready(_SHALLOW_KEYS, frozenset(), frozenset(), None)

        with patch.object(ctrl, "_kick_debounce"):
            ctrl.set_player_selection("Player B")

        view = self._simulate_theme_rebuild(ctrl)

        self.assertEqual(view._narrative_text(), "")
        self.assertEqual(ctrl.get_last_shallow_result()[:2], (frozenset(), frozenset()))

    def test_source_change_clears_both_before_rebuild(self):
        ctrl = _make_ctrl()
        ctrl._on_narrative_thread_ready("Source A narrative.", [], None)
        ctrl._on_shallow_thread_ready(_SHALLOW_KEYS, frozenset(), frozenset(), None)

        with patch.object(ctrl, "_start_dropdown_worker"), \
             patch.object(ctrl, "_cancel_agg_worker"):
            ctrl.set_source_selection(2)

        view = self._simulate_theme_rebuild(ctrl)

        self.assertEqual(view._narrative_text(), "")
        self.assertEqual(ctrl.get_last_shallow_result()[:2], (frozenset(), frozenset()))


@requires_qt
class TestGameSetChangeClearsDisplay(unittest.TestCase):
    """#77: narrative edit, token labels, and flagged box must visually clear when
    the game set changes (DB switch, player change, source change).  Each test
    that mutates display state must fail before the fix and pass after."""

    def setUp(self):
        self._ctrl = _make_ctrl()
        self._view = DetailChessLogChartsView(_MINIMAL_CONFIG)
        with patch.object(self._ctrl, "_start_dropdown_worker"):
            self._view.set_controller(self._ctrl)
        self._ctrl._on_narrative_thread_ready("Old narrative text.", [], None)
        self._ctrl._on_shallow_thread_ready(_SHALLOW_KEYS, frozenset(), frozenset(), None)
        self.assertNotEqual(self._view._narrative_edit.toPlainText().strip(), "")

    def _clear_via_controller(self):
        """Everything that invalidates results does so through the controller."""
        with patch.object(self._ctrl, "_kick_debounce"):
            self._ctrl._clear_result_cache()

    # --- DB switch / reset_player_selection ---

    def test_db_switch_clears_narrative_edit_text(self):
        """A controller-side clear (DB switch) empties the narrative display."""
        self._clear_via_controller()
        self.assertEqual(self._view._narrative_edit.toPlainText().strip(), "")

    def test_db_switch_clears_stored_narrative(self):
        """The controller's stored narrative is gone (PDF export protection)."""
        self._clear_via_controller()
        self.assertEqual(self._view._narrative_text(), "")

    def test_db_switch_clears_shallow_token_label(self):
        self._view._shallow_token_label.setText("Tokens: 100 in / 50 out")
        self._clear_via_controller()
        self.assertEqual(self._view._shallow_token_label.text(), "")

    def test_db_switch_clears_narrative_token_label(self):
        self._view._narrative_token_label.setText("Tokens: 200 in / 80 out")
        self._clear_via_controller()
        self.assertEqual(self._view._narrative_token_label.text(), "")

    # --- player change ---

    def test_player_change_clears_narrative_edit_text(self):
        """Choosing a player clears the narrative display (through the controller)."""
        with patch.object(self._ctrl, "_kick_debounce"):
            self._ctrl.set_player_selection("Player B")
        self.assertEqual(self._view._narrative_edit.toPlainText().strip(), "")

    def test_player_change_clears_stored_narrative(self):
        self.assertEqual(self._view._narrative_text(), "Old narrative text.")
        with patch.object(self._ctrl, "_kick_debounce"):
            self._ctrl.set_player_selection("Player B")
        self.assertEqual(self._view._narrative_text(), "")

    def test_player_change_clears_stored_check_logs_result(self):
        with patch.object(self._ctrl, "_kick_debounce"):
            self._ctrl.set_player_selection("Player B")
        self.assertEqual(self._ctrl.get_last_shallow_result()[:2], (frozenset(), frozenset()))

    def test_view_player_handler_clears_nothing_itself(self):
        """_on_player_changed only forwards to the controller; the controller clears."""
        self._view._player_combo.addItem("Player B (1 logged)", "Player B")
        with patch.object(self._ctrl, "_kick_debounce"):
            self._view._on_player_changed(0)
        self.assertEqual(self._ctrl.get_player_display_name(), "Player B")
        self.assertEqual(self._view._narrative_text(), "")

    def test_source_change_clears_through_controller(self):
        with patch.object(self._ctrl, "_start_dropdown_worker"), \
             patch.object(self._ctrl, "_cancel_agg_worker"):
            self._view._on_source_changed(2)
        self.assertEqual(self._view._narrative_text(), "")
        self.assertEqual(self._view._narrative_edit.toPlainText().strip(), "")
        self.assertEqual(self._ctrl.get_last_shallow_result()[:2], (frozenset(), frozenset()))

    # --- positive control: chart redraw does NOT clear ---

    def test_chart_loading_does_not_clear_narrative(self):
        """_on_charts_loading (chart redraw, same game set) must not clear narrative."""
        self._view._on_charts_loading()
        self.assertEqual(self._view._narrative_text(), "Old narrative text.")
        self.assertNotEqual(self._view._narrative_edit.toPlainText().strip(), "")

    def test_chart_updated_does_not_clear_narrative(self):
        self._view._on_charts_updated({})
        self.assertEqual(self._view._narrative_text(), "Old narrative text.")

    # --- saved data untouched ---

    def test_clear_does_not_call_any_save_method(self):
        """_clear_narrative_and_check_logs must not invoke any Chess Log storage method."""
        with patch(
            "app.services.chess_log_storage_service.ChessLogStorageService.store_tags"
        ) as mock_store:
            self._view._clear_narrative_and_check_logs()
            self._clear_via_controller()
        mock_store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
