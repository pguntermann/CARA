"""#92: ChessLogController emits chess_log_changed; views subscribe.

Covers the owner's emits (Log, Clear, dialog edit, save current / all), the
Chess Log tab's single debounced refresh, the Moves List's single icon refresh
for the active game, and a guard that no caller notifies the views directly.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[2]


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                           timeout=10, cwd=str(REPO))
        return r.returncode == 0 and b"ok" in r.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"][Round "?"]'
    '[White "W"][Black "B"][Result "*"]\n\n1. e4 e5 *\n'
)


def _game(n=1):
    from app.models.database_model import GameData
    return GameData(game_number=n, pgn=PGN)


def _entry(cat="C"):
    from app.services.chess_log_storage_service import ChessLogStorageService
    return ChessLogStorageService.make_entry("CLAMP", cat, "note")


def _owner(game):
    """Real ChessLogController whose active game is *game*."""
    from app.controllers.chess_log_controller import ChessLogController
    game_model = MagicMock()
    game_model.active_game = game
    game_model.get_active_path.return_value = []
    game_controller = MagicMock()
    game_controller.get_game_model.return_value = game_model
    ctrl = ChessLogController(config={}, game_controller=game_controller,
                              database_controller=None)
    ctrl._load_into_cache(game)
    return ctrl, game_model


def _pump(until, timeout=2.0):
    deadline = time.time() + timeout
    while not until() and time.time() < deadline:
        _APP.processEvents()
    for _ in range(3):
        _APP.processEvents()


class _Recorder:
    def __init__(self, owner):
        self.games = []
        owner.chess_log_changed.connect(self.games.append)


@requires_qt
class TestOwnerEmits(unittest.TestCase):

    def test_log_moment_emits_for_the_game(self):
        game = _game()
        owner, _ = _owner(game)
        rec = _Recorder(owner)
        self.assertTrue(owner.add_moment_at_active_path(
            [{"preset": "CLAMP", "cat": "C", "why": "x"}]))
        self.assertEqual(len(rec.games), 1)
        self.assertIs(rec.games[0], game)

    def test_clear_emits(self):
        game = _game()
        owner, _ = _owner(game)
        owner.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "x"}])
        rec = _Recorder(owner)
        owner.clear_tags_for_current_game()
        self.assertEqual(len(rec.games), 1)
        self.assertIs(rec.games[0], game)

    def test_dialog_edit_emits(self):
        game = _game()
        owner, _ = _owner(game)
        rec = _Recorder(owner)
        owner.replace_entries_at_path("0", "CLAMP", [_entry()])
        owner.replace_entries_at_path_for_game(game, "0", "CLAMP", [_entry("L")])
        self.assertEqual(len(rec.games), 2)
        self.assertTrue(all(g is game for g in rec.games))

    def test_save_current_game_emits_after_successful_persist(self):
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _game()
        owner, _ = _owner(game)
        owner.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "x"}])
        rec = _Recorder(owner)
        self.assertTrue(owner.save_tags_for_current_game())
        self.assertEqual(len(rec.games), 1)
        self.assertIs(rec.games[0], game)
        # A failed persist emits nothing.
        rec.games.clear()
        with patch.object(ChessLogStorageService, "store_tags", return_value=False):
            self.assertFalse(owner.save_tags_for_current_game())
        self.assertEqual(rec.games, [])

    def test_save_all_emits_once_per_game(self):
        g1, g2 = _game(1), _game(2)
        owner, _ = _owner(g1)
        owner.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "x"}])
        owner.replace_entries_at_path_for_game(g2, "0", "CLAMP", [_entry()])
        rec = _Recorder(owner)
        saved, failed = owner.save_all_dirty_games()
        self.assertEqual((saved, failed), (2, 0))
        self.assertEqual({id(g) for g in rec.games}, {id(g1), id(g2)})
        self.assertEqual(len(rec.games), 2)


@requires_qt
class TestSubscribersRefreshOnce(unittest.TestCase):
    """Real owner + real charts controller + real Moves List view."""

    def _wire(self):
        from app.controllers.chess_log_charts_controller import ChessLogChartsController
        from app.models.moveslist_model import MovesListModel
        from app.views.detail_moveslist_view import DetailMovesListView

        game = _game()
        owner, game_model = _owner(game)

        charts = ChessLogChartsController({}, MagicMock())
        charts.set_chess_log_controller(owner)
        charts._source_selection = 1
        charts._player_explicit_selected = True
        charts._current_player = "W"
        charts._data_changed_debounce_ms = 1
        charts._start_dropdown_worker = MagicMock()
        charts._schedule_charts_refresh = MagicMock()
        charts._resolve_games = lambda: [game]

        model = MovesListModel()
        model.notify_chess_log_changed = MagicMock()
        view = DetailMovesListView(config={})
        view._moveslist_model = model
        view._game_model = game_model
        view.set_chess_log_controller(owner)
        return game, owner, charts, model, view

    def _settle(self, charts):
        _pump(lambda: charts._schedule_charts_refresh.call_count > 0)

    def test_log_pending_edit_one_chart_refresh_one_icon_refresh(self):
        game, owner, charts, model, _view = self._wire()
        owner.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "x"}])
        self._settle(charts)
        charts._schedule_charts_refresh.assert_called_once()
        charts._start_dropdown_worker.assert_called_once()
        model.notify_chess_log_changed.assert_called_once()

    def test_clear_one_each(self):
        game, owner, charts, model, _view = self._wire()
        owner.clear_tags_for_current_game()
        self._settle(charts)
        charts._schedule_charts_refresh.assert_called_once()
        model.notify_chess_log_changed.assert_called_once()

    def test_dialog_edit_one_each(self):
        game, owner, charts, model, _view = self._wire()
        owner.replace_entries_at_path("0", "CLAMP", [_entry()])
        self._settle(charts)
        charts._schedule_charts_refresh.assert_called_once()
        model.notify_chess_log_changed.assert_called_once()

    def test_save_current_game_one_each(self):
        game, owner, charts, model, _view = self._wire()
        owner.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "x"}])
        self._settle(charts)
        charts._schedule_charts_refresh.reset_mock()
        charts._start_dropdown_worker.reset_mock()
        model.notify_chess_log_changed.reset_mock()
        owner.save_tags_for_current_game()
        self._settle(charts)
        charts._schedule_charts_refresh.assert_called_once()
        charts._start_dropdown_worker.assert_called_once()
        model.notify_chess_log_changed.assert_called_once()

    def test_save_all_games_one_chart_refresh_icon_refresh_only_for_active(self):
        game, owner, charts, model, _view = self._wire()
        other = _game(2)
        owner.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "x"}])
        owner.replace_entries_at_path_for_game(other, "0", "CLAMP", [_entry()])
        self._settle(charts)
        charts._schedule_charts_refresh.reset_mock()
        model.notify_chess_log_changed.reset_mock()
        owner.save_all_dirty_games()   # two games saved -> two emits
        self._settle(charts)
        charts._schedule_charts_refresh.assert_called_once()
        model.notify_chess_log_changed.assert_called_once()  # only the active game

    def test_change_to_inactive_game_leaves_moves_list_alone(self):
        game, owner, charts, model, _view = self._wire()
        owner.replace_entries_at_path_for_game(_game(2), "0", "CLAMP", [_entry()])
        self._settle(charts)
        charts._schedule_charts_refresh.assert_called_once()
        model.notify_chess_log_changed.assert_not_called()

    def test_moves_list_ignores_owner_after_it_is_replaced(self):
        game, owner, charts, model, view = self._wire()
        view.set_chess_log_controller(None)
        owner.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "x"}])
        model.notify_chess_log_changed.assert_not_called()


class TestNoDirectNotifications(unittest.TestCase):
    """Only ChessLogController's signal reaches the views' Chess Log refreshes."""

    def _app_sources(self):
        for path in (REPO / "app").rglob("*.py"):
            yield path, path.read_text(encoding="utf-8")

    def test_removed_notify_helpers_are_gone(self):
        pattern = re.compile(r"\bnotify_chess_log_saved\b|\b_notify_moveslist_chess_log_changed\b")
        offenders = [str(p.relative_to(REPO)) for p, text in self._app_sources()
                     if pattern.search(text)]
        self.assertEqual(offenders, [])

    def test_moves_list_refresh_is_called_only_by_its_own_subscription(self):
        call = re.compile(r"\.notify_chess_log_changed\(")
        offenders = [str(p.relative_to(REPO)) for p, text in self._app_sources()
                     if call.search(text)]
        self.assertEqual(offenders, ["app/views/detail_moveslist_view.py"])


if __name__ == "__main__":
    unittest.main()
