"""Unit tests for ChessLogController.

Uses MagicMock for GameModel to avoid requiring a running QApplication;
the real Qt signal/slot wiring is exercised in CI (QT_QPA_PLATFORM=offscreen).
"""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import MagicMock, patch

from app.controllers.chess_log_controller import ChessLogController
from app.models.database_model import GameData
from app.services.chess_log_storage_service import ChessLogStorageService

MINIMAL_PGN = (
    '[Event "Test"]\n[Site "?"]\n[Date "2026.08.24"]\n'
    '[Round "?"]\n[White "White"]\n[Black "Black"]\n[Result "*"]\n\n'
    '1. e4 ( 1. d4 ) e5 2. Nf3 Nc6 *\n'
)


def make_game(game_number: int = 1, pgn: str = MINIMAL_PGN) -> GameData:
    return GameData(game_number=game_number, pgn=pgn)


def make_game_model_mock(game: GameData = None, active_path=()) -> MagicMock:
    """Return a MagicMock that behaves like GameModel for ChessLogController."""
    gm = MagicMock()
    gm.active_game = game
    gm.get_active_path.return_value = active_path
    gm.active_game_changed = MagicMock()
    gm.active_game_changed.connect = MagicMock()
    gm.metadata_updated = MagicMock()
    gm.metadata_updated.emit = MagicMock()
    return gm


def make_game_controller_mock(game_model: MagicMock) -> MagicMock:
    gc = MagicMock()
    gc.get_game_model.return_value = game_model
    return gc


def make_user_settings_mock(active_preset="CLAMP") -> MagicMock:
    uss = MagicMock()
    uss.get_chess_log.return_value = {"active_preset": active_preset}
    return uss


def make_controller(game=None, active_path=(), user_settings_service=None) -> tuple[ChessLogController, MagicMock]:
    gm = make_game_model_mock(game, active_path)
    gc = make_game_controller_mock(gm)
    ctrl = ChessLogController({}, gc, user_settings_service=user_settings_service)
    if game is not None:
        ctrl._cached_game = game
    return ctrl, gm


class TestPresetAccessors(unittest.TestCase):
    def test_get_active_preset_reads_from_user_settings(self):
        uss = make_user_settings_mock(active_preset="CCT")
        ctrl, _ = make_controller(user_settings_service=uss)
        self.assertEqual(ctrl.get_active_preset(), "CCT")

    def test_get_active_preset_defaults_to_clamp_when_no_service(self):
        ctrl, _ = make_controller(user_settings_service=None)
        self.assertEqual(ctrl.get_active_preset(), "CLAMP")

    def test_get_active_preset_defaults_to_clamp_when_key_missing(self):
        uss = MagicMock()
        uss.get_chess_log.return_value = {}  # chess_log key exists but active_preset missing
        ctrl, _ = make_controller(user_settings_service=uss)
        self.assertEqual(ctrl.get_active_preset(), "CLAMP")

    def test_get_active_preset_coerces_unknown_preset_to_clamp(self):
        uss = make_user_settings_mock(active_preset="Custom")
        ctrl, _ = make_controller(user_settings_service=uss)
        self.assertEqual(ctrl.get_active_preset(), "CLAMP")


class TestAddMomentBelowCap(unittest.TestCase):
    def test_add_first_moment(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)

        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            result = ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "M", "why": ""}])

        self.assertTrue(result)
        self.assertEqual(ChessLogStorageService.count_tags(ctrl._cached_paths_data), 1)

    def test_add_three_distinct_moments(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        for path_key in ("0", "0.0", "0.0.0"):
            with patch("app.controllers.chess_log_controller.encode_path", return_value=path_key):
                self.assertTrue(
                    ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "L", "why": ""}])
                )
        self.assertEqual(ChessLogStorageService.count_tags(ctrl._cached_paths_data), 3)

    def test_empty_entries_returns_false(self):
        ctrl, _ = make_controller(make_game())
        self.assertFalse(ctrl.add_moment_at_active_path([]))

    def test_no_active_game_returns_false(self):
        ctrl, _ = make_controller(game=None)
        self.assertFalse(ctrl.add_moment_at_active_path([{"preset": "CCT", "cat": "C", "why": ""}]))


class TestAddMomentNagRemoved(unittest.TestCase):
    """add_moment_at_active_path no longer fires the nag — nag moved to should_confirm_extra_moment."""

    def _ctrl_with_three_moments(self) -> ChessLogController:
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M")],
            "0.0": [ChessLogStorageService.make_entry("CLAMP", "L")],
            "0.0.0": [ChessLogStorageService.make_entry("CCT", "C")],
        }
        return ctrl

    def test_fourth_moment_added_without_nag(self):
        ctrl = self._ctrl_with_three_moments()
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0.0.0.0"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation") as mock_dlg:
            result = ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "P", "why": ""}])
        self.assertTrue(result)
        self.assertEqual(ChessLogStorageService.count_tags(ctrl._cached_paths_data), 4)
        mock_dlg.assert_not_called()

    def test_adding_to_existing_path_succeeds(self):
        ctrl = self._ctrl_with_three_moments()
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0.0"):
            result = ctrl.add_moment_at_active_path([{"preset": "CCT", "cat": "T", "why": ""}])
        self.assertTrue(result)
        self.assertEqual(ChessLogStorageService.count_tags(ctrl._cached_paths_data), 3)
        self.assertEqual(len(ctrl._cached_paths_data["0.0"]), 2)


class TestShouldConfirmExtraMoment(unittest.TestCase):
    """should_confirm_extra_moment: nag fires at the right time and is suppressed correctly."""

    def _ctrl_with_three_moments(self, gid: int = 1) -> tuple[ChessLogController, MagicMock]:
        game = make_game(game_number=gid)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M")],
            "0.0": [ChessLogStorageService.make_entry("CLAMP", "L")],
            "0.0.0": [ChessLogStorageService.make_entry("CCT", "C")],
        }
        return ctrl, gm

    def test_nag_fires_on_fourth_new_moment_when_never_shown(self):
        ctrl, gm = self._ctrl_with_three_moments()
        gm.get_active_path.return_value = (99,)  # maps to a fresh path key
        with patch("app.controllers.chess_log_controller.encode_path", return_value="fresh"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation", return_value=True) as mock_dlg:
            result = ctrl.should_confirm_extra_moment(None)
        mock_dlg.assert_called_once()
        self.assertTrue(result)
        self.assertTrue(ctrl._nag_shown_this_session)
        self.assertTrue(ctrl._nag_shown_by_game.get(id(ctrl._cached_game), False))

    def test_nag_suppressed_by_session_flag(self):
        ctrl, gm = self._ctrl_with_three_moments()
        ctrl._nag_shown_this_session = True
        gm.get_active_path.return_value = (99,)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="fresh"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation") as mock_dlg:
            result = ctrl.should_confirm_extra_moment(None)
        mock_dlg.assert_not_called()
        self.assertTrue(result)

    def test_nag_suppressed_by_per_game_flag(self):
        ctrl, gm = self._ctrl_with_three_moments(gid=1)
        ctrl._nag_shown_by_game[id(ctrl._cached_game)] = True
        ctrl._nag_shown_this_session = False
        gm.get_active_path.return_value = (99,)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="fresh"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation") as mock_dlg:
            result = ctrl.should_confirm_extra_moment(None)
        mock_dlg.assert_not_called()
        self.assertTrue(result)

    def test_nag_does_not_fire_for_reused_path(self):
        ctrl, gm = self._ctrl_with_three_moments()
        gm.get_active_path.return_value = ()
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0.0"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation") as mock_dlg:
            result = ctrl.should_confirm_extra_moment(None)
        mock_dlg.assert_not_called()
        self.assertTrue(result)

    def test_nag_does_not_fire_below_threshold(self):
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M")],
            "0.0": [ChessLogStorageService.make_entry("CLAMP", "L")],
        }
        gm.get_active_path.return_value = ()
        with patch("app.controllers.chess_log_controller.encode_path", return_value="fresh"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation") as mock_dlg:
            result = ctrl.should_confirm_extra_moment(None)
        mock_dlg.assert_not_called()
        self.assertTrue(result)

    def test_nag_declined_still_sets_flags(self):
        """Declining the nag still sets both flags — it fires at most once regardless of answer."""
        ctrl, gm = self._ctrl_with_three_moments(gid=1)
        gm.get_active_path.return_value = (99,)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="fresh"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation", return_value=False):
            result = ctrl.should_confirm_extra_moment(None)
        self.assertFalse(result)
        self.assertTrue(ctrl._nag_shown_this_session)
        self.assertTrue(ctrl._nag_shown_by_game.get(id(ctrl._cached_game), False))

    def test_add_moment_no_longer_fires_nag(self):
        ctrl, gm = self._ctrl_with_three_moments()
        gm.get_active_path.return_value = ()
        with patch("app.controllers.chess_log_controller.encode_path", return_value="fresh"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation") as mock_dlg:
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "A", "why": ""}])
        mock_dlg.assert_not_called()


class TestStep3ClearedGameLog(unittest.TestCase):
    """Failing test for issue #85 Step 3: cleared game → log → moment invisible.

    Root cause: add_moment_at_active_path never sets game.has_chess_log_tags = True,
    so multi-game views (Show All Games, Log column, charts) remain blind to the new
    moment.  For a cleared game the symptom is especially visible: the game WAS shown
    (has_chess_log_tags was True after the last save), then immediately disappeared when
    the user cleared (clear_tags wrote the PGN and set it False), and never came back
    after the new log.
    """

    def test_has_chess_log_tags_synced_after_log_on_cleared_game(self):
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game

        with patch("app.controllers.chess_log_controller.encode_path", return_value="0.0.0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "M", "why": ""}])
        ctrl.save_tags_for_current_game()
        self.assertTrue(game.has_chess_log_tags, "precondition: saved moment sets True")

        ctrl.clear_tags_for_current_game()
        self.assertFalse(game.has_chess_log_tags, "pending clear sets False immediately")

        with patch("app.controllers.chess_log_controller.encode_path", return_value="0.0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "new"}])

        self.assertTrue(
            game.has_chess_log_tags,
            "logging on a cleared game must set has_chess_log_tags=True "
            "(multi-game views filter on this attribute)",
        )

    def test_has_chess_log_tags_synced_after_first_log_on_new_game(self):
        """Addendum: same bug on a brand-new game (never had moments)."""
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game

        self.assertFalse(game.has_chess_log_tags, "precondition: new game starts False")

        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "M", "why": ""}])

        self.assertTrue(
            game.has_chess_log_tags,
            "first log on a new game must set has_chess_log_tags=True",
        )


class TestSaveAndClear(unittest.TestCase):
    def test_save_persists_to_pgn(self):
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "A", "why": "test"}])
        ctrl.save_tags_for_current_game()
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game))
        loaded = ChessLogStorageService.load_tags(game)
        self.assertEqual(ChessLogStorageService.count_tags(loaded), 1)

    def test_clear_pending_clears_in_memory_and_syncs_has_tags(self):
        """clear_tags_for_current_game is pending: empties cache and sets has_chess_log_tags=False
        immediately, but does NOT write through to PGN until save."""
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CCT", "cat": "C", "why": ""}])
        ctrl.save_tags_for_current_game()
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game))
        ctrl.clear_tags_for_current_game()
        # In-memory cache is empty immediately.
        self.assertEqual(ctrl._cached_paths_data, {})
        # has_chess_log_tags Python attribute is synced immediately via _write_store.
        self.assertFalse(game.has_chess_log_tags)
        # PGN is NOT yet changed — save required to remove headers from disk.
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game))
        # After saving, PGN headers are removed.
        ctrl.save_tags_for_current_game()
        self.assertFalse(ChessLogStorageService.has_chess_log_tags(game))

    def test_metadata_updated_emitted_on_save(self):
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl.save_tags_for_current_game()
        gm.metadata_updated.emit.assert_called_once()

    def test_metadata_updated_emitted_on_clear(self):
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl.clear_tags_for_current_game()
        gm.metadata_updated.emit.assert_called_once()

    def test_clear_marks_game_dirty(self):
        """clear_tags_for_current_game is pending — it adds the game to _dirty_games
        so save_all_dirty_games will remove the PGN headers."""
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game
        ctrl.clear_tags_for_current_game()
        self.assertIn(id(game), ctrl._dirty_games)

    def test_clear_appears_in_subsequent_save_all(self):
        """After clearing, save_all_dirty_games saves the pending clear (removes PGN headers)."""
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game
        ctrl.clear_tags_for_current_game()
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)


class TestGetEntriesAtActivePath(unittest.TestCase):
    def test_returns_empty_for_untagged_path(self):
        ctrl, _ = make_controller(make_game())
        ctrl._cached_game_id = make_game().game_number
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            result = ctrl.get_entries_at_active_path()
        self.assertEqual(result, [])

    def test_returns_entries_for_tagged_path(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        entry = ChessLogStorageService.make_entry("CLAMP", "M")
        ctrl._cached_paths_data = {"0": [entry]}
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            result = ctrl.get_entries_at_active_path()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["cat"], "M")

    def test_returns_copy_not_reference(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "C")]}
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            result = ctrl.get_entries_at_active_path()
        result.clear()
        self.assertEqual(len(ctrl._cached_paths_data["0"]), 1)


class TestRetagSamePresetReplaces(unittest.TestCase):
    def test_retag_same_preset_replaces_not_appends(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M")],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": ""}])
        entries = ctrl._cached_paths_data["0"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["cat"], "C")

    def test_retag_different_preset_preserves_existing(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M")],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CCT", "cat": "Threats", "why": ""}])
        entries = ctrl._cached_paths_data["0"]
        self.assertEqual(len(entries), 2)
        presets = {e["preset"] for e in entries}
        self.assertEqual(presets, {"CLAMP", "CCT"})

    def test_retag_still_counts_as_one_moment(self):
        """Re-tagging an existing path doesn't increase the moment count."""
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "M")],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": ""}])
        self.assertEqual(ChessLogStorageService.count_tags(ctrl._cached_paths_data), 1)


class TestCacheReloadOnGameChange(unittest.TestCase):
    def test_cache_reloads_when_game_changes(self):
        game2 = make_game(game_number=2)
        ChessLogStorageService.store_tags(
            game2, {"0": [ChessLogStorageService.make_entry("CLAMP", "P")]}
        )
        ctrl, gm = make_controller(game=None)

        # Simulate game1 loaded (no tags)
        game1 = make_game(game_number=1)
        gm.active_game = game1
        ctrl._on_active_game_changed(game1)
        self.assertEqual(ctrl.get_tags_for_current_game(), {})

        # Switch to game2 (has a tag)
        gm.active_game = game2
        ctrl._on_active_game_changed(game2)
        tags = ctrl.get_tags_for_current_game()
        self.assertEqual(ChessLogStorageService.count_tags(tags), 1)

    def test_cache_clears_on_none_game(self):
        game = make_game()
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {"0": [ChessLogStorageService.make_entry("CCT", "C")]}

        gm.active_game = None
        ctrl._on_active_game_changed(None)
        self.assertEqual(ctrl._cached_paths_data, {})
        self.assertIsNone(ctrl._cached_game_id)


