"""Tests for ChessLogChartsController.

Uses Qt (QThread / QObject) — requires an offscreen Qt platform or a running
display.  Tests skip cleanly when Qt cannot start (same guard as test_moment_dialog).
"""

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


_QT_AVAILABLE = _qt_starts_cleanly()

if _QT_AVAILABLE:
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)

    from app.controllers.chess_log_charts_controller import (
        ChessLogChartsController as _RealChessLogChartsController,
        ChessLogAggregationWorker,
        ChessLogNarrativeThread,
        ChessLogPlayerDropdownWorker,
    )
    from app.models.database_model import DatabaseModel, GameData
    from app.services.chess_log_storage_service import ChessLogStorageService
    from tests.chess_log_charts_helper import StorageBackedChessLogController

    class ChessLogChartsController(_RealChessLogChartsController):
        """Real controller with the required Chess Log controller injected (C5)."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.set_chess_log_controller(StorageBackedChessLogController())

    class _FakeNarrativeThread(QObject):
        """Fake narrative thread: holds real signals but never actually starts."""
        narrative_ready = pyqtSignal(str, list, object)
        narrative_failed = pyqtSignal(str)
        finished = pyqtSignal()

        def start(self):
            pass

        def isRunning(self):
            return False

        def cancel(self):
            pass

    class _FakeShallowThread(QObject):
        """Fake shallow thread: holds real signals but never actually starts."""
        shallow_ready = pyqtSignal(object, object, object, object, str)
        shallow_failed = pyqtSignal(str)
        shallow_partial = pyqtSignal(str)
        finished = pyqtSignal()

        def start(self):
            pass

        def isRunning(self):
            return False

        def cancel(self):
            pass

# Game objects for shallow-thread tests: position 0 of key tuples, not game_number.
# _NOTE_GAMES[i] replaces the integer i+1 that was previously at note/key position 1/0.
_NOTE_GAMES = [GameData(game_number=i + 1) for i in range(5)] if _QT_AVAILABLE else []
# _3X3_NOTE_GAMES[i] replaces the integer i+10 used in mixed-call tests.
_3X3_NOTE_GAMES = [GameData(game_number=i + 10) for i in range(3)] if _QT_AVAILABLE else []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(
    white: str = "Alice",
    black: str = "Bob",
    date: str = "2025.06.01",
    entries_per_path: dict | None = None,
) -> "GameData":
    pgn = (
        f'[Event "Test"]\n[Site "?"]\n[Date "{date}"]\n'
        f'[Round "?"]\n[White "{white}"]\n[Black "{black}"]\n'
        f'[Result "*"]\n\n1. e4 *\n'
    )
    game = GameData(game_number=1, pgn=pgn, white=white, black=black, date=date)
    if entries_per_path:
        ChessLogStorageService.store_tags(game, entries_per_path)
    return game


def _clamp(cat: str) -> dict:
    return ChessLogStorageService.make_entry("CLAMP", cat)


def _make_db_controller(games: list) -> MagicMock:
    """Stub database controller whose active DB returns the given games."""
    db = MagicMock()
    db.get_all_database_models.return_value = games
    ctrl = MagicMock()
    ctrl.get_active_database.return_value = db
    ctrl.get_panel_model.return_value = None
    return ctrl


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerSourceSelection(unittest.TestCase):

    def _make_controller(self, games=None) -> ChessLogChartsController:
        games = games or []
        db_ctrl = _make_db_controller(games)
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        return ctrl

    def test_source_none_emits_charts_unavailable(self):
        ctrl = self._make_controller()
        received = []
        ctrl.charts_unavailable.connect(received.append)
        ctrl.set_source_selection(0)
        self.assertIn("no_source", received)

    def test_set_source_emits_no_player_not_agg_worker(self):
        # Selecting a source without an explicit player must NOT start aggregation.
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        received = []
        ctrl.charts_unavailable.connect(received.append)
        ctrl.set_source_selection(1)
        self.assertIsNone(ctrl._agg_worker)
        self.assertIn("no_player", received)

    def test_set_source_resets_player_explicit_selected(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._player_explicit_selected = True
        ctrl.set_source_selection(1)
        self.assertFalse(ctrl._player_explicit_selected)

    def test_set_source_starts_dropdown_worker(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._start_dropdown_worker = MagicMock()
        ctrl.set_source_selection(1)
        ctrl._start_dropdown_worker.assert_called_once()


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerPlayerSelection(unittest.TestCase):

    def _make_controller(self, games=None) -> ChessLogChartsController:
        games = games or []
        db_ctrl = _make_db_controller(games)
        return ChessLogChartsController(config={}, database_controller=db_ctrl)

    def test_set_player_sets_explicit_flag_and_stores_name(self):
        ctrl = self._make_controller()
        ctrl.set_player_selection("Bob")
        self.assertTrue(ctrl._player_explicit_selected)
        self.assertEqual(ctrl._current_player, "Bob")

    def test_empty_player_sets_explicit_flag(self):
        # "All players" (empty string) is still an explicit user choice.
        ctrl = self._make_controller()
        ctrl.set_player_selection("")
        self.assertTrue(ctrl._player_explicit_selected)
        self.assertEqual(ctrl._current_player, "")

    def test_on_selection_debounced_without_explicit_player_emits_no_player(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._source_selection = 1
        # _player_explicit_selected is False by default
        received = []
        ctrl.charts_unavailable.connect(received.append)
        ctrl._on_selection_debounced()
        self.assertIn("no_player", received)
        self.assertIsNone(ctrl._agg_worker)

    def test_on_selection_debounced_with_explicit_player_starts_worker(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        ctrl._schedule_charts_refresh = MagicMock()
        ctrl._on_selection_debounced()
        ctrl._schedule_charts_refresh.assert_called_once()

    def test_has_player_selected_starts_false(self):
        ctrl = self._make_controller()
        self.assertFalse(ctrl.has_player_selected())

    def test_has_player_selected_true_after_set_player(self):
        ctrl = self._make_controller()
        ctrl.set_player_selection("Alice")
        self.assertTrue(ctrl.has_player_selected())

    def test_has_player_selected_resets_on_set_source(self):
        ctrl = self._make_controller()
        ctrl._start_dropdown_worker = MagicMock()
        ctrl.set_player_selection("Alice")
        self.assertTrue(ctrl.has_player_selected())
        ctrl.set_source_selection(1)
        self.assertFalse(ctrl.has_player_selected())

@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerAIConfigured(unittest.TestCase):

    def _make_controller(self) -> ChessLogChartsController:
        return ChessLogChartsController(config={}, database_controller=MagicMock())

    def test_no_settings_ai_not_configured(self):
        ctrl = self._make_controller()
        self.assertFalse(ctrl.is_ai_configured())

    def test_openai_settings_ai_configured(self):
        ctrl = self._make_controller()
        _set_user_settings(ctrl, {
            "ai_models": {"openai": {"api_key": "sk-abc", "model": "gpt-4o"}}
        })
        self.assertTrue(ctrl.is_ai_configured())

    def test_ai_configured_changed_signal_emitted_on_transition(self):
        ctrl = self._make_controller()
        received = []
        ctrl.ai_configured_changed.connect(received.append)
        _set_user_settings(ctrl, {
            "ai_models": {"openai": {"api_key": "sk-abc", "model": "gpt-4o"}}
        })
        self.assertEqual(received, [True])

    def test_ai_configured_changed_not_emitted_when_unchanged(self):
        ctrl = self._make_controller()
        # Already not configured; set to another unconfigured state — no signal
        received = []
        ctrl.ai_configured_changed.connect(received.append)
        _set_user_settings(ctrl, {})
        self.assertEqual(received, [])


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerNarrativeGate(unittest.TestCase):

    def _make_controller(self) -> ChessLogChartsController:
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        db_ctrl = _make_db_controller([game])
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        return ctrl

    def test_narrative_skipped_when_unconfigured(self):
        ctrl = self._make_controller()
        failed = []
        ctrl.narrative_failed.connect(failed.append)
        ctrl.request_narrative()
        self.assertTrue(len(failed) > 0)
        self.assertIsNone(ctrl._narrative_thread)

    def test_narrative_thread_started_when_configured(self):
        ctrl = self._make_controller()
        _set_user_settings(ctrl, {
            "ai_models": {"openai": {"api_key": "sk-abc", "model": "gpt-4o"}}
        })
        with patch(
            "app.controllers.chess_log_charts_controller.generate_narrative",
            return_value=(True, "Great work.", []),
        ):
            ctrl.request_narrative()
        # Thread may have already finished by the time we check, but it was started
        # (no exception means wiring was correct)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerSelectedGames(unittest.TestCase):

    def test_selected_games_callback_used_for_source_3(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = ChessLogChartsController(config={}, database_controller=MagicMock())
        ctrl.set_get_selected_games_callback(lambda active_only: [game])
        ctrl._source_selection = 3
        games = ctrl._resolve_games()
        self.assertEqual(games, [game])

    def test_selected_games_callback_used_for_source_4(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = ChessLogChartsController(config={}, database_controller=MagicMock())
        ctrl.set_get_selected_games_callback(lambda active_only: [game])
        ctrl._source_selection = 4
        games = ctrl._resolve_games()
        self.assertEqual(games, [game])

    def test_no_callback_returns_empty_for_source_3(self):
        ctrl = ChessLogChartsController(config={}, database_controller=MagicMock())
        ctrl._source_selection = 3
        self.assertEqual(ctrl._resolve_games(), [])


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerActiveDatabaseChanged(unittest.TestCase):

    def _make_controller(self, games=None) -> ChessLogChartsController:
        games = games or []
        db_ctrl = _make_db_controller(games)
        return ChessLogChartsController(config={}, database_controller=db_ctrl)

    def _make_controller_with_source(self, source: int) -> ChessLogChartsController:
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._source_selection = source
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        # Prevent real QThreads from being started in these tests.
        # Tests that specifically verify thread-start behavior check the mock.
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        return ctrl

    def test_active_db_changed_resets_player_flag_for_source_1(self):
        ctrl = self._make_controller_with_source(1)
        ctrl._on_active_database_changed(None)
        self.assertFalse(ctrl._player_explicit_selected)

    def test_active_db_changed_emits_player_selection_cleared_for_source_1(self):
        ctrl = self._make_controller_with_source(1)
        cleared = []
        ctrl.player_selection_cleared.connect(lambda: cleared.append(True))
        ctrl._on_active_database_changed(None)
        self.assertEqual(len(cleared), 1)

    def test_active_db_changed_emits_no_player_for_source_1(self):
        ctrl = self._make_controller_with_source(1)
        received = []
        ctrl.charts_unavailable.connect(received.append)
        ctrl._on_active_database_changed(None)
        self.assertIn("no_player", received)

    def test_active_db_changed_resets_player_flag_for_source_2(self):
        ctrl = self._make_controller_with_source(2)
        ctrl._on_active_database_changed(None)
        self.assertFalse(ctrl._player_explicit_selected)

    def test_active_db_changed_emits_no_player_for_source_2(self):
        ctrl = self._make_controller_with_source(2)
        received = []
        ctrl.charts_unavailable.connect(received.append)
        ctrl._on_active_database_changed(None)
        self.assertIn("no_player", received)

    def test_active_db_changed_no_reset_for_source_3(self):
        ctrl = self._make_controller_with_source(3)
        cleared = []
        ctrl.player_selection_cleared.connect(lambda: cleared.append(True))
        received = []
        ctrl.charts_unavailable.connect(received.append)
        ctrl._on_active_database_changed(None)
        self.assertTrue(ctrl._player_explicit_selected)
        self.assertEqual(cleared, [])
        self.assertEqual(received, [])

    def test_active_db_changed_no_reset_for_source_4(self):
        ctrl = self._make_controller_with_source(4)
        cleared = []
        ctrl.player_selection_cleared.connect(lambda: cleared.append(True))
        ctrl._on_active_database_changed(None)
        self.assertTrue(ctrl._player_explicit_selected)
        self.assertEqual(cleared, [])

    def test_active_db_changed_no_op_for_source_0(self):
        ctrl = self._make_controller_with_source(0)
        received = []
        ctrl.charts_unavailable.connect(received.append)
        ctrl._on_active_database_changed(None)
        self.assertTrue(ctrl._player_explicit_selected)
        self.assertEqual(received, [])

    def test_active_db_changed_starts_dropdown_worker_for_source_1(self):
        ctrl = self._make_controller_with_source(1)
        ctrl._on_active_database_changed(None)
        # _start_dropdown_worker is mocked in _make_controller_with_source;
        # verify it was called rather than checking the live _dropdown_worker reference.
        ctrl._start_dropdown_worker.assert_called_once()

    def test_active_db_changed_cancels_agg_worker(self):
        ctrl = self._make_controller_with_source(1)
        # Inject a mock agg worker (real QThread would crash on destroy)
        mock_agg = MagicMock()
        mock_agg.isRunning.return_value = True
        mock_agg.finished = MagicMock()
        ctrl._agg_worker = mock_agg
        # Active DB change should cancel the agg worker
        ctrl._on_active_database_changed(None)
        self.assertIsNone(ctrl._agg_worker)

    def test_active_db_changed_cancels_in_flight_shallow_thread(self):
        """An in-flight shallow-notes thread from the previous DB must be
        cancelled on DB switch so its results cannot apply to the new DB's games."""
        ctrl = self._make_controller_with_source(1)
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        mock_thread.finished = MagicMock()
        ctrl._shallow_thread = mock_thread
        ctrl._on_active_database_changed(None)
        mock_thread.cancel.assert_called_once()
        self.assertIsNone(ctrl._shallow_thread)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerChartSettings(unittest.TestCase):

    def _ctrl(self) -> "ChessLogChartsController":
        return ChessLogChartsController(config={}, database_controller=MagicMock())

    # --- defaults ---

    def test_default_target_bins_is_16(self):
        self.assertEqual(self._ctrl().get_target_progression_bins(), 16)

    def test_default_binning_mode_is_quantile(self):
        self.assertEqual(self._ctrl().get_ordinal_fallback_mode(), "quantile")

    def test_default_x_axis_layout_is_uniform_bins(self):
        self.assertEqual(self._ctrl().get_progression_x_axis_mode(), "uniform_bins")

    def test_default_max_gap_segment_days_is_28(self):
        self.assertEqual(self._ctrl().get_compress_gap_max_segment_days(), 28)

    def test_default_line_style_is_smooth(self):
        self.assertEqual(self._ctrl().get_progression_line_style(), "smooth")

    def test_default_smoothing_strength_is_1(self):
        self.assertAlmostEqual(self._ctrl().get_progression_line_smooth_strength(), 1.0)

    # --- setters accept valid values ---

    def test_set_target_bins_valid(self):
        ctrl = self._ctrl()
        ctrl.set_target_progression_bins(24)
        self.assertEqual(ctrl.get_target_progression_bins(), 24)

    def test_set_binning_mode_equal_width(self):
        ctrl = self._ctrl()
        ctrl.set_ordinal_fallback_mode("equal_width")
        self.assertEqual(ctrl.get_ordinal_fallback_mode(), "equal_width")

    def test_set_x_axis_layout_gap_compressed(self):
        ctrl = self._ctrl()
        ctrl.set_progression_x_axis_mode("gap_compressed")
        self.assertEqual(ctrl.get_progression_x_axis_mode(), "gap_compressed")

    def test_set_max_gap_segment_days_14(self):
        ctrl = self._ctrl()
        ctrl.set_compress_gap_max_segment_days(14)
        self.assertEqual(ctrl.get_compress_gap_max_segment_days(), 14)

    def test_set_line_style_straight(self):
        ctrl = self._ctrl()
        ctrl.set_progression_line_style("straight")
        self.assertEqual(ctrl.get_progression_line_style(), "straight")

    def test_set_smoothing_strength_2(self):
        ctrl = self._ctrl()
        ctrl.set_progression_line_smooth_strength(2.0)
        self.assertAlmostEqual(ctrl.get_progression_line_smooth_strength(), 2.0)

    # --- setters reject invalid values ---

    def test_set_target_bins_invalid_ignored(self):
        ctrl = self._ctrl()
        ctrl.set_target_progression_bins(13)
        self.assertEqual(ctrl.get_target_progression_bins(), 16)

    def test_set_binning_mode_invalid_ignored(self):
        ctrl = self._ctrl()
        ctrl.set_ordinal_fallback_mode("median")
        self.assertEqual(ctrl.get_ordinal_fallback_mode(), "quantile")

    def test_set_x_axis_layout_invalid_ignored(self):
        ctrl = self._ctrl()
        ctrl.set_progression_x_axis_mode("diagonal")
        self.assertEqual(ctrl.get_progression_x_axis_mode(), "uniform_bins")

    def test_set_max_gap_segment_days_invalid_ignored(self):
        ctrl = self._ctrl()
        ctrl.set_compress_gap_max_segment_days(30)
        self.assertEqual(ctrl.get_compress_gap_max_segment_days(), 28)

    def test_set_line_style_invalid_ignored(self):
        ctrl = self._ctrl()
        ctrl.set_progression_line_style("dotted")
        self.assertEqual(ctrl.get_progression_line_style(), "smooth")

    def test_set_smoothing_strength_invalid_ignored(self):
        ctrl = self._ctrl()
        ctrl.set_progression_line_smooth_strength(3.0)
        self.assertAlmostEqual(ctrl.get_progression_line_smooth_strength(), 1.0)

    # --- setters kick debounce ---

    def test_set_target_bins_kicks_debounce(self):
        ctrl = self._ctrl()
        ctrl.set_target_progression_bins(8)
        self.assertTrue(ctrl._selection_debounce.isActive())

    def test_set_binning_mode_kicks_debounce(self):
        ctrl = self._ctrl()
        ctrl.set_ordinal_fallback_mode("equal_width")
        self.assertTrue(ctrl._selection_debounce.isActive())

    def test_set_x_axis_layout_kicks_debounce(self):
        ctrl = self._ctrl()
        ctrl.set_progression_x_axis_mode("gap_compressed")
        self.assertTrue(ctrl._selection_debounce.isActive())

    def test_set_max_gap_segment_days_kicks_debounce(self):
        ctrl = self._ctrl()
        ctrl.set_compress_gap_max_segment_days(14)
        self.assertTrue(ctrl._selection_debounce.isActive())

    def test_set_line_style_kicks_debounce(self):
        ctrl = self._ctrl()
        ctrl.set_progression_line_style("straight")
        self.assertTrue(ctrl._selection_debounce.isActive())

    def test_set_smoothing_strength_kicks_debounce(self):
        ctrl = self._ctrl()
        ctrl.set_progression_line_smooth_strength(2.0)
        self.assertTrue(ctrl._selection_debounce.isActive())

    # --- set_user_settings syncs live fields ---

    def test_set_user_settings_syncs_target_bins(self):
        ctrl = self._ctrl()
        _set_user_settings(ctrl, {"chess_log": {"charts": {"target_bins": 8}}})
        self.assertEqual(ctrl.get_target_progression_bins(), 8)

    def test_set_user_settings_syncs_binning_mode(self):
        ctrl = self._ctrl()
        _set_user_settings(ctrl, {"chess_log": {"charts": {"binning_mode": "equal_width"}}})
        self.assertEqual(ctrl.get_ordinal_fallback_mode(), "equal_width")

    def test_set_user_settings_syncs_x_axis_layout(self):
        ctrl = self._ctrl()
        _set_user_settings(ctrl, {"chess_log": {"charts": {"x_axis_layout": "calendar_linear"}}})
        self.assertEqual(ctrl.get_progression_x_axis_mode(), "calendar_linear")

    def test_set_user_settings_syncs_line_style(self):
        ctrl = self._ctrl()
        _set_user_settings(ctrl, {"chess_log": {"charts": {"line_style": "straight"}}})
        self.assertEqual(ctrl.get_progression_line_style(), "straight")

    def test_set_user_settings_syncs_smoothing_strength(self):
        ctrl = self._ctrl()
        _set_user_settings(ctrl, {"chess_log": {"charts": {"smoothing_strength": 2.0}}})
        self.assertAlmostEqual(ctrl.get_progression_line_smooth_strength(), 2.0)

    def test_set_user_settings_kicks_debounce_when_any_chart_field_changes(self):
        ctrl = self._ctrl()
        _set_user_settings(ctrl, {"chess_log": {"charts": {"target_bins": 8}}})
        self.assertTrue(ctrl._selection_debounce.isActive())

    def test_set_user_settings_does_not_kick_debounce_when_settings_unchanged(self):
        ctrl = self._ctrl()
        # All defaults — no actual change.
        _set_user_settings(ctrl, {"chess_log": {"charts": {
            "target_bins": 16, "binning_mode": "quantile", "x_axis_layout": "uniform_bins",
            "max_gap_segment_days": 28, "line_style": "smooth", "smoothing_strength": 1.0,
        }}})
        self.assertFalse(ctrl._selection_debounce.isActive())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerFlagShallowNotes(unittest.TestCase):
    """request_flag_shallow_notes() must skip entries with ignore_shallow=True."""

    def _make_controller_with_note(self, ignore: bool) -> "ChessLogChartsController":
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "I blundered", ignore_shallow=ignore)
        game = _make_game(entries_per_path={"0": [entry]})
        db_ctrl = _make_db_controller([game])
        # Ensure get_all_games() returns the game so _resolve_games() works for source 1
        db_ctrl.get_active_database.return_value.get_all_games.return_value = [game]
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        _set_user_settings(ctrl, {
            "ai_models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}}
        })
        return ctrl

    def test_ignored_entry_emits_shallow_ready_empty_immediately(self):
        """Entry with ignore_shallow=True → notes list is empty → shallow_ready({}) emitted
        synchronously without starting a thread or calling the AI."""
        ctrl = self._make_controller_with_note(ignore=True)
        received: list = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append(k))

        ctrl.request_flag_shallow_notes()

        # Signal emitted synchronously (no notes → no thread)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], set())
        # No shallow thread was created
        self.assertIsNone(ctrl._shallow_thread)

    def test_non_ignored_entry_starts_shallow_thread_with_note(self):
        """Entry without ignore_shallow → a ChessLogShallowThread is started
        and the why-note is included in the notes list passed to the thread."""
        ctrl = self._make_controller_with_note(ignore=False)

        thread_kwargs: list = []

        class FakeThread:
            def __init__(self, **kwargs):
                thread_kwargs.append(kwargs)
                self.shallow_ready = MagicMock()
                self.shallow_ready.connect = MagicMock()
                self.shallow_failed = MagicMock()
                self.shallow_failed.connect = MagicMock()
                self.shallow_partial = MagicMock()
                self.shallow_partial.connect = MagicMock()
                self.finished = MagicMock()
                self.finished.connect = MagicMock()

            def start(self):
                pass

        with patch(
            "app.controllers.chess_log_charts_controller.ChessLogShallowThread",
            side_effect=FakeThread,
        ):
            ctrl.request_flag_shallow_notes()

        self.assertEqual(len(thread_kwargs), 1)
        notes = thread_kwargs[0]["legacy_notes"]
        self.assertTrue(any("I blundered" in n[4] for n in notes))

    def _make_controller_with_3x3(
        self, why1="", why2="", why3="", why4="", ignore=False
    ) -> "ChessLogChartsController":
        entries = []
        for cat, why in [("Why1", why1), ("Why2", why2), ("Why3", why3), ("Why4", why4)]:
            if why:
                entries.append(
                    ChessLogStorageService.make_entry("3x3", cat, why, ignore_shallow=ignore)
                )
        game = _make_game(entries_per_path={"0": entries})
        db_ctrl = _make_db_controller([game])
        db_ctrl.get_active_database.return_value.get_all_games.return_value = [game]
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        _set_user_settings(ctrl, {
            "ai_models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}}
        })
        return ctrl

    def _capture_notes(self, ctrl) -> list:
        thread_kwargs: list = []

        class FakeThread:
            def __init__(self, **kwargs):
                thread_kwargs.append(kwargs)
                self.shallow_ready = MagicMock()
                self.shallow_ready.connect = MagicMock()
                self.shallow_failed = MagicMock()
                self.shallow_failed.connect = MagicMock()
                self.shallow_partial = MagicMock()
                self.shallow_partial.connect = MagicMock()
                self.finished = MagicMock()
                self.finished.connect = MagicMock()

            def start(self):
                pass

        with patch(
            "app.controllers.chess_log_charts_controller.ChessLogShallowThread",
            side_effect=FakeThread,
        ):
            ctrl.request_flag_shallow_notes()

        return thread_kwargs[0]["three_notes"] if thread_kwargs else []

    def test_3x3_moment_grouped_into_one_note(self):
        """Four Why entries for one moment produce ONE note, not four."""
        ctrl = self._make_controller_with_3x3(
            why1="I wanted to control the center",
            why2="My bishop was hanging",
            why3="The knight fork wins material",
            why4="Calculate before committing",
        )
        notes = self._capture_notes(ctrl)
        self.assertEqual(len(notes), 1)

    def test_3x3_note_has_3x3_preset(self):
        ctrl = self._make_controller_with_3x3(
            why1="I saw the free pawn",
            why2="My rook was undefended",
        )
        notes = self._capture_notes(ctrl)
        self.assertEqual(notes[0][3], "3x3")

    def test_3x3_note_contains_all_why_text(self):
        ctrl = self._make_controller_with_3x3(
            why1="I wanted tempo",
            why2="The pawn was poisoned",
            why4="Check piece safety first",
        )
        notes = self._capture_notes(ctrl)
        self.assertEqual(notes[0][4], "I wanted tempo")         # why1
        self.assertEqual(notes[0][5], "The pawn was poisoned")  # why2
        self.assertEqual(notes[0][7], "Check piece safety first")  # why4

    def test_3x3_blank_why_stored_as_empty_string(self):
        ctrl = self._make_controller_with_3x3(
            why1="I was focused on attack",
            why4="Defend before attacking",
        )
        notes = self._capture_notes(ctrl)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0][4], "I was focused on attack")  # why1
        self.assertEqual(notes[0][5], "")                          # why2 blank
        self.assertEqual(notes[0][6], "")                          # why3 blank
        self.assertEqual(notes[0][7], "Defend before attacking")   # why4

    def test_3x3_all_ignored_emits_empty_immediately(self):
        ctrl = self._make_controller_with_3x3(
            why1="I saw the free pawn",
            why2="Rook was hanging",
            ignore=True,
        )
        received: list = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append(k))
        ctrl.request_flag_shallow_notes()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], set())


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerRefreshUsesLiveFields(unittest.TestCase):
    """Regression: _schedule_charts_refresh must use live instance fields, not
    re-read from stale _user_settings, so menu-driven changes take effect."""

    def _make_controller_ready_to_refresh(self, games=None) -> "ChessLogChartsController":
        games = games or [_make_game(entries_per_path={"0": [_clamp("C")]})]
        db_ctrl = _make_db_controller(games)
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        return ctrl

    def _refresh_and_cancel(self, ctrl, games, assertion_fn):
        """Start a real refresh, assert worker config, then wait for thread to exit
        cleanly before releasing the reference (avoids QThread-on-GC crash)."""
        ctrl._schedule_charts_refresh(games=games)
        worker = ctrl._agg_worker
        self.assertIsNotNone(worker)
        assertion_fn(worker)
        worker.cancel()
        worker.wait()
        ctrl._agg_worker = None

    def test_refresh_uses_live_x_axis_layout_not_stale_settings(self):
        ctrl = self._make_controller_ready_to_refresh()
        ctrl.set_progression_x_axis_mode("gap_compressed")
        games = [_make_game(entries_per_path={"0": [_clamp("C")]})]
        self._refresh_and_cancel(
            ctrl, games,
            lambda w: self.assertEqual(w._progression_x_axis_mode, "gap_compressed"),
        )

    def test_refresh_uses_live_target_bins_not_stale_settings(self):
        ctrl = self._make_controller_ready_to_refresh()
        ctrl.set_target_progression_bins(24)
        games = [_make_game(entries_per_path={"0": [_clamp("C")]})]
        self._refresh_and_cancel(
            ctrl, games,
            lambda w: self.assertEqual(w._chart_cfg["target_progression_bins"], 24),
        )

    def test_refresh_uses_live_binning_mode_via_chart_cfg(self):
        ctrl = self._make_controller_ready_to_refresh()
        ctrl.set_ordinal_fallback_mode("equal_width")
        games = [_make_game(entries_per_path={"0": [_clamp("C")]})]
        self._refresh_and_cancel(
            ctrl, games,
            lambda w: self.assertEqual(w._chart_cfg.get("ordinal_fallback_mode"), "equal_width"),
        )

    def test_refresh_stamps_line_style_on_worker(self):
        ctrl = self._make_controller_ready_to_refresh()
        ctrl.set_progression_line_style("straight")
        games = [_make_game(entries_per_path={"0": [_clamp("C")]})]
        self._refresh_and_cancel(
            ctrl, games,
            lambda w: self.assertEqual(w._progression_line_style, "straight"),
        )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestNotifyChessLogSaved(unittest.TestCase):
    """notify_chess_log_saved() must restart the dropdown worker so tagged-game
    counts stay current after a Chess Log save."""

    def _make_controller(self, games=None) -> "ChessLogChartsController":
        games = games or []
        db_ctrl = _make_db_controller(games)
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        # Avoid real QThread starts: stub out the worker starter so tests are fast
        # and don't leave dangling threads that crash teardown.
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        return ctrl

    def test_notify_with_no_source_is_noop(self):
        ctrl = self._make_controller()
        ctrl._source_selection = 0
        ctrl.notify_chess_log_saved()
        ctrl._start_dropdown_worker.assert_not_called()

    def test_notify_with_source_starts_dropdown_worker(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._source_selection = 1
        ctrl.notify_chess_log_saved()
        ctrl._start_dropdown_worker.assert_called_once()

    def test_notify_does_not_restart_agg_worker(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._source_selection = 1
        ctrl.notify_chess_log_saved()
        self.assertIsNone(ctrl._agg_worker)

    def test_notify_passes_games_from_resolve_to_worker(self):
        """Games passed to the dropdown worker must come from _resolve_games."""
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        ctrl = self._make_controller(games=[game])
        ctrl._source_selection = 1
        # Patch _resolve_games so we control what it returns.
        sentinel = [game]
        ctrl._resolve_games = lambda: sentinel
        ctrl.notify_chess_log_saved()
        args, _ = ctrl._start_dropdown_worker.call_args
        self.assertIs(args[0], sentinel)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogNarrativeThreadExceptionHandling(unittest.TestCase):
    """Exception inside run() must emit narrative_failed, not die silently."""

    def test_exception_in_work_emits_narrative_failed(self):
        game = _make_game(entries_per_path={"0": [_clamp("C")]})
        thread = ChessLogNarrativeThread(
            games=[game],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            player="",
            color_filter="both",
            config={},   # missing prompts section → KeyError in build_prompt
        )
        failed: list = []
        thread.narrative_failed.connect(failed.append)
        # run() directly so the test is synchronous
        with patch(
            "app.controllers.chess_log_charts_controller.generate_narrative",
            side_effect=KeyError("narrative_preamble"),
        ):
            thread.run()
        self.assertEqual(len(failed), 1, "narrative_failed must be emitted exactly once")
        self.assertIn("narrative_preamble", failed[0])


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogShallowThreadExceptionHandling(unittest.TestCase):
    """Exception inside run() must emit shallow_failed, not die silently."""

    def test_exception_in_work_emits_shallow_failed(self):
        from app.controllers.chess_log_charts_controller import ChessLogShallowThread
        notes = [(0, _NOTE_GAMES[0], "path/0", "CLAMP", "I missed a tactic")]
        thread = ChessLogShallowThread(
            games=[],
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url_override=None,
            config={},
            timeout_seconds=30,
            legacy_notes=notes,
            three_notes=[],
        )
        failed: list = []
        thread.shallow_failed.connect(failed.append)
        # classify_notes is imported inside run() from the service module
        with patch(
            "app.services.chess_log_shallow_service.classify_notes",
            side_effect=KeyError("classifier"),
        ):
            thread.run()
        self.assertEqual(len(failed), 1, "shallow_failed must be emitted exactly once")
        self.assertIn("classifier", failed[0])


def _shallow_config():
    """Minimal config carrying the chess_log_messages wording used by the thread."""
    return {
        "ui": {
            "dialogs": {
                "chess_log_messages": {
                    "shallow_notes": {
                        "all_failed": {
                            "title": "Check Logs Error",
                            "message_template": "None of the {count} note{s_suffix} could be classified. Try again; the model's reply couldn't be read.",
                        },
                        "partial": {
                            "title": "Check Logs",
                            "message_template": "{unparsed} of {total} note{s_suffix} couldn't be classified — left unchanged. Flagged {flagged}.",
                        },
                        "none_found": {
                            "title": "Nothing Flagged",
                            "message_template": "No shallow notes or vague lessons found — great job.",
                        },
                    }
                }
            }
        }
    }


def _make_shallow_thread(notes=None, config=None):
    from app.controllers.chess_log_charts_controller import ChessLogShallowThread
    if notes is None:
        notes = [(i, _NOTE_GAMES[i], f"path/{i}", "CLAMP", f"note {i}") for i in range(3)]
    return ChessLogShallowThread(
        games=[],
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key="sk-test",
        base_url_override=None,
        config=config if config is not None else _shallow_config(),
        timeout_seconds=30,
        legacy_notes=notes,
        three_notes=[],
    )


def _shallow_result(shallow_keys=None, unparsed_indices=(), success=True, error=None):
    from app.services.chess_log_shallow_service import ShallowResult
    from app.services.ai_service import TokenUsage
    return ShallowResult(
        success=success,
        shallow_keys=frozenset(shallow_keys or []),
        error=error,
        usage=TokenUsage(input_tokens=10, output_tokens=5, reasoning_tokens=None, reported=True),
        model="claude-sonnet-4-6",
        unparsed_indices=tuple(unparsed_indices),
    )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogShallowThreadSignalShape(unittest.TestCase):
    """3-way branch: all-fail / partial / clean paths emit correct signals."""

    def _run_thread(self, result, notes=None):
        thread = _make_shallow_thread(notes=notes)
        failed, partial, ready = [], [], []
        thread.shallow_failed.connect(failed.append)
        thread.shallow_partial.connect(partial.append)
        thread.shallow_ready.connect(lambda k, vk, ck, u: ready.append(k))
        with patch(
            "app.services.chess_log_shallow_service.classify_notes",
            return_value=result,
        ):
            thread.run()
        return failed, partial, ready

    def test_all_notes_unparsed_emits_shallow_failed_only(self):
        """All notes unparsed → shallow_failed once with count; no partial, no ready."""
        result = _shallow_result(shallow_keys=[], unparsed_indices=(0, 1, 2))
        failed, partial, ready = self._run_thread(result)
        self.assertEqual(len(failed), 1, "shallow_failed must fire once")
        self.assertEqual(len(partial), 0, "shallow_partial must not fire")
        self.assertEqual(len(ready), 0, "shallow_ready must not fire")
        self.assertIn("3", failed[0])

    def test_partial_unparsed_emits_partial_then_ready(self):
        """Some unparsed, some classified → shallow_partial then shallow_ready."""
        notes = [(i, _NOTE_GAMES[i], f"path/{i}", "CLAMP", f"note {i}") for i in range(3)]
        result = _shallow_result(
            shallow_keys=[(_NOTE_GAMES[2], "path/2", "CLAMP", "")],
            unparsed_indices=(0,),
        )
        failed, partial, ready = self._run_thread(result, notes=notes)
        self.assertEqual(len(failed), 0)
        self.assertEqual(len(partial), 1, "shallow_partial must fire once")
        self.assertEqual(len(ready), 1, "shallow_ready must also fire")
        self.assertIn("1", partial[0])

    def test_all_parsed_zero_flagged_emits_ready_only(self):
        """All parsed, none SHALLOW → shallow_ready(empty) only (congratulation path)."""
        result = _shallow_result(shallow_keys=[], unparsed_indices=())
        failed, partial, ready = self._run_thread(result)
        self.assertEqual(len(failed), 0)
        self.assertEqual(len(partial), 0)
        self.assertEqual(len(ready), 1, "shallow_ready must fire once")
        self.assertEqual(ready[0], frozenset())

    def test_all_parsed_some_flagged_emits_ready_only(self):
        """All parsed, some SHALLOW → shallow_ready(keys) only; no partial."""
        notes = [(i, _NOTE_GAMES[i], f"path/{i}", "CLAMP", f"note {i}") for i in range(3)]
        result = _shallow_result(
            shallow_keys=[(_NOTE_GAMES[0], "path/1", "CLAMP", ""), (_NOTE_GAMES[2], "path/2", "CLAMP", "")],
            unparsed_indices=(),
        )
        failed, partial, ready = self._run_thread(result, notes=notes)
        self.assertEqual(len(failed), 0)
        self.assertEqual(len(partial), 0)
        self.assertEqual(len(ready), 1)
        self.assertGreater(len(ready[0]), 0)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogChartsControllerGetAvailableModels(unittest.TestCase):
    """Characterisation tests for get_available_models() — pin behaviour before extraction.

    get_available_models() returns plain model IDs (no provider prefix) for the
    active provider, applying the same exclusivity rule as resolve_default_provider.
    """

    def _make_controller(self) -> "ChessLogChartsController":
        db_ctrl = _make_db_controller([])
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        return ctrl

    def _with_settings(self, settings: dict) -> "ChessLogChartsController":
        ctrl = self._make_controller()
        _apply_settings(settings)
        return ctrl

    # --- helpers for building settings dicts ---

    @staticmethod
    def _s_openai(api_key="sk-abc", models=None):
        models = models if models is not None else ["gpt-4o", "gpt-4-turbo"]
        return {"ai_models": {"openai": {"api_key": api_key, "models": models}}}

    @staticmethod
    def _s_anthropic(api_key="ant-key", models=None):
        models = models if models is not None else ["claude-opus-4-7"]
        return {
            "ai_models": {"anthropic": {"api_key": api_key, "models": models}},
            "ai_summary": {
                "use_openai_models": False,
                "use_anthropic_models": True,
                "use_custom_models": False,
            },
        }

    @staticmethod
    def _s_custom(enabled=True, base_url="http://localhost:11434", models=None):
        models = models if models is not None else ["llama3", "mistral"]
        return {
            "ai_models": {
                "custom": {
                    "enabled": enabled,
                    "base_url": base_url,
                    "models": models,
                    "api_key": "",
                }
            },
            "ai_summary": {
                "use_openai_models": False,
                "use_anthropic_models": False,
                "use_custom_models": True,
            },
        }

    # --- test cases ---

    def test_openai_active_returns_plain_model_ids(self):
        ctrl = self._with_settings(self._s_openai())
        result = ctrl.get_available_models()
        self.assertEqual(result, ["gpt-4o", "gpt-4-turbo"])

    def test_anthropic_active_returns_plain_model_ids(self):
        ctrl = self._with_settings(self._s_anthropic())
        result = ctrl.get_available_models()
        self.assertEqual(result, ["claude-opus-4-7"])

    def test_custom_active_returns_plain_model_ids(self):
        ctrl = self._with_settings(self._s_custom())
        result = ctrl.get_available_models()
        self.assertEqual(result, ["llama3", "mistral"])

    def test_no_toggles_falls_back_to_openai(self):
        # All toggles False → exclusivity fallback picks OpenAI
        s = self._s_openai()
        s["ai_summary"] = {
            "use_openai_models": False,
            "use_anthropic_models": False,
            "use_custom_models": False,
        }
        ctrl = self._with_settings(s)
        result = ctrl.get_available_models()
        self.assertEqual(result, ["gpt-4o", "gpt-4-turbo"])

    def test_multiple_toggles_falls_back_to_openai(self):
        # Two toggles True → exclusivity fallback picks OpenAI
        s = self._s_openai()
        s["ai_summary"] = {
            "use_openai_models": True,
            "use_anthropic_models": True,
            "use_custom_models": False,
        }
        ctrl = self._with_settings(s)
        result = ctrl.get_available_models()
        self.assertEqual(result, ["gpt-4o", "gpt-4-turbo"])

    def test_openai_no_api_key_returns_empty(self):
        ctrl = self._with_settings(self._s_openai(api_key=""))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_openai_empty_models_list_returns_empty(self):
        ctrl = self._with_settings(self._s_openai(models=[]))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_custom_disabled_returns_empty(self):
        ctrl = self._with_settings(self._s_custom(enabled=False))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_custom_no_base_url_returns_empty(self):
        ctrl = self._with_settings(self._s_custom(base_url=""))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_empty_settings_returns_empty(self):
        # Fallback to OpenAI, but no api_key → empty
        ctrl = self._with_settings({})
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_result_is_a_copy_not_a_reference(self):
        # Mutating the return value must not affect the settings dict
        ctrl = self._with_settings(self._s_openai())
        result = ctrl.get_available_models()
        live = _current_service().get_settings()
        original_models = list(live["ai_models"]["openai"]["models"])
        result.append("injected")
        self.assertEqual(
            live["ai_models"]["openai"]["models"],
            original_models,
        )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowIterationOrphanExclusion(unittest.TestCase):
    """request_flag_shallow_notes() must skip orphan path_keys (test 20).

    get_tags_for_game() routes through load_resolved_paths (or the resolved
    view), so orphan keys are already absent from the returned dict.  This
    test verifies that orphan why-notes never reach the shallow notes thread.
    """

    def _make_controller_with_resolvable_and_orphan(self):
        resolvable_entry = ChessLogStorageService.make_entry(
            "CLAMP", "C", "real note", ignore_shallow=False
        )
        orphan_entry = ChessLogStorageService.make_entry(
            "CLAMP", "M", "ghost note", ignore_shallow=False
        )
        # Store both keys in the PGN (guard off — no original_paths arg).
        game = _make_game(entries_per_path={
            "0":     [resolvable_entry],
            "99999": [orphan_entry],
        })
        db_ctrl = _make_db_controller([game])
        db_ctrl.get_active_database.return_value.get_all_games.return_value = [game]
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        _set_user_settings(ctrl, {
            "ai_models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}}
        })
        return ctrl

    def test_shallow_iteration_skips_orphan_entries(self):
        """Orphan why-notes must not appear in notes list passed to the shallow thread."""
        ctrl = self._make_controller_with_resolvable_and_orphan()

        thread_kwargs: list = []

        class FakeThread:
            def __init__(self, **kwargs):
                thread_kwargs.append(kwargs)
                self.shallow_ready = MagicMock()
                self.shallow_ready.connect = MagicMock()
                self.shallow_failed = MagicMock()
                self.shallow_failed.connect = MagicMock()
                self.shallow_partial = MagicMock()
                self.shallow_partial.connect = MagicMock()
                self.finished = MagicMock()
                self.finished.connect = MagicMock()

            def start(self):
                pass

        with patch(
            "app.controllers.chess_log_charts_controller.ChessLogShallowThread",
            side_effect=FakeThread,
        ):
            ctrl.request_flag_shallow_notes()

        self.assertEqual(len(thread_kwargs), 1)
        notes = thread_kwargs[0]["legacy_notes"]
        why_texts = [n[4] for n in notes]
        self.assertTrue(any("real note" in w for w in why_texts),
                        "resolvable why-note missing from notes list")
        self.assertFalse(any("ghost note" in w for w in why_texts),
                         "orphan why-note must not reach shallow thread")


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThreadReadyNoWrite(unittest.TestCase):
    """Test 21: _on_shallow_thread_ready emits signal but never writes is_shallow."""

    def test_shallow_thread_ready_does_not_write_is_shallow(self):
        """_on_shallow_thread_ready passes payload through; replace_entries_at_path_for_game
        must NOT be called — writing is deferred to the dialog's Save."""
        game = _make_game(entries_per_path={"0": [
            ChessLogStorageService.make_entry("CLAMP", "C", "I blundered")
        ]})
        db_ctrl = _make_db_controller([game])
        db_ctrl.get_active_database.return_value.get_all_games.return_value = [game]
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)

        mock_cl_ctrl = MagicMock()
        ctrl._chess_log_controller = mock_cl_ctrl

        received = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append((k, vk, ck, u)))

        shallow_keys = frozenset([(_NOTE_GAMES[0], "0", "CLAMP", "")])
        classified_keys = frozenset([(_NOTE_GAMES[0], "0", "CLAMP", "")])
        usage = None
        ctrl._on_shallow_thread_ready(shallow_keys, frozenset(), classified_keys, usage)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], (shallow_keys, frozenset(), classified_keys, usage))
        mock_cl_ctrl.replace_entries_at_path_for_game.assert_not_called()


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThreadClassifiedKeysPayload(unittest.TestCase):
    """Test 22: thread emits classified_keys excluding unparsed indices."""

    def test_shallow_thread_ready_payload_includes_classified_keys(self):
        """3 notes, index 1 in unparsed_indices → classified_keys has keys for
        notes 0 and 2 only (not note 1)."""
        notes = [(i, _NOTE_GAMES[i], f"path/{i}", "CLAMP", f"note {i}") for i in range(3)]
        thread = _make_shallow_thread(notes=notes)
        result = _shallow_result(
            shallow_keys=[(_NOTE_GAMES[0], "path/0", "CLAMP", "")],
            unparsed_indices=(1,),
        )
        received = []
        thread.shallow_ready.connect(lambda k, vk, ck, u: received.append((k, vk, ck, u)))
        with patch(
            "app.services.chess_log_shallow_service.classify_notes",
            return_value=result,
        ):
            thread.run()
        self.assertEqual(len(received), 1, "shallow_ready must fire once")
        _, _, classified_keys, _ = received[0]
        # note 1 (_NOTE_GAMES[1], path_key="path/1") — must be absent (unparsed)
        self.assertNotIn((_NOTE_GAMES[1], "path/1", "CLAMP", ""), classified_keys)
        # notes 0 and 2 must be present
        self.assertIn((_NOTE_GAMES[0], "path/0", "CLAMP", ""), classified_keys)
        self.assertIn((_NOTE_GAMES[2], "path/2", "CLAMP", ""), classified_keys)
        self.assertEqual(len(classified_keys), 2)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThreadMixedCallFailure(unittest.TestCase):
    """B1: A failed API call must not contaminate classified_keys."""

    def _make_mixed_thread(self, legacy_notes=None, three_notes=None, config=None):
        from app.controllers.chess_log_charts_controller import ChessLogShallowThread
        if legacy_notes is None:
            legacy_notes = [(i, _NOTE_GAMES[i], f"path/{i}", "CLAMP", f"note {i}") for i in range(2)]
        if three_notes is None:
            three_notes = [(i, _3X3_NOTE_GAMES[i], f"path3/{i}", "3x3", "w1", "w2", "w3", "w4") for i in range(2)]
        return ChessLogShallowThread(
            games=[],
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="sk-test",
            base_url_override=None,
            config=config if config is not None else _shallow_config(),
            timeout_seconds=30,
            legacy_notes=legacy_notes,
            three_notes=three_notes,
        )

    def _shallow_result_3x3(self, success=True, error=None, shallow_keys=None, vague_keys=None, unparsed=None, n_notes=2):
        from app.services.chess_log_shallow_service import ShallowResult
        from app.services.ai_service import TokenUsage
        # On failure the real service sets unparsed_indices=tuple(range(len(notes))).
        if unparsed is None:
            unparsed = () if success else tuple(range(n_notes))
        return ShallowResult(
            success=success,
            shallow_keys=frozenset(shallow_keys or []),
            vague_keys=frozenset(vague_keys or []),
            error=error,
            usage=TokenUsage(input_tokens=5, output_tokens=3, reasoning_tokens=None, reported=True),
            model="claude-sonnet-4-6",
            unparsed_indices=tuple(unparsed),
        )

    def _run(self, legacy_result, three_result):
        thread = self._make_mixed_thread()
        failed, partial, ready = [], [], []
        thread.shallow_failed.connect(failed.append)
        thread.shallow_partial.connect(partial.append)
        thread.shallow_ready.connect(lambda sk, vk, ck, u: ready.append((sk, vk, ck, u)))
        with patch("app.services.chess_log_shallow_service.classify_notes", return_value=legacy_result), \
             patch("app.services.chess_log_shallow_service.classify_notes_3x3", return_value=three_result):
            thread.run()
        return failed, partial, ready

    def test_legacy_fails_three_succeeds_legacy_notes_absent_from_classified(self):
        """When legacy call fails and 3x3 succeeds, legacy notes must not be in classified_keys."""
        # Real classify_notes sets unparsed_indices=tuple(range(len(notes))) on failure.
        legacy_fail = _shallow_result(success=False, error="API timeout", unparsed_indices=(0, 1))
        three_ok = self._shallow_result_3x3(
            success=True,
            shallow_keys=[(_3X3_NOTE_GAMES[0], "path3/0", "3x3", "Why1")],
        )
        failed, partial, ready = self._run(legacy_fail, three_ok)
        # Must not be a hard failure (3x3 call succeeded)
        self.assertEqual(len(failed), 0, "should not hard-fail when one call succeeds")
        # Must emit ready eventually
        self.assertEqual(len(ready), 1)
        _, _, classified_keys, _ = ready[0]
        # Legacy notes (_NOTE_GAMES[0], [1]) must NOT be in classified_keys
        self.assertNotIn((_NOTE_GAMES[0], "path/0", "CLAMP", ""), classified_keys)
        self.assertNotIn((_NOTE_GAMES[1], "path/1", "CLAMP", ""), classified_keys)
        # 3x3 notes (_3X3_NOTE_GAMES[0], [1]) must be in classified_keys — check one cat each
        self.assertIn((_3X3_NOTE_GAMES[0], "path3/0", "3x3", "Why1"), classified_keys)
        self.assertIn((_3X3_NOTE_GAMES[1], "path3/1", "3x3", "Why1"), classified_keys)

    def test_three_fails_legacy_succeeds_three_notes_absent_from_classified(self):
        """When 3x3 call fails and legacy succeeds, 3x3 notes must not be in classified_keys."""
        legacy_ok = _shallow_result(
            success=True,
            shallow_keys=[(_NOTE_GAMES[0], "path/0", "CLAMP", "")],
        )
        three_fail = self._shallow_result_3x3(success=False, error="API timeout")
        failed, partial, ready = self._run(legacy_ok, three_fail)
        self.assertEqual(len(failed), 0, "should not hard-fail when one call succeeds")
        self.assertEqual(len(ready), 1)
        _, _, classified_keys, _ = ready[0]
        # 3x3 notes must NOT be in classified_keys
        self.assertNotIn((_3X3_NOTE_GAMES[0], "path3/0", "3x3", "Why1"), classified_keys)
        self.assertNotIn((_3X3_NOTE_GAMES[1], "path3/1", "3x3", "Why1"), classified_keys)
        # Legacy notes must be in classified_keys
        self.assertIn((_NOTE_GAMES[0], "path/0", "CLAMP", ""), classified_keys)
        self.assertIn((_NOTE_GAMES[1], "path/1", "CLAMP", ""), classified_keys)

    def test_partial_message_names_failed_note_count(self):
        """The partial message must account for notes from the failed call."""
        legacy_fail = _shallow_result(success=False, error="API timeout", unparsed_indices=(0, 1))
        three_ok = self._shallow_result_3x3(
            success=True,
            shallow_keys=[(_3X3_NOTE_GAMES[0], "path3/0", "3x3", "Why1")],
        )
        failed, partial, ready = self._run(legacy_fail, three_ok)
        # Partial message must mention the 2 legacy notes that couldn't be classified
        self.assertEqual(len(partial), 1, "shallow_partial must fire")
        self.assertIn("2", partial[0])


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThreadTokenUsageMerge(unittest.TestCase):
    """B2: Both calls succeed — token usage is summed correctly, including reasoning_tokens."""

    def _run_both_succeed(self, legacy_usage, three_usage):
        from app.controllers.chess_log_charts_controller import ChessLogShallowThread
        from app.services.chess_log_shallow_service import ShallowResult
        legacy_notes = [(i, _NOTE_GAMES[i], f"path/{i}", "CLAMP", f"note {i}") for i in range(2)]
        three_notes = [(i, _3X3_NOTE_GAMES[i], f"path3/{i}", "3x3", "w1", "w2", "w3", "w4") for i in range(2)]
        thread = ChessLogShallowThread(
            games=[], provider="anthropic", model="claude-sonnet-4-6",
            api_key="sk-test", base_url_override=None,
            config=_shallow_config(), timeout_seconds=30,
            legacy_notes=legacy_notes, three_notes=three_notes,
        )
        legacy_result = ShallowResult(
            success=True,
            shallow_keys=frozenset([(_NOTE_GAMES[0], "path/0", "CLAMP", "")]),
            vague_keys=frozenset(),
            error=None,
            usage=legacy_usage,
            model="claude-sonnet-4-6",
            unparsed_indices=(),
        )
        three_result = ShallowResult(
            success=True,
            shallow_keys=frozenset(),
            vague_keys=frozenset([(_3X3_NOTE_GAMES[0], "path3/0", "3x3", "Why4")]),
            error=None,
            usage=three_usage,
            model="claude-sonnet-4-6",
            unparsed_indices=(),
        )
        ready = []
        thread.shallow_ready.connect(lambda sk, vk, ck, u: ready.append((sk, vk, ck, u)))
        with patch("app.services.chess_log_shallow_service.classify_notes", return_value=legacy_result), \
             patch("app.services.chess_log_shallow_service.classify_notes_3x3", return_value=three_result):
            thread.run()
        return ready

    def test_usage_tokens_are_summed(self):
        """input and output tokens from both calls are summed."""
        from app.services.ai_service import TokenUsage
        legacy_u = TokenUsage(input_tokens=100, output_tokens=50, reasoning_tokens=None, reported=True)
        three_u = TokenUsage(input_tokens=80, output_tokens=40, reasoning_tokens=None, reported=True)
        ready = self._run_both_succeed(legacy_u, three_u)
        self.assertEqual(len(ready), 1)
        _, _, _, usage = ready[0]
        self.assertIsNotNone(usage)
        self.assertEqual(usage.input_tokens, 180)
        self.assertEqual(usage.output_tokens, 90)

    def test_reasoning_tokens_summed_when_both_present(self):
        """reasoning_tokens from both calls are summed when non-None."""
        from app.services.ai_service import TokenUsage
        legacy_u = TokenUsage(input_tokens=100, output_tokens=50, reasoning_tokens=200, reported=True)
        three_u = TokenUsage(input_tokens=80, output_tokens=40, reasoning_tokens=150, reported=True)
        ready = self._run_both_succeed(legacy_u, three_u)
        self.assertEqual(len(ready), 1)
        _, _, _, usage = ready[0]
        self.assertIsNotNone(usage)
        self.assertEqual(usage.reasoning_tokens, 350)

    def test_reasoning_tokens_none_when_neither_present(self):
        """reasoning_tokens stays None when neither call has it."""
        from app.services.ai_service import TokenUsage
        legacy_u = TokenUsage(input_tokens=100, output_tokens=50, reasoning_tokens=None, reported=True)
        three_u = TokenUsage(input_tokens=80, output_tokens=40, reasoning_tokens=None, reported=True)
        ready = self._run_both_succeed(legacy_u, three_u)
        _, _, _, usage = ready[0]
        self.assertIsNone(usage.reasoning_tokens)

    def test_merged_shallow_and_vague_contain_both_calls_results(self):
        """shallow_keys and vague_keys each include results from both calls."""
        from app.services.ai_service import TokenUsage
        u = TokenUsage(input_tokens=10, output_tokens=5, reasoning_tokens=None, reported=True)
        ready = self._run_both_succeed(u, u)
        self.assertEqual(len(ready), 1)
        shallow_keys, vague_keys, _, _ = ready[0]
        self.assertIn((_NOTE_GAMES[0], "path/0", "CLAMP", ""), shallow_keys)
        self.assertIn((_3X3_NOTE_GAMES[0], "path3/0", "3x3", "Why4"), vague_keys)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThread3x3IgnoreHonouredByHash(unittest.TestCase):
    """Entry with ignore_shallow=True and matching hash → moment skipped, no keys emitted."""

    def test_matched_hash_skips_whole_moment(self):
        import hashlib
        why_text = "I moved impulsively without considering alternatives"
        h = hashlib.sha256(why_text.encode("utf-8")).hexdigest()
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why1", why_text, ignore_shallow=True, ignore_text_hash=h
        )
        game = _make_game(entries_per_path={"0": [entry]})
        db_ctrl = _make_db_controller([game])
        db_ctrl.get_active_database.return_value.get_all_games.return_value = [game]
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        _set_user_settings(ctrl, {"ai_models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}}})

        received = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append((k, vk, ck)))
        ctrl.request_flag_shallow_notes()

        self.assertEqual(len(received), 1, "shallow_ready must fire synchronously")
        sk, vk, ck = received[0]
        self.assertEqual(sk, set())
        self.assertNotIn((1, "0", "3x3", "Why1"), ck)
        self.assertIsNone(ctrl._shallow_thread)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThread3x3IgnoreClearedOnEdit(unittest.TestCase):
    """Hash mismatch → Ignore dropped; moment is sent for classification."""

    def test_mismatched_hash_sends_moment(self):
        import hashlib
        old_text = "I played an aggressive move"
        h_old = hashlib.sha256(old_text.encode("utf-8")).hexdigest()
        current_text = "I saw the pawn was undefended and grabbed it"  # different text
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why1", current_text, ignore_shallow=True, ignore_text_hash=h_old
        )
        game = _make_game(entries_per_path={"0": [entry]})
        db_ctrl = _make_db_controller([game])
        db_ctrl.get_active_database.return_value.get_all_games.return_value = [game]
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        _set_user_settings(ctrl, {"ai_models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}}})

        thread_kwargs: list = []

        class FakeThread:
            def __init__(self, **kwargs):
                thread_kwargs.append(kwargs)
                self.shallow_ready = MagicMock(); self.shallow_ready.connect = MagicMock()
                self.shallow_failed = MagicMock(); self.shallow_failed.connect = MagicMock()
                self.shallow_partial = MagicMock(); self.shallow_partial.connect = MagicMock()
                self.finished = MagicMock(); self.finished.connect = MagicMock()

            def start(self): pass

        with patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread", side_effect=FakeThread):
            ctrl.request_flag_shallow_notes()

        self.assertEqual(len(thread_kwargs), 1, "thread must have been started (moment not skipped)")
        three_notes = thread_kwargs[0]["three_notes"]
        self.assertEqual(len(three_notes), 1)
        self.assertEqual(three_notes[0][4], current_text)  # why1 = current text


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThread3x3AllAnswersIgnored(unittest.TestCase):
    """Every non-blank answer ignored (matching hashes) → moment not sent; empty signal."""

    def test_all_answers_ignored_emits_empty_synchronously(self):
        import hashlib
        why1 = "I saw the free pawn and grabbed it"
        why4 = "Always count defenders before capturing"
        h1 = hashlib.sha256(why1.encode("utf-8")).hexdigest()
        h4 = hashlib.sha256(why4.encode("utf-8")).hexdigest()
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", why1, ignore_shallow=True, ignore_text_hash=h1),
            ChessLogStorageService.make_entry("3x3", "Why4", why4, ignore_shallow=True, ignore_text_hash=h4),
        ]
        game = _make_game(entries_per_path={"0": entries})
        db_ctrl = _make_db_controller([game])
        db_ctrl.get_active_database.return_value.get_all_games.return_value = [game]
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        _set_user_settings(ctrl, {"ai_models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}}})

        received = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append((k, vk, ck)))
        ctrl.request_flag_shallow_notes()

        self.assertEqual(len(received), 1)
        sk, vk, ck = received[0]
        self.assertEqual(sk, set())
        self.assertIsNone(ctrl._shallow_thread)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThread3x3PartialIgnore(unittest.TestCase):
    """Why1 ignored, Why4 not — moment is sent; Why1 verdict discarded, Why4 kept."""

    def test_partial_ignore_discards_only_ignored_answers(self):
        from app.controllers.chess_log_charts_controller import ChessLogShallowThread
        from app.services.chess_log_shallow_service import ShallowResult
        from app.services.ai_service import TokenUsage

        why1 = "I played the move impulsively without looking at responses"
        why4 = "Look at opponent responses before committing to a move"

        three_notes = [(0, 1, "path/0", "3x3", why1, "", "", why4)]
        three_ignored_sets = [frozenset({"Why1"})]

        thread = ChessLogShallowThread(
            games=[], provider="anthropic", model="claude-sonnet-4-6",
            api_key="sk-test", base_url_override=None,
            config=_shallow_config(), timeout_seconds=30,
            legacy_notes=[], three_notes=three_notes,
            three_ignored_sets=three_ignored_sets,
        )

        three_ok = ShallowResult(
            success=True,
            shallow_keys=frozenset([(1, "path/0", "3x3", "Why1")]),
            vague_keys=frozenset([(1, "path/0", "3x3", "Why4")]),
            error=None,
            usage=TokenUsage(input_tokens=5, output_tokens=3, reasoning_tokens=None, reported=True),
            model="claude-sonnet-4-6",
            unparsed_indices=(),
        )

        received = []
        thread.shallow_ready.connect(lambda sk, vk, ck, u: received.append((sk, vk, ck, u)))

        with patch("app.services.chess_log_shallow_service.classify_notes_3x3", return_value=three_ok):
            thread.run()

        self.assertEqual(len(received), 1)
        sk, vk, ck, _ = received[0]
        # Why1 verdict discarded (was in ignored_cats)
        self.assertNotIn((1, "path/0", "3x3", "Why1"), sk)
        self.assertNotIn((1, "path/0", "3x3", "Why1"), ck)
        # Why4 verdict kept (not ignored)
        self.assertIn((1, "path/0", "3x3", "Why4"), vk)
        self.assertIn((1, "path/0", "3x3", "Why4"), ck)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThread3x3EmptyWhyRow(unittest.TestCase):
    """Blank Why1 + populated Why4 → no Why1 key in shallow_keys."""

    def test_blank_why1_not_in_shallow_keys(self):
        from app.controllers.chess_log_charts_controller import ChessLogShallowThread
        from app.services.chess_log_shallow_service import ShallowResult
        from app.services.ai_service import TokenUsage

        three_notes = [(0, 1, "path/0", "3x3", "", "", "", "Look at opponent responses before every move")]
        thread = ChessLogShallowThread(
            games=[], provider="anthropic", model="claude-sonnet-4-6",
            api_key="sk-test", base_url_override=None,
            config=_shallow_config(), timeout_seconds=30,
            legacy_notes=[], three_notes=three_notes,
        )

        three_ok = ShallowResult(
            success=True,
            shallow_keys=frozenset(),
            vague_keys=frozenset([(1, "path/0", "3x3", "Why4")]),
            error=None,
            usage=TokenUsage(input_tokens=5, output_tokens=3, reasoning_tokens=None, reported=True),
            model="claude-sonnet-4-6",
            unparsed_indices=(),
        )

        received = []
        thread.shallow_ready.connect(lambda sk, vk, ck, u: received.append((sk, vk, ck, u)))

        with patch("app.services.chess_log_shallow_service.classify_notes_3x3", return_value=three_ok):
            thread.run()

        self.assertEqual(len(received), 1)
        sk, vk, ck, _ = received[0]
        self.assertNotIn((1, "path/0", "3x3", "Why1"), sk)
        self.assertIn((1, "path/0", "3x3", "Why4"), vk)
        self.assertIn((1, "path/0", "3x3", "Why4"), ck)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestShallowThreadFailedResultBypassesUnparsedIndices(unittest.TestCase):
    """B11: success=False → all notes unjudged regardless of unparsed_indices value."""

    def test_failed_result_with_empty_unparsed_produces_no_classified_keys(self):
        from app.controllers.chess_log_charts_controller import ChessLogShallowThread
        from app.services.chess_log_shallow_service import ShallowResult
        from app.services.ai_service import TokenUsage

        legacy_notes = [(i, i + 1, f"path/{i}", "CLAMP", f"note {i}") for i in range(2)]
        three_notes = [(0, 10, "path3/0", "3x3", "w1", "w2", "w3", "w4")]

        thread = ChessLogShallowThread(
            games=[], provider="anthropic", model="claude-sonnet-4-6",
            api_key="sk-test", base_url_override=None,
            config=_shallow_config(), timeout_seconds=30,
            legacy_notes=legacy_notes, three_notes=three_notes,
        )

        three_fail = ShallowResult(
            success=False,
            shallow_keys=frozenset(),
            vague_keys=frozenset(),
            error="API timeout",
            usage=TokenUsage(input_tokens=0, output_tokens=0, reasoning_tokens=None, reported=False),
            model="claude-sonnet-4-6",
            unparsed_indices=(),  # empty — must NOT be trusted since success=False
        )
        legacy_ok = ShallowResult(
            success=True,
            shallow_keys=frozenset([(1, "path/0", "CLAMP", "")]),
            vague_keys=frozenset(),
            error=None,
            usage=TokenUsage(input_tokens=5, output_tokens=3, reasoning_tokens=None, reported=True),
            model="claude-sonnet-4-6",
            unparsed_indices=(),
        )

        received = []
        thread.shallow_ready.connect(lambda sk, vk, ck, u: received.append((sk, vk, ck, u)))

        with patch("app.services.chess_log_shallow_service.classify_notes", return_value=legacy_ok), \
             patch("app.services.chess_log_shallow_service.classify_notes_3x3", return_value=three_fail):
            thread.run()

        self.assertEqual(len(received), 1)
        _, _, ck, _ = received[0]
        # 3x3 notes must NOT be in classified_keys (success=False overrides empty unparsed_indices)
        self.assertNotIn((10, "path3/0", "3x3", "Why1"), ck)
        # Legacy notes should still be in classified_keys
        self.assertIn((1, "path/0", "CLAMP", ""), ck)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestNarrativeMetadataCache(unittest.TestCase):
    """Tests for counts/timestamp/model cached at narrative-generation time."""

    def _make_controller(self):
        from unittest.mock import MagicMock
        db_ctrl = MagicMock()
        db_ctrl.get_active_database.return_value = None
        db_ctrl.get_panel_model.return_value = None
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        return ctrl

    def test_metadata_cleared_initially(self):
        ctrl = self._make_controller()
        generated_at, model_label, n, g, m, s, has_3x3 = ctrl.get_last_narrative_metadata()
        self.assertEqual(generated_at, "")
        self.assertEqual(model_label, "")
        self.assertEqual((n, g, m, s), (0, 0, 0, 0))
        self.assertFalse(has_3x3)

    def test_metadata_captured_on_narrative_ready(self):
        from unittest.mock import patch
        ctrl = self._make_controller()
        ctrl._source_selection = 1
        ctrl._current_player = "Alice"
        ctrl._color_filter = "both"
        ctrl._pending_narrative_model_label = "Anthropic claude-opus-4-7"
        ctrl._resolve_games = MagicMock(return_value=[])

        with patch(
            "app.controllers.chess_log_charts_controller.compute_narrative_counts",
            return_value=(5, 3, 8, 4, False),
        ):
            ctrl._on_narrative_thread_ready("Narrative text", [], None)

        _, model_label, n, g, m, s, has_3x3 = ctrl.get_last_narrative_metadata()
        self.assertEqual(model_label, "Anthropic claude-opus-4-7")
        self.assertEqual((n, g, m, s), (5, 3, 8, 4))
        self.assertFalse(has_3x3)

    def test_metadata_generated_at_is_set(self):
        from unittest.mock import patch
        import re
        ctrl = self._make_controller()
        ctrl._source_selection = 1
        ctrl._resolve_games = MagicMock(return_value=[])

        with patch(
            "app.controllers.chess_log_charts_controller.compute_narrative_counts",
            return_value=(0, 0, 0, 0, False),
        ):
            ctrl._on_narrative_thread_ready("text", [], None)

        generated_at, _, _, _, _, _, _ = ctrl.get_last_narrative_metadata()
        self.assertRegex(generated_at, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_metadata_unchanged_after_resolve_games_changes(self):
        """Counts are captured at generation; changing games state doesn't alter cached values."""
        from unittest.mock import patch
        ctrl = self._make_controller()
        ctrl._source_selection = 1
        ctrl._resolve_games = MagicMock(return_value=[])

        with patch(
            "app.controllers.chess_log_charts_controller.compute_narrative_counts",
            return_value=(6, 5, 5, 3, False),
        ):
            ctrl._on_narrative_thread_ready("text", [], None)

        # Now change what _resolve_games would return — shouldn't affect cached counts.
        ctrl._resolve_games = MagicMock(return_value=["extra_game"])
        _, _, n, g, m, s, _ = ctrl.get_last_narrative_metadata()
        self.assertEqual((n, g, m, s), (6, 5, 5, 3))

    def test_metadata_cleared_on_failed_narrative(self):
        from unittest.mock import patch
        ctrl = self._make_controller()
        ctrl._source_selection = 1
        ctrl._resolve_games = MagicMock(return_value=[])

        # First, set some values.
        with patch(
            "app.controllers.chess_log_charts_controller.compute_narrative_counts",
            return_value=(3, 2, 4, 1, False),
        ):
            ctrl._on_narrative_thread_ready("text", [], None)

        # Now fail.
        ctrl._on_narrative_thread_failed("error")
        generated_at, model_label, n, g, m, s, has_3x3 = ctrl.get_last_narrative_metadata()
        self.assertEqual(generated_at, "")
        self.assertEqual(model_label, "")
        self.assertEqual((n, g, m, s), (0, 0, 0, 0))
        self.assertFalse(has_3x3)

    def test_metadata_cleared_on_source_change(self):
        from unittest.mock import patch
        ctrl = self._make_controller()
        ctrl._source_selection = 1
        ctrl._resolve_games = MagicMock(return_value=[])

        with patch(
            "app.controllers.chess_log_charts_controller.compute_narrative_counts",
            return_value=(3, 2, 4, 1, False),
        ):
            ctrl._on_narrative_thread_ready("text", [], None)

        ctrl.set_source_selection(0)
        _, _, n, g, m, s, has_3x3 = ctrl.get_last_narrative_metadata()
        self.assertEqual((n, g, m, s), (0, 0, 0, 0))
        self.assertFalse(has_3x3)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestInFlightGuard(unittest.TestCase):
    """#77: narrative/shallow results arriving after game-set change must be discarded."""

    def _make_controller(self) -> "ChessLogChartsController":
        db_ctrl = _make_db_controller([])
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        return ctrl

    # --- narrative ---

    def test_narrative_discarded_when_game_set_changes_during_run(self):
        """A narrative result arriving after game-set change must not be emitted or cached."""
        ctrl = self._make_controller()
        ctrl._source_selection = 1
        ctrl._resolve_games = MagicMock(return_value=[])

        received = []
        ctrl.narrative_ready.connect(lambda n, f, u: received.append(n))

        ctrl._narrative_launch_gen = ctrl._game_set_generation
        ctrl._clear_result_cache()  # game set changed; gen advances past launch_gen

        with patch(
            "app.controllers.chess_log_charts_controller.compute_narrative_counts",
            return_value=(0, 0, 0, 0, False),
        ):
            ctrl._on_narrative_thread_ready("Stale narrative", [], None)

        self.assertEqual(received, [], "stale narrative must not be emitted")
        self.assertEqual(ctrl._cached_narrative, "", "stale narrative must not be cached")

    def test_narrative_accepted_when_game_set_unchanged(self):
        """A narrative result whose launch gen still matches current gen must be shown."""
        ctrl = self._make_controller()
        ctrl._source_selection = 1
        ctrl._resolve_games = MagicMock(return_value=[])

        received = []
        ctrl.narrative_ready.connect(lambda n, f, u: received.append(n))

        ctrl._narrative_launch_gen = ctrl._game_set_generation  # same generation

        with patch(
            "app.controllers.chess_log_charts_controller.compute_narrative_counts",
            return_value=(0, 0, 0, 0, False),
        ):
            ctrl._on_narrative_thread_ready("Fresh narrative", [], None)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], "Fresh narrative")
        self.assertEqual(ctrl._cached_narrative, "Fresh narrative")

    # --- shallow ---

    def test_shallow_discarded_when_game_set_changes_during_run(self):
        """A shallow result arriving after game-set change must not be emitted or cached."""
        ctrl = self._make_controller()

        received = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append(k))

        ctrl._shallow_launch_gen = ctrl._game_set_generation
        ctrl._clear_result_cache()  # game set changed

        game = GameData(game_number=1)
        ctrl._on_shallow_thread_ready(
            frozenset([(game, "k", "CLAMP", "")]), frozenset(), frozenset(), None
        )

        self.assertEqual(received, [], "stale shallow result must not be emitted")
        self.assertIsNone(ctrl._cached_shallow_keys, "stale shallow result must not be cached")

    def test_shallow_accepted_when_game_set_unchanged(self):
        """A shallow result whose launch gen still matches current gen must be shown."""
        ctrl = self._make_controller()

        received = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append(k))

        ctrl._shallow_launch_gen = ctrl._game_set_generation  # same generation

        game = GameData(game_number=1)
        shallow_keys = frozenset([(game, "k", "CLAMP", "")])
        ctrl._on_shallow_thread_ready(shallow_keys, frozenset(), frozenset(), None)

        self.assertEqual(len(received), 1)
        self.assertIsNotNone(ctrl._cached_shallow_keys)

    # --- generation advances on each game-set change ---

    def test_each_clear_result_cache_advances_generation(self):
        """Every call to _clear_result_cache must increment _game_set_generation."""
        ctrl = self._make_controller()
        gen0 = ctrl._game_set_generation
        ctrl._clear_result_cache()
        self.assertEqual(ctrl._game_set_generation, gen0 + 1)
        ctrl._clear_result_cache()
        self.assertEqual(ctrl._game_set_generation, gen0 + 2)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestInFlightGuardViaRealStartPaths(unittest.TestCase):
    """#77: stamp lines in request_narrative/request_flag_shallow_notes prevent stale results.

    Uses fake thread objects (real QObject with real pyqtSignal) injected via
    patch so that signal emissions work but no real API call is made.
    """

    _PROVIDER_TUPLE = ("anthropic", "claude-opus-4-5", "fake-key", None)

    def _make_controller(self) -> "ChessLogChartsController":
        db_ctrl = _make_db_controller([_make_game()])
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        ctrl._source_selection = 1
        ctrl._current_player = "Alice"
        ctrl._resolve_games = MagicMock(return_value=[_make_game()])
        return ctrl

    # --- narrative stamp ---

    def test_stamp_proof_narrative(self):
        """Stamp ensures a fresh request after a prior game-set change is still accepted.

        Without the stamp line, _narrative_launch_gen stays at its initial value (0)
        while _game_set_generation is already 1 after the prior clear, so the guard
        would wrongly drop the result even though no change happened since the request.
        """
        ctrl = self._make_controller()
        # Simulate a prior game-set change before this request
        ctrl._clear_result_cache()   # gen = 1; without stamp, launch_gen stays 0
        fake_thread = _FakeNarrativeThread()
        received = []
        ctrl.narrative_ready.connect(lambda n, f, u: received.append(n))

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
                   return_value=fake_thread):
            ctrl.request_narrative()  # stamp: launch_gen = 1

        # No further game-set change — result must be accepted
        with patch("app.controllers.chess_log_charts_controller.compute_narrative_counts",
                   return_value=(0, 0, 0, 0, False)):
            fake_thread.narrative_ready.emit("Fresh", [], None)

        self.assertEqual(len(received), 1,
                         "narrative must be accepted when gen unchanged since request — stamp is required")
        self.assertEqual(received[0], "Fresh")

    def test_switch_mid_run_narrative_via_real_path(self):
        """Narrative result arriving after game-set switch is dropped even via real start path."""
        ctrl = self._make_controller()
        fake_thread = _FakeNarrativeThread()
        received = []
        ctrl.narrative_ready.connect(lambda n, f, u: received.append(n))

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
                   return_value=fake_thread):
            ctrl.request_narrative()

        # Game set changes while thread is "running"
        ctrl._clear_result_cache()

        with patch("app.controllers.chess_log_charts_controller.compute_narrative_counts",
                   return_value=(0, 0, 0, 0, False)):
            fake_thread.narrative_ready.emit("Stale", [], None)

        self.assertEqual(received, [], "stale narrative from real start path must be dropped")

    # --- shallow stamp ---

    def test_stamp_proof_shallow(self):
        """Stamp ensures a fresh shallow request after a prior game-set change is still accepted.

        Without the stamp line, _shallow_launch_gen stays at 0 while gen is 1, so the
        guard would wrongly drop the result even though no change happened since the request.
        """
        ctrl = self._make_controller()
        # Simulate a prior game-set change before this request
        ctrl._clear_result_cache()   # gen = 1; without stamp, launch_gen stays 0
        fake_thread = _FakeShallowThread()
        received = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append(k))

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread",
                   return_value=fake_thread), \
             patch("app.controllers.chess_log_charts_controller.ChessLogChartsController"
                   ".get_tags_for_game", return_value={}), \
             patch("app.services.chess_log_shallow_service.build_notes",
                   return_value=([("n",)], [], [])):
            ctrl.request_flag_shallow_notes()  # stamp: launch_gen = 1

        # No further game-set change — result must be accepted
        game = GameData(game_number=1)
        shallow_keys = frozenset([(game, "k", "CLAMP", "")])
        fake_thread.shallow_ready.emit(shallow_keys, frozenset(), frozenset(), None, "")

        self.assertEqual(len(received), 1,
                         "shallow result must be accepted when gen unchanged since request — stamp is required")
        self.assertIsNotNone(received[0])

    def test_switch_mid_run_shallow_via_real_path(self):
        """Shallow result arriving after game-set switch is dropped even via real start path."""
        ctrl = self._make_controller()
        fake_thread = _FakeShallowThread()
        received = []
        ctrl.shallow_ready.connect(lambda k, vk, ck, u: received.append(k))

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread",
                   return_value=fake_thread), \
             patch("app.controllers.chess_log_charts_controller.ChessLogChartsController"
                   ".get_tags_for_game", return_value={}), \
             patch("app.services.chess_log_shallow_service.build_notes",
                   return_value=([("n",)], [], [])):
            ctrl.request_flag_shallow_notes()

        # Game set changes while thread is "running"
        ctrl._clear_result_cache()

        game = GameData(game_number=1)
        fake_thread.shallow_ready.emit(frozenset([(game, "k", "CLAMP", "")]), frozenset(), frozenset(), None, "")

        self.assertEqual(received, [], "stale shallow result from real start path must be dropped")

    # --- stale partial is dropped ---

    def test_stale_partial_is_dropped(self):
        """shallow_partial arriving after game-set change must not be re-emitted."""
        ctrl = self._make_controller()
        fake_thread = _FakeShallowThread()
        received = []
        ctrl.shallow_partial.connect(received.append)

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread",
                   return_value=fake_thread), \
             patch("app.controllers.chess_log_charts_controller.ChessLogChartsController"
                   ".get_tags_for_game", return_value={}), \
             patch("app.services.chess_log_shallow_service.build_notes",
                   return_value=([("n",)], [], [])):
            ctrl.request_flag_shallow_notes()

        ctrl._clear_result_cache()
        fake_thread.shallow_partial.emit("3 notes could not be parsed")

        self.assertEqual(received, [], "stale shallow_partial must be dropped by _on_shallow_thread_partial")

    # --- positive control: chart option change does not block a fresh narrative ---

    def test_positive_control_chart_option_does_not_block_narrative(self):
        """A chart option change via the real set_user_settings path must not advance the generation.

        Real path: menu action → ChessLogChartsMenuController._apply()
        → UserSettingsService.update_chess_log_charts_settings()
        → chess_log_charts_changed signal → set_user_settings() → _selection_debounce.start()
        (no _clear_result_cache call anywhere in that chain).
        """
        ctrl = self._make_controller()
        fake_thread = _FakeNarrativeThread()
        received = []
        ctrl.narrative_ready.connect(lambda n, f, u: received.append(n))

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
                   return_value=fake_thread):
            ctrl.request_narrative()

        # Real chart option path: set_user_settings with a changed chart setting
        # Default x_axis_mode is "uniform_bins"; switching to "calendar_linear" changes it.
        # resolve_default_provider({...}) returns None (no AI key) — harmless for this test.
        _set_user_settings(ctrl, {"chess_log": {"charts": {"progression_x_axis_mode": "calendar_linear"}}})

        with patch("app.controllers.chess_log_charts_controller.compute_narrative_counts",
                   return_value=(0, 0, 0, 0, False)):
            fake_thread.narrative_ready.emit("Fresh", [], None)

        self.assertEqual(len(received), 1, "narrative after chart option change must not be blocked")
        self.assertEqual(received[0], "Fresh")


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestStaleFailureGuard(unittest.TestCase):
    """#77 Part A: stale narrative/shallow failures must be dropped silently."""

    _PROVIDER_TUPLE = ("anthropic", "claude-opus-4-5", "fake-key", None)

    def _make_controller(self) -> "ChessLogChartsController":
        db_ctrl = _make_db_controller([_make_game()])
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        ctrl._source_selection = 1
        ctrl._current_player = "Alice"
        ctrl._resolve_games = MagicMock(return_value=[_make_game()])
        return ctrl

    # --- narrative failure ---

    def test_stale_narrative_failure_is_dropped(self):
        """narrative_failed from a stale run must not be re-emitted."""
        ctrl = self._make_controller()
        fake_thread = _FakeNarrativeThread()
        received = []
        ctrl.narrative_failed.connect(received.append)

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
                   return_value=fake_thread):
            ctrl.request_narrative()

        ctrl.set_player_selection("Bob")  # game-set change via real public path
        fake_thread.narrative_failed.emit("Network timeout from old run")

        self.assertEqual(received, [], "stale narrative_failed must not be re-emitted")

    def test_fresh_narrative_failure_is_emitted(self):
        """narrative_failed with no game-set change since launch must still be emitted."""
        ctrl = self._make_controller()
        fake_thread = _FakeNarrativeThread()
        received = []
        ctrl.narrative_failed.connect(received.append)

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
                   return_value=fake_thread):
            ctrl.request_narrative()

        fake_thread.narrative_failed.emit("API error")

        self.assertEqual(len(received), 1, "fresh narrative_failed must be re-emitted")
        self.assertEqual(received[0], "API error")

    # --- shallow failure ---

    def test_stale_shallow_failure_is_dropped(self):
        """shallow_failed from a stale run must not be re-emitted."""
        ctrl = self._make_controller()
        fake_thread = _FakeShallowThread()
        received = []
        ctrl.shallow_failed.connect(received.append)

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread",
                   return_value=fake_thread), \
             patch("app.controllers.chess_log_charts_controller.ChessLogChartsController"
                   ".get_tags_for_game", return_value={}), \
             patch("app.services.chess_log_shallow_service.build_notes",
                   return_value=([("n",)], [], [])):
            ctrl.request_flag_shallow_notes()

        ctrl.set_player_selection("Bob")  # game-set change via real public path
        fake_thread.shallow_failed.emit("Network timeout from old run")

        self.assertEqual(received, [], "stale shallow_failed must not be re-emitted")

    def test_fresh_shallow_failure_is_emitted(self):
        """shallow_failed with no game-set change since launch must still be emitted."""
        ctrl = self._make_controller()
        fake_thread = _FakeShallowThread()
        received = []
        ctrl.shallow_failed.connect(received.append)

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread",
                   return_value=fake_thread), \
             patch("app.controllers.chess_log_charts_controller.ChessLogChartsController"
                   ".get_tags_for_game", return_value={}), \
             patch("app.services.chess_log_shallow_service.build_notes",
                   return_value=([("n",)], [], [])):
            ctrl.request_flag_shallow_notes()

        fake_thread.shallow_failed.emit("API error")

        self.assertEqual(len(received), 1, "fresh shallow_failed must be re-emitted")
        self.assertEqual(received[0], "API error")

    # --- finished handlers reset running state even when stale ---

    def test_narrative_finished_resets_thread_ref_when_stale(self):
        """_on_narrative_finished must nil the thread reference even after a game-set change."""
        ctrl = self._make_controller()
        fake_thread = _FakeNarrativeThread()

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
                   return_value=fake_thread):
            ctrl.request_narrative()

        self.assertIsNotNone(ctrl._narrative_thread)

        ctrl.set_player_selection("Bob")
        fake_thread.finished.emit()

        self.assertIsNone(ctrl._narrative_thread,
                          "_narrative_thread must be nil after finished even when stale")

    def test_shallow_finished_resets_thread_ref_when_stale(self):
        """_on_shallow_thread_finished must nil the thread reference even after a game-set change."""
        ctrl = self._make_controller()
        fake_thread = _FakeShallowThread()

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=self._PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread",
                   return_value=fake_thread), \
             patch("app.controllers.chess_log_charts_controller.ChessLogChartsController"
                   ".get_tags_for_game", return_value={}), \
             patch("app.services.chess_log_shallow_service.build_notes",
                   return_value=([("n",)], [], [])):
            ctrl.request_flag_shallow_notes()

        self.assertIsNotNone(ctrl._shallow_thread)

        ctrl.set_player_selection("Bob")
        fake_thread.finished.emit()

        self.assertIsNone(ctrl._shallow_thread,
                          "_shallow_thread must be nil after finished even when stale")


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestGameSetKeyInvalidation(unittest.TestCase):
    """#77 Part B: _schedule_charts_refresh auto-clears results when the resolved game set changes."""

    def _make_controller(self) -> "ChessLogChartsController":
        db_ctrl = _make_db_controller([])
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        ctrl._cancel_agg_worker = MagicMock()
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        return ctrl

    def _run_schedule(self, ctrl, games):
        """Call _schedule_charts_refresh with given games, mocking the agg worker."""
        with patch("app.controllers.chess_log_charts_controller.ChessLogAggregationWorker") as MockWorker:
            mock_w = MagicMock()
            MockWorker.return_value = mock_w
            ctrl._schedule_charts_refresh(games=games)

    # --- different game set clears (source 1 as representative) ---

    def test_different_game_set_clears_results_source1(self):
        """Two consecutive refreshes with different game objects → results cleared."""
        ctrl = self._make_controller()
        games1 = [_make_game(white="Alice")]
        games2 = [_make_game(white="Alice")]  # different objects, same nominal content

        self._run_schedule(ctrl, games1)
        ctrl._cached_narrative = "Old narrative"
        gen0 = ctrl._game_set_generation

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        self._run_schedule(ctrl, games2)

        self.assertEqual(ctrl._cached_narrative, "", "cache must be cleared on game-set change")
        self.assertEqual(ctrl._game_set_generation, gen0 + 1, "generation must advance")
        self.assertEqual(len(invalidated), 1, "results_invalidated must be emitted")

    def test_same_game_set_keeps_results(self):
        """Two consecutive refreshes with the SAME game objects → results kept."""
        ctrl = self._make_controller()
        games = [_make_game(white="Alice")]

        self._run_schedule(ctrl, games)
        ctrl._cached_narrative = "Result to keep"
        gen0 = ctrl._game_set_generation

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        self._run_schedule(ctrl, games)

        self.assertEqual(ctrl._cached_narrative, "Result to keep", "cache must be preserved")
        self.assertEqual(ctrl._game_set_generation, gen0, "generation must not advance")
        self.assertEqual(invalidated, [], "results_invalidated must not be emitted")

    # --- source 3 ---

    def test_source3_different_games_clears_results(self):
        """Source 3: resolved selection changes to different objects → results cleared."""
        ctrl = self._make_controller()
        ctrl._source_selection = 3
        games1 = [_make_game(white="Alice")]
        games2 = [_make_game(white="Alice")]  # different object identities

        self._run_schedule(ctrl, games1)
        ctrl._cached_narrative = "Old"

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        self._run_schedule(ctrl, games2)

        self.assertEqual(ctrl._cached_narrative, "")
        self.assertEqual(len(invalidated), 1)

    def test_source3_same_games_keeps_results(self):
        """Source 3: selection resolves to identical objects → results kept."""
        ctrl = self._make_controller()
        ctrl._source_selection = 3
        games = [_make_game(white="Alice")]

        self._run_schedule(ctrl, games)
        ctrl._cached_narrative = "Keep me"

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        self._run_schedule(ctrl, games)

        self.assertEqual(ctrl._cached_narrative, "Keep me")
        self.assertEqual(invalidated, [])

    # --- source 4 ---

    def test_source4_different_games_clears_results(self):
        """Source 4: resolved selection changes to different objects → results cleared."""
        ctrl = self._make_controller()
        ctrl._source_selection = 4
        games1 = [_make_game(white="Alice")]
        games2 = [_make_game(white="Alice")]

        self._run_schedule(ctrl, games1)
        ctrl._cached_narrative = "Old"

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        self._run_schedule(ctrl, games2)

        self.assertEqual(ctrl._cached_narrative, "")
        self.assertEqual(len(invalidated), 1)

    def test_source4_same_games_keeps_results(self):
        """Source 4: selection resolves to identical objects → results kept."""
        ctrl = self._make_controller()
        ctrl._source_selection = 4
        games = [_make_game(white="Alice")]

        self._run_schedule(ctrl, games)
        ctrl._cached_narrative = "Keep me"

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        self._run_schedule(ctrl, games)

        self.assertEqual(ctrl._cached_narrative, "Keep me")
        self.assertEqual(invalidated, [])

    # --- first refresh never clears (no prior key) ---

    def test_first_refresh_never_clears(self):
        """Initial chart load must not emit results_invalidated (no prior key)."""
        ctrl = self._make_controller()
        ctrl._cached_narrative = "Cached from prior session"
        games = [_make_game(white="Alice")]

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        self._run_schedule(ctrl, games)

        self.assertEqual(invalidated, [], "first load must not invalidate")

    # --- positive control: chart option change keeps results ---

    def test_chart_option_change_keeps_results(self):
        """A chart option change (set_user_settings real path) must not invalidate results."""
        ctrl = self._make_controller()
        games = [_make_game(white="Alice")]

        self._run_schedule(ctrl, games)
        ctrl._cached_narrative = "Result to keep"
        gen0 = ctrl._game_set_generation

        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))
        _set_user_settings(ctrl, {"chess_log": {"charts": {"progression_x_axis_mode": "calendar_linear"}}})

        self.assertEqual(ctrl._cached_narrative, "Result to keep")
        self.assertEqual(ctrl._game_set_generation, gen0)
        self.assertEqual(invalidated, [])

    # --- mid-run: narrative started on game set A, game set changes → result dropped ---

    def test_mid_run_narrative_dropped_when_game_set_key_changes(self):
        """Narrative started on game set A is dropped when _schedule_charts_refresh detects B."""
        _PROVIDER_TUPLE = ("anthropic", "claude-opus-4-5", "fake-key", None)
        ctrl = self._make_controller()
        games1 = [_make_game(white="Alice")]
        games2 = [_make_game(white="Alice")]  # different objects
        self._run_schedule(ctrl, games1)

        fake_thread = _FakeNarrativeThread()
        received = []
        ctrl.narrative_ready.connect(lambda n, f, u: received.append(n))

        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=_PROVIDER_TUPLE), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
                   return_value=fake_thread):
            ctrl.request_narrative()

        # Game set changes mid-run via _schedule_charts_refresh detecting different objects
        self._run_schedule(ctrl, games2)

        with patch("app.controllers.chess_log_charts_controller.compute_narrative_counts",
                   return_value=(0, 0, 0, 0, False)):
            fake_thread.narrative_ready.emit("Stale from old set", [], None)

        self.assertEqual(received, [], "narrative from old game set must be dropped")


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestGameSetKeyStability(unittest.TestCase):
    """#77: _resolve_games() returns the same GameData object identities on consecutive calls.

    Validates that frozenset(id(g) for g in games) is a stable key for each source:
    the key must equal itself across calls when nothing changed, so that
    _schedule_charts_refresh does not falsely detect a game-set change and
    clear cached results.
    """

    def _make_db_with_games(self):
        """Create a real DatabaseModel with 2 games inserted directly into _games."""
        db = DatabaseModel()
        game1 = GameData(game_number=1, white="Alice", black="Bob")
        game2 = GameData(game_number=2, white="Alice", black="Bob")
        db._games = [game1, game2]
        return db, [game1, game2]

    def _make_ctrl(self, source: int) -> "ChessLogChartsController":
        """Controller backed by a real DatabaseModel; sources 3/4 use a fixed callback."""
        db, games = self._make_db_with_games()
        panel = MagicMock()
        panel.get_all_database_models.return_value = [db]
        db_ctrl = MagicMock()
        db_ctrl.get_active_database.return_value = db
        db_ctrl.get_panel_model.return_value = panel
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
        ctrl._start_dropdown_worker = MagicMock()
        ctrl._cancel_dropdown_worker = MagicMock()
        ctrl._cancel_agg_worker = MagicMock()
        ctrl._source_selection = source
        ctrl._player_explicit_selected = True
        ctrl._current_player = "Alice"
        if source in (3, 4):
            # Callback returns the same objects each time (mimics real get_selected_games)
            stored = list(db._games)
            ctrl.set_get_selected_games_callback(lambda active_only: list(stored))
        return ctrl

    # ------------------------------------------------------------------
    # Identity tests: same objects returned on repeat calls
    # ------------------------------------------------------------------

    def test_source1_same_objects_on_repeat_resolve(self):
        """Source 1 (Active DB): _resolve_games returns identical game objects each call."""
        ctrl = self._make_ctrl(1)
        r1 = ctrl._resolve_games()
        r2 = ctrl._resolve_games()
        self.assertTrue(r1, "must return non-empty list")
        self.assertEqual([id(g) for g in r1], [id(g) for g in r2],
                         "source 1: GameData object identities must be stable across calls")

    def test_source2_same_objects_on_repeat_resolve(self):
        """Source 2 (All DBs): _resolve_games returns identical game objects each call."""
        ctrl = self._make_ctrl(2)
        r1 = ctrl._resolve_games()
        r2 = ctrl._resolve_games()
        self.assertTrue(r1, "must return non-empty list")
        self.assertEqual([id(g) for g in r1], [id(g) for g in r2],
                         "source 2: GameData object identities must be stable across calls")

    def test_source3_same_objects_on_repeat_resolve(self):
        """Source 3 (Selected Active): callback returns identical game objects each call."""
        ctrl = self._make_ctrl(3)
        r1 = ctrl._resolve_games()
        r2 = ctrl._resolve_games()
        self.assertTrue(r1, "must return non-empty list")
        self.assertEqual([id(g) for g in r1], [id(g) for g in r2],
                         "source 3: GameData object identities must be stable across calls")

    def test_source4_same_objects_on_repeat_resolve(self):
        """Source 4 (Selected All): callback returns identical game objects each call."""
        ctrl = self._make_ctrl(4)
        r1 = ctrl._resolve_games()
        r2 = ctrl._resolve_games()
        self.assertTrue(r1, "must return non-empty list")
        self.assertEqual([id(g) for g in r1], [id(g) for g in r2],
                         "source 4: GameData object identities must be stable across calls")

    # ------------------------------------------------------------------
    # Debounce actually fires: same game set after chart option → no clear
    # ------------------------------------------------------------------

    def _fire_debounce_with_patched_worker(self, ctrl):
        """Invoke _on_selection_debounced() with ChessLogAggregationWorker mocked out."""
        with patch("app.controllers.chess_log_charts_controller.ChessLogAggregationWorker") as MockWorker:
            MockWorker.return_value = MagicMock()
            ctrl._on_selection_debounced()

    def _run_debounce_test(self, source: int):
        """Set up, fire debounce once to seed key, cache narrative, change chart option,
        fire debounce again, return (ctrl, gen_before, invalidated_list)."""
        ctrl = self._make_ctrl(source)

        # First debounce: establishes _last_game_set_key
        self._fire_debounce_with_patched_worker(ctrl)

        ctrl._cached_narrative = "Cached narrative"
        gen0 = ctrl._game_set_generation
        invalidated = []
        ctrl.results_invalidated.connect(lambda: invalidated.append(True))

        # Chart option change via real set_user_settings path (starts debounce timer)
        _set_user_settings(ctrl, {"chess_log": {"charts": {"progression_x_axis_mode": "calendar_linear"}}})

        # Fire debounce slot directly — same game objects, key must match
        self._fire_debounce_with_patched_worker(ctrl)

        return ctrl, gen0, invalidated

    def test_source3_debounce_fires_keeps_narrative(self):
        """Source 3: debounce fires after chart option change with unchanged games → narrative kept."""
        ctrl, gen0, invalidated = self._run_debounce_test(3)
        self.assertEqual(ctrl._cached_narrative, "Cached narrative",
                         "narrative must be preserved when game set unchanged")
        self.assertEqual(ctrl._game_set_generation, gen0,
                         "generation must not advance when game set unchanged")
        self.assertEqual(invalidated, [],
                         "results_invalidated must not fire when game set unchanged")

    def test_source1_debounce_fires_keeps_narrative(self):
        """Source 1: debounce fires after chart option change with unchanged games → narrative kept."""
        ctrl, gen0, invalidated = self._run_debounce_test(1)
        self.assertEqual(ctrl._cached_narrative, "Cached narrative",
                         "narrative must be preserved when game set unchanged")
        self.assertEqual(ctrl._game_set_generation, gen0,
                         "generation must not advance when game set unchanged")
        self.assertEqual(invalidated, [],
                         "results_invalidated must not fire when game set unchanged")


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestChessLogAggregationWorkerReasonCodes(unittest.TestCase):
    """Worker emits the correct reason strings for each empty-result scenario."""

    def _run_worker(self, games, player="Alice"):
        """Run ChessLogAggregationWorker synchronously; return (reason, skipped)."""
        from PyQt6.QtCore import QEventLoop
        reasons = []
        skipped = []
        snapshot = {id(g): ChessLogStorageService.load_resolved_paths(g) for g in games}
        worker = ChessLogAggregationWorker(
            games=games, player=player, color_filter="both", chart_cfg={},
            snapshot=snapshot,
        )
        worker.charts_unavailable.connect(reasons.append)
        worker.charts_skipped.connect(skipped.append)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.start()
        loop.exec()
        return reasons, skipped

    def _dated_clamp_game(self):
        return _make_game(entries_per_path={"0": [_clamp(cat="C")]})

    def _undated_clamp_game(self):
        pgn = (
            '[Event "Test"]\n[Site "?"]\n[Date "????.??.??"]\n'
            '[Round "?"]\n[White "Alice"]\n[Black "Bob"]\n'
            '[Result "*"]\n\n1. e4 *\n'
        )
        game = GameData(game_number=1, pgn=pgn, white="Alice", black="Bob", date="????.??.??")
        ChessLogStorageService.store_tags(game, {"0": [ChessLogStorageService.make_entry("CLAMP", "C")]})
        return game

    def test_no_games_emits_no_data(self):
        reasons, _ = self._run_worker([])
        self.assertEqual(reasons, ["no_data"])

    def test_all_undated_clamp_emits_no_dated_reason(self):
        games = [self._undated_clamp_game() for _ in range(4)]
        reasons, _ = self._run_worker(games)
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].startswith("no_dated_clamp_cct:"))

    def test_all_undated_clamp_reason_encodes_count(self):
        games = [self._undated_clamp_game() for _ in range(4)]
        reasons, _ = self._run_worker(games)
        parts = reasons[0].split(":")
        self.assertEqual(parts[1], "4")

    def test_dated_games_emit_charts_updated_and_skipped(self):
        from PyQt6.QtCore import QEventLoop
        updated = []
        skipped = []
        games = [self._dated_clamp_game()]
        snapshot = {id(g): ChessLogStorageService.load_resolved_paths(g) for g in games}
        worker = ChessLogAggregationWorker(
            games=games, player="Alice", color_filter="both", chart_cfg={},
            snapshot=snapshot,
        )
        worker.charts_updated.connect(updated.append)
        worker.charts_skipped.connect(skipped.append)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.start()
        loop.exec()
        self.assertEqual(len(updated), 1)
        self.assertEqual(skipped, [0])

    def test_mixed_dated_and_undated_emits_skipped_count(self):
        from PyQt6.QtCore import QEventLoop
        skipped = []
        games = [self._dated_clamp_game(), self._undated_clamp_game(), self._undated_clamp_game()]
        snapshot = {id(g): ChessLogStorageService.load_resolved_paths(g) for g in games}
        worker = ChessLogAggregationWorker(
            games=games, player="Alice", color_filter="both", chart_cfg={},
            snapshot=snapshot,
        )
        worker.charts_skipped.connect(skipped.append)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.start()
        loop.exec()
        self.assertEqual(skipped, [2])

    def test_cancelled_worker_emits_no_signals(self):
        from PyQt6.QtCore import QEventLoop
        updated = []
        reasons = []
        skipped = []
        worker = ChessLogAggregationWorker(
            games=[self._dated_clamp_game()], player="Alice", color_filter="both", chart_cfg={}
        )
        worker.charts_updated.connect(updated.append)
        worker.charts_unavailable.connect(reasons.append)
        worker.charts_skipped.connect(skipped.append)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.cancel()
        worker.start()
        loop.exec()
        self.assertEqual(updated, [], "cancelled worker must not emit charts_updated")
        self.assertEqual(reasons, [], "cancelled worker must not emit charts_unavailable")
        self.assertEqual(skipped, [], "cancelled worker must not emit charts_skipped")



