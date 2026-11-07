"""Reproducing tests for Issue #88 single-source-of-truth audit.

Each test is marked @unittest.expectedFailure so the suite stays green.
A test flips to "unexpected success" (a failure) once its fix lands.

Coverage:
  B1 — Moves List icons stale after ShowTagsDialog.Save or save_games()
  B2 — Charts tab not refreshed on a Chess Log save notification
  B3 — Player combo silently unselected while controller keeps the player
  B4 — Controller classifier cache not updated by the "no notes" Check Logs path
  B5 — Charts exports omit vague-only Check Logs results
  B6 — Tokens spinbox not restored from the controller on view rebuild
  B7 — Charts controller AI-settings snapshot goes stale (timeout)
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# Qt guard
# ---------------------------------------------------------------------------

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
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

MINIMAL_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 *\n"
)


def _make_game(pgn: str = MINIMAL_PGN):
    from app.models.database_model import GameData
    return GameData(game_number=1, pgn=pgn)


def _make_entry(preset: str, cat: str, why: str = "some note"):
    from app.services.chess_log_storage_service import ChessLogStorageService
    return ChessLogStorageService.make_entry(preset, cat, why)


# ---------------------------------------------------------------------------
# B1 — Moves List icons stale after ShowTagsDialog.Save
#
# Root cause: ShowTagsDialog._on_save() calls controller.save_games()
# but neither the dialog nor the controller calls
# MovesListModel.notify_chess_log_changed() afterwards.  The Moves List
# therefore continues to show icons for moves whose entries were deleted.
#
# Fix contract: after ShowTagsDialog._on_save() causes a deletion, the
# caller (or the controller) must call notify_chess_log_changed() so that
# Qt re-renders the icon column.
# ---------------------------------------------------------------------------

@requires_qt
class TestB1MovesListIconStaleAfterShowTagsSave(unittest.TestCase):
    """B1: MovesListModel is not notified after ShowTagsDialog.Save."""

    def _controller_with_active_game(self, game, path_key, entry):
        """Real ChessLogController whose active game is `game` with one entry."""
        from app.controllers.chess_log_controller import ChessLogController

        game_model = MagicMock()
        game_model.active_game = game
        game_model.get_active_path.return_value = []
        game_controller = MagicMock()
        game_controller.get_game_model.return_value = game_model
        database_controller = MagicMock()
        database_controller.get_panel_model.return_value = None
        ctrl = ChessLogController(
            config={},
            game_controller=game_controller,
            database_controller=database_controller,
        )
        gid = id(game)
        ctrl._cached_game = game
        ctrl._cached_game_id = gid
        ctrl._cached_paths_data = {path_key: [entry]}
        ctrl._cached_original_paths[gid] = {path_key: [entry]}
        return ctrl, game_model

    # -- Test 1: save_games() does not emit metadata_updated
    # save_all_dirty_games() DOES emit metadata_updated for the active game;
    # save_games() (used by both ShowTagsDialog and ShowShallowTagsDialog) does not.
    def test_save_games_emits_metadata_updated_for_active_game(self):
        """save_games(games) should emit metadata_updated so the Moves List refreshes."""
        from app.services.chess_log_storage_service import ChessLogStorageService

        game = _make_game()
        path_key = "0"
        entry = _make_entry("CLAMP", "C", "my note")
        with patch.object(ChessLogStorageService, "store_tags", return_value=True), \
                patch.object(ChessLogStorageService, "clear_tags", return_value=True), \
                patch.object(ChessLogStorageService, "load_tags",
                             return_value={path_key: [entry]}):
            ctrl, game_model = self._controller_with_active_game(game, path_key, entry)
            saved, failed = ctrl.save_games([game])

        # Precondition: the save itself succeeded, so the failure below is
        # about the missing notification and nothing else.
        self.assertEqual((saved, failed), (1, 0))
        self.assertGreater(
            game_model.metadata_updated.emit.call_count, 0,
            "save_games() did not emit metadata_updated — Moves List icons remain stale",
        )

    # -- Test 2: the same gap, reached through ShowTagsDialog._on_save()
    # Deletion gesture (no categories, empty why) -> replace_entries_at_path_for_game
    # -> save_games.  A real controller is used so the whole Save path runs.
    def test_show_tags_dialog_save_triggers_moves_list_refresh(self):
        """ShowTagsDialog Save of a deletion must make the Moves List refresh."""
        from PyQt6.QtWidgets import QCheckBox, QPlainTextEdit
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog

        game = _make_game()
        path_key = "0"
        entry = _make_entry("CLAMP", "C", "my note")
        with patch.object(ChessLogStorageService, "store_tags", return_value=True), \
                patch.object(ChessLogStorageService, "clear_tags", return_value=True) as clear, \
                patch.object(ChessLogStorageService, "load_tags",
                             return_value={path_key: [entry]}):
            ctrl, game_model = self._controller_with_active_game(game, path_key, entry)
            dlg = ShowTagsDialog({}, [game], ctrl)
            self.assertEqual(len(dlg._row_widgets), 1)
            row = dlg._row_widgets[0]
            for cb in row.findChildren(QCheckBox):
                cb.setChecked(False)
            for te in row.findChildren(QPlainTextEdit):
                te.setPlainText("")
            dlg._on_save()

        # Precondition: the deletion really was saved (tag cleared on the PGN).
        clear.assert_called_once()
        self.assertEqual(ctrl._cached_paths_data, {})
        self.assertGreater(
            game_model.metadata_updated.emit.call_count, 0,
            "ShowTagsDialog Save cleared the tag but nothing told the Moves List",
        )


# ---------------------------------------------------------------------------
# Charts tab / AI-settings findings (B2..B7)
# ---------------------------------------------------------------------------

def _charts_controller():
    from app.controllers.chess_log_charts_controller import ChessLogChartsController
    return ChessLogChartsController({}, MagicMock())


@requires_qt
class TestB2ChartsNotRefreshedOnSave(unittest.TestCase):
    """B2: notify_chess_log_saved() refreshes only the player dropdown."""

    @unittest.expectedFailure
    def test_save_notification_reaggregates_charts(self):
        ctrl = _charts_controller()
        ctrl._source_selection = 1
        ctrl._player_explicit_selected = True
        ctrl._current_player = "W"
        with patch.object(ctrl, "_start_dropdown_worker"), \
                patch.object(ctrl, "_resolve_games", return_value=[]), \
                patch.object(ctrl, "_schedule_charts_refresh") as refresh:
            ctrl.notify_chess_log_saved()
        refresh.assert_called()


@requires_qt
class TestB3PlayerComboSilentClear(unittest.TestCase):
    """B3: _on_players_ready blanks the player combo with signals blocked."""

    def test_vanished_player_clears_results_and_controller_selection(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView

        ctrl = _charts_controller()
        view = DetailChessLogChartsView({})
        view.set_controller(ctrl)
        view._on_players_ready([("X", 1)])
        view._player_combo.setCurrentIndex(0)      # user picks X
        ctrl.set_player_selection("X")
        view._last_narrative = "narrative about X"
        # X's last moment is cleared; the refreshed dropdown no longer lists X.
        view._on_players_ready([("Y", 2)])
        self.assertEqual(view._player_combo.currentIndex(), -1)
        # The combo says "no player", so nothing about X may remain in force.
        self.assertFalse(ctrl.has_player_selected())
        self.assertEqual(view._last_narrative, "")

    def _selected_view(self, ctrl):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        view = DetailChessLogChartsView({})
        view.set_controller(ctrl)
        view._on_players_ready([("X", 1), ("Y", 2)])
        view._player_combo.setCurrentIndex(0)
        ctrl.set_player_selection("X")
        return view

    def test_refresh_still_listing_player_keeps_selection_and_results(self):
        ctrl = _charts_controller()
        view = self._selected_view(ctrl)
        ctrl._cached_narrative = "cached about X"
        view._last_narrative = "narrative about X"
        view._on_players_ready([("X", 3), ("Y", 2)])
        self.assertEqual(view._player_combo.currentData(), "X")
        self.assertTrue(ctrl.has_player_selected())
        self.assertEqual(ctrl._cached_narrative, "cached about X")
        self.assertEqual(view._last_narrative, "narrative about X")

    def test_vanished_player_disables_ai_buttons(self):
        ctrl = _charts_controller()
        view = self._selected_view(ctrl)
        view._source_combo.blockSignals(True)
        view._source_combo.setCurrentIndex(1)
        view._source_combo.blockSignals(False)
        with patch.object(ctrl, "is_ai_configured", return_value=True):
            view._refresh_ai_state()
            self.assertTrue(view._show_shallow_btn.isEnabled())
            view._on_players_ready([("Y", 2)])
            self.assertFalse(view._show_shallow_btn.isEnabled())
            # The Narrative button is enabled by AI configuration alone (existing
            # design); with no player the controller refuses the request instead.
            self.assertFalse(ctrl.has_player_selected())
            ctrl._source_selection = 1
            failures = []
            ctrl.narrative_failed.connect(failures.append)
            ctrl.request_narrative()
            self.assertEqual(failures, ["Please select a player first."])


@requires_qt
class TestB4EmptyNotesPathLeavesControllerCacheStale(unittest.TestCase):
    """B4: the 'no notes' path emits shallow_ready without updating the cache."""

    @unittest.expectedFailure
    def test_empty_check_logs_run_clears_controller_cache(self):
        ctrl = _charts_controller()
        g = _make_game()
        ctrl._cached_shallow_keys = frozenset({(g, "0", "CLAMP", "")})
        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=("openai", "m", "k", None)), \
                patch.object(ctrl, "_resolve_games", return_value=[g]), \
                patch("app.services.chess_log_shallow_service.build_notes",
                      return_value=({}, {}, {})):
            ctrl.request_flag_shallow_notes()
        # The run reported "nothing to classify"; the cached result of the
        # previous run must not survive to be restored onto a rebuilt view.
        self.assertIsNone(ctrl.get_last_shallow_result()[0])


@requires_qt
class TestB5VagueOnlyExport(unittest.TestCase):
    """B5: Check Logs export is gated on _last_shallow_keys only."""

    @unittest.expectedFailure
    def test_vague_only_result_is_exported(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView

        game = _make_game()
        entry = _make_entry("3x3", "Why4", "vague lesson")
        chess_log_ctrl = MagicMock()
        chess_log_ctrl.get_tags_for_game.return_value = {"0": [entry]}
        charts = MagicMock()
        charts.get_chess_log_controller.return_value = chess_log_ctrl
        charts.resolve_games.return_value = [game]

        view = DetailChessLogChartsView({})
        view._controller = charts
        view._last_shallow_keys = None
        view._last_vague_keys = frozenset({(game, "0", "3x3", "Why4")})
        groups = view._build_check_log_tag_groups()
        self.assertEqual(len(groups), 1, "vague-only Check Logs result missing from export")


@requires_qt
class TestB6TokensSpinNotRestored(unittest.TestCase):
    """B6: a rebuilt view shows the default token limit, the controller uses another."""

    def test_tokens_spin_reflects_controller_limit(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView

        ctrl = _charts_controller()
        ctrl.set_narrative_token_limit(20000)
        view = DetailChessLogChartsView({})          # what MainWindow.apply_theme() does
        view.set_controller(ctrl)
        self.assertEqual(view._tokens_spin.value(), ctrl._narrative_token_limit)
        self.assertEqual(ctrl.get_narrative_token_limit(), 20000)   # restoring did not write back

    def test_restore_does_not_write_back_to_controller(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView

        ctrl = _charts_controller()
        ctrl.set_narrative_token_limit(20000)
        view = DetailChessLogChartsView({})
        with patch.object(ctrl, "set_narrative_token_limit") as setter:
            view.set_controller(ctrl)
        setter.assert_not_called()

    def test_default_limit_literal_defined_once(self):
        import re
        from pathlib import Path
        from app.controllers.chess_log_charts_controller import DEFAULT_NARRATIVE_TOKEN_LIMIT

        self.assertEqual(DEFAULT_NARRATIVE_TOKEN_LIMIT, 12000)
        hits = []
        for path in Path("app").rglob("*.py"):
            if "chess_log" not in path.name:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\b12000\b", line):
                    hits.append((path.name, line.strip().split("  #")[0]))
        self.assertEqual(hits, [("chess_log_charts_controller.py", "DEFAULT_NARRATIVE_TOKEN_LIMIT = 12000")])


@requires_qt
class TestB7AISettingsSnapshotStale(unittest.TestCase):
    """B7: the Charts controller reads AI settings live, never from a snapshot."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from app.services.user_settings_service import UserSettingsService

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.svc = UserSettingsService(Path(tmp.name) / "user_settings.json")
        self.svc.get_model().set_ai_models({})
        self.svc.get_model().set_ai_summary({})
        p = patch.object(UserSettingsService, "get_instance", classmethod(lambda cls, *a, **k: self.svc))
        p.start()
        self.addCleanup(p.stop)

    def test_timeout_changed_elsewhere_is_seen(self):
        ctrl = _charts_controller()
        ctrl.set_user_settings(self.svc.get_settings())
        # #90: Chess Log's timeout is its own key; a write through the service is seen live.
        self.svc.update_chess_log_settings({"ai_timeout_seconds": 90})
        self.assertEqual(ctrl.get_narrative_timeout_seconds(), 90)
        # ...and AI Summary's timeout is no longer shared with it.
        self.svc.update_ai_summary_settings({"request_timeout_seconds": 45})
        self.assertEqual(ctrl.get_narrative_timeout_seconds(), 90)

    def test_provider_toggle_reflected_without_set_user_settings(self):
        self.svc.update_ai_model_settings({
            "openai": {"api_key": "sk-o", "model": "gpt-4o", "models": ["gpt-4o"]},
            "anthropic": {"api_key": "sk-a", "model": "claude-x", "models": ["claude-x", "claude-y"]},
        })
        self.svc.update_ai_summary_settings({
            "use_openai_models": True, "use_anthropic_models": False, "use_custom_models": False,
        })
        ctrl = _charts_controller()
        self.assertEqual(ctrl.get_available_models(), ["gpt-4o"])
        self.svc.update_ai_summary_settings({
            "use_openai_models": False, "use_anthropic_models": True, "use_custom_models": False,
        })
        self.assertEqual(ctrl.get_available_models(), ["claude-x", "claude-y"])
        self.assertEqual(ctrl.get_default_narrative_model(), "claude-x")

    def test_ai_settings_changed_signal_updates_controller_and_signals(self):
        self.svc.update_ai_model_settings({"openai": {"api_key": "k", "model": "m", "models": ["m"]}})
        self.svc.update_ai_summary_settings({"use_openai_models": True})
        ctrl = _charts_controller()
        self.svc.get_model().ai_settings_changed.connect(ctrl.on_ai_settings_changed)
        configured, models = [], []
        ctrl.ai_configured_changed.connect(configured.append)
        ctrl.ai_model_changed.connect(lambda: models.append(1))
        self.svc.update_ai_summary_settings({"request_timeout_seconds": 90})
        self.assertEqual(configured, [True])   # first sighting of a configured provider
        self.assertEqual(len(models), 1)
        self.svc.update_ai_summary_settings({"request_timeout_seconds": 91})
        self.assertEqual(configured, [True])   # unchanged provider: no repeat signal
        self.assertEqual(len(models), 1)

    def test_controller_has_no_user_settings_snapshot_attribute(self):
        ctrl = _charts_controller()
        self.assertFalse(hasattr(ctrl, "_user_settings"))
        import inspect
        from app.controllers import chess_log_charts_controller as mod
        self.assertNotIn("_user_settings", inspect.getsource(mod).replace("set_user_settings", ""))


if __name__ == "__main__":
    unittest.main()