class TestGameHasAnyTags(unittest.TestCase):
    def test_true_when_cache_has_entries(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "C")]}
        self.assertTrue(ctrl.game_has_any_tags())

    def test_false_when_cache_empty(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {}
        self.assertFalse(ctrl.game_has_any_tags())

    def test_false_when_cache_only_has_empty_lists(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {"0": [], "0.0": []}
        self.assertFalse(ctrl.game_has_any_tags())


class TestReplaceEntriesAtPath(unittest.TestCase):
    def test_replaces_only_named_preset(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {
            "0": [
                ChessLogStorageService.make_entry("CLAMP", "M"),
                ChessLogStorageService.make_entry("CCT", "Threats"),
            ]
        }
        ctrl.replace_entries_at_path(
            "0", "CLAMP", [{"preset": "CLAMP", "cat": "C", "why": "new"}]
        )
        entries = ctrl._cached_paths_data["0"]
        clamp = [e for e in entries if e["preset"] == "CLAMP"]
        cct = [e for e in entries if e["preset"] == "CCT"]
        self.assertEqual(len(clamp), 1)
        self.assertEqual(clamp[0]["cat"], "C")
        self.assertEqual(len(cct), 1)
        self.assertEqual(cct[0]["cat"], "Threats")

    def test_new_path_creates_entry(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {}
        ctrl.replace_entries_at_path(
            "9", "CCT", [{"preset": "CCT", "cat": "Threats", "why": "missed"}]
        )
        self.assertIn("9", ctrl._cached_paths_data)
        self.assertEqual(ctrl._cached_paths_data["9"][0]["cat"], "Threats")


class TestMultiGameCache(unittest.TestCase):
    """Multi-game cache: get_tags_for_game, replace_entries_at_path_for_game,
    save_all_dirty_games, and coherency at active-game transitions."""

    def _make_ctrl(self, active_game=None):
        ctrl, gm = make_controller(active_game)
        if active_game:
            ctrl._cached_game_id = id(active_game)
        return ctrl, gm

    # ------------------------------------------------------------------
    # Basic API
    # ------------------------------------------------------------------

    def test_get_tags_for_game_active_reads_from_single_cache(self):
        """For the active game, get_tags_for_game reads the single-game cache
        (resolved copy — not the raw dict reference)."""
        game = make_game(1)
        ctrl, _ = self._make_ctrl(game)
        entry = ChessLogStorageService.make_entry("CLAMP", "C")
        ctrl._cached_paths_data = {"0": [entry]}
        result = ctrl.get_tags_for_game(game)
        # Returns a resolved copy; verify the expected entry is present.
        self.assertIn("0", result)
        self.assertEqual(result["0"][0]["cat"], "C")

    def test_get_tags_for_game_inactive_loads_and_caches(self):
        game_a = make_game(1)
        game_b = make_game(2)
        ChessLogStorageService.store_tags(
            game_b, {"0": [ChessLogStorageService.make_entry("CCT", "C")]}, {}
        )
        ctrl, _ = self._make_ctrl(game_a)
        result = ctrl.get_tags_for_game(game_b)
        self.assertEqual(ChessLogStorageService.count_tags(result), 1)
        self.assertIn(id(game_b), ctrl._multi_cache)

    def test_replace_entries_at_path_for_game_active_writes_to_single_cache(self):
        game = make_game(1)
        ctrl, _ = self._make_ctrl(game)
        ctrl.replace_entries_at_path_for_game(
            game, "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "test"}]
        )
        self.assertIn("0", ctrl._cached_paths_data)
        self.assertTrue(ctrl.has_dirty_games())

    def test_replace_entries_at_path_for_game_inactive_writes_to_multi_cache(self):
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, _ = self._make_ctrl(game_a)
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CLAMP", [{"preset": "CLAMP", "cat": "P", "why": ""}]
        )
        self.assertIn(id(game_b), ctrl._multi_cache)
        self.assertIn("0", ctrl._multi_cache[id(game_b)])
        self.assertNotIn("0", ctrl._cached_paths_data)

    def test_save_all_dirty_games_calls_store_tags_for_each(self):
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = self._make_ctrl(game_a)
        gm.active_game = game_a

        # Edit active game (goes to single-game cache)
        ctrl.replace_entries_at_path_for_game(
            game_a, "0", "CLAMP", [{"preset": "CLAMP", "cat": "C", "why": "a"}]
        )
        # Edit inactive game (goes to multi-cache)
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CCT", [{"preset": "CCT", "cat": "Threats", "why": "b"}]
        )

        store_calls = []
        original = ChessLogStorageService.store_tags

        def fake_store(game, data, config, nag_shown=False, **_kwargs):
            store_calls.append((game.game_number, dict(data)))
            return original(game, data, config)

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags", side_effect=fake_store):
            saved, failed = ctrl.save_all_dirty_games()

        self.assertEqual(saved, 2)
        self.assertEqual(failed, 0)
        self.assertFalse(ctrl.has_dirty_games())
        game_numbers = {gn for gn, _ in store_calls}
        self.assertEqual(game_numbers, {1, 2})

    def test_save_all_dirty_games_reads_correct_store_for_active_game(self):
        """save_all_dirty_games must use _cached_paths_data for the active game."""
        game = make_game(1)
        ctrl, _ = self._make_ctrl(game)
        ctrl.replace_entries_at_path_for_game(
            game, "0", "CLAMP", [{"preset": "CLAMP", "cat": "L", "why": "from cache"}]
        )
        # Put stale data in multi_cache to confirm it is NOT used for the active game
        ctrl._multi_cache[id(game)] = {"0": [ChessLogStorageService.make_entry("CLAMP", "P")]}

        captured = {}

        def fake_store(game, data, config, nag_shown=False, **_kwargs):
            captured["data"] = dict(data)
            return True

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags", side_effect=fake_store):
            ctrl.save_all_dirty_games()

        self.assertEqual(captured["data"]["0"][0]["cat"], "L")

    def test_save_all_dirty_games_keeps_failed_game_dirty(self):
        game = make_game(1)
        ctrl, _ = self._make_ctrl(game)
        ctrl.replace_entries_at_path_for_game(
            game, "0", "CLAMP", [{"preset": "CLAMP", "cat": "A", "why": ""}]
        )
        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags", return_value=False):
            saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 0)
        self.assertEqual(failed, 1)
        self.assertTrue(ctrl.has_dirty_games())

    # ------------------------------------------------------------------
    # Transition coherency
    # ------------------------------------------------------------------

    def test_edit_inactive_game_then_activate_preserves_edit(self):
        """Editing Game B while Game A is active — the edit survives when Game B becomes active."""
        game_a = make_game(1)
        game_b = make_game(2)

        ctrl, gm = self._make_ctrl(game_a)
        gm.active_game = game_a

        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "edited"}]
        )
        self.assertIn("0", ctrl._multi_cache.get(id(game_b), {}))

        # Switch active game to Game B
        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)

        tags = ctrl.get_tags_for_current_game()
        self.assertIn("0", tags)
        self.assertEqual(tags["0"][0]["cat"], "M")
        self.assertEqual(tags["0"][0]["why"], "edited")

    def test_switch_away_from_dirty_active_game_preserves_edit(self):
        """Game A is active and dirty; switching to Game B and back must preserve Game A's edit."""
        game_a = make_game(1)
        game_b = make_game(2)

        ctrl, gm = self._make_ctrl(game_a)
        gm.active_game = game_a

        ctrl.replace_entries_at_path_for_game(
            game_a, "0", "CLAMP", [{"preset": "CLAMP", "cat": "P", "why": "preserved"}]
        )

        # Switch to Game B
        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)
        self.assertNotEqual(ctrl._cached_game_id, id(game_a))

        # Switch back to Game A
        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)
        self.assertEqual(ctrl._cached_game_id, id(game_a))
        self.assertIn("0", ctrl._cached_paths_data)
        self.assertEqual(ctrl._cached_paths_data["0"][0]["why"], "preserved")

    def test_save_all_dirty_games_reads_from_correct_store_after_activation(self):
        """One dirty game in multi_cache + one dirty active game — save_all reads from the right place."""
        game_a = make_game(1)  # will be active
        game_b = make_game(2)  # will stay in multi_cache

        ctrl, gm = self._make_ctrl(game_a)
        gm.active_game = game_a

        ctrl.replace_entries_at_path_for_game(
            game_a, "0", "CLAMP", [{"preset": "CLAMP", "cat": "C", "why": "active-edit"}]
        )
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CCT", [{"preset": "CCT", "cat": "Checks", "why": "multi-edit"}]
        )

        captured = {}

        def fake_store(game, data, config, nag_shown=False, **_kwargs):
            captured[game.game_number] = {
                pk: [e["why"] for e in entries]
                for pk, entries in data.items()
            }
            return True

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags", side_effect=fake_store):
            saved, failed = ctrl.save_all_dirty_games()

        self.assertEqual(saved, 2)
        self.assertEqual(failed, 0)
        self.assertIn("active-edit", captured.get(1, {}).get("0", []))
        self.assertIn("multi-edit", captured.get(2, {}).get("0", []))


class TestIgnoreShallowPreservation(unittest.TestCase):
    """replace_entries_at_path and _for_game must preserve the ignore_shallow field."""

    def test_replace_entries_at_path_preserves_ignore_shallow(self):
        game = make_game(1)
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", ignore_shallow=True)
        ctrl.replace_entries_at_path("0", "CLAMP", [entry])
        result = ctrl._cached_paths_data["0"]
        self.assertTrue(result[0].get("ignore_shallow"))

    def test_replace_entries_at_path_omits_ignore_shallow_when_false(self):
        game = make_game(1)
        ctrl, _ = make_controller(game)
        ctrl._cached_game_id = id(game)
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note")
        ctrl.replace_entries_at_path("0", "CLAMP", [entry])
        result = ctrl._cached_paths_data["0"]
        self.assertNotIn("ignore_shallow", result[0])

    def test_replace_entries_at_path_for_game_preserves_ignore_shallow(self):
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, _ = make_controller(game_a)
        ctrl._cached_game_id = id(game_a)
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", ignore_shallow=True)
        ctrl.replace_entries_at_path_for_game(game_b, "0", "CLAMP", [entry])
        result = ctrl._multi_cache[id(game_b)]["0"]
        self.assertTrue(result[0].get("ignore_shallow"))


class TestSaveAllIncludesCurrentGame(unittest.TestCase):
    """Regression: save_all_dirty_games must also save the active game's
    single-game cache even when it wasn't added to _dirty_games
    (add_moment_at_active_path does not add it there)."""

    def _make_ctrl_with_tagged_active_game(self):
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game
        # Simulate a moment tagged via add_moment_at_active_path (writes to
        # _cached_paths_data but does NOT add to _dirty_games).
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("3x3", "Why1", "test answer")]
        }
        return ctrl, gm, game

    def test_save_all_saves_active_game_not_in_dirty_games(self):
        ctrl, gm, game = self._make_ctrl_with_tagged_active_game()
        self.assertNotIn(id(game), ctrl._dirty_games)
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)
        # Tags must now be persisted in the game's PGN.
        loaded = ChessLogStorageService.load_tags(game)
        self.assertIn("0", loaded)
        self.assertEqual(loaded["0"][0]["cat"], "Why1")

    def test_save_all_active_game_already_in_dirty_not_double_saved(self):
        """If the active game is already in _dirty_games, it must be saved exactly once."""
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game
        ctrl._cached_paths_data = {
            "0": [ChessLogStorageService.make_entry("CLAMP", "C")]
        }
        ctrl._dirty_games[id(game)] = game
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)

    def test_save_all_skips_active_game_when_no_unsaved_changes(self):
        """Active game with no unsaved changes must NOT be saved (would write empty)."""
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game
        # Empty cache == no unsaved changes relative to an untagged game.
        ctrl._cached_paths_data = {}
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 0)
        self.assertEqual(failed, 0)

    def test_save_all_emits_metadata_updated_for_active_game(self):
        ctrl, gm, game = self._make_ctrl_with_tagged_active_game()
        ctrl.save_all_dirty_games()
        gm.metadata_updated.emit.assert_called()

    def test_save_all_emits_metadata_updated_exactly_once_for_active_game(self):
        """Active game among several dirty games -> exactly one emit."""
        ctrl, gm, game = self._make_ctrl_with_tagged_active_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "n")
        others = [make_game(n) for n in (2, 3)]
        for g in others:
            ctrl._multi_cache[id(g)] = {"0": [entry]}
            ctrl._dirty_games[id(g)] = g
        ctrl._dirty_games[id(game)] = game
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual((saved, failed), (3, 0))
        self.assertEqual(gm.metadata_updated.emit.call_count, 1)

    def test_failed_save_keeps_pending_check_run_and_dirty(self):
        ctrl, gm, game = self._make_ctrl_with_tagged_active_game()
        gid = id(game)
        ctrl._dirty_games[gid] = game
        run = {"model": "m"}
        ctrl.set_check_run_for_game(game, run)
        with patch.object(ChessLogStorageService, "store_tags", return_value=False):
            self.assertFalse(ctrl.save_tags_for_current_game())
        self.assertIs(ctrl._pending_check_runs.get(gid), run)
        self.assertIn(gid, ctrl._dirty_games)
        gm.metadata_updated.emit.assert_not_called()


class TestSaveCurrentGameDirtyState(unittest.TestCase):
    """Dirty-state regression tests for save and clear paths."""

    def test_save_current_game_clears_dirty_flag(self):
        """save_tags_for_current_game must pop _dirty_games for the saved game.

        Scenario: game B is dirtied via replace_entries_at_path_for_game while A
        is active (simulating a ShowTagsDialog OK); user switches to B; hits
        Ctrl+Alt+L — after save has_dirty_games() must be False.
        """
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = make_controller(game_a)
        gm.active_game = game_a
        ctrl._cached_game_id = id(game_a)

        # Dirty game B while A is active (via ShowTagsDialog OK path)
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "edit-b"}]
        )
        self.assertIn(id(game_b), ctrl._dirty_games)

        # Switch active to B (Rule A promotes from multi-cache)
        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)

        # Save B via single-game save (Ctrl+Alt+L)
        ctrl.save_tags_for_current_game()

        # After save, no games should remain dirty
        self.assertFalse(ctrl.has_dirty_games())

    def test_clear_active_game_leaves_inactive_game_dirty(self):
        """Clearing the active game must not disturb an inactive game's dirty state.
        The cleared game itself becomes dirty (pending clear) while B stays dirty."""
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = make_controller(game_a)
        gm.active_game = game_a
        ctrl._cached_game_id = id(game_a)

        # Tag A while A is active, then switch to B and tag B
        ctrl.replace_entries_at_path_for_game(
            game_a, "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "a-tag"}]
        )
        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CCT", [{"preset": "CCT", "cat": "C", "why": "b-tag"}]
        )

        # Switch back to A and clear it
        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)
        ctrl.clear_tags_for_current_game()

        # A is now dirty (pending clear) with empty cache.
        self.assertIn(id(game_a), ctrl._dirty_games)
        self.assertEqual(ctrl._cached_paths_data, {})
        # B is still dirty with its tag intact.
        self.assertIn(id(game_b), ctrl._dirty_games)
        b_data = ctrl._multi_cache.get(id(game_b), {})
        self.assertIn("0", b_data)
        self.assertEqual(b_data["0"][0]["cat"], "C")

    def test_repeated_save_all_cycles_stay_consistent(self):
        """Two successive tag → save-all cycles must each leave a clean dirty state."""
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game

        # First cycle
        ctrl.replace_entries_at_path_for_game(
            game, "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "first"}]
        )
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertFalse(ctrl.has_dirty_games())

        # Second cycle — a fresh tag on a different path
        ctrl.replace_entries_at_path_for_game(
            game, "1", "CLAMP", [{"preset": "CLAMP", "cat": "C", "why": "second"}]
        )
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertFalse(ctrl.has_dirty_games())

        loaded = ChessLogStorageService.load_tags(game)
        self.assertIn("0", loaded)
        self.assertIn("1", loaded)

    def test_clear_pending_switch_reload_stays_empty(self):
        """clear_tags_for_current_game is pending: syncs has_chess_log_tags immediately
        but does NOT write through to PGN.  Switching away and back restores the
        empty cache (from multi_cache, not disk), so the pending clear is preserved."""
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = make_controller(game_a)
        ctrl._cached_game_id = id(game_a)
        gm.active_game = game_a

        # Tag A and persist to disk
        ctrl._cached_paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "M")]}
        ctrl.save_tags_for_current_game()
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game_a))

        # Clear A — pending, syncs has_chess_log_tags but does NOT remove PGN headers yet
        ctrl.clear_tags_for_current_game()
        self.assertFalse(game_a.has_chess_log_tags)
        # PGN headers still present — save needed to remove them
        self.assertTrue(ChessLogStorageService.has_chess_log_tags(game_a))

        # Switch away and back — cache promoted from multi_cache (empty), not from disk
        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)
        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)
        self.assertEqual(ctrl._cached_paths_data, {})


