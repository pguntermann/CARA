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

    @unittest.expectedFailure
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


@requires_qt
class TestB4EmptyNotesPathLeavesControllerCacheStale(unittest.TestCase):
    """B4: the 'no notes' path emits shallow_ready without updating the cache."""

    @unittest.expectedFailure
    def test_empty_check_logs_run_clears_controller_cache(self):
        ctrl = _charts_controller()
        g = _make_game()
        ctrl._cached_shallow_keys = frozenset({(g, "0", "CLAMP", "")})
        ctrl._user_settings = {"x": 1}
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

    @unittest.expectedFailure
    def test_tokens_spin_reflects_controller_limit(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView

        ctrl = _charts_controller()
        ctrl.set_narrative_token_limit(20000)
        view = DetailChessLogChartsView({})          # what MainWindow.apply_theme() does
        view.set_controller(ctrl)
        self.assertEqual(view._tokens_spin.value(), ctrl._narrative_token_limit)


class TestB7AISettingsSnapshotStale(unittest.TestCase):
    """B7: the Charts controller reads a snapshot of user settings."""

    @unittest.expectedFailure
    def test_timeout_changed_elsewhere_is_seen(self):
        import tempfile
        from pathlib import Path
        from app.services.user_settings_service import UserSettingsService

        with tempfile.TemporaryDirectory() as d:
            svc = UserSettingsService(Path(d) / "user_settings.json")
            ctrl = _charts_controller()
            ctrl.set_user_settings(svc.get_settings())
            # AI Summary's timeout spin writes straight to the shared key.
            svc.update_ai_summary_settings({"request_timeout_seconds": 90})
            self.assertEqual(svc.get_settings()["ai_summary"]["request_timeout_seconds"], 90)
            self.assertEqual(ctrl.get_narrative_timeout_seconds(), 90)



if __name__ == "__main__":
    unittest.main()