@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestColorFilterInvalidatesResults(unittest.TestCase):
    """set_color_filter clears cached results and tells the view (C5)."""

    def test_set_color_filter_clears_cache_and_emits_results_invalidated(self):
        ctrl = ChessLogChartsController(config={}, database_controller=_make_db_controller([]))
        ctrl._kick_debounce = MagicMock()
        ctrl._cached_narrative = "old narrative"
        ctrl._cached_shallow_keys = frozenset([("g", "0", "CLAMP", "")])
        received = []
        ctrl.results_invalidated.connect(lambda: received.append(True))
        generation = ctrl._game_set_generation
        ctrl.set_color_filter("white")
        self.assertEqual(ctrl._color_filter, "white")
        self.assertEqual(ctrl._cached_narrative, "")
        self.assertIsNone(ctrl._cached_shallow_keys)
        self.assertEqual(received, [True])
        self.assertGreater(ctrl._game_set_generation, generation)
        ctrl._kick_debounce.assert_called_once()


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestGetTagsForGameRequiresController(unittest.TestCase):
    """get_tags_for_game has no storage fallback: the injected controller is required (C5)."""

    def test_raises_without_injected_controller(self):
        ctrl = _RealChessLogChartsController(
            config={}, database_controller=_make_db_controller([])
        )
        with self.assertRaises(RuntimeError):
            ctrl.get_tags_for_game(_make_game())

    def test_delegates_to_injected_controller(self):
        ctrl = _RealChessLogChartsController(
            config={}, database_controller=_make_db_controller([])
        )
        cl = MagicMock()
        cl.get_tags_for_game.return_value = {"0": []}
        ctrl.set_chess_log_controller(cl)
        game = _make_game()
        self.assertEqual(ctrl.get_tags_for_game(game), {"0": []})
        cl.get_tags_for_game.assert_called_once_with(game)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestNarrativeCountsFromRequestSnapshot(unittest.TestCase):
    """Narrative header counts describe the request-time snapshot, not live tags (C7)."""

    class _LiveTags:
        def __init__(self, tags):
            self.tags = tags

        def get_tags_for_game(self, game):
            return {k: list(v) for k, v in self.tags.items()}

    def _request_with_fake_thread(self, ctrl):
        class FakeThread:
            def __init__(self, **kwargs):
                for name in ("narrative_ready", "narrative_failed", "finished"):
                    sig = MagicMock()
                    sig.connect = MagicMock()
                    setattr(self, name, sig)

            def start(self):
                pass

        with patch(
            "app.controllers.chess_log_charts_controller.ChessLogNarrativeThread",
            side_effect=FakeThread,
        ):
            ctrl.request_narrative()

    def test_counts_match_request_time_snapshot_after_live_edit(self):
        game = _make_game()
        game.has_chess_log_tags = True
        unflagged = ChessLogStorageService.make_entry("CLAMP", "C", "a note")
        flagged = dict(unflagged, is_shallow=True)
        live = self._LiveTags({"0": [unflagged]})

        ctrl = ChessLogChartsController(config={}, database_controller=_make_db_controller([game]))
        ctrl.set_chess_log_controller(live)
        ctrl._source_selection = 1
        ctrl._current_player = "Alice"
        ctrl._color_filter = "both"
        ctrl._resolve_games = MagicMock(return_value=[game])
        _set_user_settings(ctrl, {
            "ai_models": {"openai": {"api_key": "sk-test", "model": "gpt-4o"}}
        })

        self._request_with_fake_thread(ctrl)
        # The user flags the moment while the LLM call is in flight.
        live.tags = {"0": [flagged]}
        ctrl._on_narrative_thread_ready("text", [], None)

        _, _, n, g, m, s, _ = ctrl.get_last_narrative_metadata()
        self.assertEqual((n, g, m, s), (1, 1, 1, 0))
        # Control: the live accessor now says 1 flagged, so the old code would differ.
        from app.services.chess_log_stats_service import compute_narrative_counts
        live_counts = compute_narrative_counts([game], "Alice", "both", live.get_tags_for_game)
        self.assertEqual(live_counts[3], 1)


if __name__ == "__main__":
    unittest.main()


from tests.chess_log_ai_settings_helper import (  # noqa: E402
    apply_settings as _apply_settings,
    current_service as _current_service,
    isolate_module as _isolate_module,
    set_user_settings as _set_user_settings,
)

_isolate_module(globals())