class TestSwitchAndSaveAllIntegration(unittest.TestCase):
    """Scenario 2: tag A via add_moment → switch to B → save-all → A persisted."""

    def test_clear_tag_switch_save_all_persists(self):
        """Regression: clear → tag → switch → save-all must save the new moment.

        save_all_dirty_games previously missed this because add_moment_at_active_path
        does not write _dirty_games, and the special active-game check only applies to
        the *currently* active game.  Rule B now marks the outgoing game dirty on every
        game switch that flushes a non-empty cache.
        """
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = make_controller(game_a)
        ctrl._cached_game_id = id(game_a)
        gm.active_game = game_a

        # Seed PGN with existing data so clear actually removes something
        ctrl._cached_paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "M")]}
        ctrl.save_tags_for_current_game()

        # Clear A (pending — adds to _dirty_games)
        ctrl.clear_tags_for_current_game()
        self.assertTrue(ctrl.has_dirty_games())

        # Tag a fresh moment on A — only _cached_paths_data is touched
        with patch("app.controllers.chess_log_controller.encode_path", return_value="1"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "after-clear"}])

        # Switch to B — Rule B should flush A to multi_cache AND mark A dirty
        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)
        self.assertIn(id(game_a), ctrl._dirty_games)

        # Save All while B is active — must reach A via _dirty_games
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)

        loaded = ChessLogStorageService.load_tags(game_a)
        self.assertIn("1", loaded)
        self.assertEqual(loaded["1"][0]["why"], "after-clear")

    def test_tag_switch_save_all_persists(self):
        """tag A → switch to B (stay on B) → save-all → A's moment persisted."""
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = make_controller(game_a)
        ctrl._cached_game_id = id(game_a)
        gm.active_game = game_a

        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "A", "why": "no-return"}])

        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)
        self.assertIn(id(game_a), ctrl._dirty_games)

        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)

        loaded = ChessLogStorageService.load_tags(game_a)
        self.assertIn("0", loaded)
        self.assertEqual(loaded["0"][0]["why"], "no-return")

    def test_tag_switch_back_save_all_persists(self):
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = make_controller(game_a)
        ctrl._cached_game_id = id(game_a)
        gm.active_game = game_a

        # Tag A via the UI path — writes to _cached_paths_data only (not _dirty_games)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "A", "why": "switch test"}])

        # Switch to B — Rule B flushes A's cache to multi_cache
        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)

        # Switch back to A — Rule A promotes A's data from multi_cache
        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)

        # Save All — must include A's moment via has_unsaved_changes() check
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)

        loaded = ChessLogStorageService.load_tags(game_a)
        self.assertIn("0", loaded)
        self.assertEqual(loaded["0"][0]["why"], "switch test")


class TestShallowFlagPersistence(unittest.TestCase):
    """is_shallow and ignore_shallow flags must survive save_all_dirty_games."""

    def test_is_shallow_flag_persists_via_save_all(self):
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game

        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", is_shallow=True)
        ctrl.replace_entries_at_path_for_game(game, "0", "CLAMP", [entry])
        ctrl.save_all_dirty_games()

        loaded = ChessLogStorageService.load_tags(game)
        self.assertTrue(loaded["0"][0].get("is_shallow"))

    def test_ignore_shallow_flag_persists_via_save_all(self):
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game

        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", ignore_shallow=True)
        ctrl.replace_entries_at_path_for_game(game, "0", "CLAMP", [entry])
        ctrl.save_all_dirty_games()

        loaded = ChessLogStorageService.load_tags(game)
        self.assertTrue(loaded["0"][0].get("ignore_shallow"))

    def test_shallow_flags_across_active_and_inactive_games(self):
        """Shallow flags in both active and inactive games must both persist via save_all."""
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm = make_controller(game_a)
        ctrl._cached_game_id = id(game_a)
        gm.active_game = game_a

        entry_a = ChessLogStorageService.make_entry("CLAMP", "M", "active-note", is_shallow=True)
        ctrl.replace_entries_at_path_for_game(game_a, "0", "CLAMP", [entry_a])

        entry_b = ChessLogStorageService.make_entry("CCT", "Checks", "inactive-note", ignore_shallow=True)
        ctrl.replace_entries_at_path_for_game(game_b, "0", "CCT", [entry_b])

        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 2)
        self.assertEqual(failed, 0)

        loaded_a = ChessLogStorageService.load_tags(game_a)
        loaded_b = ChessLogStorageService.load_tags(game_b)
        self.assertTrue(loaded_a["0"][0].get("is_shallow"))
        self.assertTrue(loaded_b["0"][0].get("ignore_shallow"))


class TestNagRoundTrip(unittest.TestCase):
    """Nag flag set in memory → save → fresh controller reloads → flag rehydrated."""

    def test_nag_flag_survives_save_and_reload(self):
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game

        # Three moments to put us at the threshold
        ctrl._cached_paths_data = {
            "0":     [ChessLogStorageService.make_entry("CLAMP", "M")],
            "0.0":   [ChessLogStorageService.make_entry("CLAMP", "L")],
            "0.0.0": [ChessLogStorageService.make_entry("CCT",   "C")],
        }

        # Trigger the nag for a fourth new path — sets _nag_shown_by_game[id(game)]
        gm.get_active_path.return_value = (99,)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="fresh"), \
             patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation",
                   return_value=True):
            ctrl.should_confirm_extra_moment(None)
        self.assertTrue(ctrl._nag_shown_by_game.get(id(game)))

        # Save — nag_shown flag rides along with the PGN payload
        ctrl.save_tags_for_current_game()

        # Fresh controller — simulates a new session (session-level flag reset)
        ctrl2, gm2 = make_controller(game)
        gm2.active_game = game
        ctrl2._on_active_game_changed(game)  # triggers _load_into_cache

        # Per-game nag flag must be rehydrated from disk
        self.assertTrue(ctrl2._nag_shown_by_game.get(id(game), False))


class TestIdentityKeyingCrossDatabase(unittest.TestCase):
    """Verify that identity-keyed caches isolate games from different databases
    that share the same sequential game_number."""

    def test_two_games_with_same_game_number_cache_independently(self):
        """Two GameData objects with game_number=5 from different databases
        must occupy separate cache slots and never return each other's tags."""
        pgn_a = (
            '[Event "DB-A"]\n[Site "?"]\n[Date "2026.01.01"]\n'
            '[Round "?"]\n[White "A"]\n[Black "B"]\n[Result "*"]\n\n'
            '1. e4 e5 2. Nf3 Nc6 *\n'
        )
        pgn_b = (
            '[Event "DB-B"]\n[Site "?"]\n[Date "2026.02.01"]\n'
            '[Round "?"]\n[White "C"]\n[Black "D"]\n[Result "*"]\n\n'
            '1. e4 e5 2. Nf3 Nc6 *\n'
        )
        game_a = GameData(game_number=5, pgn=pgn_a)
        game_b = GameData(game_number=5, pgn=pgn_b)
        self.assertEqual(game_a.game_number, game_b.game_number)  # same integer key
        self.assertIsNot(game_a, game_b)  # but different objects

        ctrl, _ = make_controller()

        # Tag game_a via replace_entries_at_path_for_game (inactive game path)
        ctrl.replace_entries_at_path_for_game(
            game_a, "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "a-tag"}]
        )
        # Tag game_b with a different category
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CLAMP", [{"preset": "CLAMP", "cat": "P", "why": "b-tag"}]
        )

        # Two distinct slots must exist
        self.assertEqual(len(ctrl._multi_cache), 2)
        self.assertIn(id(game_a), ctrl._multi_cache)
        self.assertIn(id(game_b), ctrl._multi_cache)

        # Each slot must contain its own data, not the other's
        tags_a = ctrl.get_tags_for_game(game_a)
        tags_b = ctrl.get_tags_for_game(game_b)
        self.assertEqual(tags_a["0"][0]["cat"], "M")
        self.assertEqual(tags_b["0"][0]["cat"], "P")

    def test_db_switch_resets_active_cache_pointers(self):
        """After switch, active-game pointers must be cleared so a new active
        game can be loaded cleanly.  (Dirty entries are preserved — see
        TestDbSwitchPreservesDirtyEdits for that contract.)"""
        game = make_game(1)
        ctrl, gm = make_controller(game)
        ctrl._cached_game_id = id(game)
        gm.active_game = game
        ctrl._cached_paths_data = {}  # untouched active game — nothing to flush

        ctrl._on_active_database_changed(None)

        self.assertEqual(ctrl._cached_paths_data, {})
        self.assertIsNone(ctrl._cached_game_id)
        self.assertIsNone(ctrl._cached_game)

    def test_identity_keyed_dirty_games_write_to_right_game(self):
        """save_all_dirty_games must write game_a's data to game_a and game_b's
        data to game_b even when both have game_number=5."""
        pgn_a = (
            '[Event "DB-A"]\n[Site "?"]\n[Date "2026.01.01"]\n'
            '[Round "?"]\n[White "A"]\n[Black "B"]\n[Result "*"]\n\n'
            '1. e4 e5 2. Nf3 Nc6 *\n'
        )
        pgn_b = (
            '[Event "DB-B"]\n[Site "?"]\n[Date "2026.02.01"]\n'
            '[Round "?"]\n[White "C"]\n[Black "D"]\n[Result "*"]\n\n'
            '1. e4 e5 2. Nf3 Nc6 *\n'
        )
        game_a = GameData(game_number=5, pgn=pgn_a)
        game_b = GameData(game_number=5, pgn=pgn_b)

        ctrl, _ = make_controller()
        ctrl.replace_entries_at_path_for_game(
            game_a, "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "a-data"}]
        )
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CLAMP", [{"preset": "CLAMP", "cat": "P", "why": "b-data"}]
        )

        written = {}

        def fake_store(game, data, config, nag_shown=False, **_kwargs):
            written[id(game)] = {
                pk: [e["why"] for e in entries]
                for pk, entries in data.items()
            }
            return True

        with patch(
            "app.controllers.chess_log_controller.ChessLogStorageService.store_tags",
            side_effect=fake_store,
        ):
            saved, failed = ctrl.save_all_dirty_games()

        self.assertEqual(saved, 2)
        self.assertEqual(failed, 0)
        self.assertIn("a-data", written.get(id(game_a), {}).get("0", []))
        self.assertIn("b-data", written.get(id(game_b), {}).get("0", []))
        # Cross-contamination check: game_a must not have b-data and vice versa
        self.assertNotIn("b-data", written.get(id(game_a), {}).get("0", []))
        self.assertNotIn("a-data", written.get(id(game_b), {}).get("0", []))


def _make_fake_panel_model(db_models):
    pm = MagicMock()
    pm.get_all_database_models.return_value = list(db_models)
    pm.active_database_changed = MagicMock()
    pm.active_database_changed.connect = MagicMock()
    pm.active_database_changed.disconnect = MagicMock()
    return pm


def _make_fake_db_model(games):
    db = MagicMock()
    db.get_all_games.return_value = list(games)
    return db


def _make_fake_db_controller(panel_model):
    dc = MagicMock()
    dc.get_panel_model.return_value = panel_model
    dc.find_database_model_for_game.return_value = None
    return dc


def make_controller_with_dbs(active_game, dbs_games, active_path=()):
    """dbs_games: list of lists of GameData (one list per database)."""
    gm = make_game_model_mock(active_game, active_path)
    gc = make_game_controller_mock(gm)
    db_models = [_make_fake_db_model(gs) for gs in dbs_games]
    panel_model = _make_fake_panel_model(db_models)
    dc = _make_fake_db_controller(panel_model)
    ctrl = ChessLogController({}, gc, database_controller=dc)
    if active_game is not None:
        ctrl._cached_game = active_game
        ctrl._cached_game_id = id(active_game)
    return ctrl, gm, dc


class TestDbSwitchPreservesDirtyEdits(unittest.TestCase):
    """Phase 2 — _on_active_database_changed must preserve unsaved Chess Log
    edits.  Phase 1 cleared _dirty_games unconditionally on switch; the fix
    flushes the outgoing active game's real edits into _dirty_games/_multi_cache
    and only prunes entries belonging to games no longer in any open DB."""

    def test_db_switch_preserves_dirty_edits_from_outgoing_active_game(self):
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm, _dc = make_controller_with_dbs(game_a, [[game_a], [game_b]])
        gm.active_game = game_a
        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "L", "why": "edit"}])

        ctrl._on_active_database_changed(None)

        self.assertIn(id(game_a), ctrl._dirty_games)
        self.assertIn(id(game_a), ctrl._multi_cache)
        self.assertEqual(ctrl._multi_cache[id(game_a)][""][0]["why"], "edit")

        captured = {}

        def fake_store(game, data, config, nag_shown=False, **_kwargs):
            captured[id(game)] = {pk: [e["why"] for e in es] for pk, es in data.items()}
            return True

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags",
                   side_effect=fake_store):
            saved, failed = ctrl.save_all_dirty_games()

        self.assertEqual((saved, failed), (1, 0))
        self.assertIn("edit", captured.get(id(game_a), {}).get("", []))

    def test_db_switch_preserves_dirty_edits_from_inactive_game_tags_report(self):
        active = make_game(1)
        game_a7 = make_game(7)
        game_b = make_game(99)
        ctrl, gm, _dc = make_controller_with_dbs(active, [[active, game_a7], [game_b]])
        gm.active_game = active
        ctrl.replace_entries_at_path_for_game(
            game_a7, "", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "tags-report-edit"}]
        )
        self.assertIn(id(game_a7), ctrl._dirty_games)
        self.assertIn(id(game_a7), ctrl._multi_cache)

        ctrl._on_active_database_changed(None)

        self.assertIn(id(game_a7), ctrl._dirty_games)
        self.assertIn(id(game_a7), ctrl._multi_cache)

    def test_db_switch_prunes_non_dirty_multi_cache_entries(self):
        active = make_game(1)
        peek_game = make_game(2)
        ctrl, gm, _dc = make_controller_with_dbs(active, [[active, peek_game]])
        gm.active_game = active
        # Peek at an inactive game (populates _multi_cache without dirtying)
        _ = ctrl.get_tags_for_game(peek_game)
        self.assertIn(id(peek_game), ctrl._multi_cache)
        self.assertNotIn(id(peek_game), ctrl._dirty_games)

        ctrl._on_active_database_changed(None)

        self.assertNotIn(id(peek_game), ctrl._multi_cache)

    def test_db_switch_untouched_active_game_not_marked_dirty(self):
        game = make_game(1)
        ctrl, gm, _dc = make_controller_with_dbs(game, [[game]])
        gm.active_game = game
        # No edits — _cached_paths_data stays matching the on-disk tag (both empty)
        ctrl._on_active_database_changed(None)
        self.assertNotIn(id(game), ctrl._dirty_games)
        self.assertNotIn(id(game), ctrl._multi_cache)

    def test_db_switch_last_moment_deletion_survives_and_saves(self):
        """Game has 1 moment on disk; delete via replace_entries_at_path on the
        active cache (does NOT dirty-mark); switch DB; verify dirty + save
        writes a tag-less PGN."""
        game = make_game(1)
        # Pre-seed on-disk tag with one CLAMP moment at path ""
        ChessLogStorageService.store_tags(
            game, {"": [ChessLogStorageService.make_entry("CLAMP", "C", "orig")]}, {}
        )
        ctrl, gm, _dc = make_controller_with_dbs(game, [[game]])
        gm.active_game = game
        # Force-load from disk so _cached_paths_data reflects the stored moment
        ctrl._load_into_cache(game)
        self.assertEqual(ChessLogStorageService.count_tags(ctrl._cached_paths_data), 1)
        # Delete the moment via the active-cache replace (NOT dirty-marking)
        ctrl.replace_entries_at_path("", "CLAMP", [])
        self.assertEqual(ctrl._cached_paths_data, {})
        self.assertNotIn(id(game), ctrl._dirty_games)  # replace_entries_at_path doesn't dirty-mark

        ctrl._on_active_database_changed(None)

        # Flush decision compared against disk (which had 1 moment) → dirty
        self.assertIn(id(game), ctrl._dirty_games)
        self.assertIn(id(game), ctrl._multi_cache)
        self.assertEqual(ctrl._multi_cache[id(game)], {})

        saved, failed = ctrl.save_all_dirty_games()

        self.assertEqual((saved, failed), (1, 0))
        # Empty-data save calls clear_tags (removes headers), not store_tags.
        self.assertFalse(ChessLogStorageService.has_chess_log_tags(game))

    def test_db_switch_then_back_then_save_persists_edits(self):
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm, _dc = make_controller_with_dbs(game_a, [[game_a], [game_b]])
        gm.active_game = game_a
        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "A", "why": "edit-a"}])

        # Switch away (DB-B)
        ctrl._on_active_database_changed(None)
        # Switch back (DB-A) — simulate the user clicking game_a in the newly-active tab
        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)

        self.assertEqual(ctrl._cached_game_id, id(game_a))
        self.assertEqual(ctrl._cached_paths_data[""][0]["why"], "edit-a")

        captured = {}

        def fake_store(game_, data, config, nag_shown=False, **_kwargs):
            captured[id(game_)] = {pk: [e["why"] for e in es] for pk, es in data.items()}
            return True

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags",
                   side_effect=fake_store):
            ctrl.save_tags_for_current_game()

        self.assertIn("edit-a", captured.get(id(game_a), {}).get("", []))

    def test_save_all_dirty_after_cross_db_edits_writes_each_to_own_pgn(self):
        game_a3 = make_game(3)
        game_b5 = make_game(5)
        other = make_game(1)
        ctrl, gm, _dc = make_controller_with_dbs(other, [[other, game_a3], [game_b5]])
        gm.active_game = other
        ctrl.replace_entries_at_path_for_game(
            game_a3, "", "CLAMP", [{"preset": "CLAMP", "cat": "C", "why": "a3-edit"}]
        )
        ctrl.replace_entries_at_path_for_game(
            game_b5, "", "CCT", [{"preset": "CCT", "cat": "Threats", "why": "b5-edit"}]
        )

        ctrl._on_active_database_changed(None)

        captured = {}

        def fake_store(game_, data, config, nag_shown=False, **_kwargs):
            captured[id(game_)] = {pk: [e["why"] for e in es] for pk, es in data.items()}
            return True

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags",
                   side_effect=fake_store):
            saved, failed = ctrl.save_all_dirty_games()

        self.assertEqual((saved, failed), (2, 0))
        self.assertIn("a3-edit", captured.get(id(game_a3), {}).get("", []))
        self.assertIn("b5-edit", captured.get(id(game_b5), {}).get("", []))
        self.assertNotIn("b5-edit", captured.get(id(game_a3), {}).get("", []))
        self.assertNotIn("a3-edit", captured.get(id(game_b5), {}).get("", []))

    def test_reload_drops_dirty_entries_for_games_no_longer_open(self):
        game_a3 = make_game(3)
        game_b5 = make_game(5)
        other = make_game(1)
        db_a_games = [other, game_a3]
        db_b_games = [game_b5]
        ctrl, gm, dc = make_controller_with_dbs(other, [db_a_games, db_b_games])
        gm.active_game = other
        ctrl.replace_entries_at_path_for_game(
            game_a3, "", "CLAMP", [{"preset": "CLAMP", "cat": "C", "why": "a3"}]
        )
        ctrl.replace_entries_at_path_for_game(
            game_b5, "", "CCT", [{"preset": "CCT", "cat": "Threats", "why": "b5"}]
        )
        self.assertIn(id(game_a3), ctrl._dirty_games)
        self.assertIn(id(game_b5), ctrl._dirty_games)

        # Simulate reload of DB-A: replace game list with fresh GameData objects.
        new_other = make_game(1)
        new_a3 = make_game(3)
        panel_model = dc.get_panel_model()
        panel_model.get_all_database_models.return_value[0].get_all_games.return_value = [new_other, new_a3]

        # active_game_changed(None) fires on reload — same prune path.
        gm.active_game = None
        ctrl._on_active_game_changed(None)

        self.assertNotIn(id(game_a3), ctrl._dirty_games)
        self.assertIn(id(game_b5), ctrl._dirty_games)

    def test_chess_log_edit_does_not_mark_database_unsaved(self):
        """Edit methods are cache-only; the pulse fires only on save paths."""
        game = make_game(1)
        ctrl, gm, dc = make_controller_with_dbs(game, [[game]])
        gm.active_game = game
        dc.find_database_model_for_game.return_value = MagicMock()

        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "A", "why": "x"}])
        ctrl.replace_entries_at_path("", "CLAMP", [
            ChessLogStorageService.make_entry("CLAMP", "B", "y")
        ])
        other = make_game(2)
        ctrl.replace_entries_at_path_for_game(other, "", "CLAMP", [
            {"preset": "CLAMP", "cat": "C", "why": "z"}
        ])

        self.assertEqual(dc.mark_database_unsaved.call_count, 0)

    def test_edit_preserved_when_active_game_becomes_none(self):
        """Amendment 21: active game becomes None (close / clipboard clear) →
        the outgoing-game flush must still fire.  Covers the regression where
        has_unsaved_changes() would read active_game=None and skip the flush."""
        game = make_game(1)
        ctrl, gm, _dc = make_controller_with_dbs(game, [[game]])
        gm.active_game = game
        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "A", "why": "preserved"}])

        # Simulate close/clear: game model's active_game goes to None BEFORE
        # the handler fires.  If the flush decision used has_unsaved_changes()
        # (which reads game model.active_game), the edit would be lost.
        gm.active_game = None
        ctrl._on_active_game_changed(None)

        self.assertIn(id(game), ctrl._dirty_games)
        self.assertIn(id(game), ctrl._multi_cache)
        self.assertEqual(ctrl._multi_cache[id(game)][""][0]["why"], "preserved")

        captured = {}

        def fake_store(game_, data, config, nag_shown=False, **_kwargs):
            captured[id(game_)] = {pk: [e["why"] for e in es] for pk, es in data.items()}
            return True

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags",
                   side_effect=fake_store):
            saved, failed = ctrl.save_all_dirty_games()

        self.assertEqual((saved, failed), (1, 0))
        self.assertIn("preserved", captured.get(id(game), {}).get("", []))


class TestSaveOrphanGuard(unittest.TestCase):
    """Commit 2 — save-side orphan guard wired through production save paths.

    Tests 10-13 from the Phase 2 plan.
    """

    def _make_ctrl_with_game(self):
        """Return a controller with an active game fully loaded into cache."""
        game = make_game()
        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)
        return ctrl, gm, game

    def test_save_tags_for_current_game_passes_original_paths(self):
        """save_tags_for_current_game must pass _cached_original_paths[gid] as
        original_paths= to store_tags so the orphan guard is active."""
        ctrl, gm, game = self._make_ctrl_with_game()
        # Put a moment in the cache so save goes through store_tags (not clear_tags).
        ctrl._cached_paths_data = {"0": [ChessLogStorageService.make_entry("CLAMP", "M")]}
        # Inject a recognisable sentinel snapshot so we can verify identity.
        sentinel = {"sentinel": [ChessLogStorageService.make_entry("CLAMP", "M")]}
        ctrl._cached_original_paths[id(game)] = sentinel

        captured = {}

        def fake_store(game_, data, config, nag_shown=False, original_paths=None, check_run=None):
            captured["original_paths"] = original_paths
            return True

        with patch("app.controllers.chess_log_controller.ChessLogStorageService.store_tags",
                   side_effect=fake_store):
            ctrl.save_tags_for_current_game()

        self.assertIs(captured["original_paths"], sentinel)

    def test_save_refuses_new_orphan_via_production_path(self):
        """An unresolvable path_key injected into the in-memory cache after load
        must not reach the PGN.  LoggingService.error must fire exactly once."""
        ctrl, gm, game = self._make_ctrl_with_game()
        orphan_key = "99999"
        ctrl._cached_paths_data[orphan_key] = [ChessLogStorageService.make_entry("CLAMP", "M")]

        with patch("app.services.chess_log_storage_service.LoggingService") as mock_ls:
            mock_logger = MagicMock()
            mock_ls.get_instance.return_value = mock_logger
            ctrl.save_tags_for_current_game()

        loaded = ChessLogStorageService.load_tags(game)
        self.assertNotIn(orphan_key, loaded)
        mock_logger.error.assert_called_once()

    def test_save_refuses_new_orphan_remains_refused_on_second_save(self):
        """The orphan guard must fire on every save.

        After a successful save, _cached_original_paths is refreshed from the
        on-disk snapshot (which never received the refused key), so the refused
        key is still treated as 'new' on the next save call.
        """
        ctrl, gm, game = self._make_ctrl_with_game()
        orphan_key = "99999"
        ctrl._cached_paths_data[orphan_key] = [ChessLogStorageService.make_entry("CLAMP", "M")]

        with patch("app.services.chess_log_storage_service.LoggingService") as mock_ls:
            mock_logger = MagicMock()
            mock_ls.get_instance.return_value = mock_logger
            ctrl.save_tags_for_current_game()   # first save
            ctrl.save_tags_for_current_game()   # second save

        loaded = ChessLogStorageService.load_tags(game)
        self.assertNotIn(orphan_key, loaded)
        self.assertEqual(mock_logger.error.call_count, 2)

    def test_save_preserves_preexisting_on_disk_orphan(self):
        """An orphan path_key already present in the PGN must pass through on save
        (byte-identical round-trip), even when a new resolvable moment is added."""
        game = make_game()
        orphan_key = "99999"
        # Pre-seed the PGN with an orphan key — bypass guard with no original_paths.
        ChessLogStorageService.store_tags(
            game,
            {orphan_key: [ChessLogStorageService.make_entry("CLAMP", "M", "orphan")]},
            {},
        )

        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)   # _cached_original_paths[gid] = {orphan_key: [...]}

        # Add a new resolvable moment at path "0" (first move — exists in MINIMAL_PGN).
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "new"}])

        ctrl.save_tags_for_current_game()

        loaded = ChessLogStorageService.load_tags(game)
        self.assertIn(orphan_key, loaded)
        self.assertIn("0", loaded)
        self.assertEqual(loaded["0"][0]["why"], "new")


# ---------------------------------------------------------------------------
# Resolved view — orphans excluded from feature code (tests 14–16, amendments 22–23)
# ---------------------------------------------------------------------------

class TestResolvedView(unittest.TestCase):
    """_resolved_view filters orphan path_keys; get_tags_for_current_game returns the
    filtered copy; memoization prevents redundant PGN re-parsing."""

    def _make_ctrl_with_orphan_game(self):
        """Return (ctrl, game) where game has one resolvable + one orphan path key."""
        game = make_game()
        orphan_key = "99999"
        resolvable_key = "0"
        ChessLogStorageService.store_tags(game, {
            resolvable_key: [ChessLogStorageService.make_entry("CLAMP", "C", "real note")],
            orphan_key: [ChessLogStorageService.make_entry("CLAMP", "M", "ghost note")],
        })
        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)
        return ctrl, game

    def test_get_tags_for_current_game_returns_resolved_view(self):
        """get_tags_for_current_game must exclude orphan path_keys.

        has_unsaved_changes() must still return False immediately after load —
        both sides of the full-dict comparison include the orphan, so cache==disk.
        """
        ctrl, game = self._make_ctrl_with_orphan_game()
        result = ctrl.get_tags_for_current_game()
        self.assertIn("0", result)
        self.assertNotIn("99999", result)
        # Full-dict comparison: cached == stored (both include the orphan)
        self.assertFalse(ctrl.has_unsaved_changes())

    def test_should_confirm_extra_moment_ignores_on_disk_orphans(self):
        """On-disk orphans must not count toward the 3-moment nag threshold.

        2 resolvable + 2 orphan moments in the PGN.  Tagging a 3rd resolvable
        path must not trigger the nag (resolved count = 2 < 3).
        """
        game = make_game()
        ChessLogStorageService.store_tags(game, {
            "0":     [ChessLogStorageService.make_entry("CLAMP", "C", "note1")],
            "0.0":   [ChessLogStorageService.make_entry("CLAMP", "L", "note2")],
            "99997": [ChessLogStorageService.make_entry("CLAMP", "A", "orphan1")],
            "99998": [ChessLogStorageService.make_entry("CLAMP", "M", "orphan2")],
        })
        # active path is "0.0.0" — a new, not-yet-tagged move
        ctrl, gm = make_controller(game, active_path=(0, 0, 0))
        gm.active_game = game
        ctrl._load_into_cache(game)

        with patch.object(ctrl, "_confirm_extra_moment", return_value=True) as mock_nag:
            result = ctrl.should_confirm_extra_moment()
        # Resolved count = 2 < 3, so no nag should fire; confirm returns True
        self.assertTrue(result)
        mock_nag.assert_not_called()

    def test_resolved_view_memoized_across_calls(self):
        """Calling get_tags_for_current_game 100× must parse the PGN exactly once.

        After add_moment_at_active_path bumps the version, the next call parses
        the PGN exactly once more (total 2 times).
        """
        import chess.pgn as _chess_pgn

        game = make_game()
        ChessLogStorageService.store_tags(game, {
            "0": [ChessLogStorageService.make_entry("CLAMP", "C", "memo test")],
        })
        ctrl, gm = make_controller(game, active_path=(0,))
        gm.active_game = game
        ctrl._load_into_cache(game)

        with patch.object(_chess_pgn, "read_game", wraps=_chess_pgn.read_game) as spy:
            for _ in range(100):
                ctrl.get_tags_for_current_game()
            self.assertEqual(spy.call_count, 1, "PGN parsed more than once despite stable version")

            # Bump version via add_moment_at_active_path
            with patch("app.controllers.chess_log_controller.encode_path", return_value="0.0"):
                ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "L", "why": "new"}])

            # Exactly one more parse
            ctrl.get_tags_for_current_game()
            self.assertEqual(spy.call_count, 2, "Cache not invalidated after version bump")

    def test_resolved_view_invalidates_on_same_length_pgn_change(self):
        """Blake2b-16 content hash, not len(), drives cache invalidation.

        Replacing Nf3 with Nc3 produces a PGN of identical byte length but
        a different content hash.  The resolved cache must recompute.
        """
        import chess.pgn as _chess_pgn

        game = make_game()
        ChessLogStorageService.store_tags(game, {
            "0": [ChessLogStorageService.make_entry("CLAMP", "C", "hash test")],
        })
        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)

        with patch.object(_chess_pgn, "read_game", wraps=_chess_pgn.read_game) as spy:
            ctrl.get_tags_for_current_game()
            self.assertEqual(spy.call_count, 1)

            # Substitute Nf3 → Nc3 — same byte length, different content
            before = game.pgn
            modified = before.replace("Nf3", "Nc3")
            self.assertEqual(len(before), len(modified), "Precondition: byte length must be identical")
            self.assertNotEqual(before, modified, "Precondition: content must differ")
            game.pgn = modified

            ctrl.get_tags_for_current_game()
            self.assertEqual(spy.call_count, 2, "Cache not invalidated on same-length PGN content change")

    def test_resolved_view_returns_copy_not_reference(self):
        """Mutating the returned dict must not corrupt the memoized resolved view."""
        game = make_game()
        ChessLogStorageService.store_tags(game, {
            "0": [ChessLogStorageService.make_entry("CLAMP", "C", "copy test")],
        })
        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)

        result1 = ctrl.get_tags_for_current_game()
        self.assertIn("0", result1)

        # Mutate the returned dict: add a bogus key and remove the real one
        result1["bogus_key"] = []
        del result1["0"]

        # Second call must return the unmutated view
        result2 = ctrl.get_tags_for_current_game()
        self.assertNotIn("bogus_key", result2)
        self.assertIn("0", result2)


class TestSaveModel(unittest.TestCase):
    """Plan tests 1-8a: the new save-model semantics."""

    def _make_controller_with_db(self, game):
        gm = make_game_model_mock(game)
        gc = make_game_controller_mock(gm)
        db_model = MagicMock()
        db_model.get_all_games.return_value = [game]
        pm = MagicMock()
        pm.get_all_database_models.return_value = [db_model]
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()
        dc = MagicMock()
        dc.get_panel_model.return_value = pm
        dc.find_database_model_for_game.return_value = db_model
        ctrl = ChessLogController({}, gc, database_controller=dc)
        ctrl._cached_game = game
        ctrl._cached_game_id = id(game)
        return ctrl, gm, dc, db_model

    def test_log_this_moment_does_not_mark_db_unsaved(self):
        """Plan test 1: add_moment_at_active_path must NOT call mark_database_unsaved."""
        game = make_game()
        ctrl, gm, dc, _db = self._make_controller_with_db(game)
        gm.active_game = game
        ctrl._load_into_cache(game)

        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "L", "why": "test"}])

        dc.mark_database_unsaved.assert_not_called()
        self.assertIn("", ctrl._cached_paths_data)

    def test_save_tags_for_current_game_marks_db_unsaved_and_persists(self):
        """Plan test 2: save_tags_for_current_game marks DB unsaved and writes game.pgn."""
        game = make_game()
        ctrl, gm, dc, db_model = self._make_controller_with_db(game)
        gm.active_game = game
        ctrl._load_into_cache(game)
        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "L", "why": "test"}])
        dc.mark_database_unsaved.reset_mock()

        ctrl.save_tags_for_current_game()

        dc.mark_database_unsaved.assert_called_once_with(db_model)
        loaded = ChessLogStorageService.load_tags(game)
        self.assertTrue(any(e.get("why") == "test" for entries in loaded.values() for e in entries))

    def test_replace_entries_at_path_does_not_mark_db_unsaved(self):
        """Plan test 3: replace_entries_at_path must NOT call mark_database_unsaved."""
        game = make_game()
        ctrl, gm, dc, _db = self._make_controller_with_db(game)
        ctrl._cached_game = game
        ctrl._cached_game_id = id(game)
        gm.active_game = game

        ctrl.replace_entries_at_path(
            "0", "CLAMP",
            [ChessLogStorageService.make_entry("CLAMP", "C", "replaced")],
        )

        dc.mark_database_unsaved.assert_not_called()

    def test_replace_entries_at_path_for_game_does_not_mark_db_unsaved(self):
        """Plan test 4: replace_entries_at_path_for_game must NOT call mark_database_unsaved."""
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm, dc, _db = self._make_controller_with_db(game_a)
        gm.active_game = game_a
        ctrl._load_into_cache(game_a)

        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CLAMP",
            [ChessLogStorageService.make_entry("CLAMP", "C", "for b")],
        )

        dc.mark_database_unsaved.assert_not_called()
        self.assertIn(id(game_b), ctrl._dirty_games)

    def test_save_games_persists_each_and_marks_each_db_unsaved(self):
        """Plan test 5: save_games writes both games and marks both DBs unsaved."""
        game_a = make_game(1)
        game_b = make_game(2)

        gm = make_game_model_mock(game_a)
        gc = make_game_controller_mock(gm)
        db_a = MagicMock()
        db_a.get_all_games.return_value = [game_a]
        db_b = MagicMock()
        db_b.get_all_games.return_value = [game_b]
        pm = MagicMock()
        pm.get_all_database_models.return_value = [db_a, db_b]
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()
        dc = MagicMock()
        dc.get_panel_model.return_value = pm

        def _find_db(game):
            if game is game_a:
                return db_a
            if game is game_b:
                return db_b
            return None

        dc.find_database_model_for_game.side_effect = _find_db
        ctrl = ChessLogController({}, gc, database_controller=dc)
        ctrl._cached_game = game_a
        ctrl._cached_game_id = id(game_a)
        gm.active_game = game_a

        ctrl.replace_entries_at_path_for_game(
            game_a, "0", "CLAMP",
            [ChessLogStorageService.make_entry("CLAMP", "C", "edit a")],
        )
        ctrl.replace_entries_at_path_for_game(
            game_b, "0", "CLAMP",
            [ChessLogStorageService.make_entry("CLAMP", "C", "edit b")],
        )
        dc.mark_database_unsaved.reset_mock()

        saved, failed = ctrl.save_games([game_a, game_b])

        self.assertEqual((saved, failed), (2, 0))
        dc.mark_database_unsaved.assert_any_call(db_a)
        dc.mark_database_unsaved.assert_any_call(db_b)
        self.assertNotIn(id(game_a), ctrl._dirty_games)
        self.assertNotIn(id(game_b), ctrl._dirty_games)
        loaded_a = ChessLogStorageService.load_tags(game_a)
        loaded_b = ChessLogStorageService.load_tags(game_b)
        self.assertTrue(any(e.get("why") == "edit a" for es in loaded_a.values() for e in es))
        self.assertTrue(any(e.get("why") == "edit b" for es in loaded_b.values() for e in es))

    def test_save_games_touches_only_passed_games_not_other_dirty(self):
        """Plan test 6: save_games([gA]) leaves gB and gC still dirty."""
        game_a = make_game(1)
        game_b = make_game(2)
        game_c = make_game(3)

        gm = make_game_model_mock(game_a)
        gc = make_game_controller_mock(gm)
        db = MagicMock()
        db.get_all_games.return_value = [game_a, game_b, game_c]
        pm = MagicMock()
        pm.get_all_database_models.return_value = [db]
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()
        dc = MagicMock()
        dc.get_panel_model.return_value = pm
        dc.find_database_model_for_game.return_value = db
        ctrl = ChessLogController({}, gc, database_controller=dc)
        ctrl._cached_game = game_a
        ctrl._cached_game_id = id(game_a)

        for game in [game_a, game_b, game_c]:
            ctrl.replace_entries_at_path_for_game(
                game, "0", "CLAMP",
                [ChessLogStorageService.make_entry("CLAMP", "C", f"edit {game.game_number}")],
            )
        dc.mark_database_unsaved.reset_mock()

        ctrl.save_games([game_a])

        self.assertNotIn(id(game_a), ctrl._dirty_games)
        self.assertIn(id(game_b), ctrl._dirty_games)
        self.assertIn(id(game_c), ctrl._dirty_games)
        dc.mark_database_unsaved.assert_called_once_with(db)

    def test_save_games_commits_entire_pending_data_for_game(self):
        """Plan test 8a: save_games writes BOTH a Log-this-Moment edit AND a
        replace_entries_at_path_for_game edit on the same game in one store_tags call.
        Commit granularity is the game, not the dialog edit."""
        game = make_game()
        ctrl, gm, dc, db_model = self._make_controller_with_db(game)
        gm.active_game = game
        ctrl._load_into_cache(game)

        # Log-this-Moment edit at path ""
        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "L", "why": "moment edit"}])
        # Dialog-style edit at a different path
        ctrl.replace_entries_at_path_for_game(
            game, "0", "CLAMP",
            [ChessLogStorageService.make_entry("CLAMP", "C", "dialog edit")],
        )

        ctrl.save_games([game])

        loaded = ChessLogStorageService.load_tags(game)
        all_whys = [e.get("why") for es in loaded.values() for e in es]
        self.assertIn("moment edit", all_whys)
        self.assertIn("dialog edit", all_whys)

    def test_clear_tags_does_not_mark_db_unsaved(self):
        """Plan test 8: clear_tags_for_current_game is pending — does NOT mark DB unsaved.

        Consistent with add_moment_at_active_path: neither pending op marks the DB
        unsaved. _mark_database_unsaved fires only on the subsequent save.
        """
        game = make_game()
        ctrl, gm, dc, db_model = self._make_controller_with_db(game)
        gm.active_game = game
        ctrl._load_into_cache(game)
        ChessLogStorageService.store_tags(
            game,
            {"0": [ChessLogStorageService.make_entry("CLAMP", "C", "to clear")]},
            {},
        )
        dc.mark_database_unsaved.reset_mock()

        ctrl.clear_tags_for_current_game()

        dc.mark_database_unsaved.assert_not_called()


class TestF2RuleBFalseUnsaved(unittest.TestCase):
    """F2: Rule B must not mark an unedited game dirty on game switch.

    Tests (a) must fail before the fix (guard was `self._cached_paths_data`, not
    `_outgoing_has_real_edits()`); tests (b) and (c) are positive controls that
    must pass both before and after.
    """

    def _make_ctrl_with_db(self, game_a, game_b=None):
        gm = make_game_model_mock()
        gc = make_game_controller_mock(gm)
        live = [game_a] + ([game_b] if game_b else [])
        db_model = MagicMock()
        db_model.get_all_games.return_value = live
        pm = MagicMock()
        pm.get_all_database_models.return_value = [db_model]
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()
        dc = MagicMock()
        dc.get_panel_model.return_value = pm
        dc.find_database_model_for_game.return_value = db_model
        ctrl = ChessLogController({}, gc, database_controller=dc)
        return ctrl, gm, dc, db_model

    def test_a_unedited_tagged_game_not_saved_after_switch(self):
        """(a) Load tagged game, switch away with no edits → save_all returns (0, 0).

        Fails before fix: Rule B adds the game to _dirty_games whenever the cache is
        non-empty, regardless of edits.  Passes after: guard uses
        _outgoing_has_real_edits() which returns False for an unedited game.
        """
        game_a = make_game(1)
        ChessLogStorageService.store_tags(
            game_a, {"0": [ChessLogStorageService.make_entry("CLAMP", "M", "disk moment")]}, {}
        )
        game_b = make_game(2)
        ctrl, gm, dc, _db = self._make_ctrl_with_db(game_a, game_b)

        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)
        self.assertTrue(ctrl._cached_paths_data, "Precondition: cache non-empty after load")
        self.assertNotIn(id(game_a), ctrl._dirty_games, "Precondition: game_a not dirty before switch")
        dc.mark_database_unsaved.reset_mock()

        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)

        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 0)
        self.assertEqual(failed, 0)
        dc.mark_database_unsaved.assert_not_called()

    def test_b_add_moment_switch_away_saves_game(self):
        """(b) Positive control: add moment, switch away → save_all saves the game.

        Must pass both before and after the fix.
        """
        game_a = make_game(1)
        game_b = make_game(2)
        ctrl, gm, dc, db_model = self._make_ctrl_with_db(game_a, game_b)

        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "M", "why": "b-test"}])
        dc.mark_database_unsaved.reset_mock()

        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)

        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)
        dc.mark_database_unsaved.assert_called_once_with(db_model)
        loaded = ChessLogStorageService.load_tags(game_a)
        self.assertIn("0", loaded)
        self.assertEqual(loaded["0"][0]["why"], "b-test")

    def test_c_edit_text_switch_away_saves_game(self):
        """(c) Positive control: edit existing moment text, switch away → save_all saves it.

        Must pass both before and after the fix.
        """
        game_a = make_game(1)
        ChessLogStorageService.store_tags(
            game_a, {"0": [ChessLogStorageService.make_entry("CLAMP", "M", "old text")]}, {}
        )
        game_b = make_game(2)
        ctrl, gm, dc, db_model = self._make_ctrl_with_db(game_a, game_b)

        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)
        ctrl.replace_entries_at_path(
            "0", "CLAMP", [{"preset": "CLAMP", "cat": "M", "why": "new text"}]
        )
        dc.mark_database_unsaved.reset_mock()

        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)

        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 1)
        self.assertEqual(failed, 0)
        dc.mark_database_unsaved.assert_called_once_with(db_model)
        loaded = ChessLogStorageService.load_tags(game_a)
        self.assertEqual(loaded["0"][0]["why"], "new text")


class TestF1DeletedGamePruning(unittest.TestCase):
    """F1: save_all_dirty_games must skip games no longer in any open database.

    Must fail before the fix (no pre-save prune); must pass after
    (_prune_dirty_games_against_open_databases is called first in save_all_dirty_games).
    """

    def test_deleted_game_pruned_before_save_all(self):
        """Edit and switch away (game becomes dirty), remove from DB, then save_all → (0, 0).

        Fails before fix: save_all iterates _dirty_games without pruning first and
        writes to the orphaned game object, returning (1, 0).  Passes after:
        _prune_dirty_games_against_open_databases is called first and drops the game.
        """
        game_a = make_game(1)
        game_b = make_game(2)

        live_games = [game_a, game_b]
        db_model = MagicMock()
        db_model.get_all_games.side_effect = lambda: list(live_games)
        pm = MagicMock()
        pm.get_all_database_models.return_value = [db_model]
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()
        dc = MagicMock()
        dc.get_panel_model.return_value = pm
        dc.find_database_model_for_game.return_value = None

        gm = make_game_model_mock()
        gc = make_game_controller_mock(gm)
        ctrl = ChessLogController({}, gc, database_controller=dc)

        gm.active_game = game_a
        ctrl._on_active_game_changed(game_a)
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "M", "why": "f1-test"}])

        gm.active_game = game_b
        ctrl._on_active_game_changed(game_b)
        self.assertIn(id(game_a), ctrl._dirty_games, "Precondition: game_a dirty after switch")

        live_games.remove(game_a)

        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual(saved, 0)
        self.assertEqual(failed, 0)
        dc.mark_database_unsaved.assert_not_called()
        self.assertNotIn(id(game_a), ctrl._dirty_games)


class TestPickPreset(unittest.TestCase):
    """Unit tests for the _pick_preset module-level helper."""

    def setUp(self):
        from app.controllers.chess_log_controller import _pick_preset
        self._fn = _pick_preset

    def test_single_preset_returned(self):
        self.assertEqual(self._fn([{"preset": "CLAMP", "cat": "M"}], "3x3"), "CLAMP")

    def test_multiple_entries_same_method_count_once(self):
        # CLAMP has 2 cats at this path, CCT has 1 — both count as ONE method.
        # Tie → setting "3x3" not among leaders → alphabetical: "CCT" < "CLAMP"
        entries = [
            {"preset": "CLAMP", "cat": "M"},
            {"preset": "CLAMP", "cat": "A"},
            {"preset": "CCT", "cat": "T"},
        ]
        self.assertEqual(self._fn(entries, "3x3"), "CCT")

    def test_setting_wins_tie(self):
        entries = [{"preset": "CLAMP", "cat": "M"}, {"preset": "CCT", "cat": "T"}]
        self.assertEqual(self._fn(entries, "CCT"), "CCT")

    def test_alphabetically_first_wins_tie_when_setting_absent(self):
        entries = [{"preset": "CLAMP", "cat": "M"}, {"preset": "CCT", "cat": "T"}]
        self.assertEqual(self._fn(entries, "3x3"), "CCT")  # "CCT" < "CLAMP"

    def test_empty_entries_returns_tiebreak(self):
        self.assertEqual(self._fn([], "3x3"), "3x3")

    def test_entries_with_empty_preset_ignored(self):
        entries = [{"preset": "", "cat": "M"}, {"preset": "CCT", "cat": "T"}]
        self.assertEqual(self._fn(entries, "3x3"), "CCT")

    def test_all_empty_preset_returns_tiebreak(self):
        self.assertEqual(self._fn([{"preset": "", "cat": "M"}], "CLAMP"), "CLAMP")

    def test_three_way_tie_setting_wins(self):
        entries = [
            {"preset": "CLAMP", "cat": "M"},
            {"preset": "CCT", "cat": "T"},
            {"preset": "3x3", "cat": "W"},
        ]
        self.assertEqual(self._fn(entries, "CCT"), "CCT")

    def test_three_way_tie_alphabetically_first(self):
        entries = [
            {"preset": "CLAMP", "cat": "M"},
            {"preset": "CCT", "cat": "T"},
            {"preset": "3x3", "cat": "W"},
        ]
        self.assertEqual(self._fn(entries, "ZZZZ"), "3x3")


class TestPickPresetInGame(unittest.TestCase):
    """Unit tests for _pick_preset_in_game — game-level path counting."""

    def setUp(self):
        from app.controllers.chess_log_controller import _pick_preset_in_game
        self._fn = _pick_preset_in_game

    def test_empty_tags_returns_tiebreak(self):
        self.assertEqual(self._fn({}, "CLAMP"), "CLAMP")

    def test_single_path_single_preset(self):
        tags = {"0": [{"preset": "CLAMP", "cat": "M"}]}
        self.assertEqual(self._fn(tags, "3x3"), "CLAMP")

    def test_two_clamp_paths_beat_one_3x3_path(self):
        tags = {
            "0": [{"preset": "CLAMP", "cat": "M"}],
            "0.0": [{"preset": "CLAMP", "cat": "A"}],
            "0.0.0": [{"preset": "3x3", "cat": "Why1"},
                      {"preset": "3x3", "cat": "Why2"},
                      {"preset": "3x3", "cat": "Why3"}],
        }
        # CLAMP=2 paths, 3x3=1 path → CLAMP wins regardless of entry count
        self.assertEqual(self._fn(tags, "3x3"), "CLAMP")

    def test_path_with_multicategory_clamp_counts_once(self):
        # One path with [CLAMP-M, CLAMP-A] contributes 1 to CLAMP, not 2
        tags = {
            "0": [{"preset": "CLAMP", "cat": "M"}, {"preset": "CLAMP", "cat": "A"}],
            "0.0": [{"preset": "3x3", "cat": "Why1"},
                    {"preset": "3x3", "cat": "Why2"},
                    {"preset": "3x3", "cat": "Why3"}],
        }
        # CLAMP=1 path, 3x3=1 path → tie → setting 3x3 → 3x3
        self.assertEqual(self._fn(tags, "3x3"), "3x3")

    def test_tie_setting_wins(self):
        tags = {"0": [{"preset": "CLAMP", "cat": "M"}],
                "0.0": [{"preset": "CCT", "cat": "T"}]}
        self.assertEqual(self._fn(tags, "CCT"), "CCT")

    def test_tie_alphabetical(self):
        tags = {"0": [{"preset": "CLAMP", "cat": "M"}],
                "0.0": [{"preset": "CCT", "cat": "T"}]}
        # "CCT" < "CLAMP"
        self.assertEqual(self._fn(tags, "3x3"), "CCT")

    def test_path_with_two_presets_credits_both(self):
        # A single path that has both CLAMP and 3x3 entries credits 1 to each
        tags = {"0": [{"preset": "CLAMP", "cat": "M"},
                      {"preset": "3x3", "cat": "Why1"}]}
        self.assertEqual(self._fn(tags, "CLAMP"), "CLAMP")


class TestPresetForLogging(unittest.TestCase):
    """Integration tests for ChessLogController.preset_for_logging().

    The tests fail before the fix (method does not exist) and pass after.
    The core behavioral case: setting=3x3, game has CLAMP entries at the
    active path → preset_for_logging() must return CLAMP, not 3x3.
    """

    def _make_ctrl(self, active_preset="3x3"):
        game = make_game()
        uss = make_user_settings_mock(active_preset)
        ctrl, _ = make_controller(game, active_path=(0,), user_settings_service=uss)
        ctrl._cached_game_id = id(game)
        return ctrl, game

    def test_no_active_game_returns_setting(self):
        uss = make_user_settings_mock("3x3")
        ctrl, _ = make_controller(game=None, user_settings_service=uss)
        self.assertEqual(ctrl.preset_for_logging(), "3x3")

    def test_no_entries_returns_setting(self):
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        ctrl._cached_paths_data = {}
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            self.assertEqual(ctrl.preset_for_logging(), "3x3")

    def test_path_entries_override_setting(self):
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        ctrl._cached_paths_data = {"0": [{"preset": "CLAMP", "cat": "M"}]}
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            self.assertEqual(ctrl.preset_for_logging(), "CLAMP")

    def test_game_entries_used_when_path_empty(self):
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        # "0.0" is a valid path in MINIMAL_PGN (e5); "0" is the active path
        ctrl._cached_paths_data = {"0.0": [{"preset": "CLAMP", "cat": "M"}]}
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            self.assertEqual(ctrl.preset_for_logging(), "CLAMP")

    def test_path_takes_precedence_over_game_majority(self):
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        ctrl._cached_paths_data = {
            "0": [{"preset": "CCT", "cat": "T"}],
            "0.0": [{"preset": "CLAMP", "cat": "M"}],
            "0.0.0": [{"preset": "CLAMP", "cat": "M"}],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            self.assertEqual(ctrl.preset_for_logging(), "CCT")

    def test_game_majority_with_tie_prefers_setting(self):
        ctrl, _ = self._make_ctrl(active_preset="CCT")
        ctrl._cached_paths_data = {
            "0.0": [{"preset": "CLAMP", "cat": "M"}],
            "0.0.0": [{"preset": "CCT", "cat": "T"}],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            self.assertEqual(ctrl.preset_for_logging(), "CCT")

    def test_3x3_at_path_overrides_clamp_game(self):
        """Case 3: Mostly-CLAMP game; this move has a 3x3 entry → use 3x3."""
        ctrl, _ = self._make_ctrl(active_preset="CLAMP")
        ctrl._cached_paths_data = {
            "0": [{"preset": "3x3", "cat": "Why1"}],   # active path
            "0.0": [{"preset": "CLAMP", "cat": "M"}],
            "1": [{"preset": "CLAMP", "cat": "A"}],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            self.assertEqual(ctrl.preset_for_logging(), "3x3")

    def test_game_majority_two_clamp_one_3x3(self):
        """Case 4: 2 CLAMP moments, 1 3x3, no entry at active path → CLAMP."""
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        ctrl._cached_paths_data = {
            "0.0": [{"preset": "CLAMP", "cat": "M"}],
            "0.0.0": [{"preset": "CLAMP", "cat": "A"}],
            "1": [{"preset": "3x3", "cat": "Why1"}],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            self.assertEqual(ctrl.preset_for_logging(), "CLAMP")

    def test_new_moment_on_clamp_game_stored_as_clamp(self):
        """Case 6: preset_for_logging returns CLAMP; a moment saved under that
        preset is stored with preset=CLAMP, not the setting (3x3)."""
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        ctrl._cached_paths_data = {"0.0": [{"preset": "CLAMP", "cat": "M"}]}
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            method = ctrl.preset_for_logging()
        self.assertEqual(method, "CLAMP")
        new_entries = [{"preset": method, "cat": "A", "why": ""}]
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path(new_entries)
        stored = ctrl._cached_paths_data.get("0", [])
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["preset"], "CLAMP")

    def test_setting_unchanged_after_preset_for_logging(self):
        """Case 8: preset_for_logging() never mutates the setting."""
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        ctrl._cached_paths_data = {"0": [{"preset": "CLAMP", "cat": "M"}]}
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.preset_for_logging()
        self.assertEqual(ctrl.get_active_preset(), "3x3")

    def test_realistic_counts_clamp_wins_over_3x3_by_paths(self):
        """Fail-before (entry counting): 3 CLAMP entries vs 3 3x3 entries → tie → '3x3'.
        Pass-after (path counting): 2 CLAMP paths vs 1 3x3 path → 'CLAMP'."""
        ctrl, _ = self._make_ctrl(active_preset="3x3")
        ctrl._cached_paths_data = {
            # 2 CLAMP moments; one has two categories (2 entries), one has one (1 entry) = 3 entries total
            "0.0": [{"preset": "CLAMP", "cat": "M"}, {"preset": "CLAMP", "cat": "A"}],
            "0.0.0": [{"preset": "CLAMP", "cat": "M"}],
            # 1 3x3 moment with all three entries = 3 entries total
            "1": [{"preset": "3x3", "cat": "Why1"},
                  {"preset": "3x3", "cat": "Why2"},
                  {"preset": "3x3", "cat": "Why3"}],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            result = ctrl.preset_for_logging()
        self.assertEqual(result, "CLAMP")

    def test_move_level_tie_resolved_by_setting(self):
        """Fail-before (entry counting): 3x3 has 3 entries, CLAMP has 1 → '3x3'.
        Pass-after (distinct presets at path): tie {CLAMP, 3x3}, setting CLAMP → 'CLAMP'."""
        ctrl, _ = self._make_ctrl(active_preset="CLAMP")
        ctrl._cached_paths_data = {
            "0": [{"preset": "CLAMP", "cat": "M"},
                  {"preset": "3x3", "cat": "Why1"},
                  {"preset": "3x3", "cat": "Why2"},
                  {"preset": "3x3", "cat": "Why3"}],
        }
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            result = ctrl.preset_for_logging()
        self.assertEqual(result, "CLAMP")


class TestGetShallowVagueKeys(unittest.TestCase):
    """get_shallow_vague_keys returns (shallow, vague) frozensets from stored flags."""

    def _make_ctrl_with_tags(self, game, tags):
        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)
        ChessLogStorageService.store_tags(game, tags, {})
        ctrl._load_into_cache(game)
        return ctrl

    def test_empty_when_no_flags(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._load_into_cache(game)
        s, v = ctrl.get_shallow_vague_keys([game])
        self.assertEqual(s, frozenset())
        self.assertEqual(v, frozenset())

    def test_shallow_key_for_is_shallow_clamp(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("CLAMP", "C", "a note", is_shallow=True)
        ctrl = self._make_ctrl_with_tags(game, {"0": [e]})
        s, _ = ctrl.get_shallow_vague_keys([game])
        self.assertIn((game, "0", "CLAMP", ""), s)

    def test_vague_key_for_is_vague_3x3(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("3x3", "Why4", "lesson", is_vague=True)
        ctrl = self._make_ctrl_with_tags(game, {"0": [e]})
        _, v = ctrl.get_shallow_vague_keys([game])
        self.assertIn((game, "0", "3x3", "Why4"), v)

    def test_3x3_key_includes_cat(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("3x3", "Why1", "why", is_shallow=True)
        ctrl = self._make_ctrl_with_tags(game, {"0": [e]})
        s, _ = ctrl.get_shallow_vague_keys([game])
        self.assertIn((game, "0", "3x3", "Why1"), s)
        self.assertNotIn((game, "0", "3x3", ""), s)

    def test_clamp_key_has_empty_cat(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("CLAMP", "M", "note", is_shallow=True)
        ctrl = self._make_ctrl_with_tags(game, {"0": [e]})
        s, _ = ctrl.get_shallow_vague_keys([game])
        self.assertIn((game, "0", "CLAMP", ""), s)

    def test_false_is_shallow_not_included(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("CLAMP", "C", "note")  # no is_shallow
        ctrl = self._make_ctrl_with_tags(game, {"0": [e]})
        s, _ = ctrl.get_shallow_vague_keys([game])
        self.assertEqual(s, frozenset())


class TestHasAnyCheckedAnswer(unittest.TestCase):
    """has_any_checked_answer returns True when at least one note has been checked."""

    def _ctrl(self, game, tags):
        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)
        ChessLogStorageService.store_tags(game, tags, {})
        ctrl._load_into_cache(game)
        return ctrl

    def test_false_when_no_entries(self):
        game = make_game()
        ctrl, _ = make_controller(game)
        ctrl._load_into_cache(game)
        self.assertFalse(ctrl.has_any_checked_answer([game]))

    def test_false_when_no_check_hash_no_flags(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("CLAMP", "C", "a note")
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertFalse(ctrl.has_any_checked_answer([game]))

    def test_true_for_matching_check_hash(self):
        game = make_game()
        why = "a note"
        h = ChessLogStorageService.compute_check_hash(why)
        e = ChessLogStorageService.make_entry("CLAMP", "C", why, check_hash=h)
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertTrue(ctrl.has_any_checked_answer([game]))

    def test_true_for_legacy_is_shallow(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("CLAMP", "C", "note", is_shallow=True)
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertTrue(ctrl.has_any_checked_answer([game]))

    def test_true_for_honoured_ignore(self):
        game = make_game()
        why = "my why"
        h = hashlib.sha256(why.encode("utf-8")).hexdigest()
        e = ChessLogStorageService.make_entry(
            "CLAMP", "C", why, ignore_shallow=True, ignore_text_hash=h
        )
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertTrue(ctrl.has_any_checked_answer([game]))

    def test_false_for_blank_why(self):
        game = make_game()
        h = ChessLogStorageService.compute_check_hash("")
        e = ChessLogStorageService.make_entry("CLAMP", "C", "", check_hash=h)
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertFalse(ctrl.has_any_checked_answer([game]))


class TestCountUncheckedAnswers(unittest.TestCase):
    """count_unchecked_answers uses correct units for CLAMP/CCT vs 3x3."""

    def _ctrl(self, game, tags):
        ctrl, gm = make_controller(game)
        gm.active_game = game
        ctrl._load_into_cache(game)
        ChessLogStorageService.store_tags(game, tags, {})
        ctrl._load_into_cache(game)
        return ctrl

    def test_zero_when_all_checked_via_hash(self):
        game = make_game()
        why = "good note"
        h = ChessLogStorageService.compute_check_hash(why)
        e = ChessLogStorageService.make_entry("CLAMP", "C", why, check_hash=h)
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertEqual(ctrl.count_unchecked_answers([game]), 0)

    def test_clamp_two_cats_one_note_counts_once(self):
        """C and L share one note text — should count as one unchecked, not two."""
        game = make_game()
        why = "shared note"
        e_c = ChessLogStorageService.make_entry("CLAMP", "C", why)
        e_l = ChessLogStorageService.make_entry("CLAMP", "L", why)
        ctrl = self._ctrl(game, {"0": [e_c, e_l]})
        self.assertEqual(ctrl.count_unchecked_answers([game]), 1)

    def test_3x3_each_why_counted_separately(self):
        game = make_game()
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "w1"),
            ChessLogStorageService.make_entry("3x3", "Why2", "w2"),
            ChessLogStorageService.make_entry("3x3", "Why3", "w3"),
            ChessLogStorageService.make_entry("3x3", "Why4", "w4"),
        ]
        ctrl = self._ctrl(game, {"0": entries})
        self.assertEqual(ctrl.count_unchecked_answers([game]), 4)

    def test_blank_why_not_counted(self):
        game = make_game()
        e = ChessLogStorageService.make_entry("CLAMP", "C", "")
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertEqual(ctrl.count_unchecked_answers([game]), 0)

    def test_checked_not_counted(self):
        game = make_game()
        why = "checked note"
        h = ChessLogStorageService.compute_check_hash(why)
        e = ChessLogStorageService.make_entry("CLAMP", "C", why, check_hash=h)
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertEqual(ctrl.count_unchecked_answers([game]), 0)

    def test_ignored_not_counted(self):
        game = make_game()
        why = "ignored note"
        h = hashlib.sha256(why.encode("utf-8")).hexdigest()
        e = ChessLogStorageService.make_entry(
            "CLAMP", "C", why, ignore_shallow=True, ignore_text_hash=h
        )
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertEqual(ctrl.count_unchecked_answers([game]), 0)

    def test_hash_mismatch_counts_as_unchecked(self):
        """An edited note (wrong hash) is unchecked even though hash field exists."""
        game = make_game()
        original = "original note"
        h = ChessLogStorageService.compute_check_hash(original)
        edited = "edited note"
        e = ChessLogStorageService.make_entry("CLAMP", "C", edited, check_hash=h)
        ctrl = self._ctrl(game, {"0": [e]})
        self.assertEqual(ctrl.count_unchecked_answers([game]), 1)


# ---------------------------------------------------------------------------
# Log this Moment: check_hash handling in add_moment_at_active_path
# ---------------------------------------------------------------------------

class TestLogThisMomentCheckHash(unittest.TestCase):
    """Log this Moment (add_moment_at_active_path) does not preserve check_hash.

    This is a known limitation: MomentDialog.get_entries() returns {preset,cat,why}
    dicts without check_hash, and add_moment_at_active_path calls make_entry() which
    creates fresh entries.  The existing check_hash is discarded on every re-log,
    even when the text is unchanged.

    These tests document the actual behaviour.  If the path is ever fixed to
    preserve check_hash, the assertions must be updated.
    """

    def _make_ctrl(self, game, paths_data):
        """Return a real ChessLogController seeded with paths_data for game."""
        gm = make_game_model_mock(game, active_path=(0,))
        gc = make_game_controller_mock(gm)
        ctrl = ChessLogController({}, gc)
        ctrl._cached_game = game
        ctrl._cached_game_id = id(game)
        ctrl._cached_paths_data = {k: list(v) for k, v in paths_data.items()}
        return ctrl

    def test_relogging_same_text_drops_check_hash(self):
        """Re-logging with identical text replaces the entry and drops check_hash.

        Known limitation: add_moment_at_active_path creates fresh entries via
        make_entry() which does not carry over the existing check_hash field.
        """
        game = make_game()
        note = "a checked note"
        h = ChessLogStorageService.compute_check_hash(note)
        existing = ChessLogStorageService.make_entry("CLAMP", "C", note, check_hash=h)
        ctrl = self._make_ctrl(game, {"0": [existing]})
        # Re-log with the same text (simulating MomentDialog returning unchanged entries)
        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": note}])
        new_entries = ctrl._cached_paths_data.get("0", [])
        self.assertTrue(new_entries, "Expected entries after re-log")
        # Known limitation: check_hash is dropped (fresh entry created)
        for e in new_entries:
            if e.get("preset") == "CLAMP":
                self.assertNotIn(
                    "check_hash", e,
                    "add_moment_at_active_path drops check_hash (known limitation — "
                    "update this assertion if the path is fixed to preserve it)",
                )

    def test_relogging_changed_text_drops_check_hash(self):
        """Re-logging with changed text also drops check_hash (no check_hash is kept)."""
        game = make_game()
        original = "original text"
        h = ChessLogStorageService.compute_check_hash(original)
        existing = ChessLogStorageService.make_entry("CLAMP", "C", original, check_hash=h)
        ctrl = self._make_ctrl(game, {"0": [existing]})
        ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "C", "why": "changed text"}])
        new_entries = ctrl._cached_paths_data.get("0", [])
        for e in new_entries:
            if e.get("preset") == "CLAMP":
                self.assertNotIn(
                    "check_hash", e,
                    "check_hash must not be present in fresh entry from add_moment_at_active_path",
                )


# ---------------------------------------------------------------------------
# Issue #85 — end-to-end sequences
# ---------------------------------------------------------------------------

class TestIssue85EndToEnd(unittest.TestCase):
    """End-to-end coverage for the two sequences described in issue #85.

    All interactions use the public controller API (what menus call).
    Private controller state is never set directly in these tests;
    game switches are driven via _on_active_game_changed, which is what
    the active_game_changed signal triggers in production.
    """

    # --- helpers ---

    def _make_ctrl(self, games):
        """Return (ctrl, gm, dc) with no private controller state pre-set."""
        gm = make_game_model_mock()
        gc = make_game_controller_mock(gm)
        db_model = MagicMock()
        db_model.get_all_games.return_value = list(games)
        pm = MagicMock()
        pm.get_all_database_models.return_value = [db_model]
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()
        dc = MagicMock()
        dc.get_panel_model.return_value = pm
        dc.find_database_model_for_game.return_value = db_model
        ctrl = ChessLogController({}, gc, database_controller=dc)
        return ctrl, gm, dc

    def _switch_to(self, ctrl, gm, game):
        """Simulate what active_game_changed fires: update active_game and reload cache."""
        gm.active_game = game
        ctrl._on_active_game_changed(game)

    def _assert_game(self, ctrl, game, mem, flag, disk, dirty, label):
        """Assert the four observable views for a game.

        mem:   expected count_tags from get_tags_for_game (in-memory / Show All)
        flag:  expected game.has_chess_log_tags (Log column)
        disk:  expected count_tags from load_tags (PGN on disk / close-reopen)
        dirty: expected bool(id(game) in ctrl._dirty_games) (pending save)
        """
        actual_mem = ChessLogStorageService.count_tags(ctrl.get_tags_for_game(game))
        actual_flag = game.has_chess_log_tags
        actual_disk = ChessLogStorageService.count_tags(ChessLogStorageService.load_tags(game))
        actual_dirty = id(game) in ctrl._dirty_games
        self.assertEqual(actual_mem, mem, f"{label}: in-memory count")
        self.assertEqual(actual_flag, flag, f"{label}: has_chess_log_tags")
        self.assertEqual(actual_disk, disk, f"{label}: disk count")
        self.assertEqual(actual_dirty, dirty, f"{label}: in dirty_games")

    # --- sequence 1 ---

    def test_sequence_1_three_game_clear_log_cycle(self):
        """Three pre-tagged games: edit+save → clear all three → switch-away/back
        → save all → log on game2 → save all → simulate close+reopen.

        Exercises the full pending-clear + pending-log lifecycle across multiple
        games with game switches between each step.
        """
        from app.services.chess_log_stats_service import aggregate

        # Fixture: 3 pre-tagged games, 1 CLAMP/M moment each at path "0".
        game1, game2, game3 = make_game(1), make_game(2), make_game(3)
        for game in (game1, game2, game3):
            game.white = "Alice"
            game.black = "Bob"
            game.date = "2026.01.01"
            ChessLogStorageService.store_tags(
                game,
                {"0": [ChessLogStorageService.make_entry("CLAMP", "M", "initial")]},
                {},
            )

        ctrl, gm, dc = self._make_ctrl([game1, game2, game3])

        # Switch to game1; sanity-check fixture.
        self._switch_to(ctrl, gm, game1)

        # Simulate "open Show All + Charts": populate multi-cache for all games.
        for g in (game1, game2, game3):
            ctrl.get_tags_for_game(g)

        for i, g in enumerate((game1, game2, game3), 1):
            self._assert_game(ctrl, g, mem=1, flag=True, disk=1, dirty=False,
                              label=f"fixture: game{i}")

        # --- Step 2: edit+save game1 (simulates ShowTags dialog Save) ---
        ctrl.replace_entries_at_path_for_game(
            game1, "0", "CLAMP",
            [ChessLogStorageService.make_entry("CLAMP", "M", "edited text")],
        )
        dc.mark_database_unsaved.reset_mock()
        ctrl.save_games([game1])

        self._assert_game(ctrl, game1, mem=1, flag=True, disk=1, dirty=False,
                          label="after edit+save game1")
        self.assertEqual(dc.mark_database_unsaved.call_count, 1,
                         "edit+save marks DB unsaved once")
        self.assertEqual(
            ChessLogStorageService.load_tags(game1)["0"][0]["why"], "edited text",
            "edit persisted in PGN",
        )

        # --- Step 3: clear all 3 games with switches ---
        dc.mark_database_unsaved.reset_mock()

        # Clear game1 (currently active).
        ctrl.clear_tags_for_current_game()
        self._assert_game(ctrl, game1, mem=0, flag=False, disk=1, dirty=True,
                          label="clear game1 pending")

        # Switch to game2 and clear it.
        self._switch_to(ctrl, gm, game2)
        ctrl.clear_tags_for_current_game()
        self._assert_game(ctrl, game2, mem=0, flag=False, disk=1, dirty=True,
                          label="clear game2 pending")

        # Switch to game3 and clear it.
        self._switch_to(ctrl, gm, game3)
        ctrl.clear_tags_for_current_game()
        self._assert_game(ctrl, game3, mem=0, flag=False, disk=1, dirty=True,
                          label="clear game3 pending")

        # game1 and game2 must still be pending: switching didn't save them.
        self._assert_game(ctrl, game1, mem=0, flag=False, disk=1, dirty=True,
                          label="game1 still pending after game3 switch")
        self._assert_game(ctrl, game2, mem=0, flag=False, disk=1, dirty=True,
                          label="game2 still pending after game3 switch")
        # Clears are pending — DB must NOT yet be marked unsaved.
        dc.mark_database_unsaved.assert_not_called()

        # --- Step 4: switch away and back to verify pending clear survives ---
        self._switch_to(ctrl, gm, game1)
        self._switch_to(ctrl, gm, game2)
        self._assert_game(ctrl, game2, mem=0, flag=False, disk=1, dirty=True,
                          label="game2 after switch-away/back — pending clear preserved")
        self.assertTrue(ctrl.has_dirty_games(),
                        "has_dirty_games() True while clears pending")
        self.assertTrue(ctrl.has_unsaved_changes(),
                        "has_unsaved_changes() True for active game2 (disk has 1, cache has 0)")

        # --- Step 5: save all — commits all pending clears ---
        dc.mark_database_unsaved.reset_mock()
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual((saved, failed), (3, 0),
                         "save_all saves all 3 pending clears")

        for i, g in enumerate((game1, game2, game3), 1):
            self._assert_game(ctrl, g, mem=0, flag=False, disk=0, dirty=False,
                              label=f"after save_all: game{i}")
        self.assertEqual(dc.mark_database_unsaved.call_count, 3,
                         "DB marked unsaved once per game")
        self.assertFalse(ctrl.has_dirty_games())
        self.assertFalse(ctrl.has_unsaved_changes())

        # --- Step 6: log on game2 (still active) ---
        dc.mark_database_unsaved.reset_mock()
        with patch("app.controllers.chess_log_controller.encode_path", return_value="1"):
            ctrl.add_moment_at_active_path(
                [{"preset": "CLAMP", "cat": "C", "why": "new moment"}]
            )

        self._assert_game(ctrl, game2, mem=1, flag=True, disk=0, dirty=False,
                          label="after log on game2 (pending)")
        self.assertTrue(ctrl.game_has_any_tags(),
                        "game_has_any_tags() True after pending log")
        self.assertTrue(ctrl.has_unsaved_changes(),
                        "has_unsaved_changes() True after pending log")
        dc.mark_database_unsaved.assert_not_called()

        # Aggregate snapshot (Charts tab) sees the pending moment.
        snap = {id(g): ctrl.get_tags_for_game(g) for g in (game1, game2, game3)}
        result = aggregate(
            [game1, game2, game3],
            player="Alice",
            color_filter="both",
            get_tags_for_game=lambda g: snap.get(id(g), {}),
        )
        self.assertIn("CLAMP", result.series,
                      "aggregate snapshot exposes pending log to Charts")
        self.assertEqual(
            sum(b.total for b in result.series["CLAMP"].bins), 1,
            "exactly 1 moment in CLAMP series",
        )

        # --- Step 7: save all, then simulate close+reopen on game2 ---
        dc.mark_database_unsaved.reset_mock()
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual((saved, failed), (1, 0),
                         "save_all saves only game2 (pending log)")
        self._assert_game(ctrl, game2, mem=1, flag=True, disk=1, dirty=False,
                          label="after save_all: game2 saved")
        self.assertEqual(dc.mark_database_unsaved.call_count, 1,
                         "DB marked unsaved once for game2")

        # Simulate close+reopen: construct a fresh GameData from the saved PGN.
        saved_pgn = game2.pgn
        self.assertTrue(saved_pgn, "game2.pgn non-empty after save")
        new_game2 = GameData(game_number=2, pgn=saved_pgn)
        reopened = ChessLogStorageService.load_tags(new_game2)
        self.assertEqual(
            ChessLogStorageService.count_tags(reopened), 1,
            "reopened game2: exactly 1 moment",
        )
        self.assertEqual(
            reopened.get("1", [{}])[0].get("why"), "new moment",
            "reopened game2: contains the new moment",
        )
        self.assertNotIn("0", reopened,
                         "old path '0' absent in reopened game2 (cleared before relog)")

    # --- sequence 2 ---

    def test_sequence_2_pending_log_and_clear_lifecycle(self):
        """Single game: log (pending) → save all → clear (pending) → switch-away/back
        → save all.

        Verifies that pending Log and pending Clear both survive game switches and
        that all observable views reflect the correct state at each step.
        """
        # Fixture: 1 fresh game (no tags) + a dummy for the switch-away.
        game = make_game(1)
        game.white = "Alice"
        game.black = "Bob"
        game.date = "2026.01.01"
        dummy = make_game(2)   # used as switch-away target only

        ctrl, gm, dc = self._make_ctrl([game, dummy])
        self._switch_to(ctrl, gm, game)

        self._assert_game(ctrl, game, mem=0, flag=False, disk=0, dirty=False,
                          label="initial state")
        self.assertFalse(ctrl.has_unsaved_changes(), "no changes at start")

        # --- Step 1: log → pending, check all views ---
        dc.mark_database_unsaved.reset_mock()
        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path(
                [{"preset": "CLAMP", "cat": "M", "why": "first"}]
            )

        self._assert_game(ctrl, game, mem=1, flag=True, disk=0, dirty=False,
                          label="after log (pending)")
        self.assertTrue(ctrl.game_has_any_tags(),
                        "game_has_any_tags() True after pending log")
        self.assertTrue(ctrl.has_unsaved_changes(),
                        "has_unsaved_changes() True after pending log")
        self.assertFalse(ctrl.has_dirty_games(),
                         "has_dirty_games() False — pending log uses single-game cache")
        dc.mark_database_unsaved.assert_not_called()

        # --- Step 2: save all ---
        dc.mark_database_unsaved.reset_mock()
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual((saved, failed), (1, 0))

        self._assert_game(ctrl, game, mem=1, flag=True, disk=1, dirty=False,
                          label="after save_all")
        self.assertFalse(ctrl.has_unsaved_changes())
        self.assertEqual(dc.mark_database_unsaved.call_count, 1)
        loaded = ChessLogStorageService.load_tags(game)
        self.assertEqual(loaded.get("0", [{}])[0].get("why"), "first",
                         "first moment persisted in PGN")

        # --- Step 3: clear → switch-away → switch-back ---
        dc.mark_database_unsaved.reset_mock()
        ctrl.clear_tags_for_current_game()

        self._assert_game(ctrl, game, mem=0, flag=False, disk=1, dirty=True,
                          label="after pending clear")
        self.assertTrue(ctrl.has_dirty_games(),
                        "has_dirty_games() True after pending clear")
        self.assertTrue(ctrl.has_unsaved_changes(),
                        "has_unsaved_changes() True (disk has 1, cache has 0)")
        dc.mark_database_unsaved.assert_not_called()

        # Switch away (to dummy) and back — pending clear must survive.
        self._switch_to(ctrl, gm, dummy)
        self._switch_to(ctrl, gm, game)

        self._assert_game(ctrl, game, mem=0, flag=False, disk=1, dirty=True,
                          label="after switch-away/back — pending clear preserved")
        self.assertTrue(ctrl.has_unsaved_changes(),
                        "has_unsaved_changes() still True after switch-away/back")

        # --- Step 4: save all — commits the pending clear ---
        dc.mark_database_unsaved.reset_mock()
        saved, failed = ctrl.save_all_dirty_games()
        self.assertEqual((saved, failed), (1, 0))

        self._assert_game(ctrl, game, mem=0, flag=False, disk=0, dirty=False,
                          label="after save_all (clear committed)")
        self.assertFalse(ctrl.has_unsaved_changes())
        self.assertFalse(ctrl.has_dirty_games())
        self.assertEqual(dc.mark_database_unsaved.call_count, 1)


# ---------------------------------------------------------------------------
# Structural test: only _write_store may update cached stores / has_chess_log_tags
# ---------------------------------------------------------------------------

class TestWriteStoreIsOnlyMutationPath(unittest.TestCase):
    """Source-level guard: no code in app/ bypasses the _write_store contract.

    Scans app/**/*.py with AST-based function-level analysis and asserts that
    restricted patterns appear only in their allowlisted (file, function) pairs.
    A test failure means a new caller was added outside the allowlist — either
    add an entry with a justification or route through the approved path.

    _ALLOWLIST_REASONS documents why each (file, function) pair is legitimate.
    _RULES maps each pattern to the frozenset of allowed pairs.
    """

    # Reasons for each (filename_suffix, function_name) pair.
    # Each entry justifies why that function may contain the matched pattern.
    _ALLOWLIST_REASONS = {
        ("chess_log_controller.py", "_save_single_game"):
            "saves dirty games (Save All / save_games paths)",
        ("chess_log_controller.py", "save_tags_for_current_game"):
            "Save button path: persists the active game's cache to PGN",
        ("chess_log_controller.py", "_write_store"):
            "sole authorized write path for _cached_paths_data, _multi_cache, and has_chess_log_tags",
        ("chess_log_controller.py", "_load_into_cache"):
            "disk load / multi-cache promotion when a game becomes active",
        ("chess_log_controller.py", "_on_active_game_changed"):
            "Rule B: flushes + prunes caches on game switch",
        ("chess_log_controller.py", "_on_active_database_changed"):
            "flushes + prunes caches on database switch",
        ("chess_log_controller.py", "get_tags_for_game"):
            "lazy load from disk into multi-cache on first peek",
        ("chess_log_controller.py", "replace_entries_at_path_for_game"):
            "lazy load from disk into multi-cache on first edit",
        ("chess_log_controller.py", "_prune_dirty_games_against_open_databases"):
            "removes stale multi-cache entries for closed databases",
        ("chess_log_storage_service.py", "store_tags"):
            "own definition; sets has_chess_log_tags after writing",
        ("chess_log_storage_service.py", "clear_tags"):
            "own definition; sets has_chess_log_tags = False after clearing; "
            "sole caller of _remove_chess_log_tags",
    }
    # Initial flag value is set by pgn_service._extract_game_data:976 via GameData.__init__
    # at database open time (calls ChessLogStorageService.has_moments(headers) — not a
    # game.has_chess_log_tags= assignment; uses local variable + constructor).

    # Rules: (regex_pattern, frozenset_of_allowed_keys, failure_message).
    # Each key is a (filename_suffix, function_name) pair from _ALLOWLIST_REASONS.
    _RULES = [
        (
            r"ChessLogStorageService\.(store_tags|clear_tags)\s*\(",
            frozenset({
                ("chess_log_controller.py", "_save_single_game"),
                ("chess_log_controller.py", "save_tags_for_current_game"),
                ("chess_log_storage_service.py", "store_tags"),
                ("chess_log_storage_service.py", "clear_tags"),
            }),
            "ChessLogStorageService.store_tags / clear_tags called outside allowlist",
        ),
        (
            r"\bgame\.has_chess_log_tags\s*=",
            frozenset({
                ("chess_log_controller.py", "_write_store"),
                ("chess_log_storage_service.py", "store_tags"),
                ("chess_log_storage_service.py", "clear_tags"),
            }),
            "game.has_chess_log_tags assigned outside allowlist",
        ),
        (
            r"self\._cached_paths_data\s*=",
            frozenset({
                ("chess_log_controller.py", "_write_store"),
                ("chess_log_controller.py", "_load_into_cache"),
                ("chess_log_controller.py", "_on_active_game_changed"),
                ("chess_log_controller.py", "_on_active_database_changed"),
            }),
            "_cached_paths_data assigned outside allowlist",
        ),
        (
            r"self\._multi_cache\[.*\]\s*="
            r"|del\s+self\._multi_cache\["
            r"|self\._multi_cache\.(?:pop|clear|update|setdefault)\s*\(",
            frozenset({
                ("chess_log_controller.py", "get_tags_for_game"),
                ("chess_log_controller.py", "replace_entries_at_path_for_game"),
                ("chess_log_controller.py", "_write_store"),
                ("chess_log_controller.py", "_load_into_cache"),
                ("chess_log_controller.py", "_on_active_game_changed"),
                ("chess_log_controller.py", "_on_active_database_changed"),
                ("chess_log_controller.py", "_prune_dirty_games_against_open_databases"),
            }),
            "_multi_cache mutated outside allowlist",
        ),
        (
            r"\._remove_chess_log_tags\s*\(",
            frozenset({
                ("chess_log_storage_service.py", "clear_tags"),
            }),
            "_remove_chess_log_tags called outside save path (must not be called from load_tags)",
        ),
    ]

    @classmethod
    def _app_py_files(cls):
        import glob
        app_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "app"
        )
        return sorted(glob.glob(_os.path.join(app_dir, "**", "*.py"), recursive=True))

    @staticmethod
    def _build_line_to_func(source: str) -> dict:
        """Map each line number to the name of the innermost function containing it.

        Lines outside any function map to '<module>'.  Innermost wins when
        functions are nested (sort outer functions first so inner ones overwrite).
        """
        import ast

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}

        funcs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                funcs.append((node.name, node.lineno, end, end - node.lineno))

        # Sort descending by span: outer first, inner (smaller span) overwrites.
        funcs.sort(key=lambda x: x[3], reverse=True)
        line_to_func: dict = {}
        for fname, start, end, _span in funcs:
            for lineno in range(start, end + 1):
                line_to_func[lineno] = fname
        return line_to_func

    def _violations(self, pattern, allowlist):
        import re

        hits = []
        for path in self._app_py_files():
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            line_to_func = self._build_line_to_func(source)
            filename = _os.path.basename(path)
            for lineno, line in enumerate(source.split("\n"), 1):
                if not re.search(pattern, line):
                    continue
                if line.lstrip().startswith("#"):
                    continue
                func_name = line_to_func.get(lineno, "<module>")
                if (filename, func_name) in allowlist:
                    continue
                hits.append((path, lineno, line.rstrip()))
        return hits

    def test_store_and_clear_tags_only_in_allowlist(self):
        pattern, allowlist, msg = self._RULES[0]
        violations = self._violations(pattern, allowlist)
        if violations:
            detail = "\n".join(f"  {p}:{ln}: {l}" for p, ln, l in violations)
            self.fail(f"{msg}:\n{detail}")

    def test_store_and_clear_tags_called_only_from_save_single_game(self):
        """Within chess_log_controller.py, store_tags( and clear_tags( are each
        called from exactly one function: _save_single_game."""
        import re
        path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))),
            "app", "controllers", "chess_log_controller.py",
        )
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        line_to_func = self._build_line_to_func(source)
        for name in ("store_tags", "clear_tags"):
            funcs = {
                line_to_func.get(i, "<module>")
                for i, line in enumerate(source.split("\n"), 1)
                if re.search(r"\b%s\(" % name, line)
                and not line.lstrip().startswith("#")
            }
            self.assertEqual(funcs, {"_save_single_game"}, name)

    def test_has_chess_log_tags_assignment_only_in_allowlist(self):
        pattern, allowlist, msg = self._RULES[1]
        violations = self._violations(pattern, allowlist)
        if violations:
            detail = "\n".join(f"  {p}:{ln}: {l}" for p, ln, l in violations)
            self.fail(f"{msg}:\n{detail}")

    def test_load_tags_does_not_set_has_chess_log_tags(self):
        """load_tags is a pure read — it must not write game.has_chess_log_tags."""
        game = make_game(1)
        # Write a moment so the PGN tag exists.
        ChessLogStorageService.store_tags(
            game,
            {"0": [ChessLogStorageService.make_entry("CLAMP", "M", "hi")]},
            {},
        )
        # Simulate a pending Clear: in-memory flag is False, but PGN still has the tag.
        game.has_chess_log_tags = False
        # load_tags must return the PGN data without touching the flag.
        result = ChessLogStorageService.load_tags(game)
        self.assertEqual(ChessLogStorageService.count_tags(result), 1,
                         "load_tags returns PGN data")
        self.assertFalse(game.has_chess_log_tags,
                         "load_tags must not clobber the pending-clear flag")

    def test_cached_paths_data_assignment_only_in_allowlist(self):
        pattern, allowlist, msg = self._RULES[2]
        violations = self._violations(pattern, allowlist)
        if violations:
            detail = "\n".join(f"  {p}:{ln}: {l}" for p, ln, l in violations)
            self.fail(f"{msg}:\n{detail}")

    def test_multi_cache_mutation_only_in_allowlist(self):
        pattern, allowlist, msg = self._RULES[3]
        violations = self._violations(pattern, allowlist)
        if violations:
            detail = "\n".join(f"  {p}:{ln}: {l}" for p, ln, l in violations)
            self.fail(f"{msg}:\n{detail}")

    def test_remove_chess_log_tags_only_in_save_path(self):
        pattern, allowlist, msg = self._RULES[4]
        violations = self._violations(pattern, allowlist)
        if violations:
            detail = "\n".join(f"  {p}:{ln}: {l}" for p, ln, l in violations)
            self.fail(f"{msg}:\n{detail}")


# ---------------------------------------------------------------------------
# Integration test: Log column in a real DatabaseModel reflects pending state
# ---------------------------------------------------------------------------

import os as _os
import sys as _sys
import subprocess as _subprocess

_os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_available() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = _subprocess.run(
            [_sys.executable, "-c", probe],
            capture_output=True, timeout=10,
            cwd=_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_available()


@unittest.skipUnless(_QT_OK, "Qt not available in this environment")
class TestLogColumnRealDatabaseModel(unittest.TestCase):
    """Prove the Log column reflects pending Log and pending Clear without a save.

    Uses a real DatabaseModel so the full chain is exercised:
        _write_store → game.has_chess_log_tags → DatabaseModel.data(COL_LOG)
    """

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication(_sys.argv)
        from app.models.database_model import DatabaseModel
        cls.DatabaseModel = DatabaseModel

    def _make_ctrl_with_real_db(self, game):
        db_model = self.DatabaseModel()
        db_model.add_game(game, mark_unsaved=False, tags=[])

        pm = MagicMock()
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()

        dc = MagicMock()
        dc.find_database_model_for_game.return_value = db_model
        dc.get_panel_model.return_value = pm

        gm = make_game_model_mock(game)
        gm.active_game = game
        gc = make_game_controller_mock(gm)

        ctrl = ChessLogController({}, gc, database_controller=dc)
        ctrl._cached_game_id = id(game)
        return ctrl, gm, db_model

    def _col_log_value(self, db_model, game):
        from PyQt6.QtCore import Qt
        row = db_model.find_game(game)
        idx = db_model.index(row, db_model.COL_LOG)
        return db_model.data(idx, Qt.ItemDataRole.DisplayRole)

    def test_pending_log_shows_checkmark_in_log_column(self):
        """add_moment_at_active_path sets has_chess_log_tags=True; Log column shows ✓."""
        game = make_game()
        ctrl, gm, db_model = self._make_ctrl_with_real_db(game)

        self.assertEqual(self._col_log_value(db_model, game), "",
                         "precondition: Log column empty before any moment")

        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            ctrl.add_moment_at_active_path([{"preset": "CLAMP", "cat": "M", "why": ""}])

        self.assertTrue(game.has_chess_log_tags,
                        "has_chess_log_tags must be True after pending Log")
        self.assertEqual(self._col_log_value(db_model, game), "✓",
                         "Log column must show ✓ after pending Log (no save required)")

    def test_pending_clear_removes_checkmark_in_log_column(self):
        """clear_tags_for_current_game sets has_chess_log_tags=False; Log column shows empty."""
        game = make_game()
        ChessLogStorageService.store_tags(
            game,
            {"0": [ChessLogStorageService.make_entry("CLAMP", "M")]},
            {},
        )
        ctrl, gm, db_model = self._make_ctrl_with_real_db(game)
        ctrl._load_into_cache(game)

        self.assertEqual(self._col_log_value(db_model, game), "✓",
                         "precondition: Log column shows ✓ after store_tags")

        ctrl.clear_tags_for_current_game()

        self.assertFalse(game.has_chess_log_tags,
                         "has_chess_log_tags must be False after pending Clear")
        self.assertEqual(self._col_log_value(db_model, game), "",
                         "Log column must show empty after pending Clear (no save required)")


if __name__ == "__main__":
    unittest.main()
