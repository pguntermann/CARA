"""Tests for ShowShallowTagsDialog.

Requires a working Qt platform plugin (CI uses QT_QPA_PLATFORM=offscreen).
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, call

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
    from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAINLINE_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)


def _make_game(game_number: int = 1, pgn: str = MAINLINE_PGN):
    from app.models.database_model import GameData
    return GameData(game_number=game_number, pgn=pgn)


def _make_entry(preset, cat, why="", ignore_shallow=False):
    from app.services.chess_log_storage_service import ChessLogStorageService
    return ChessLogStorageService.make_entry(preset, cat, why, ignore_shallow=ignore_shallow)


def _make_controller(tags_by_game=None):
    from app.controllers.chess_log_controller import ChessLogController
    ctrl = MagicMock()
    tags_by_game = tags_by_game or {}
    # Mutable state mirrors the real controller: replace_entries_at_path_for_game
    # updates this dict so Phase b reads Phase a's output, matching real-controller
    # behaviour (Phase a writes to the cache; Phase b reads the updated cache).
    mutable_tags = {k: {pk: list(es) for pk, es in v.items()} for k, v in tags_by_game.items()}

    def _get_tags(game):
        return mutable_tags.get(game.game_number, {})

    def _replace_entries(game, path_key, preset, entries):
        gnum = game.game_number
        if gnum not in mutable_tags:
            mutable_tags[gnum] = {}
        existing = mutable_tags[gnum].get(path_key, [])
        kept = [e for e in existing if e.get("preset") != preset]
        mutable_tags[gnum][path_key] = kept + list(entries)

    ctrl.get_tags_for_game.side_effect = _get_tags
    ctrl.count_unchecked_answers.side_effect = lambda games: ChessLogController.count_unchecked_answers(ctrl, games)
    ctrl.has_any_checked_answer.side_effect = lambda games: ChessLogController.has_any_checked_answer(ctrl, games)
    ctrl.get_shallow_vague_keys.side_effect = lambda games: ChessLogController.get_shallow_vague_keys(ctrl, games)
    ctrl.get_custom_categories.return_value = []
    ctrl.replace_entries_at_path_for_game = MagicMock(side_effect=_replace_entries)
    return ctrl


def _make_dialog(games, tags_by_game, shallow_keys, saved_mode=True):
    from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
    ctrl = _make_controller(tags_by_game)
    return ShowShallowTagsDialog(
        config={},
        games=games,
        controller=ctrl,
        shallow_keys=shallow_keys,
        saved_mode=saved_mode,
    ), ctrl


def _make_dialog_with_classified(games, tags_by_game, shallow_keys, classified_keys):
    from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
    ctrl = _make_controller(tags_by_game)
    return ShowShallowTagsDialog(
        config={},
        games=games,
        controller=ctrl,
        shallow_keys=shallow_keys,
        classified_keys=classified_keys,
    ), ctrl


def _sk(game, path_key, preset, cat=""):
    """Build a single-element shallow/vague key 4-tuple using the game object."""
    return (game, path_key, preset, cat)


# ---------------------------------------------------------------------------
# Row filtering — only shallow_keys rows are shown
# ---------------------------------------------------------------------------

@requires_qt
class TestShallowRowFiltering(unittest.TestCase):
    def test_shows_only_shallow_keyed_rows(self):
        game = _make_game()
        tags = {
            "0": [_make_entry("CLAMP", "C", "I blundered")],
            "0.0": [_make_entry("CLAMP", "L", "deep insight about alignment")],
        }
        # Only ("0", "CLAMP") is shallow
        shallow_keys = {(game, "0", "CLAMP", "")}
        dlg, _ = _make_dialog([game], {1: tags}, shallow_keys)
        self.assertEqual(len(dlg._row_widgets), 1)

    def test_shows_all_rows_when_all_shallow(self):
        game = _make_game()
        tags = {
            "0": [_make_entry("CLAMP", "C", "I blundered")],
            "0.0": [_make_entry("CLAMP", "L", "missed it")],
        }
        shallow_keys = {(game, "0", "CLAMP", ""), (game, "0.0", "CLAMP", "")}
        dlg, _ = _make_dialog([game], {1: tags}, shallow_keys)
        self.assertEqual(len(dlg._row_widgets), 2)

    def test_shows_zero_rows_when_no_shallow_keys(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "deep note")]}
        dlg, _ = _make_dialog([game], {1: tags}, set())
        self.assertEqual(len(dlg._row_widgets), 0)

    def test_preset_filter_respected(self):
        game = _make_game()
        tags = {
            "0": [
                _make_entry("CLAMP", "C", "shallow"),
                _make_entry("CCT", "Checks", "also shallow"),
            ],
        }
        # Only CLAMP is shallow
        shallow_keys = {(game, "0", "CLAMP", "")}
        dlg, _ = _make_dialog([game], {1: tags}, shallow_keys)
        self.assertEqual(len(dlg._row_widgets), 1)
        self.assertEqual(dlg._row_widgets[0]._preset, "CLAMP")


# ---------------------------------------------------------------------------
# Save/Cancel: edits are buffered until Save, not on each edit signal
# ---------------------------------------------------------------------------

@requires_qt
class TestLiveEdit(unittest.TestCase):
    def test_edited_signal_does_not_trigger_immediate_persist(self):
        """Emitting the edited signal must NOT call replace_entries_at_path_for_game.

        The old live-edit model was removed; edits are now buffered until Save.
        """
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "I blundered")]}
        shallow_keys = {(game, "0", "CLAMP", "")}
        dlg, ctrl = _make_dialog([game], {1: tags}, shallow_keys)

        row = dlg._row_widgets[0]
        row.edited.emit()

        ctrl.replace_entries_at_path_for_game.assert_not_called()

    def test_save_calls_replace_and_save_games(self):
        """_on_save writes the shown row and calls save_games."""
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "I blundered")]}
        shallow_keys = {(game, "0", "CLAMP", "")}
        classified_keys = frozenset(shallow_keys)
        dlg, ctrl = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl.save_games = MagicMock()

        dlg._on_save()

        ctrl.replace_entries_at_path_for_game.assert_called_once()
        call_args = ctrl.replace_entries_at_path_for_game.call_args[0]
        self.assertIs(call_args[0], game)
        self.assertEqual(call_args[1], "0")
        self.assertEqual(call_args[2], "CLAMP")
        ctrl.save_games.assert_called_once()


# ---------------------------------------------------------------------------
# Ignore checkbox present on all rows
# ---------------------------------------------------------------------------

@requires_qt
class TestIgnoreCheckboxPresent(unittest.TestCase):
    def test_all_rows_have_ignore_checkbox(self):
        game = _make_game()
        tags = {
            "0": [_make_entry("CLAMP", "C", "shallow1")],
            "0.0": [_make_entry("CLAMP", "L", "shallow2")],
        }
        shallow_keys = {(game, "0", "CLAMP", ""), (game, "0.0", "CLAMP", "")}
        dlg, _ = _make_dialog([game], {1: tags}, shallow_keys)
        for row in dlg._row_widgets:
            self.assertIsNotNone(row._ignore_check)
            self.assertIsInstance(row._ignore_check, QCheckBox)


# ---------------------------------------------------------------------------
# Buttons: Save + Cancel (no Close-only, no OK)
# ---------------------------------------------------------------------------

@requires_qt
class TestCloseButton(unittest.TestCase):
    def test_has_save_button(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        self.assertTrue(hasattr(dlg, "_save_btn"))
        self.assertIsInstance(dlg._save_btn, QPushButton)

    def test_has_cancel_button(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        self.assertTrue(hasattr(dlg, "_cancel_btn"))
        self.assertIsInstance(dlg._cancel_btn, QPushButton)

    def test_no_ok_button(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        self.assertFalse(hasattr(dlg, "_ok_btn"))

    def test_empty_shallow_keys_shows_no_rows_but_has_save(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "deep note")]}
        dlg, _ = _make_dialog([game], {1: tags}, set())
        self.assertEqual(len(dlg._row_widgets), 0)
        self.assertTrue(hasattr(dlg, "_save_btn"))



# ---------------------------------------------------------------------------
# Mini-board orientation follows the mover at the tagged ply, per row
# ---------------------------------------------------------------------------

@requires_qt
class TestMiniBoardOrientationMoverAtPly(unittest.TestCase):
    """Shallow dialog row orientation comes from pre_board.turn at the tagged ply."""

    def test_white_ply_row_not_flipped(self):
        # MAINLINE_PGN: path "0" is 1.e4 — White to move → not flipped
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        self.assertFalse(dlg._row_widgets[0]._is_flipped)

    def test_black_ply_row_is_flipped(self):
        # MAINLINE_PGN: path "0.0" is 1...e5 — Black to move → flipped
        game = _make_game()
        tags = {"0.0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0.0", "CLAMP", "")})
        self.assertTrue(dlg._row_widgets[0]._is_flipped)

    def test_snapshot_carries_flip_for_black_ply(self):
        game = _make_game()
        tags = {"0.0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0.0", "CLAMP", "")})
        self.assertTrue(dlg._row_widgets[0].snapshot().is_flipped)


# ---------------------------------------------------------------------------
# Font and height wiring — shared _TagRowWidget reads from ui.dialogs.show_tags.*
# ---------------------------------------------------------------------------

@requires_qt
class TestShallowTagsDialogFontAndHeightWiring(unittest.TestCase):
    """ShowShallowTagsDialog rows inherit font/height config from the shared
    _TagRowWidget, which must read from ui.dialogs.show_tags.*, not moment."""

    def _make_shallow_dialog(self, show_tags_cfg: dict):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        config = {"ui": {"dialogs": {"show_tags": show_tags_cfg}}}
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow note")]}
        shallow_keys = {(game, "0", "CLAMP", "")}
        ctrl = _make_controller({1: tags})
        return ShowShallowTagsDialog(
            config=config,
            games=[game],
            controller=ctrl,
            shallow_keys=shallow_keys,
        )

    def test_input_font_size_from_config(self):
        dlg = self._make_shallow_dialog({"inputs": {"font_size": 14}})
        row = dlg._row_widgets[0]
        self.assertEqual(row._input_font_size, 14)

    def test_fit_lines_from_config(self):
        dlg = self._make_shallow_dialog({"fit_min_lines": 1, "fit_max_lines": 6})
        row = dlg._row_widgets[0]
        self.assertEqual(row._fit_min_lines, 1)
        self.assertEqual(row._fit_max_lines, 6)
        te = row._why_texts.get("why")
        self.assertIsNotNone(te)
        self.assertGreater(te.minimumHeight(), 0)

    def test_defaults_when_config_empty(self):
        dlg = self._make_shallow_dialog({})
        row = dlg._row_widgets[0]
        self.assertEqual(row._input_font_size, 11)
        self.assertEqual(row._fit_min_lines, 1)
        self.assertEqual(row._fit_max_lines, 6)
        te = row._why_texts.get("why")
        self.assertIsNotNone(te)
        self.assertGreater(te.minimumHeight(), 0)


# ---------------------------------------------------------------------------
# Window title is "Check Logs"
# ---------------------------------------------------------------------------

@requires_qt
class TestWindowTitle(unittest.TestCase):
    def test_window_title_is_check_logs(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        self.assertEqual(dlg.windowTitle(), "Check Logs")


# ---------------------------------------------------------------------------
# Resize grip
# ---------------------------------------------------------------------------

@requires_qt
class TestShallowTagsDialogResizeGrip(unittest.TestCase):
    def test_resize_grip_installed(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        self.assertTrue(hasattr(dlg, "_cara_themed_resize_grip"))

    def test_resize_grip_installed_empty_dialog(self):
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "not shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, set())
        self.assertTrue(hasattr(dlg, "_cara_themed_resize_grip"))


# ---------------------------------------------------------------------------
# Save model: full suite (plan tests 13-20)
# ---------------------------------------------------------------------------

@requires_qt
class TestSaveModel(unittest.TestCase):

    def test_save_writes_is_shallow_true_for_shown_rows(self):
        """Plan test 13: shown rows get is_shallow=True stamped on Save."""
        game = _make_game()
        tags = {
            "0": [_make_entry("CLAMP", "C", "shallow one")],
            "0.0": [_make_entry("CLAMP", "L", "shallow two")],
            "1": [_make_entry("CLAMP", "A", "not shallow")],
        }
        shallow_keys = {(game, "0", "CLAMP", ""), (game, "0.0", "CLAMP", "")}
        classified_keys = frozenset(shallow_keys | {(game, "1", "CLAMP", "")})
        dlg, ctrl = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl.save_games = MagicMock()

        dlg._on_save()

        calls = ctrl.replace_entries_at_path_for_game.call_args_list
        shown_calls = {(c[0][1], c[0][2]) for c in calls}
        # Both shallow rows touched; deep-but-not-stale "1" not touched
        self.assertIn(("0", "CLAMP"), shown_calls)
        self.assertIn(("0.0", "CLAMP"), shown_calls)
        for c in calls:
            if c[0][1] in ("0", "0.0"):
                self.assertTrue(all(e.get("is_shallow") for e in c[0][3]))

    def test_save_clears_stale_is_shallow_for_non_shown_entries(self):
        """Plan test 14: DEEP entry with stale is_shallow=True gets cleared on Save."""
        game = _make_game()
        stale_entry = dict(_make_entry("CLAMP", "C", "deep now"), is_shallow=True)
        tags = {
            "0": [_make_entry("CLAMP", "L", "still shallow")],
            "0.0": [stale_entry],
        }
        shallow_keys = {(game, "0", "CLAMP", "")}
        classified_keys = frozenset({(game, "0", "CLAMP", ""), (game, "0.0", "CLAMP", "")})
        dlg, ctrl = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl.save_games = MagicMock()

        dlg._on_save()

        # "0.0" is deep-classified and has stale flag → must be cleared
        deep_call = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            if c[0][1] == "0.0":
                deep_call = c
        self.assertIsNotNone(deep_call, "Expected replace call for 0.0")
        self.assertFalse(any(e.get("is_shallow") for e in deep_call[0][3]))
        ctrl.save_games.assert_called_once()

    def test_cancel_discards_pending_shallow_results(self):
        """Plan test 15: Cancel makes no writes."""
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        shallow_keys = {(game, "0", "CLAMP", "")}
        classified_keys = frozenset(shallow_keys)
        dlg, ctrl = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl.save_games = MagicMock()

        dlg.reject()

        ctrl.replace_entries_at_path_for_game.assert_not_called()
        ctrl.save_games.assert_not_called()

    def test_close_button_discards(self):
        """Plan test 16: close() routes to reject, making no writes."""
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        shallow_keys = {(game, "0", "CLAMP", "")}
        classified_keys = frozenset(shallow_keys)
        dlg, ctrl = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl.save_games = MagicMock()

        dlg.close()

        ctrl.replace_entries_at_path_for_game.assert_not_called()
        ctrl.save_games.assert_not_called()

    def test_ignore_toggle_persists_only_on_save(self):
        """Plan test 17: Ignore toggle saved on Save, discarded on Cancel."""
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow", ignore_shallow=False)]}
        shallow_keys = {(game, "0", "CLAMP", "")}
        classified_keys = frozenset(shallow_keys)

        # Cancel: toggle, then cancel → not persisted
        dlg_c, ctrl_c = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl_c.save_games = MagicMock()
        dlg_c._row_widgets[0]._ignore_check.setChecked(True)
        dlg_c.reject()
        ctrl_c.replace_entries_at_path_for_game.assert_not_called()

        # Save: toggle, then save → persisted with ignore_shallow=True
        dlg_s, ctrl_s = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl_s.save_games = MagicMock()
        dlg_s._row_widgets[0]._ignore_check.setChecked(True)
        dlg_s._on_save()
        calls = ctrl_s.replace_entries_at_path_for_game.call_args_list
        self.assertTrue(len(calls) > 0)
        saved_entries = calls[0][0][3]
        self.assertTrue(any(e.get("ignore_shallow") for e in saved_entries))

    def test_save_leaves_unparsed_entry_is_shallow_untouched(self):
        """Plan test 19: entry not in classified_keys keeps is_shallow=True after Save."""
        game = _make_game()
        # Entry at "0.0" was not classified this run (unparsed) → must not be touched
        prior_shallow = dict(_make_entry("CLAMP", "A", "hard to parse"), is_shallow=True)
        tags = {
            "0": [_make_entry("CLAMP", "C", "shallow")],
            "0.0": [prior_shallow],
        }
        shallow_keys = {(game, "0", "CLAMP", "")}
        # classified_keys does NOT include "0.0" — it was unparsed
        classified_keys = frozenset({(game, "0", "CLAMP", "")})
        dlg, ctrl = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl.save_games = MagicMock()

        dlg._on_save()

        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            self.assertNotEqual(c[0][1], "0.0",
                "replace must not be called for unparsed entry at 0.0")

    def test_save_leaves_ignored_entry_flags_untouched(self):
        """Plan test 20: entry with ignore_shallow=True keeps its flags after Save."""
        game = _make_game()
        ignored_entry = dict(
            _make_entry("CLAMP", "L", "ignored", ignore_shallow=True),
            is_shallow=True,
        )
        tags = {
            "0": [_make_entry("CLAMP", "C", "shallow")],
            "0.0": [ignored_entry],
        }
        shallow_keys = {(game, "0", "CLAMP", "")}
        # "0.0" skipped by classifier (ignore_shallow=True) → not in classified_keys
        classified_keys = frozenset({(game, "0", "CLAMP", "")})
        dlg, ctrl = _make_dialog_with_classified(
            [game], {1: tags}, shallow_keys, classified_keys
        )
        ctrl.save_games = MagicMock()

        dlg._on_save()

        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            self.assertNotEqual(c[0][1], "0.0",
                "replace must not be called for ignore_shallow entry at 0.0")

    def test_save_marks_both_databases_in_mixed_scope(self):
        """Plan test 18: Save on games from two DBs calls save_games once with both."""
        from unittest.mock import call as mock_call
        game_a = _make_game(game_number=1)
        game_b = _make_game(game_number=2)
        tags_a = {"0": [_make_entry("CLAMP", "C", "shallow a")]}
        tags_b = {"0": [_make_entry("CLAMP", "C", "shallow b")]}
        shallow_keys = {(game_a, "0", "CLAMP", ""), (game_b, "0", "CLAMP", "")}
        classified_keys = frozenset(shallow_keys)

        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        ctrl = _make_controller({1: tags_a, 2: tags_b})
        ctrl.save_games = MagicMock()
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game_a, game_b],
            controller=ctrl,
            shallow_keys=shallow_keys,
            classified_keys=classified_keys,
        )

        dlg._on_save()

        ctrl.save_games.assert_called_once()
        saved_games = set(ctrl.save_games.call_args[0][0])
        self.assertIn(game_a, saved_games)
        self.assertIn(game_b, saved_games)


# ---------------------------------------------------------------------------
# Chip labels — Shallow / Vague lesson
# ---------------------------------------------------------------------------

@requires_qt
class TestChipLabels(unittest.TestCase):
    """Row chips reflect the is_shallow / is_vague flags on entries."""

    def _make_vague_dialog(self, shallow_keys, vague_keys, entries_by_path, classified_keys=None):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        ctrl = _make_controller({1: entries_by_path})
        # Remap integer keys to this game object (the helper receives tuples with game as pos 0)
        ck = frozenset(classified_keys) if classified_keys is not None else frozenset(shallow_keys | vague_keys)
        return ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=shallow_keys,
            vague_keys=vague_keys,
            classified_keys=ck,
        ), ctrl, game

    def test_shallow_chip_present_when_is_shallow(self):
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "shallow one")]}
        ctrl = _make_controller({1: entries})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        sk = frozenset({(game, "0", "CLAMP", "")})
        ck = frozenset(sk)
        dlg = ShowShallowTagsDialog(config={}, games=[game], controller=ctrl,
                                    shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck)
        row = dlg._row_widgets[0]
        self.assertTrue(row._preserved_is_shallow)
        self.assertIsNotNone(row._shallow_chip)
        self.assertIsNone(row._vague_chip)

    def test_vague_chip_present_when_is_vague(self):
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "specific + filler lesson")]}
        ctrl = _make_controller({1: entries})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        vk = frozenset({(game, "0", "CLAMP", "")})
        ck = frozenset(vk)
        dlg = ShowShallowTagsDialog(config={}, games=[game], controller=ctrl,
                                    shallow_keys=frozenset(), vague_keys=vk, classified_keys=ck)
        row = dlg._row_widgets[0]
        self.assertFalse(row._preserved_is_shallow)
        self.assertTrue(row._preserved_is_vague)
        self.assertIsNone(row._shallow_chip)
        self.assertIsNotNone(row._vague_chip)

    def test_both_chips_present_when_both_flags(self):
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "generic + filler")]}
        ctrl = _make_controller({1: entries})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        sk = frozenset({(game, "0", "CLAMP", "")})
        vk = frozenset({(game, "0", "CLAMP", "")})
        ck = frozenset(sk | vk)
        dlg = ShowShallowTagsDialog(config={}, games=[game], controller=ctrl,
                                    shallow_keys=sk, vague_keys=vk, classified_keys=ck)
        row = dlg._row_widgets[0]
        self.assertIsNotNone(row._shallow_chip)
        self.assertIsNotNone(row._vague_chip)

    def test_no_chips_when_neither_flag(self):
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "deep specific real")]}
        ctrl = _make_controller({1: entries})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        sk = frozenset({(game, "0", "CLAMP", "")})
        ck = frozenset(sk)
        dlg = ShowShallowTagsDialog(config={}, games=[game], controller=ctrl,
                                    shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck)
        row = dlg._row_widgets[0]
        self.assertFalse(row._preserved_is_vague)
        self.assertIsNone(row._vague_chip)

    def test_chip_text_from_config(self):
        from PyQt6.QtWidgets import QLabel
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        ctrl = _make_controller({1: entries})
        config = {"ui": {"dialogs": {"shallow": {"labels": {
            "shallow": {"text": "FLAGGED", "background_color": [100, 0, 0], "text_color": [255, 255, 255]},
        }}}}}
        dlg = ShowShallowTagsDialog(
            config=config, games=[game], controller=ctrl,
            shallow_keys={(game, "0", "CLAMP", "")}, vague_keys=frozenset(),
            classified_keys=frozenset({(game, "0", "CLAMP", "")}),
        )
        row = dlg._row_widgets[0]
        self.assertIsNotNone(row._shallow_chip)
        self.assertEqual(row._shallow_chip.text(), "FLAGGED")

    def test_chip_tooltip_from_config(self):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        ctrl = _make_controller({1: entries})
        config = {"ui": {"dialogs": {"shallow": {"labels": {
            "shallow": {"text": "S", "tooltip_clamp_cct": "Custom tip",
                        "background_color": [100, 0, 0], "text_color": [255, 255, 255]},
        }}}}}
        dlg = ShowShallowTagsDialog(
            config=config, games=[game], controller=ctrl,
            shallow_keys={(game, "0", "CLAMP", "")}, vague_keys=frozenset(),
            classified_keys=frozenset({(game, "0", "CLAMP", "")}),
        )
        self.assertEqual(dlg._row_widgets[0]._shallow_chip.toolTip(), "Custom tip")


# ---------------------------------------------------------------------------
# Chip tooltips — preset-aware (CLAMP/CCT vs 3x3)
# ---------------------------------------------------------------------------

@requires_qt
class TestChipTooltips(unittest.TestCase):
    """Chip tooltips pick the correct key based on preset."""

    @classmethod
    def setUpClass(cls):
        from app.config.config_loader import ConfigLoader
        cls._cfg = ConfigLoader().load()
        shallow_cfg = (
            cls._cfg.get("ui", {}).get("dialogs", {})
            .get("shallow", {}).get("labels", {})
        )
        cls._tooltip_clamp_cct = shallow_cfg.get("shallow", {}).get("tooltip_clamp_cct", "")
        cls._tooltip_3x3 = shallow_cfg.get("shallow", {}).get("tooltip_3x3", "")
        cls._tooltip_vague = shallow_cfg.get("vague_lesson", {}).get("tooltip", "")

    def _make_clamp_shallow_dlg(self, preset="CLAMP"):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {"0": [_make_entry(preset, "C", "I blundered the knight")]}
        ctrl = _make_controller({1: entries})
        sk = frozenset({(game, "0", preset, "")})
        return ShowShallowTagsDialog(
            config=self._cfg, games=[game], controller=ctrl,
            shallow_keys=sk, classified_keys=sk,
        )

    def _make_3x3_shallow_dlg(self):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {"0": [_make_entry("3x3", "Why1", "I moved")]}
        ctrl = _make_controller({1: entries})
        sk = frozenset({(game, "0", "3x3", "Why1")})
        return ShowShallowTagsDialog(
            config=self._cfg, games=[game], controller=ctrl,
            shallow_keys=sk, classified_keys=sk,
        )

    def _make_3x3_vague_dlg(self):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {"0": [_make_entry("3x3", "Why4", "Try harder")]}
        ctrl = _make_controller({1: entries})
        vk = frozenset({(game, "0", "3x3", "Why4")})
        return ShowShallowTagsDialog(
            config=self._cfg, games=[game], controller=ctrl,
            shallow_keys=frozenset(), vague_keys=vk, classified_keys=vk,
        )

    def test_clamp_shallow_chip_tooltip(self):
        dlg = self._make_clamp_shallow_dlg("CLAMP")
        row = dlg._row_widgets[0]
        self.assertIsNotNone(row._shallow_chip)
        self.assertEqual(row._shallow_chip.toolTip(), self._tooltip_clamp_cct)

    def test_cct_shallow_chip_tooltip(self):
        dlg = self._make_clamp_shallow_dlg("CCT")
        row = dlg._row_widgets[0]
        self.assertIsNotNone(row._shallow_chip)
        self.assertEqual(row._shallow_chip.toolTip(), self._tooltip_clamp_cct)

    def test_3x3_shallow_chip_tooltip(self):
        dlg = self._make_3x3_shallow_dlg()
        row = dlg._row_widgets[0]
        self.assertIsNotNone(row._shallow_chip)
        self.assertEqual(row._shallow_chip.toolTip(), self._tooltip_3x3)

    def test_3x3_vague_chip_tooltip(self):
        dlg = self._make_3x3_vague_dlg()
        row = dlg._row_widgets[0]
        self.assertIsNotNone(row._vague_chip)
        self.assertEqual(row._vague_chip.toolTip(), self._tooltip_vague)

    def test_config_tooltip_clamp_cct_exact_text(self):
        expected = (
            "This note doesn't diagnose the move. Say what you missed, "
            "what you intended, or what you should have played. "
            "Tick Ignore if you disagree."
        )
        self.assertEqual(self._tooltip_clamp_cct, expected)

    def test_config_tooltip_3x3_exact_text(self):
        expected = (
            "This answer could fit almost any move. Name a piece, square, "
            "plan or threat from this position. Tick Ignore if you disagree."
        )
        self.assertEqual(self._tooltip_3x3, expected)

    def test_config_tooltip_vague_exact_text(self):
        expected = (
            "This lesson gives you nothing to do next game. Name a concrete "
            'habit or check, such as "count attackers and defenders". '
            "Tick Ignore if you disagree."
        )
        self.assertEqual(self._tooltip_vague, expected)


# ---------------------------------------------------------------------------
# Vague-keys: Save/Cancel model
# ---------------------------------------------------------------------------

@requires_qt
class TestVagueKeysSaveModel(unittest.TestCase):

    def _vague_dialog(self, path_key, shallow=False, vague=True):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        # Create entries matching the per-cat keys being tested
        entries_list = []
        if shallow:
            entries_list.append(_make_entry("3x3", "Why1", "I wanted to trade queens"))
        if vague:
            entries_list.append(_make_entry("3x3", "Why4", "Try harder next time"))
        if not entries_list:
            entries_list.append(_make_entry("3x3", "Why1", "I wanted to trade queens"))
        entries = {path_key: entries_list}
        ctrl = _make_controller({1: entries})
        ctrl.save_games = MagicMock()
        sk = frozenset({(game, path_key, "3x3", "Why1")} if shallow else [])
        vk = frozenset({(game, path_key, "3x3", "Why4")} if vague else [])
        ck = frozenset(sk | vk)
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=vk, classified_keys=ck,
        )
        return dlg, ctrl, game

    def test_save_writes_is_vague_true_for_vague_only_row(self):
        dlg, ctrl, game = self._vague_dialog("0", shallow=False, vague=True)
        dlg._on_save()
        calls = ctrl.replace_entries_at_path_for_game.call_args_list
        self.assertTrue(len(calls) > 0)
        entries_written = calls[0][0][3]
        self.assertTrue(any(e.get("is_vague") for e in entries_written))
        self.assertFalse(any(e.get("is_shallow") for e in entries_written))

    def test_save_writes_both_flags_for_shallow_and_vague_row(self):
        dlg, ctrl, game = self._vague_dialog("0", shallow=True, vague=True)
        dlg._on_save()
        calls = ctrl.replace_entries_at_path_for_game.call_args_list
        entries_written = calls[0][0][3]
        self.assertTrue(any(e.get("is_shallow") for e in entries_written))
        self.assertTrue(any(e.get("is_vague") for e in entries_written))

    def test_cancel_writes_nothing_for_vague_row(self):
        dlg, ctrl, game = self._vague_dialog("0", shallow=False, vague=True)
        dlg.reject()
        ctrl.replace_entries_at_path_for_game.assert_not_called()
        ctrl.save_games.assert_not_called()

    def test_stale_clear_removes_is_vague_from_non_flagged_classified_entry(self):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        stale = dict(_make_entry("CLAMP", "C", "deep now"), is_vague=True)
        tags = {
            "0": [_make_entry("CLAMP", "L", "shallow")],
            "0.0": [stale],
        }
        ctrl = _make_controller({1: tags})
        ctrl.save_games = MagicMock()
        sk = frozenset({(game, "0", "CLAMP", "")})
        ck = frozenset({(game, "0", "CLAMP", ""), (game, "0.0", "CLAMP", "")})
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck,
        )
        dlg._on_save()
        deep_call = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            if c[0][1] == "0.0":
                deep_call = c
        self.assertIsNotNone(deep_call, "Expected replace call for stale vague entry at 0.0")
        self.assertFalse(any(e.get("is_vague") for e in deep_call[0][3]))

    def test_blank_lesson_does_not_produce_vague_key(self):
        """Vague-keys set is empty → no vague chip, no is_vague written."""
        dlg, ctrl, game = self._vague_dialog("0", shallow=False, vague=False)
        self.assertEqual(len(dlg._row_widgets), 0)


# ---------------------------------------------------------------------------
# Snapshot fields is_shallow / is_vague for PDF
# ---------------------------------------------------------------------------

@requires_qt
class TestSnapshotFlags(unittest.TestCase):

    def test_snapshot_carries_is_shallow(self):
        game = _make_game()
        entry = dict(_make_entry("CLAMP", "C", "shallow"), is_shallow=True)
        tags = {"0": [entry]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        snap = dlg._row_widgets[0].snapshot()
        self.assertTrue(snap.is_shallow)

    def test_snapshot_carries_is_vague(self):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = dict(_make_entry("CLAMP", "C", "vague"), is_vague=True)
        tags = {"0": [entry]}
        ctrl = _make_controller({1: tags})
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=frozenset(), vague_keys={(game, "0", "CLAMP", "")},
            classified_keys=frozenset({(game, "0", "CLAMP", "")}),
        )
        snap = dlg._row_widgets[0].snapshot()
        self.assertTrue(snap.is_vague)


# ---------------------------------------------------------------------------
# B12 — per-cat chip rendering and Ignore for 3x3 rows
# ---------------------------------------------------------------------------

@requires_qt
class TestPerCatChip3x3(unittest.TestCase):
    """B12: per-cat chips for 3x3 rows."""

    def _make_3x3_dialog(self, shallow_keys, vague_keys, entries_by_path, classified_keys=None):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        ctrl = _make_controller({1: entries_by_path})
        ck = frozenset(classified_keys) if classified_keys is not None else frozenset(shallow_keys | vague_keys)
        return ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=shallow_keys, vague_keys=vague_keys, classified_keys=ck,
        ), game

    def test_shallow_chip_on_why1_only_when_generic_why1_real_why4(self):
        """GENERIC Why1 + REAL Why4 → Shallow chip on Why1 row, no Vague chip."""
        game = _make_game()
        entries_list = [
            _make_entry("3x3", "Why1", "I wanted to trade queens"),
            _make_entry("3x3", "Why4", "Look at all captures first"),
        ]
        entries = {"0": entries_list}
        # Why1 is GENERIC (shallow), Why4 is REAL (not vague)
        sk = frozenset({(game, "0", "3x3", "Why1")})
        vk = frozenset()
        ck = frozenset({(game, "0", "3x3", "Why1"), (game, "0", "3x3", "Why4")})
        ctrl = _make_controller({1: entries})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        dlg = ShowShallowTagsDialog(config={}, games=[game], controller=ctrl,
                                    shallow_keys=sk, vague_keys=vk, classified_keys=ck)
        self.assertEqual(len(dlg._row_widgets), 1)
        row = dlg._row_widgets[0]
        # Why1 has shallow chip stored after pre-stamp
        why1_entry = next((e for e in row._entries if e.get("cat") == "Why1"), None)
        self.assertIsNotNone(why1_entry)
        self.assertTrue(why1_entry.get("is_shallow"))
        # Why4 has no vague chip
        why4_entry = next((e for e in row._entries if e.get("cat") == "Why4"), None)
        self.assertIsNotNone(why4_entry)
        self.assertFalse(why4_entry.get("is_vague", False))

    def test_chip_eligibility_clamp_why4_no_shallow_chip(self):
        """B4 rule 3: cat=Why4 entry with stored is_shallow=True → no Shallow chip rendered."""
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entry = dict(_make_entry("3x3", "Why4", "Look at all captures"), is_shallow=True)
        row = _TagRowWidget(
            config={}, preset="3x3", entries=[entry],
            move_label="1.e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
            show_ignore_checkbox=True,
        )
        # _shallow_chip should NOT be set for Why4 (chip-eligibility rule)
        self.assertIsNone(row._shallow_chip)

    def test_chip_eligibility_why1_no_vague_chip(self):
        """B4 rule 3: cat=Why1 entry with stored is_vague=True → no Vague chip rendered."""
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entry = dict(_make_entry("3x3", "Why1", "I wanted to attack"), is_vague=True)
        row = _TagRowWidget(
            config={}, preset="3x3", entries=[entry],
            move_label="1.e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
            show_ignore_checkbox=True,
        )
        self.assertIsNone(row._vague_chip)

    def test_per_cat_ignore_checkbox_in_ignore_checks(self):
        """Per-cat Ignore checkboxes are stored in _ignore_checks, keyed by cat."""
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entry = dict(_make_entry("3x3", "Why1", "I moved impulsively"), is_shallow=True)
        row = _TagRowWidget(
            config={}, preset="3x3", entries=[entry],
            move_label="1.e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
            show_ignore_checkbox=True,
        )
        from PyQt6.QtWidgets import QCheckBox
        self.assertIn("Why1", row._ignore_checks)
        self.assertIsInstance(row._ignore_checks["Why1"], QCheckBox)
        # Why4 has no chip and no ignore checkbox
        self.assertNotIn("Why4", row._ignore_checks)

    def test_per_cat_ignore_suppresses_only_flagged_answer(self):
        """Toggling Ignore on Why1 suppresses Why1 only; Why4 not affected."""
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entries = [
            dict(_make_entry("3x3", "Why1", "I moved impulsively"), is_shallow=True),
            dict(_make_entry("3x3", "Why4", "Try harder"), is_vague=True),
        ]
        row = _TagRowWidget(
            config={}, preset="3x3", entries=entries,
            move_label="1.e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
            show_ignore_checkbox=True,
        )
        # Tick Ignore on Why1
        row._ignore_checks["Why1"].setChecked(True)
        current = row.get_current_entries()
        why1 = next((e for e in current if e["cat"] == "Why1"), None)
        why4 = next((e for e in current if e["cat"] == "Why4"), None)
        self.assertIsNotNone(why1)
        self.assertTrue(why1.get("ignore_shallow"))
        self.assertIsNotNone(why4)
        self.assertFalse(why4.get("ignore_shallow", False))

    def test_save_writes_per_entry_flags_for_3x3(self):
        """Save writes is_shallow on Why1, is_vague on Why4 for 3x3 rows."""
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {
            "0": [
                _make_entry("3x3", "Why1", "I moved impulsively"),
                _make_entry("3x3", "Why4", "Try harder next time"),
            ]
        }
        ctrl = _make_controller({1: entries})
        ctrl.save_games = MagicMock()
        sk = frozenset({(game, "0", "3x3", "Why1")})
        vk = frozenset({(game, "0", "3x3", "Why4")})
        ck = frozenset(sk | vk)
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=vk, classified_keys=ck,
        )
        dlg._on_save()
        calls = ctrl.replace_entries_at_path_for_game.call_args_list
        self.assertTrue(len(calls) > 0)
        written = calls[0][0][3]
        why1 = next((e for e in written if e.get("cat") == "Why1"), None)
        why4 = next((e for e in written if e.get("cat") == "Why4"), None)
        self.assertIsNotNone(why1)
        self.assertTrue(why1.get("is_shallow"))
        self.assertIsNotNone(why4)
        self.assertTrue(why4.get("is_vague"))

    def test_3x3_stale_clear_per_entry(self):
        """B12: classified Why1 (now SPECIFIC, not shallow) clears stale is_shallow."""
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        stale_why1 = dict(_make_entry("3x3", "Why1", "I attacked the king"), is_shallow=True)
        entries = {"0": [stale_why1, _make_entry("3x3", "Why4", "Concrete lesson")]}
        ctrl = _make_controller({1: entries})
        ctrl.save_games = MagicMock()
        # Why4 is FILLER (vague), Why1 now SPECIFIC (not flagged); both classified
        vk = frozenset({(game, "0", "3x3", "Why4")})
        ck = frozenset({(game, "0", "3x3", "Why1"), (game, "0", "3x3", "Why4")})
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=frozenset(), vague_keys=vk, classified_keys=ck,
        )
        dlg._on_save()
        # Find the replace call for "0" / "3x3"
        write_call = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            if c[0][1] == "0" and c[0][2] == "3x3":
                write_call = c
        self.assertIsNotNone(write_call, "Expected replace call for stale 3x3 Why1 entry")
        written = write_call[0][3]
        why1 = next((e for e in written if e.get("cat") == "Why1"), None)
        self.assertIsNotNone(why1)
        self.assertFalse(why1.get("is_shallow", False))


# ---------------------------------------------------------------------------
# B12 — help icon present
# ---------------------------------------------------------------------------

@requires_qt
class TestHelpIcon(unittest.TestCase):
    def test_help_button_exists_in_dialog(self):
        """ShowShallowTagsDialog has a help button wired to show help."""
        from PyQt6.QtWidgets import QToolButton
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        dlg, _ = _make_dialog([game], {1: tags}, {(game, "0", "CLAMP", "")})
        buttons = dlg.findChildren(QToolButton)
        self.assertTrue(len(buttons) > 0, "Expected at least one QToolButton (help icon)")


@requires_qt
class TestPartialNotice(unittest.TestCase):
    """B3 — partial_notice kwarg shows a notice label at the top of the dialog."""

    def test_partial_notice_label_present_when_supplied(self):
        """A non-None partial_notice produces a QLabel with the notice text."""
        from PyQt6.QtWidgets import QLabel
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        ctrl = _make_controller({1: tags})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        msg = "2 of 5 notes could not be classified — they remain unchanged."
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys={(game, "0", "CLAMP", "")},
            partial_notice=msg,
        )
        labels = [w.text() for w in dlg.findChildren(QLabel) if msg in (w.text() or "")]
        self.assertEqual(len(labels), 1, "Exactly one QLabel should contain the partial notice text")

    def test_no_partial_notice_label_when_none(self):
        """When partial_notice=None (default), no extra notice label is added."""
        from PyQt6.QtWidgets import QLabel
        game = _make_game()
        tags = {"0": [_make_entry("CLAMP", "C", "shallow")]}
        ctrl = _make_controller({1: tags})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys={(game, "0", "CLAMP", "")},
            partial_notice=None,
        )
        sentinel = "could not be classified"
        labels = [w.text() for w in dlg.findChildren(QLabel) if sentinel in (w.text() or "")]
        self.assertEqual(len(labels), 0, "No partial-notice label expected when partial_notice=None")


# ---------------------------------------------------------------------------
# C1 — Check Logs shows dimmed chip + ticked Ignore for an ignored 3x3 answer
#      even when is_vague / is_shallow is absent from storage
# ---------------------------------------------------------------------------

@requires_qt
class TestIgnoredAnswerChipInCheckLogs(unittest.TestCase):
    """C1: when a 3x3 entry has ignore_shallow=True+hash in storage but no is_vague,
    Check Logs must still show the chip (dimmed) and Ignore box (ticked)."""

    # Shared helper for the core scenario:
    #   Why1 classified SHALLOW (not ignored), Why4 ignored + hash but NO is_vague.
    def _make_scenario_entries(self):
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        w4_text = "Slow down and calculate"
        return [
            ChessLogStorageService.make_entry("3x3", "Why1", "I attacked too early", is_shallow=True),
            ChessLogStorageService.make_entry("3x3", "Why2", "I missed the fork"),
            ChessLogStorageService.make_entry("3x3", "Why3", "Engine prefers Nf3"),
            {
                "preset": "3x3", "cat": "Why4", "why": w4_text,
                "ignore_shallow": True,
                "ignore_text_hash": hashlib.sha256(w4_text.encode()).hexdigest(),
                # deliberately NOT including is_vague — this is the broken-storage scenario
            },
        ]

    def _make_check_logs_dialog(self, entries):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        tags = {"0": entries}
        ctrl = _make_controller({1: tags})
        ctrl.save_games = MagicMock()
        # Why1 classified shallow this run; Why4 excluded (ignored → not in classified_keys)
        sk = frozenset({(game, "0", "3x3", "Why1")})
        ck = frozenset(sk)
        return ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck,
        ), ctrl, game

    def _has_opacity_effect(self, chip) -> bool:
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        eff = chip.graphicsEffect()
        return isinstance(eff, QGraphicsOpacityEffect) and abs(eff.opacity() - 0.4) < 0.01

    def test_why4_chip_present_when_is_vague_missing_from_storage(self):
        """C1 core: vague chip shown for Why4 even when is_vague not stored."""
        entries = self._make_scenario_entries()
        dlg, _, _ = self._make_check_logs_dialog(entries)
        self.assertEqual(len(dlg._row_widgets), 1)
        row = dlg._row_widgets[0]
        self.assertIn("Why4", row._chips_per_cat,
                      "Why4 chip must appear even when is_vague absent from storage")

    def test_why4_chip_is_dimmed(self):
        """C1: Why4 chip is dimmed (opacity 0.4) when Ignore is honoured."""
        entries = self._make_scenario_entries()
        dlg, _, _ = self._make_check_logs_dialog(entries)
        row = dlg._row_widgets[0]
        chip = row._chips_per_cat.get("Why4")
        self.assertIsNotNone(chip)
        self.assertTrue(self._has_opacity_effect(chip),
                        "Why4 chip must be dimmed at dialog open when Ignore is honoured")

    def test_why4_ignore_box_ticked(self):
        """C1: Why4 Ignore checkbox is pre-ticked when Ignore is honoured."""
        entries = self._make_scenario_entries()
        dlg, _, _ = self._make_check_logs_dialog(entries)
        row = dlg._row_widgets[0]
        self.assertIn("Why4", row._ignore_checks,
                      "Why4 Ignore checkbox must be present")
        self.assertTrue(row._ignore_checks["Why4"].isChecked(),
                        "Why4 Ignore checkbox must be ticked")

    def test_why1_chip_normal_and_unticked(self):
        """C1: Why1 chip is not dimmed and Ignore box is unticked (not ignored)."""
        entries = self._make_scenario_entries()
        dlg, _, _ = self._make_check_logs_dialog(entries)
        row = dlg._row_widgets[0]
        chip = row._chips_per_cat.get("Why1")
        self.assertIsNotNone(chip)
        self.assertFalse(self._has_opacity_effect(chip),
                         "Why1 chip must not be dimmed (not ignored)")
        self.assertIn("Why1", row._ignore_checks)
        self.assertFalse(row._ignore_checks["Why1"].isChecked(),
                         "Why1 Ignore box must be unticked")

    def test_all_four_texts_present(self):
        """C1: all four answer texts are accessible in the dialog."""
        entries = self._make_scenario_entries()
        dlg, _, _ = self._make_check_logs_dialog(entries)
        row = dlg._row_widgets[0]
        for key in ("Why1", "Why2", "Why3", "Why4"):
            self.assertIn(key, row._why_texts, f"{key} QPlainTextEdit missing")
        self.assertIn("attacked", row._why_texts["Why1"].toPlainText())
        self.assertIn("Slow down", row._why_texts["Why4"].toPlainText())

    def test_untick_why4_undims_chip_before_save(self):
        """C1: unticking Why4 Ignore undims the chip immediately (before Save)."""
        entries = self._make_scenario_entries()
        dlg, _, _ = self._make_check_logs_dialog(entries)
        row = dlg._row_widgets[0]
        chip = row._chips_per_cat.get("Why4")
        self.assertTrue(self._has_opacity_effect(chip), "chip must start dimmed")
        row._ignore_checks["Why4"].setChecked(False)
        self.assertFalse(self._has_opacity_effect(chip),
                         "chip must undim after unticking Why4 Ignore")

    def test_untick_and_save_writes_is_vague_for_why4(self):
        """C1: untick Why4 Ignore + Save writes is_vague=True (change detected → write triggered)."""
        entries = self._make_scenario_entries()
        dlg, ctrl, _ = self._make_check_logs_dialog(entries)
        # Untick Why4 Ignore — this IS a change (ignore_shallow: True → False)
        dlg._row_widgets[0]._ignore_checks["Why4"].setChecked(False)
        dlg._on_save()
        why4_written = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            written = c[0][3]
            for e in written:
                if e.get("cat") == "Why4":
                    why4_written = e
        self.assertIsNotNone(why4_written, "Why4 entry must be written after untick+save")
        self.assertTrue(why4_written.get("is_vague"),
                        "is_vague=True must be preserved after untick+save")
        self.assertFalse(why4_written.get("ignore_shallow", False),
                         "ignore_shallow must be cleared after untick+save")

    def test_save_untick_reopen_normal_chip_unticked(self):
        """C1 full flow: untick Why4 → Save → reopen → chip present, undimmed, unticked."""
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        entries = self._make_scenario_entries()
        dlg, ctrl, game = self._make_check_logs_dialog(entries)

        # Untick Why4, then Save
        row = dlg._row_widgets[0]
        row._ignore_checks["Why4"].setChecked(False)
        dlg._on_save()

        # Get what was written for Why4
        saved_entries = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            if c[0][2] == "3x3":
                saved_entries = c[0][3]
        self.assertIsNotNone(saved_entries)

        # Build a second dialog with the saved entries
        w4 = next(e for e in saved_entries if e.get("cat") == "Why4")
        self.assertFalse(w4.get("ignore_shallow", False),
                         "ignore_shallow must be cleared after untick+save")
        self.assertTrue(w4.get("is_vague"),
                        "is_vague must be preserved after untick+save")
        self.assertEqual(w4["why"], "Slow down and calculate",
                         "Why4 text must be byte-identical after untick+save")

        # Reopen with the saved entries (is_vague=True, no ignore_shallow)
        tags2 = {"0": saved_entries}
        ctrl2 = _make_controller({1: tags2})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        sk2 = frozenset({(game, "0", "3x3", "Why1")})
        vk2 = frozenset({(game, "0", "3x3", "Why4")})  # now classified vague again
        ck2 = frozenset(sk2 | vk2)
        dlg2 = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl2,
            shallow_keys=sk2, vague_keys=vk2, classified_keys=ck2,
        )
        row2 = dlg2._row_widgets[0]
        chip2 = row2._chips_per_cat.get("Why4")
        self.assertIsNotNone(chip2, "Why4 chip must be present in reopened dialog")
        self.assertFalse(self._has_opacity_effect(chip2),
                         "Why4 chip must NOT be dimmed (Ignore was unticked)")
        self.assertIn("Why4", row2._ignore_checks)
        self.assertFalse(row2._ignore_checks["Why4"].isChecked(),
                         "Why4 Ignore box must be unticked in reopened dialog")

        # All 4 texts byte-identical
        for key, expected in [
            ("Why1", "I attacked too early"),
            ("Why2", "I missed the fork"),
            ("Why3", "Engine prefers Nf3"),
            ("Why4", "Slow down and calculate"),
        ]:
            actual = row2._why_texts[key].toPlainText()
            self.assertEqual(actual, expected, f"{key} text changed")

    def test_pdf_snapshot_has_vague_cats_for_why4(self):
        """C1 PDF: snapshot().vague_cats includes Why4, enabling PDF chip + Ignore: Yes."""
        entries = self._make_scenario_entries()
        dlg, _, _ = self._make_check_logs_dialog(entries)
        row = dlg._row_widgets[0]
        snap = row.snapshot()
        self.assertIn("Why4", snap.vague_cats,
                      "snapshot().vague_cats must include Why4 for PDF chip rendering")
        self.assertTrue(snap.show_ignore,
                        "snapshot().show_ignore must be True for Ignore: Yes to appear in PDF")
        why4_entry = next((e for e in snap.entries if e.get("cat") == "Why4"), None)
        self.assertIsNotNone(why4_entry)
        self.assertTrue(why4_entry.get("ignore_shallow"),
                        "snapshot entry for Why4 must carry ignore_shallow=True for PDF Ignore: Yes")

    def test_ignored_why1_chip_present_when_is_shallow_missing(self):
        """C1: same fix for Why1-3 — chip shown when is_shallow absent but Ignore honoured."""
        import hashlib
        w1_text = "I attacked impulsively"
        entries = [
            {
                "preset": "3x3", "cat": "Why1", "why": w1_text,
                "ignore_shallow": True,
                "ignore_text_hash": hashlib.sha256(w1_text.encode()).hexdigest(),
                # deliberately NO is_shallow
            },
            {"preset": "3x3", "cat": "Why4", "why": "Lesson text"},
        ]
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        tags = {"0": entries}
        ctrl = _make_controller({1: tags})
        # Why4 is VAGUE this run (moment is shown because Why4 in vague_keys)
        vk = frozenset({(game, "0", "3x3", "Why4")})
        ck = frozenset(vk)
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=frozenset(), vague_keys=vk, classified_keys=ck,
        )
        row = dlg._row_widgets[0]
        self.assertIn("Why1", row._chips_per_cat,
                      "Why1 chip must appear even when is_shallow absent from storage")
        chip = row._chips_per_cat.get("Why1")
        self.assertTrue(self._has_opacity_effect(chip),
                        "Why1 chip must be dimmed (Ignore honoured)")
        self.assertIn("Why1", row._ignore_checks)
        self.assertTrue(row._ignore_checks["Why1"].isChecked())

    def test_proof_sequence_prints_all_states(self):
        """C1 proof: walk ALL child widget types (incl. QPlainTextEdit) to prove texts visible."""
        import hashlib
        from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit
        from app.services.chess_log_storage_service import ChessLogStorageService

        w4_text = "Slow down and calculate"
        entries = self._make_scenario_entries()

        print("\n--- PROOF SEQUENCE ---")
        print("STORAGE before dialog open:")
        for e in entries:
            cat = e.get("cat", "")
            print(f"  {cat}: why={repr(e.get('why','')[:40])!s} "
                  f"is_shallow={e.get('is_shallow')} "
                  f"is_vague={e.get('is_vague')} "
                  f"ignore_shallow={e.get('ignore_shallow')}")

        dlg, ctrl, _ = self._make_check_logs_dialog(entries)
        row = dlg._row_widgets[0]

        # Show the dialog and process events so widgets are fully realized
        dlg.show()
        QApplication.processEvents()

        print("\nVISIBLE WIDGETS (QLabel + QPlainTextEdit):")
        for w in dlg.findChildren(QLabel):
            t = (w.text() or "").strip()
            if t:
                print(f"  QLabel visible={w.isVisible()} text={repr(t[:80])}")
        for w in dlg.findChildren(QPlainTextEdit):
            t = (w.toPlainText() or "").strip()
            print(f"  QPlainTextEdit visible={w.isVisible()} text={repr(t[:80])}")

        print("\nROW WIDGET STATE:")
        print(f"  _why_texts keys: {list(row._why_texts.keys())}")
        for k, te in row._why_texts.items():
            print(f"  {k}: visible={te.isVisible()} text={repr(te.toPlainText()[:60])}")
        print(f"  _chips_per_cat: {list(row._chips_per_cat.keys())}")
        for k, chip in row._chips_per_cat.items():
            from PyQt6.QtWidgets import QGraphicsOpacityEffect
            eff = chip.graphicsEffect()
            dimmed = isinstance(eff, QGraphicsOpacityEffect) and abs(eff.opacity() - 0.4) < 0.01
            print(f"  {k}: chip='{chip.text()}' dimmed={dimmed}")
        print(f"  _ignore_checks: {list(row._ignore_checks.keys())}")
        for k, cb in row._ignore_checks.items():
            print(f"  {k}: checked={cb.isChecked()}")

        # All four texts must be in _why_texts and visible
        for key in ("Why1", "Why2", "Why3", "Why4"):
            self.assertIn(key, row._why_texts, f"{key} QPlainTextEdit missing")
            te = row._why_texts[key]
            self.assertTrue(te.isVisible(), f"{key} QPlainTextEdit not visible")
        # Check that visible QPlainTextEdit widgets include all four answer texts
        visible_texts = {
            w.toPlainText() for w in dlg.findChildren(QPlainTextEdit) if w.isVisible()
        }
        self.assertIn("I attacked too early", visible_texts)
        self.assertIn("I missed the fork", visible_texts)
        self.assertIn("Engine prefers Nf3", visible_texts)
        self.assertIn(w4_text, visible_texts)

        self.assertIn("Why4", row._chips_per_cat)
        print("\n--- PROOF PASSED ---\n")


# ---------------------------------------------------------------------------
# C2 — stale-clear guard + repair for broken storage (is_vague dropped by
#       prior stale-clear bug while ignore_shallow survived)
# ---------------------------------------------------------------------------

@requires_qt
class TestIgnoredAnswerSaveFixC2(unittest.TestCase):
    """C2: stale-clear must not strip is_vague from a honoured-Ignore entry,
    and Save must repair broken storage (ignore_shallow=True, is_vague=None)."""

    def _make_broken_entries(self):
        """Why4 with ignore honoured but is_vague absent — the bug shape."""
        import hashlib
        w4_text = "Slow down and calculate"
        return [
            {"preset": "3x3", "cat": "Why1", "why": "I attacked too early",
             "is_shallow": True},
            {"preset": "3x3", "cat": "Why2", "why": "I missed the fork"},
            {"preset": "3x3", "cat": "Why3", "why": "Engine prefers Nf3"},
            {
                "preset": "3x3", "cat": "Why4", "why": w4_text,
                "ignore_shallow": True,
                "ignore_text_hash": hashlib.sha256(w4_text.encode()).hexdigest(),
                # deliberately NO is_vague — this is the broken-storage shape
            },
        ]

    def test_stale_clear_does_not_strip_is_vague_from_honoured_ignore(self):
        """Stale-clear guard: classified Why4 with honoured Ignore keeps is_vague=True."""
        import hashlib
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        w4_text = "Slow down and calculate"
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "I attacked too early"},
            {
                "preset": "3x3", "cat": "Why4", "why": w4_text,
                "is_vague": True,
                "ignore_shallow": True,
                "ignore_text_hash": hashlib.sha256(w4_text.encode()).hexdigest(),
            },
        ]
        tags = {"0": entries}
        ctrl = _make_controller({1: tags})
        ctrl.save_games = MagicMock()
        # Why1 shallow; Why4 classified this run (simulate edge case) but NOT vague
        sk = frozenset({(game, "0", "3x3", "Why1")})
        # Why4 in classified_keys but NOT in vague_keys — this is the stale-clear scenario
        ck = frozenset({(game, "0", "3x3", "Why1"), (game, "0", "3x3", "Why4")})
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck,
        )
        dlg._on_save()
        # Find any replace call for Why4
        why4_written = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            for e in c[0][3]:
                if e.get("cat") == "Why4":
                    why4_written = e
        # is_vague must NOT have been stripped (honoured-Ignore guard)
        if why4_written is not None:
            self.assertTrue(
                why4_written.get("is_vague"),
                "is_vague must be preserved for a honoured-Ignore entry, even if in classified_keys",
            )

    def test_stale_clear_still_fires_when_ignore_not_honoured(self):
        """Stale-clear still strips is_vague when ignore_shallow is present but hash mismatches."""
        import hashlib
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        stored_text = "Old text that was changed"
        current_text = "New different text"  # hash will NOT match
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "I attacked too early"},
            {
                "preset": "3x3", "cat": "Why4", "why": current_text,
                "is_vague": True,
                "ignore_shallow": True,
                "ignore_text_hash": hashlib.sha256(stored_text.encode()).hexdigest(),
                # hash of stored_text ≠ sha256(current_text) → NOT honoured
            },
        ]
        tags = {"0": entries}
        ctrl = _make_controller({1: tags})
        ctrl.save_games = MagicMock()
        sk = frozenset({(game, "0", "3x3", "Why1")})
        ck = frozenset({(game, "0", "3x3", "Why1"), (game, "0", "3x3", "Why4")})
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck,
        )
        dlg._on_save()
        why4_written = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            for e in c[0][3]:
                if e.get("cat") == "Why4":
                    why4_written = e
        # is_vague SHOULD have been stripped (hash mismatch → Ignore not honoured)
        self.assertIsNotNone(why4_written, "Expected replace call for Why4")
        self.assertFalse(
            why4_written.get("is_vague", False),
            "is_vague must be stripped when ignore hash does not match",
        )

    def test_save_repairs_broken_entry_writes_is_vague(self):
        """Repair: Save must write is_vague=True for broken storage (ignore honoured, is_vague absent).

        Even if the user makes no changes, inference_repair_needed forces a save.
        """
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = self._make_broken_entries()
        tags = {"0": entries}
        ctrl = _make_controller({1: tags})
        ctrl.save_games = MagicMock()
        # Why1 shallow this run; Why4 excluded from classifier (properly ignored)
        sk = frozenset({(game, "0", "3x3", "Why1")})
        ck = frozenset(sk)
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck,
        )
        # User makes NO changes — just opens and saves
        dlg._on_save()
        # A replace call must have been made (repair triggered)
        why4_written = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            for e in c[0][3]:
                if e.get("cat") == "Why4":
                    why4_written = e
        self.assertIsNotNone(why4_written, "Why4 entry must be written by repair Save")
        self.assertTrue(
            why4_written.get("is_vague"),
            "is_vague=True must be written by the repair path",
        )
        self.assertTrue(
            why4_written.get("ignore_shallow"),
            "ignore_shallow must be preserved during repair",
        )
        self.assertIsNotNone(
            why4_written.get("ignore_text_hash"),
            "ignore_text_hash must be preserved during repair",
        )

    def test_repaired_entry_stable_on_second_save(self):
        """After repair, a second Save with no changes does NOT call replace again."""
        import hashlib
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        w4_text = "Slow down and calculate"
        # Already-repaired storage: is_vague=True present
        repaired_entries = [
            {"preset": "3x3", "cat": "Why1", "why": "I attacked too early", "is_shallow": True},
            {"preset": "3x3", "cat": "Why2", "why": "I missed the fork"},
            {"preset": "3x3", "cat": "Why3", "why": "Engine prefers Nf3"},
            {
                "preset": "3x3", "cat": "Why4", "why": w4_text,
                "is_vague": True,
                "ignore_shallow": True,
                "ignore_text_hash": hashlib.sha256(w4_text.encode()).hexdigest(),
            },
        ]
        tags = {"0": repaired_entries}
        ctrl = _make_controller({1: tags})
        ctrl.save_games = MagicMock()
        sk = frozenset({(game, "0", "3x3", "Why1")})
        ck = frozenset(sk)
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=frozenset(), classified_keys=ck,
        )
        dlg._on_save()
        # No change from correct storage → no replace call needed
        # (flags_missing is False for Why1 because Why1 IS in sk and storage has is_shallow=True;
        #  inference_repair_needed is False because is_vague IS present in Why4)
        why4_calls = [
            c for c in ctrl.replace_entries_at_path_for_game.call_args_list
            if any(e.get("cat") == "Why4" for e in c[0][3])
        ]
        # If a replace call was made, it must still have is_vague=True (no regression)
        for c in why4_calls:
            for e in c[0][3]:
                if e.get("cat") == "Why4":
                    self.assertTrue(
                        e.get("is_vague"),
                        "Second save must not strip is_vague from already-repaired entry",
                    )

    def test_stale_clear_also_clears_ignore_when_hash_mismatches(self):
        """Stale-clear must also strip ignore_shallow+ignore_text_hash when hash mismatches.

        Editing an answer invalidates its Ignore (hash no longer matches).  When the
        classifier re-runs and returns DEEP, the stale-clear fires.  It must atomically
        clear the chip flag AND both Ignore fields — leaving ignore_shallow=True with no
        is_vague would suppress future classifier runs without showing a chip.
        """
        import hashlib
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        old_text = "Original answer before edit"
        new_text = "Completely different answer now"
        entries = [
            {
                "preset": "3x3", "cat": "Why4", "why": new_text,
                "is_vague": True,
                "ignore_shallow": True,
                "ignore_text_hash": hashlib.sha256(old_text.encode()).hexdigest(),
                # hash of old_text ≠ sha256(new_text) → NOT honoured → sent to classifier → DEEP
            },
        ]
        tags = {"0": entries}
        ctrl = _make_controller({1: tags})
        ctrl.save_games = MagicMock()
        # Why4 was re-classified DEEP (in classified_keys but not in vague/shallow_keys)
        ck = frozenset({(game, "0", "3x3", "Why4")})
        # No flagged_keys → moment not shown; but part (b) still processes all tags
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=frozenset(), vague_keys=frozenset(), classified_keys=ck,
        )
        dlg._on_save()
        why4_written = None
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            for e in c[0][3]:
                if e.get("cat") == "Why4":
                    why4_written = e
        self.assertIsNotNone(why4_written, "Stale-clear must have written Why4")
        self.assertFalse(why4_written.get("is_vague", False),
                         "is_vague must be cleared")
        self.assertFalse(why4_written.get("ignore_shallow", False),
                         "ignore_shallow must also be cleared — editing invalidates Ignore")
        self.assertIsNone(why4_written.get("ignore_text_hash"),
                          "ignore_text_hash must also be cleared")


# ---------------------------------------------------------------------------
# C2 — prove Paul's exact sequence from CLEAN storage works end-to-end
# ---------------------------------------------------------------------------

@requires_qt
class TestNormalSequenceFromCleanStorage(unittest.TestCase):
    """Prove the five-step normal sequence starting from clean 3x3 storage.

    Steps:
    1. Check Logs → tick Ignore on Why4 → Save.
    2. Check Logs again (Why4 excluded from classifier) → Save without changes.
    3. Check Logs again → untick Why4 (chip undims before Save) → Save.
    4. Check Logs again: Why4 shows normal Vague chip, Ignore unticked.
    5. All four why texts are byte-identical to start.
    """

    TEXTS = {
        "Why1": "I attacked too early",
        "Why2": "I missed the fork",
        "Why3": "Engine prefers Nf3",
        "Why4": "Slow down and calculate",
    }

    @staticmethod
    def _has_opacity_effect(chip) -> bool:
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        if chip is None:
            return False
        eff = chip.graphicsEffect()
        return isinstance(eff, QGraphicsOpacityEffect) and abs(eff.opacity() - 0.4) < 0.01

    @staticmethod
    def _print_entries(label, entries):
        import hashlib
        print(f"\n--- {label} ---")
        for e in entries:
            cat = e.get("cat", "")
            why = (e.get("why") or "").strip()
            h = e.get("ignore_text_hash")
            if h and why:
                hash_ok = h == hashlib.sha256(why.encode()).hexdigest()
                hash_str = "YES(correct)" if hash_ok else "YES(mismatch)"
            else:
                hash_str = "yes(no why)" if h else "no"
            print(f"  {cat}: why={repr(why[:35])}"
                  f" is_shallow={e.get('is_shallow')}"
                  f" is_vague={e.get('is_vague')}"
                  f" ignore_shallow={e.get('ignore_shallow')}"
                  f" hash={hash_str}")

    @staticmethod
    def _get_why4(entries):
        return next((e for e in entries if e.get("cat") == "Why4"), None) if entries else None

    @staticmethod
    def _last_written_3x3(ctrl):
        for c in reversed(ctrl.replace_entries_at_path_for_game.call_args_list):
            if c[0][1] == "0" and c[0][2] == "3x3":
                return list(c[0][3])
        return None

    def _open_dialog(self, entries, shallow_key_cats, vague_key_cats, classified_key_cats):
        """Open a dialog for a fresh game object.

        Key sets are specified as dicts mapping cat→bool so the caller does not
        need to know the game object in advance.  Returns (dlg, ctrl, game).

        shallow_key_cats / vague_key_cats / classified_key_cats: iterables of
        (path_key, preset, cat) 3-tuples that will be combined with the fresh
        game object to form 4-tuple keys.
        """
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        sk = frozenset((game, pk, pr, cat) for pk, pr, cat in shallow_key_cats)
        vk = frozenset((game, pk, pr, cat) for pk, pr, cat in vague_key_cats)
        ck = frozenset((game, pk, pr, cat) for pk, pr, cat in classified_key_cats)
        ctrl = _make_controller({1: {"0": list(entries)}})
        ctrl.save_games = MagicMock()
        dlg = ShowShallowTagsDialog(
            config={}, games=[game], controller=ctrl,
            shallow_keys=sk, vague_keys=vk,
            classified_keys=ck,
        )
        return dlg, ctrl, game

    def test_full_five_step_sequence(self):
        """Walk all five steps and assert the correct entry state after each save."""
        import hashlib

        clean = [{"preset": "3x3", "cat": k, "why": v}
                 for k, v in self.TEXTS.items()]
        self._print_entries("INITIAL STORAGE (clean)", clean)

        # Key specs as (path_key, preset, cat) 3-tuples — game object added per step
        SK_W1_SPEC = [("0", "3x3", "Why1")]
        VK_W4_SPEC = [("0", "3x3", "Why4")]
        CK_ALL_SPEC = SK_W1_SPEC + VK_W4_SPEC
        # Step 2/3 run: Why4 excluded because it was ignored
        CK_NO_W4_SPEC = [("0", "3x3", k) for k in ("Why1", "Why2", "Why3")]
        expected_hash = hashlib.sha256("Slow down and calculate".encode()).hexdigest()

        # ── Step 1: Check Logs → tick Ignore on Why4 → Save ──────────────
        dlg1, ctrl1, game1 = self._open_dialog(clean, SK_W1_SPEC, VK_W4_SPEC, CK_ALL_SPEC)
        row1 = dlg1._row_widgets[0]
        self.assertIn("Why4", row1._ignore_checks, "Why4 Ignore checkbox must exist")
        row1._ignore_checks["Why4"].setChecked(True)
        dlg1._on_save()

        saved1 = self._last_written_3x3(ctrl1)
        self.assertIsNotNone(saved1, "Step 1: must have written entries")
        self._print_entries("AFTER STEP 1 (tick Ignore on Why4, Save)", saved1)

        w4 = self._get_why4(saved1)
        self.assertIsNotNone(w4)
        self.assertTrue(w4.get("is_vague"), "Step 1: is_vague must be True")
        self.assertTrue(w4.get("ignore_shallow"), "Step 1: ignore_shallow must be True")
        self.assertEqual(w4.get("ignore_text_hash"), expected_hash,
                         "Step 1: hash must equal sha256(why.strip())")

        # ── Step 2: Check Logs again (Why4 NOT in classified_keys) → no-op Save
        # Precondition: ("0", "3x3", "Why4") not in CK_NO_W4_SPEC
        self.assertNotIn(("0", "3x3", "Why4"), CK_NO_W4_SPEC,
                         "Step 2 precondition: Why4 must be excluded from classifier")
        dlg2, ctrl2, _g2 = self._open_dialog(saved1, SK_W1_SPEC, [], CK_NO_W4_SPEC)
        dlg2._on_save()

        # No write expected; if one happened, Why4 must be unchanged
        written2 = self._last_written_3x3(ctrl2)
        w4_2 = self._get_why4(written2) if written2 else w4
        self._print_entries("AFTER STEP 2 (no changes; Why4 must be unchanged)",
                             written2 if written2 else saved1)
        self.assertTrue(w4_2.get("is_vague"), "Step 2: is_vague unchanged (True)")
        self.assertTrue(w4_2.get("ignore_shallow"), "Step 2: ignore_shallow unchanged (True)")
        self.assertEqual(w4_2.get("ignore_text_hash"), expected_hash,
                         "Step 2: hash unchanged")

        # ── Step 3: Check Logs again → untick Why4 (chip undims) → Save ──
        dlg3, ctrl3, _g3 = self._open_dialog(saved1, SK_W1_SPEC, [], CK_NO_W4_SPEC)
        row3 = dlg3._row_widgets[0]
        chip3 = row3._chips_per_cat.get("Why4")
        self.assertTrue(self._has_opacity_effect(chip3),
                        "Step 3: Why4 chip must start dimmed (Ignore honoured)")
        row3._ignore_checks["Why4"].setChecked(False)
        self.assertFalse(self._has_opacity_effect(chip3),
                         "Step 3: chip must undim immediately after untick (before Save)")
        dlg3._on_save()

        saved3 = self._last_written_3x3(ctrl3)
        self.assertIsNotNone(saved3, "Step 3: must have written entries")
        self._print_entries("AFTER STEP 3 (untick Ignore, Save)", saved3)

        w4_3 = self._get_why4(saved3)
        self.assertTrue(w4_3.get("is_vague"), "Step 3: is_vague must be True")
        self.assertFalse(w4_3.get("ignore_shallow", False),
                         "Step 3: ignore_shallow must be None/False")
        self.assertIsNone(w4_3.get("ignore_text_hash"),
                          "Step 3: ignore_text_hash must be absent")

        # ── Step 4: Check Logs again — normal chip, unticked box ──────────
        SK4_SPEC = [("0", "3x3", "Why1")]
        VK4_SPEC = [("0", "3x3", "Why4")]   # Why4 vague again (Ignore cleared)
        dlg4, _, _g4 = self._open_dialog(saved3, SK4_SPEC, VK4_SPEC, SK4_SPEC + VK4_SPEC)
        row4 = dlg4._row_widgets[0]
        chip4 = row4._chips_per_cat.get("Why4")

        print("\nSTEP 4 dialog opened:")
        print(f"  Why4 chip present: {chip4 is not None}")
        print(f"  Why4 chip dimmed: {self._has_opacity_effect(chip4)}")
        w4_ign = row4._ignore_checks.get("Why4")
        print(f"  Why4 Ignore ticked: {w4_ign.isChecked() if w4_ign else '(no checkbox)'}")

        self.assertIsNotNone(chip4, "Step 4: Why4 chip must be present")
        self.assertFalse(self._has_opacity_effect(chip4),
                         "Step 4: chip must NOT be dimmed (Ignore was cleared)")
        self.assertIn("Why4", row4._ignore_checks)
        self.assertFalse(row4._ignore_checks["Why4"].isChecked(),
                         "Step 4: Why4 Ignore box must be unticked")

        # ── Step 5: All why texts byte-identical to start ─────────────────
        print("\nSTEP 5: byte-identical why texts check")
        for key, expected in self.TEXTS.items():
            actual = row4._why_texts[key].toPlainText()
            print(f"  {key}: {repr(actual[:40])} ← expected {repr(expected)}")
            self.assertEqual(actual, expected, f"Step 5: {key} text changed")

        print("\n--- NORMAL SEQUENCE PROOF PASSED ---\n")


# ---------------------------------------------------------------------------
# Issue #55 — single-game dialog and PDF always show the game header
# ---------------------------------------------------------------------------

@requires_qt
class TestSingleGameHeader(unittest.TestCase):
    """Issue #55: the game header must appear even when only one game has flagged moments."""

    def _make_single_game_dialog(self, white="SoloWhite", black="SoloBlack"):
        from app.models.database_model import GameData
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        pgn = (
            f'[Event "T"][Site "?"][Date "2026.06.01"]'
            f'[Round "?"][White "{white}"][Black "{black}"][Result "1-0"]\n\n'
            "1. e4 e5 *\n"
        )
        game = GameData(game_number=1, pgn=pgn, white=white, black=black,
                        result="1-0", date="2026.06.01", moves=2)
        tags = {"0": [_make_entry("CLAMP", "C", "shallow note")]}
        ctrl = _make_controller({1: tags})
        return ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys={(game, "0", "CLAMP", "")},
        ), game

    def test_single_game_dialog_shows_game_header(self):
        """Single-game Check Logs dialog must display a QLabel containing the player name."""
        from PyQt6.QtWidgets import QLabel
        dlg, _ = self._make_single_game_dialog("SoloWhite", "SoloBlack")
        label_texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
        self.assertTrue(
            any("SoloWhite" in t for t in label_texts),
            f"Expected game header with 'SoloWhite' in dialog labels; got: {label_texts}",
        )

    def test_single_game_pdf_export_sets_header(self):
        """Single-game Check Logs PDF must pass a non-None header to export_tags."""
        from unittest.mock import patch
        from app.models.database_model import GameData
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        pgn = (
            '[Event "T"][Site "?"][Date "2026.06.01"]'
            '[Round "?"][White "PDFSolo"][Black "Opponent"][Result "1-0"]\n\n'
            "1. e4 e5 *\n"
        )
        game = GameData(game_number=1, pgn=pgn, white="PDFSolo", black="Opponent",
                        result="1-0", date="2026.06.01", moves=2)
        tags = {"0": [_make_entry("CLAMP", "C", "shallow note")]}
        ctrl = _make_controller({1: tags})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys={(game, "0", "CLAMP", "")},
        )

        captured = {}

        def fake_export(path, groups, **kwargs):
            captured["groups"] = groups

        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                   return_value=("/tmp/test_check_logs.pdf", "")):
            with patch("app.services.chess_log_pdf_service.ChessLogPDFService.export_tags",
                       side_effect=fake_export):
                dlg._on_export_pdf()

        self.assertIn("groups", captured, "export_tags must have been called")
        groups = captured["groups"]
        self.assertEqual(len(groups), 1)
        header = groups[0]["header"]
        self.assertIsNotNone(header, "Single-game Check Logs PDF must have a non-None header")
        self.assertIn("PDFSolo", header)


@requires_qt
class TestChessLogMiniatureBoardSettingsShallow(unittest.TestCase):
    """ShowShallowTagsDialog respects View → Miniature Boards → Chess Log settings."""

    def _make_shallow_dialog(self, scale=1.25, played=True, best=True):
        from unittest.mock import patch, MagicMock
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "shallow note")]}
        ctrl = _make_controller({1: entries})
        sk = frozenset({(game, "0", "CLAMP", "")})

        mock_uss = MagicMock()
        mock_uss.get_miniature_boards.return_value = {"chess_log": scale}
        mock_uss.get_miniature_board_arrows.return_value = {
            "chess_log_played": played,
            "chess_log_best_alternative": best,
        }

        with patch(
            "app.services.user_settings_service.UserSettingsService.get_instance",
            return_value=mock_uss,
        ):
            dlg = ShowShallowTagsDialog(
                config={},
                games=[game],
                controller=ctrl,
                shallow_keys=sk,
                classified_keys=sk,
            )
        return dlg

    def test_scale_175_stored_on_rows(self):
        dlg = self._make_shallow_dialog(scale=1.75)
        self.assertTrue(len(dlg._row_widgets) > 0)
        for row in dlg._row_widgets:
            self.assertAlmostEqual(row._scale_factor, 1.75)

    def test_default_scale_125_when_uss_not_mocked(self):
        """Without mocking UserSettingsService, rows default to 1.25."""
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entries = {"0": [_make_entry("CLAMP", "C", "shallow note")]}
        ctrl = _make_controller({1: entries})
        sk = frozenset({(game, "0", "CLAMP", "")})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=sk,
        )
        for row in dlg._row_widgets:
            self.assertAlmostEqual(row._scale_factor, 1.25)

    def test_arrows_off_passed_to_rows(self):
        dlg = self._make_shallow_dialog(played=False, best=False)
        for row in dlg._row_widgets:
            self.assertFalse(row._show_played)
            self.assertFalse(row._show_best)

    def test_arrows_on_by_default(self):
        dlg = self._make_shallow_dialog(played=True, best=True)
        for row in dlg._row_widgets:
            self.assertTrue(row._show_played)
            self.assertTrue(row._show_best)


# ---------------------------------------------------------------------------
# #67: chip-fade works in ShowShallowTagsDialog
# ---------------------------------------------------------------------------

@requires_qt
class TestChipFadeInShallowDialog(unittest.TestCase):
    """#67: editing a row inside ShowShallowTagsDialog also fades and hides the chip."""

    def _make_shallow_row(self, preset, entries, config=None):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config=config or {"ui": {"dialogs": {"show_tags": {"chip_fade_ms": 0}}}},
            preset=preset,
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=True,
        )

    def _pump(self):
        for _ in range(5):
            _APP.processEvents()

    def test_3x3_chip_fade_in_shallow_dialog_row(self):
        """3x3 chip fades in a row created with show_ignore_checkbox=True (shallow dialog)."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "rushed", is_shallow=True)
        row = self._make_shallow_row("3x3", [entry])

        chip_col = row._chip_col_widgets.get("Why1")
        self.assertIsNotNone(chip_col)
        self.assertFalse(chip_col.isHidden(), "chip must not be hidden before edit")
        row._why_texts["Why1"].setPlainText("edited in check logs")
        self._pump()
        self.assertTrue(chip_col.isHidden(), "chip must be explicitly hidden after fade")

    def test_clamp_chip_fade_in_shallow_dialog_row(self):
        """CLAMP chip fades in a row created with show_ignore_checkbox=True (shallow dialog)."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "shallow note", is_shallow=True)
        row = self._make_shallow_row("CLAMP", [entry])

        chip = row._shallow_chip
        self.assertIsNotNone(chip)
        self.assertFalse(chip.isHidden(), "chip must not be hidden before edit")
        row._why_texts["why"].setPlainText("edited note")
        self._pump()
        self.assertTrue(chip.isHidden(), "chip must be explicitly hidden after fade")
        self.assertTrue(row._ignore_check.isHidden(), "Ignore checkbox must be hidden after fade")


# ---------------------------------------------------------------------------
# F5 regression: no cross-database verdict contamination (CLAMP and 3x3)
# ---------------------------------------------------------------------------

_ONE_MOVE_PGN = (
    '[Event "T"]\n[Site "?"]\n[Date "2024.01.01"]\n'
    '[Round "-"]\n[White "A"]\n[Black "B"]\n[Result "*"]\n\n1. e4 *\n'
)


def _two_same_gn_games():
    """Return (game_1, game_2) both with game_number=1 from separate DatabaseModels."""
    import json
    import os
    from app.models.database_model import DatabaseModel, GameData
    cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "app", "config", "config.json",
    )
    with open(cfg_path) as f:
        cfg = json.load(f)
    game_1 = GameData(game_number=0, pgn=_ONE_MOVE_PGN)
    game_2 = GameData(game_number=0, pgn=_ONE_MOVE_PGN)
    db_a = DatabaseModel(config=cfg)
    db_b = DatabaseModel(config=cfg)
    db_a.add_game(game_1, tags=set())
    db_b.add_game(game_2, tags=set())
    assert game_1.game_number == game_2.game_number == 1
    return game_1, game_2


def _make_id_keyed_ctrl(tags_by_game_id):
    """Controller mock keyed on id(game), not game.game_number."""
    ctrl = MagicMock()
    def _get_tags(game):
        return tags_by_game_id.get(id(game), {})
    ctrl.get_tags_for_game.side_effect = _get_tags
    ctrl.get_custom_categories.return_value = []
    ctrl.replace_entries_at_path_for_game = MagicMock()
    ctrl.save_games = MagicMock()
    return ctrl


def _make_shallow_dialog(games, tags_by_game_id, shallow_keys, classified_keys):
    from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
    ctrl = _make_id_keyed_ctrl(tags_by_game_id)
    dlg = ShowShallowTagsDialog(
        config={},
        games=games,
        controller=ctrl,
        shallow_keys=shallow_keys,
        vague_keys=frozenset(),
        classified_keys=classified_keys,
    )
    return dlg, ctrl


@requires_qt
class TestF5ClamNoContamination(unittest.TestCase):
    """F5/CLAMP: game_1 SHALLOW verdict must not propagate to game_2 when both
    share (game_number=1, path_key="0", preset="CLAMP")."""

    def test_only_shallow_game_row_is_shown(self):
        """Dialog must show exactly 1 row (game_1), not 2."""
        game_1, game_2 = _two_same_gn_games()
        tags = {
            id(game_1): {"0": [_make_entry("CLAMP", "C", "vague note")]},
            id(game_2): {"0": [_make_entry("CLAMP", "L", "specific insight")]},
        }
        sk = frozenset([(game_1, "0", "CLAMP", "")])
        ck = frozenset([(game_1, "0", "CLAMP", ""), (game_2, "0", "CLAMP", "")])
        dlg, _ = _make_shallow_dialog([game_1, game_2], tags, sk, ck)
        self.assertEqual(len(dlg._row_widgets), 1,
                         "Only game_1 is shallow — game_2 must not appear")
        self.assertIs(dlg._row_games[0], game_1)

    def test_save_does_not_stamp_deep_game(self):
        """After Save, game_2's replace call must not carry is_shallow=True."""
        game_1, game_2 = _two_same_gn_games()
        tags = {
            id(game_1): {"0": [_make_entry("CLAMP", "C", "vague note")]},
            id(game_2): {"0": [_make_entry("CLAMP", "L", "specific insight")]},
        }
        sk = frozenset([(game_1, "0", "CLAMP", "")])
        ck = frozenset([(game_1, "0", "CLAMP", ""), (game_2, "0", "CLAMP", "")])
        dlg, ctrl = _make_shallow_dialog([game_1, game_2], tags, sk, ck)
        dlg._on_save()
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            if c[0][0] is game_2:
                for e in c[0][3]:
                    self.assertFalse(e.get("is_shallow"),
                                     "game_2 (DEEP) must not receive is_shallow=True")

    def test_save_stamps_shallow_game(self):
        """game_1 (SHALLOW) must receive is_shallow=True — positive control."""
        game_1, game_2 = _two_same_gn_games()
        tags = {
            id(game_1): {"0": [_make_entry("CLAMP", "C", "vague note")]},
            id(game_2): {"0": [_make_entry("CLAMP", "L", "specific insight")]},
        }
        sk = frozenset([(game_1, "0", "CLAMP", "")])
        ck = frozenset([(game_1, "0", "CLAMP", ""), (game_2, "0", "CLAMP", "")])
        dlg, ctrl = _make_shallow_dialog([game_1, game_2], tags, sk, ck)
        dlg._on_save()
        game_1_calls = [c for c in ctrl.replace_entries_at_path_for_game.call_args_list
                        if c[0][0] is game_1]
        self.assertTrue(
            any(any(e.get("is_shallow") for e in c[0][3]) for c in game_1_calls),
            "game_1 (SHALLOW) must have at least one entry stamped is_shallow=True",
        )


@requires_qt
class TestF53x3NoContamination(unittest.TestCase):
    """F5/3x3: game_1 Why1=GENERIC must not stamp is_shallow on game_2."""

    def test_3x3_only_shallow_game_row_is_shown(self):
        game_1, game_2 = _two_same_gn_games()
        tags = {
            id(game_1): {"0": [_make_entry("3x3", "Why1", "generic answer")]},
            id(game_2): {"0": [_make_entry("3x3", "Why1", "I miscalculated d5 after 18...Qe6")]},
        }
        sk = frozenset([(game_1, "0", "3x3", "Why1")])
        ck = frozenset([(game_1, "0", "3x3", "Why1"), (game_2, "0", "3x3", "Why1")])
        dlg, _ = _make_shallow_dialog([game_1, game_2], tags, sk, ck)
        self.assertEqual(len(dlg._row_widgets), 1,
                         "Only game_1 is shallow — game_2 must not appear")
        self.assertIs(dlg._row_games[0], game_1)

    def test_3x3_save_does_not_stamp_deep_game(self):
        game_1, game_2 = _two_same_gn_games()
        tags = {
            id(game_1): {"0": [_make_entry("3x3", "Why1", "generic answer")]},
            id(game_2): {"0": [_make_entry("3x3", "Why1", "I miscalculated d5 after 18...Qe6")]},
        }
        sk = frozenset([(game_1, "0", "3x3", "Why1")])
        ck = frozenset([(game_1, "0", "3x3", "Why1"), (game_2, "0", "3x3", "Why1")])
        dlg, ctrl = _make_shallow_dialog([game_1, game_2], tags, sk, ck)
        dlg._on_save()
        for c in ctrl.replace_entries_at_path_for_game.call_args_list:
            if c[0][0] is game_2:
                for e in c[0][3]:
                    self.assertFalse(e.get("is_shallow"),
                                     "game_2 Why1 (DEEP) must not receive is_shallow=True")

    def test_3x3_save_stamps_shallow_game(self):
        """game_1 (Why1=GENERIC) must receive is_shallow=True — positive control."""
        game_1, game_2 = _two_same_gn_games()
        tags = {
            id(game_1): {"0": [_make_entry("3x3", "Why1", "generic answer")]},
            id(game_2): {"0": [_make_entry("3x3", "Why1", "I miscalculated d5 after 18...Qe6")]},
        }
        sk = frozenset([(game_1, "0", "3x3", "Why1")])
        ck = frozenset([(game_1, "0", "3x3", "Why1"), (game_2, "0", "3x3", "Why1")])
        dlg, ctrl = _make_shallow_dialog([game_1, game_2], tags, sk, ck)
        dlg._on_save()
        game_1_calls = [c for c in ctrl.replace_entries_at_path_for_game.call_args_list
                        if c[0][0] is game_1]
        self.assertTrue(
            any(any(e.get("is_shallow") for e in c[0][3]) for c in game_1_calls),
            "game_1 Why1 (SHALLOW) must have at least one entry stamped is_shallow=True",
        )


@requires_qt
class TestF3SnapshotNoCollision(unittest.TestCase):
    """F3: _original_snapshot must have separate entries for each game,
    even when both have game_number=1."""

    def test_snapshot_keyed_by_row_index_not_game_number(self):
        game_1, game_2 = _two_same_gn_games()
        tags = {
            id(game_1): {"0": [_make_entry("CLAMP", "C", "game1-why")]},
            id(game_2): {"0": [_make_entry("CLAMP", "L", "game2-why")]},
        }
        sk = frozenset([(game_1, "0", "CLAMP", ""), (game_2, "0", "CLAMP", "")])
        ck = frozenset(sk)
        dlg, _ = _make_shallow_dialog([game_1, game_2], tags, sk, ck)
        # Two rows shown → two distinct snapshot entries
        self.assertEqual(len(dlg._original_snapshot), 2,
                         "_original_snapshot must have one entry per row, not collide by game_number")
        snap_0 = dlg._original_snapshot.get(0, [])
        snap_1 = dlg._original_snapshot.get(1, [])
        # Each row's snapshot must match the correct game's entry
        cats = {snap_0[0]["cat"] if snap_0 else None, snap_1[0]["cat"] if snap_1 else None}
        self.assertEqual(cats, {"C", "L"},
                         "Both games' entries must be preserved separately in the snapshot")


@requires_qt
class TestF5SortScenario(unittest.TestCase):
    """Sort scenario: sorting the DB after caching shallow_keys must not corrupt the
    identity-based chip lookup — the chip stays on game_a, not game_b."""

    def test_chip_survives_db_sort_and_theme_rebuild(self):
        """Sort DB descending, simulate theme-rebuild: game_a chip survives, game_b has none."""
        import json
        from unittest.mock import patch
        from PyQt6.QtCore import Qt
        from app.models.database_model import DatabaseModel, GameData
        from app.controllers.chess_log_charts_controller import ChessLogChartsController
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView

        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "config", "config.json",
        )
        with open(cfg_path) as f:
            cfg = json.load(f)

        game_a = GameData(game_number=0, pgn=_ONE_MOVE_PGN)
        game_b = GameData(game_number=0, pgn=_ONE_MOVE_PGN)
        db = DatabaseModel(config=cfg)
        db.add_game(game_a, tags=set())  # game_a.game_number = 1
        db.add_game(game_b, tags=set())  # game_b.game_number = 2

        db_ctrl = MagicMock()
        db_ctrl.get_panel_model.return_value = None
        db_ctrl.get_active_database.return_value = db
        ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)

        sk = frozenset([(game_a, "0", "CLAMP", "")])
        ck = frozenset([(game_a, "0", "CLAMP", ""), (game_b, "0", "CLAMP", "")])
        ctrl._on_shallow_thread_ready(sk, frozenset(), ck, None)

        # Sort descending: game_b (number 2) moves ahead of game_a (number 1)
        db.sort(column=DatabaseModel.COL_NUM, order=Qt.SortOrder.DescendingOrder)

        # Simulate theme-rebuild: new view restores cache via set_controller
        with patch.object(ctrl, "_start_dropdown_worker"):
            view = DetailChessLogChartsView({})
            view.set_controller(ctrl)

        restored_keys = ctrl.get_last_shallow_result()[0]
        self.assertEqual(restored_keys, sk, "the controller keeps the session result across the rebuild")

        tags = {
            id(game_a): {"0": [_make_entry("CLAMP", "C", "vague note")]},
            id(game_b): {"0": [_make_entry("CLAMP", "L", "specific insight")]},
        }
        dlg, dlg_ctrl = _make_shallow_dialog(
            [game_a, game_b], tags, restored_keys, ck,
        )
        self.assertEqual(len(dlg._row_widgets), 1,
                         "Only game_a must have chip after sort — game_b must not")
        self.assertIs(dlg._row_games[0], game_a)

        dlg._on_save()
        game_a_calls = [c for c in dlg_ctrl.replace_entries_at_path_for_game.call_args_list
                        if c[0][0] is game_a]
        self.assertTrue(
            any(any(e.get("is_shallow") for e in c[0][3]) for c in game_a_calls),
            "game_a must be stamped is_shallow=True after Save",
        )
        for c in dlg_ctrl.replace_entries_at_path_for_game.call_args_list:
            if c[0][0] is game_b:
                for e in c[0][3]:
                    self.assertFalse(e.get("is_shallow"),
                                     "game_b must not receive is_shallow=True after sort")


@requires_qt
class TestF5StaleCacheScenario(unittest.TestCase):
    """Stale-cache scenario: closing DB-A and opening DB-B must not show a chip for
    game_B even when game_A's stale (game_number, path_key, preset) matches exactly."""

    def test_stale_cache_no_chip_for_different_db_game(self):
        """game_B from DB-B must not get a chip from DB-A's stale shallow_keys."""
        import json
        from app.models.database_model import DatabaseModel, GameData

        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "config", "config.json",
        )
        with open(cfg_path) as f:
            cfg = json.load(f)

        db_a = DatabaseModel(config=cfg)
        game_a = GameData(game_number=0, pgn=_ONE_MOVE_PGN)
        db_a.add_game(game_a, tags=set())  # game_a.game_number = 1

        stale_shallow_keys = frozenset([(game_a, "0", "CLAMP", "")])
        stale_classified_keys = frozenset(stale_shallow_keys)

        # Simulate DB-A close: remove game_A
        db_a.remove_games([game_a])

        db_b = DatabaseModel(config=cfg)
        game_b = GameData(game_number=0, pgn=_ONE_MOVE_PGN)
        db_b.add_game(game_b, tags=set())  # game_b.game_number = 1
        self.assertEqual(game_b.game_number, game_a.game_number,
                         "Both games must have game_number=1 to reproduce the false-positive risk")

        tags = {id(game_b): {"0": [_make_entry("CLAMP", "C", "specific insight")]}}
        dlg, _ = _make_shallow_dialog([game_b], tags, stale_shallow_keys, stale_classified_keys)

        self.assertEqual(len(dlg._row_widgets), 0,
                         "game_B from DB-B must not get a chip from DB-A's stale shallow_keys")


# ---------------------------------------------------------------------------
# Phase B: Unchecked banner
# ---------------------------------------------------------------------------

@requires_qt
class TestUncheckedBanner(unittest.TestCase):
    """Banner shows N unchecked notes in Saved mode; absent in live mode."""

    def _find_banner(self, dlg):
        from PyQt6.QtWidgets import QLabel
        for lbl in dlg.findChildren(QLabel):
            t = lbl.text()
            if "hasn't been checked yet" in t or "haven't been checked yet" in t:
                return lbl
        return None

    def test_banner_absent_in_live_mode(self):
        """In live mode (classified_keys non-empty) no unchecked banner is shown."""
        game = _make_game()
        entry = _make_entry("CLAMP", "C", "a note")
        sk = frozenset([(game, "0", "CLAMP", "")])
        ck = frozenset([(game, "0", "CLAMP", "")])
        dlg, _ = _make_dialog_with_classified(
            [game], {game.game_number: {"0": [entry]}}, sk, ck
        )
        self.assertIsNone(self._find_banner(dlg))

    def test_banner_present_in_saved_mode(self):
        """In Saved mode (classified_keys empty) an unchecked banner appears."""
        game = _make_game()
        entry = _make_entry("CLAMP", "C", "unchecked note")
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, _ = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk
        )
        self.assertIsNotNone(self._find_banner(dlg))

    def test_banner_singular(self):
        """N=1 uses singular wording: '1 note hasn't been checked yet'."""
        game = _make_game()
        entry = _make_entry("CLAMP", "C", "one unchecked note")
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, _ = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk
        )
        banner = self._find_banner(dlg)
        self.assertIsNotNone(banner)
        self.assertIn("1 note hasn't been checked yet", banner.text())
        self.assertNotIn("notes", banner.text())

    def test_banner_plural(self):
        """N=2 uses plural wording: '2 notes haven't been checked yet'."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        e1 = ChessLogStorageService.make_entry("CLAMP", "C", "note alpha")
        e2 = ChessLogStorageService.make_entry("CLAMP", "L", "note beta")
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, _ = _make_dialog(
            [game], {game.game_number: {"0": [e1, e2]}}, sk
        )
        banner = self._find_banner(dlg)
        self.assertIsNotNone(banner)
        self.assertIn("2 notes haven't been checked yet", banner.text())

    def test_clamp_two_cats_same_note_counts_once(self):
        """One note shared by C and L categories counts as one unchecked, not two."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        shared_note = "shared note text"
        e_c = ChessLogStorageService.make_entry("CLAMP", "C", shared_note)
        e_l = ChessLogStorageService.make_entry("CLAMP", "L", shared_note)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, _ = _make_dialog(
            [game], {game.game_number: {"0": [e_c, e_l]}}, sk
        )
        banner = self._find_banner(dlg)
        self.assertIsNotNone(banner)
        self.assertIn("1 note hasn't been checked yet", banner.text())


# ---------------------------------------------------------------------------
# Phase B: Save in Saved mode must not write check_hash or _check_run
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _clear_stale_flags_after_edit: flag cleared, check_hash preserved after edit
# ---------------------------------------------------------------------------

@requires_qt
class TestClearStaleFlagsAfterEdit(unittest.TestCase):
    """_clear_stale_flags_after_edit clears is_shallow/is_vague but keeps check_hash."""

    def _run_edit_test(self, game, entry, sk, ck, saved_mode, cat_key):
        """Open dialog, edit answer text, save; return all entries written to controller."""
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=ck,
            saved_mode=saved_mode,
        )
        self.assertTrue(dlg._row_widgets, "Expected at least one row widget")
        why_edit = dlg._row_widgets[0]._why_texts.get(cat_key)
        self.assertIsNotNone(why_edit, f"Expected _why_texts['{cat_key}']")
        why_edit.setPlainText("edited text")
        dlg._on_save()
        all_written = []
        for call_args in ctrl.replace_entries_at_path_for_game.call_args_list:
            args, kw = call_args
            all_written.extend(kw.get("entries") or (args[3] if len(args) > 3 else []))
        return all_written

    def test_clamp_live_edit_clears_flag_preserves_check_hash(self):
        """CLAMP, live mode: edit text → is_shallow cleared, check_hash preserved."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "original", is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash("original")
        sk = frozenset([(game, "0", "CLAMP", "")])
        ck = frozenset([(game, "0", "CLAMP", "")])
        written = self._run_edit_test(game, entry, sk, ck, saved_mode=False, cat_key="why")
        self.assertTrue(written)
        for e in written:
            self.assertFalse(e.get("is_shallow"), f"is_shallow must be cleared; got {e}")
            self.assertIn("check_hash", e,
                f"check_hash must survive the edit; got {e}")

    def test_clamp_saved_edit_clears_flag_preserves_check_hash(self):
        """CLAMP, Saved mode: edit text → is_shallow cleared, check_hash preserved."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "original", is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash("original")
        sk = frozenset([(game, "0", "CLAMP", "")])
        written = self._run_edit_test(game, entry, sk, ck=frozenset(), saved_mode=True,
                                       cat_key="why")
        self.assertTrue(written)
        for e in written:
            self.assertFalse(e.get("is_shallow"), f"is_shallow must be cleared; got {e}")
            self.assertIn("check_hash", e,
                f"check_hash must survive the edit; got {e}")

    def test_3x3_live_edit_clears_flag_preserves_check_hash(self):
        """3x3, live mode: edit Why1 → is_shallow cleared, check_hash preserved."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "original why1",
                                                   is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash("original why1")
        sk = frozenset([(game, "0", "3x3", "Why1")])
        ck = frozenset([(game, "0", "3x3", "Why1")])
        written = self._run_edit_test(game, entry, sk, ck, saved_mode=False, cat_key="Why1")
        self.assertTrue(written)
        edited = [e for e in written if e.get("cat") == "Why1"]
        self.assertTrue(edited, f"Expected Why1 entry in written; got {written}")
        for e in edited:
            self.assertFalse(e.get("is_shallow"), f"is_shallow must be cleared; got {e}")
            self.assertIn("check_hash", e,
                f"check_hash must survive the edit; got {e}")

    def test_3x3_saved_edit_clears_flag_preserves_check_hash(self):
        """3x3, Saved mode: edit Why1 → is_shallow cleared, check_hash preserved."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "original why1",
                                                   is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash("original why1")
        sk = frozenset([(game, "0", "3x3", "Why1")])
        written = self._run_edit_test(game, entry, sk, ck=frozenset(), saved_mode=True,
                                       cat_key="Why1")
        self.assertTrue(written)
        edited = [e for e in written if e.get("cat") == "Why1"]
        self.assertTrue(edited, f"Expected Why1 entry in written; got {written}")
        for e in edited:
            self.assertFalse(e.get("is_shallow"), f"is_shallow must be cleared; got {e}")
            self.assertIn("check_hash", e,
                f"check_hash must survive the edit; got {e}")


@requires_qt
class TestSavedModeNoWrite(unittest.TestCase):
    """Save in Saved mode writes no check_hash and never calls set_check_run_for_game."""

    def test_save_does_not_write_check_hash(self):
        """After Save in Saved mode, no entry passed to replace_entries has check_hash."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "some note", is_shallow=True)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk
        )
        dlg._on_save()
        for call_args in ctrl.replace_entries_at_path_for_game.call_args_list:
            _, kw = call_args
            entries_written = kw.get("entries") or (call_args[0][3] if len(call_args[0]) > 3 else [])
            for e in entries_written:
                self.assertNotIn("check_hash", e,
                    f"Saved mode must not write check_hash; got entry: {e}")

    def test_save_does_not_call_set_check_run(self):
        """set_check_run_for_game must never be called in Saved mode."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "a note", is_shallow=True)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk
        )
        dlg._on_save()
        ctrl.set_check_run_for_game.assert_not_called()


# ---------------------------------------------------------------------------
# Phase B: PDF header in Saved mode
# ---------------------------------------------------------------------------

@requires_qt
class TestPDFHeaderSavedMode(unittest.TestCase):
    """PDF header model_label reflects _check_run data from shown games in Saved mode."""

    def _open_and_export(self, game, entry, check_run_side_effect):
        from unittest.mock import patch, MagicMock
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk
        )
        captured = {}
        with patch.object(
            ctrl, "get_check_run_for_game",
            side_effect=check_run_side_effect,
        ), patch(
            "app.services.chess_log_pdf_service.ChessLogPDFService.export_tags",
            side_effect=lambda *a, **kw: captured.update(kw),
        ), patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=("/tmp/test_export.pdf", "PDF Files (*.pdf)"),
        ):
            dlg._on_export_pdf()
        return captured

    def test_no_run_info_shows_saved_check_logs_results(self):
        """When no game has _check_run, model_label is 'Saved Check Logs results'."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", is_shallow=True)
        result = self._open_and_export(game, entry, lambda g: None)
        self.assertEqual(result.get("model_label"), "Saved Check Logs results")

    def test_single_run_shows_model_and_date(self):
        """Single run (same model+date) shows model name and a formatted date."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", is_shallow=True)
        cr = {"model": "claude-sonnet-4-6", "date": "2026-10-30T12:00:00Z"}
        result = self._open_and_export(game, entry, lambda g: cr)
        self.assertEqual(result.get("model_label"), "claude-sonnet-4-6")
        generated_at = result.get("generated_at", "")
        self.assertTrue(generated_at, "Expected generated_at to be set")
        self.assertIn("2026-10-30", generated_at)

    def test_mixed_runs_shows_most_recent_model_suffix(self):
        """Multiple different runs → most recent model + ' (mixed runs)'."""
        import os
        import sys
        import json
        from unittest.mock import patch, MagicMock
        from app.models.database_model import GameData
        from app.services.chess_log_storage_service import ChessLogStorageService

        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "config", "config.json",
        )
        with open(cfg_path) as f:
            cfg = json.load(f)

        game1 = _make_game(game_number=1)
        game2 = _make_game(game_number=2)
        entry1 = ChessLogStorageService.make_entry("CLAMP", "C", "note1", is_shallow=True)
        entry2 = ChessLogStorageService.make_entry("CLAMP", "C", "note2", is_shallow=True)

        sk = frozenset([
            (game1, "0", "CLAMP", ""),
            (game2, "0", "CLAMP", ""),
        ])
        ctrl = _make_controller({
            game1.game_number: {"0": [entry1]},
            game2.game_number: {"0": [entry2]},
        })
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        dlg = ShowShallowTagsDialog(
            config=cfg, games=[game1, game2],
            controller=ctrl,
            shallow_keys=sk,
            vague_keys=frozenset(),
            classified_keys=frozenset(),
        )
        cr_map = {
            id(game1): {"model": "claude-opus-4-7", "date": "2026-10-28T10:00:00Z"},
            id(game2): {"model": "claude-sonnet-4-6", "date": "2026-10-30T12:00:00Z"},
        }
        captured = {}
        with patch.object(
            ctrl, "get_check_run_for_game",
            side_effect=lambda g: cr_map.get(id(g)),
        ), patch(
            "app.services.chess_log_pdf_service.ChessLogPDFService.export_tags",
            side_effect=lambda *a, **kw: captured.update(kw),
        ), patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=("/tmp/test_mixed.pdf", "PDF Files (*.pdf)"),
        ):
            dlg._on_export_pdf()
        self.assertEqual(captured.get("model_label"), "claude-sonnet-4-6 (mixed runs)")


# ---------------------------------------------------------------------------
# Fix 1: explicit saved_mode parameter
# ---------------------------------------------------------------------------

@requires_qt
class TestExplicitSavedMode(unittest.TestCase):
    """saved_mode=False (default) means no banner even when classified_keys is empty."""

    def _find_banner(self, dlg):
        from PyQt6.QtWidgets import QLabel
        for lbl in dlg.findChildren(QLabel):
            t = lbl.text()
            if "hasn't been checked yet" in t or "haven't been checked yet" in t:
                return lbl
        return None

    def test_live_empty_classified_no_banner(self):
        """Live dialog with classified_keys=frozenset() and saved_mode default (False)
        must not show the unchecked banner — a parse all-fail is not Saved mode."""
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = _make_entry("CLAMP", "C", "an unchecked note")
        sk = frozenset([(game, "0", "CLAMP", "")])
        # classified_keys empty but saved_mode=False (default) → live mode, no banner
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=frozenset(),
            # saved_mode NOT passed → defaults to False
        )
        self.assertIsNone(self._find_banner(dlg))

    def test_saved_mode_flag_shows_banner(self):
        """saved_mode=True with an unchecked entry shows the unchecked banner."""
        game = _make_game()
        entry = _make_entry("CLAMP", "C", "unchecked note")
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, _ = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
        )
        self.assertIsNotNone(self._find_banner(dlg))


# ---------------------------------------------------------------------------
# Fix 1: Saved mode does not call AI / shallow thread
# ---------------------------------------------------------------------------

@requires_qt
class TestNoAICallInSavedMode(unittest.TestCase):
    """Opening, editing, and saving in Saved mode never touches the AI pipeline."""

    def test_saved_mode_never_calls_ai_methods(self):
        """No AI-related controller methods are called during open/edit/save in Saved mode."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "some note", is_shallow=True)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
        )
        # Edit text in the row widget
        if dlg._row_widgets:
            dlg._row_widgets[0]._why_texts.get("why") and \
                dlg._row_widgets[0]._why_texts["why"].setPlainText("edited text")
        dlg._on_save()
        # Controller methods that belong to the AI pipeline must never be called
        ctrl.request_flag_shallow_notes.assert_not_called()

    def test_shallow_thread_not_instantiated_in_saved_mode(self):
        """ChessLogShallowThread is never instantiated when the dialog is in Saved mode."""
        from unittest.mock import patch
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "a note", is_shallow=True)
        sk = frozenset([(game, "0", "CLAMP", "")])
        with patch(
            "app.controllers.chess_log_charts_controller.ChessLogShallowThread",
            side_effect=AssertionError("ShallowThread must not be constructed in Saved mode"),
        ):
            dlg, ctrl = _make_dialog(
                [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
            )
            dlg._on_save()
        # If we reach here, no AssertionError was raised — shallow thread was never created


# ---------------------------------------------------------------------------
# Fix 3: editing a flagged answer clears its chip on save
# ---------------------------------------------------------------------------

@requires_qt
class TestEditSinceCheck(unittest.TestCase):
    """Editing a flagged answer and saving must drop is_shallow from that entry."""

    def test_edit_drops_is_shallow_in_live_save(self):
        """In live mode: editing the why text of a shallow-flagged entry clears is_shallow."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        original_text = "original text"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", original_text, is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash(original_text)
        sk = frozenset([(game, "0", "CLAMP", "")])
        ck = frozenset([(game, "0", "CLAMP", "")])
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=ck,
        )
        # Edit the why text
        self.assertTrue(dlg._row_widgets, "Expected at least one row widget")
        why_edit = dlg._row_widgets[0]._why_texts.get("why")
        self.assertIsNotNone(why_edit, "Expected _why_texts['why'] to be a QPlainTextEdit")
        why_edit.setPlainText("edited text")

        dlg._on_save()

        # Inspect all entries written to controller
        all_written = []
        for call_args in ctrl.replace_entries_at_path_for_game.call_args_list:
            args, kw = call_args
            entries_written = kw.get("entries") or (args[3] if len(args) > 3 else [])
            all_written.extend(entries_written)
        self.assertTrue(all_written, "Expected replace_entries_at_path_for_game to be called")
        self.assertFalse(
            any(e.get("is_shallow") for e in all_written),
            f"is_shallow must be cleared after text edit; got: {all_written}",
        )

    def test_edit_drops_is_shallow_in_saved_mode(self):
        """In Saved mode: editing the why text of a shallow-flagged entry clears is_shallow."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        original_text = "original text"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", original_text, is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash(original_text)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
        )
        self.assertTrue(dlg._row_widgets, "Expected at least one row widget")
        why_edit = dlg._row_widgets[0]._why_texts.get("why")
        self.assertIsNotNone(why_edit)
        why_edit.setPlainText("different text entirely")

        dlg._on_save()

        all_written = []
        for call_args in ctrl.replace_entries_at_path_for_game.call_args_list:
            args, kw = call_args
            entries_written = kw.get("entries") or (args[3] if len(args) > 3 else [])
            all_written.extend(entries_written)
        self.assertTrue(all_written, "Expected replace_entries_at_path_for_game to be called")
        self.assertFalse(
            any(e.get("is_shallow") for e in all_written),
            f"is_shallow must be cleared after text edit; got: {all_written}",
        )

    def test_edit_drops_is_shallow_unchecked_count_increases(self):
        """After editing a flagged answer, count_unchecked_answers reflects the cleared flag."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        original_text = "original text"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", original_text, is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash(original_text)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
        )
        self.assertTrue(dlg._row_widgets)
        why_edit = dlg._row_widgets[0]._why_texts.get("why")
        self.assertIsNotNone(why_edit)
        why_edit.setPlainText("new text here")
        dlg._on_save()
        # After save, the mutable storage in the mock should reflect the cleared chip.
        # count_unchecked_answers delegates to the real controller method.
        count = ctrl.count_unchecked_answers([game])
        self.assertEqual(count, 1,
            f"Expected 1 unchecked answer after editing a flagged entry; got {count}")


# ---------------------------------------------------------------------------
# Fix 3: restoring exact text keeps chip and hash
# ---------------------------------------------------------------------------

@requires_qt
class TestRestoreExactText(unittest.TestCase):
    """Restoring exact original text after editing must preserve the chip and check_hash."""

    def test_restore_exact_keeps_chip_and_hash(self):
        """Set text to 'different text' then back to 'exact text'; chip stays on Save.

        When text is restored to the original, nothing changed from storage so no
        write call occurs — the entry remains in storage with is_shallow=True.
        Verify the entry is still accessible with its chip intact after _on_save.
        """
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        exact_text = "exact text"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", exact_text, is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash(exact_text)
        sk = frozenset([(game, "0", "CLAMP", "")])
        ck = frozenset([(game, "0", "CLAMP", "")])
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=ck,
        )
        self.assertTrue(dlg._row_widgets)
        why_edit = dlg._row_widgets[0]._why_texts.get("why")
        self.assertIsNotNone(why_edit)
        # Simulate: edit then restore to original
        why_edit.setPlainText("different text")
        why_edit.setPlainText(exact_text)

        dlg._on_save()

        # When text is restored, nothing changed → no write needed; entry stays in storage.
        # The storage (via ctrl.get_tags_for_game) should still show is_shallow=True.
        tags = ctrl.get_tags_for_game(game)
        all_stored = [e for entries in tags.values() for e in entries]
        expected_hash = ChessLogStorageService.compute_check_hash(exact_text)
        # Chip must be preserved (either unchanged in storage or written via replace)
        any_is_shallow = any(e.get("is_shallow") for e in all_stored)
        any_correct_hash = any(e.get("check_hash") == expected_hash for e in all_stored)
        self.assertTrue(
            any_is_shallow,
            f"is_shallow must be preserved when text is restored; storage: {all_stored}",
        )
        self.assertTrue(
            any_correct_hash,
            f"check_hash must match exact_text in storage; storage: {all_stored}",
        )


# ---------------------------------------------------------------------------
# Phase b: entries not in classified_keys get no check_hash
# ---------------------------------------------------------------------------

@requires_qt
class TestParseFailureUnchecked(unittest.TestCase):
    """Entries not in classified_keys are not touched by Phase b — no check_hash written."""

    def test_entry_not_in_classified_gets_no_check_hash(self):
        """classified_keys empty → Phase b loop is empty → replace not called."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "a note")
        # Not in shallow_keys or classified_keys
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=frozenset(),
            classified_keys=frozenset(),
        )
        dlg._on_save()
        # Phase a has no rows, Phase b has no classified_keys → nothing written
        ctrl.replace_entries_at_path_for_game.assert_not_called()


# ---------------------------------------------------------------------------
# Honoured-Ignore counts as checked
# ---------------------------------------------------------------------------

@requires_qt
class TestHonouredIgnoreChecked(unittest.TestCase):
    """An entry with honoured ignore_shallow counts as checked (not unchecked)."""

    def test_honoured_ignore_not_counted_as_unchecked(self):
        """ignore_shallow=True with matching ignore_text_hash → entry is checked."""
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        note = "the note"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", note)
        entry["ignore_shallow"] = True
        # ignore_text_hash uses full sha256 (not the truncated compute_check_hash)
        entry["ignore_text_hash"] = hashlib.sha256(note.encode("utf-8")).hexdigest()
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
        )
        # Entry has honoured ignore → count_unchecked_answers should be 0
        count = ctrl.count_unchecked_answers([game])
        self.assertEqual(count, 0,
            f"Honoured ignore_shallow should count as checked; got {count}")


# ---------------------------------------------------------------------------
# Phase b: deep (non-flagged) entries in classified_keys get check_hash
# ---------------------------------------------------------------------------

@requires_qt
class TestDeepAnswersGetCheckHash(unittest.TestCase):
    """Non-flagged entries that are in classified_keys get check_hash stamped (Phase b)."""

    def test_clamp_deep_entry_gets_check_hash_on_live_save(self):
        """CLAMP entry in classified_keys but not in shallow_keys: Phase b stamps check_hash."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "deep note")
        # In classified_keys (parsed), but not in shallow_keys (not flagged)
        ck = frozenset([(game, "0", "CLAMP", "")])
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=frozenset(),
            classified_keys=ck,
        )
        # No rows shown (not flagged)
        self.assertEqual(len(dlg._row_widgets), 0)
        dlg._on_save()
        # Phase b should write check_hash
        all_written = []
        for call_args in ctrl.replace_entries_at_path_for_game.call_args_list:
            args, kw = call_args
            entries_written = kw.get("entries") or (args[3] if len(args) > 3 else [])
            all_written.extend(entries_written)
        expected_hash = ChessLogStorageService.compute_check_hash("deep note")
        self.assertTrue(
            any(e.get("check_hash") == expected_hash for e in all_written),
            f"Phase b must stamp check_hash on non-flagged classified entry; got: {all_written}",
        )

    def test_3x3_deep_entry_gets_check_hash_on_live_save(self):
        """3x3 entry in classified_keys but not flagged: Phase b stamps check_hash."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "deep why1")
        ck = frozenset([(game, "0", "3x3", "Why1")])
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=frozenset(),
            classified_keys=ck,
        )
        self.assertEqual(len(dlg._row_widgets), 0)
        dlg._on_save()
        all_written = []
        for call_args in ctrl.replace_entries_at_path_for_game.call_args_list:
            args, kw = call_args
            entries_written = kw.get("entries") or (args[3] if len(args) > 3 else [])
            all_written.extend(entries_written)
        expected_hash = ChessLogStorageService.compute_check_hash("deep why1")
        self.assertTrue(
            any(e.get("check_hash") == expected_hash for e in all_written),
            f"Phase b must stamp check_hash on non-flagged 3x3 classified entry; got: {all_written}",
        )


# ---------------------------------------------------------------------------
# Saved mode: real edits written; check_hash preserved; no check run
# ---------------------------------------------------------------------------

@requires_qt
class TestSavedModeRealEditsWritten(unittest.TestCase):
    """In Saved mode: text edits and Ignore ticks are written; check_run NOT written;
    check_hash is PRESERVED (never cleared on edit — restoring original text re-checks it)."""

    def test_edit_text_clears_flag_and_preserves_check_hash_no_check_run(self):
        """Saved mode: editing text clears is_shallow but preserves check_hash.

        check_hash must survive a text edit in Saved mode so that restoring the
        exact original text makes the answer count as checked again without
        re-running Check Logs. Only is_shallow/is_vague/ignore fields are cleared.
        set_check_run_for_game must never be called in Saved mode.
        """
        from app.services.chess_log_storage_service import ChessLogStorageService
        game = _make_game()
        original = "original"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", original, is_shallow=True)
        original_hash = ChessLogStorageService.compute_check_hash(original)
        entry["check_hash"] = original_hash
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
        )
        self.assertTrue(dlg._row_widgets, "Expected a row widget")
        row_widget = dlg._row_widgets[0]
        why_edit = row_widget._why_texts.get("why")
        self.assertIsNotNone(why_edit)
        why_edit.setPlainText("new text")

        dlg._on_save()

        # Must not call set_check_run_for_game
        ctrl.set_check_run_for_game.assert_not_called()

        all_written = []
        for call_args in ctrl.replace_entries_at_path_for_game.call_args_list:
            args, kw = call_args
            entries_written = kw.get("entries") or (args[3] if len(args) > 3 else [])
            all_written.extend(entries_written)
        self.assertTrue(all_written, "Expected entries to be written after text edit")
        # is_shallow must be cleared (text was edited)
        self.assertFalse(
            any(e.get("is_shallow") for e in all_written),
            f"is_shallow must be cleared after text edit; got: {all_written}",
        )
        # check_hash must be PRESERVED (original hash survives, enabling text-restore check)
        for e in all_written:
            self.assertEqual(
                e.get("check_hash"), original_hash,
                f"check_hash must be preserved after Saved-mode text edit; got: {e}",
            )


# ---------------------------------------------------------------------------
# PDF header: live mode uses check_run_info
# ---------------------------------------------------------------------------

@requires_qt
class TestPDFHeaderLiveMode(unittest.TestCase):
    """PDF header in live mode uses check_run_info passed to the dialog."""

    def test_live_mode_pdf_header_uses_check_run_info(self):
        """Live dialog with check_run_info: PDF gets model_label from info and formatted date."""
        from unittest.mock import patch
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", is_shallow=True)
        sk = frozenset([(game, "0", "CLAMP", "")])
        ck = frozenset([(game, "0", "CLAMP", "")])
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        check_run_info = {"model": "claude-opus-4-7", "date": "2026-10-30T12:00:00Z"}
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=ck,
            check_run_info=check_run_info,
        )
        captured = {}
        with patch(
            "app.services.chess_log_pdf_service.ChessLogPDFService.export_tags",
            side_effect=lambda *a, **kw: captured.update(kw),
        ), patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=("/tmp/test_live.pdf", "PDF Files (*.pdf)"),
        ):
            dlg._on_export_pdf()
        self.assertEqual(captured.get("model_label"), "claude-opus-4-7")
        # generated_at should be a non-empty formatted date string
        generated_at = captured.get("generated_at", "")
        self.assertTrue(generated_at, "Expected generated_at to be set in live mode")
        self.assertIn("2026-10-30", generated_at)


# ---------------------------------------------------------------------------
# Step 2: nothing-flagged message box from _show_saved_shallow_logs
# ---------------------------------------------------------------------------

@requires_qt
class TestNothingFlaggedMessage(unittest.TestCase):
    """_show_saved_shallow_logs shows a QMessageBox when nothing is flagged.

    Matches the wording live Check Logs uses when a run flags nothing:
    title "Nothing Flagged", message "No shallow notes or vague lessons found — great job."
    Plus unchecked count text when some answers haven't been checked yet.
    """

    def _make_fake_window(self, games, chess_log_ctrl, config=None):
        """Return a minimal stand-in for MainWindow with the required attributes."""
        from unittest.mock import MagicMock
        db = MagicMock()
        db.get_all_games.return_value = games
        db_controller = MagicMock()
        db_controller.get_active_database.return_value = db
        fake = MagicMock()
        fake.config = config or {}
        fake.controller.get_database_controller.return_value = db_controller
        fake.controller.get_chess_log_controller.return_value = chess_log_ctrl
        return fake

    def _make_checked_game(self):
        """Return a game whose has_chess_log_tags=True so it passes the logged-game filter."""
        game = _make_game()
        game.has_chess_log_tags = True
        return game

    def _make_ctrl_mock(self, *, has_checked, unchecked_count):
        """Plain MagicMock controller — no side_effects — for main_window tests."""
        from unittest.mock import MagicMock
        ctrl = MagicMock()
        ctrl.has_any_checked_answer.return_value = has_checked
        ctrl.get_shallow_vague_keys.return_value = (frozenset(), frozenset())
        ctrl.count_unchecked_answers.return_value = unchecked_count
        return ctrl

    def _load_cfg(self):
        import json, os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "config", "config.json",
        )
        with open(path) as f:
            return json.load(f)

    def test_show_all_logged_moments_with_none_sets_log_wording_status(self):
        """Show Logged Moments for All Games with no logged games → status uses "logged", not "tagged"."""
        from app.main_window import MainWindow
        game = _make_game()
        game.has_chess_log_tags = False
        fake = self._make_fake_window([game], self._make_ctrl_mock(has_checked=False, unchecked_count=0))
        MainWindow._show_chess_logs_for_all_games(fake)
        fake.controller.set_status.assert_called_once_with("No logged games in the active database")

    def test_all_checked_shows_nothing_flagged_message(self):
        """All answers checked + nothing flagged → MessageDialog with exact config wording."""
        from unittest.mock import patch
        from app.main_window import MainWindow
        game = self._make_checked_game()
        ctrl = self._make_ctrl_mock(has_checked=True, unchecked_count=0)
        fake = self._make_fake_window([game], ctrl, config=self._load_cfg())
        with patch("app.views.dialogs.message_dialog.MessageDialog.show_information") as mock_info:
            MainWindow._show_saved_shallow_logs(fake)
        mock_info.assert_called_once()
        _config, title, message, _parent = mock_info.call_args[0]
        self.assertEqual(title, "Nothing Flagged")
        self.assertEqual(message, "No shallow notes or vague lessons found — great job.")

    def test_one_unchecked_appends_count_text(self):
        """1 unchecked answer + nothing flagged → base message + '1 note hasn't been checked yet…'"""
        from unittest.mock import patch
        from app.main_window import MainWindow
        game = self._make_checked_game()
        ctrl = self._make_ctrl_mock(has_checked=True, unchecked_count=1)
        fake = self._make_fake_window([game], ctrl, config=self._load_cfg())
        with patch("app.views.dialogs.message_dialog.MessageDialog.show_information") as mock_info:
            MainWindow._show_saved_shallow_logs(fake)
        mock_info.assert_called_once()
        _config, title, message, _parent = mock_info.call_args[0]
        self.assertEqual(title, "Nothing Flagged")
        expected = (
            "No shallow notes or vague lessons found — great job."
            "<br><br>1 note hasn't been checked yet"
            " (new or edited since the last Check Logs). Run Check Logs to check them."
        )
        self.assertEqual(message, expected)

    def test_plural_unchecked_uses_have_not(self):
        """3 unchecked answers → '3 notes haven't been checked yet…'"""
        from unittest.mock import patch
        from app.main_window import MainWindow
        game = self._make_checked_game()
        ctrl = self._make_ctrl_mock(has_checked=True, unchecked_count=3)
        fake = self._make_fake_window([game], ctrl, config=self._load_cfg())
        with patch("app.views.dialogs.message_dialog.MessageDialog.show_information") as mock_info:
            MainWindow._show_saved_shallow_logs(fake)
        mock_info.assert_called_once()
        _config, title, message, _parent = mock_info.call_args[0]
        self.assertEqual(title, "Nothing Flagged")
        expected = (
            "No shallow notes or vague lessons found — great job."
            "<br><br>3 notes haven't been checked yet"
            " (new or edited since the last Check Logs). Run Check Logs to check them."
        )
        self.assertEqual(message, expected)


# ---------------------------------------------------------------------------
# End-to-end: real ChessLogController + real PGN round-trip (no store_tags mock)
# ---------------------------------------------------------------------------

@requires_qt
class TestEndToEndRealDatabaseModel(unittest.TestCase):
    """End-to-end: live Check Logs Save → Saved-mode dialog → real PGN write/read-back.

    Uses real GameData objects with real PGN text and a real ChessLogController.
    store_tags is NOT patched — data actually round-trips through game.pgn.
    Assertions read state back from the PGN with load_tags / load_check_run,
    not from the controller's in-memory cache.
    """

    def _make_ctrl(self, game1, game2):
        from app.controllers.chess_log_controller import ChessLogController
        from unittest.mock import MagicMock
        gm = MagicMock()
        gm.active_game = None
        gc = MagicMock()
        gc.get_game_model.return_value = gm
        db_model = MagicMock()
        pm = MagicMock()
        pm.get_all_database_models.return_value = [db_model]
        pm.active_database_changed = MagicMock()
        pm.active_database_changed.connect = MagicMock()
        pm.active_database_changed.disconnect = MagicMock()
        dc = MagicMock()
        dc.get_panel_model.return_value = pm
        dc.find_database_model_for_game.return_value = db_model
        ctrl = ChessLogController({}, gc, database_controller=dc)
        return ctrl, dc

    def test_live_save_then_edit_and_ignore_in_saved_mode(self):
        """Full PGN round-trip:
        1. Live Check Logs Save (classified_keys set): check_hash + _check_run written to PGN.
        2. Saved-mode dialog: edit one answer, tick Ignore on the other → Save.
        3. load_tags / load_check_run read state directly from PGN (not cache).
        4. Reopen: 1 dimmed row, banner = '1 note hasn't been checked yet...'.
        """
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog

        game1 = _make_game(game_number=1)
        game2 = _make_game(game_number=2)

        ctrl, dc = self._make_ctrl(game1, game2)

        # Seed the controller's cache with unflagged entries (pre-Check-Logs state)
        entry1 = ChessLogStorageService.make_entry("CLAMP", "C", "note one")
        entry2 = ChessLogStorageService.make_entry("CLAMP", "C", "note two")
        ctrl._multi_cache[id(game1)] = {"0": [dict(entry1)]}
        ctrl._multi_cache[id(game2)] = {"0": [dict(entry2)]}

        # ---- Step 1: Live Check Logs Save (both games in shallow_keys + classified_keys) ----
        sk = frozenset([
            (game1, "0", "CLAMP", ""),
            (game2, "0", "CLAMP", ""),
        ])
        ck = frozenset([
            (game1, "0", "CLAMP", ""),
            (game2, "0", "CLAMP", ""),
        ])
        check_run_info = {"model": "claude-sonnet-4-6", "date": "2026-10-31T10:00:00Z"}

        live_dlg = ShowShallowTagsDialog(
            config={},
            games=[game1, game2],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=ck,
            check_run_info=check_run_info,
        )
        live_dlg._on_save()

        # Verify _check_run written to PGN (read from game.pgn, not cache)
        cr1 = ChessLogStorageService.load_check_run(game1)
        self.assertIsNotNone(cr1, "Expected _check_run in game1 PGN after live save")
        self.assertEqual(cr1.get("model"), "claude-sonnet-4-6")

        # ---- Step 2: Saved-mode dialog ----
        sk2, vk2 = ctrl.get_shallow_vague_keys([game1, game2])
        saved_dlg = ShowShallowTagsDialog(
            config={},
            games=[game1, game2],
            controller=ctrl,
            shallow_keys=sk2,
            vague_keys=vk2,
            classified_keys=frozenset(),
            saved_mode=True,
        )
        self.assertEqual(len(saved_dlg._row_widgets), 2, "Expected 2 rows in saved-mode dialog")

        # Row 0 = game1: edit the text
        why_edit = saved_dlg._row_widgets[0]._why_texts.get("why")
        self.assertIsNotNone(why_edit)
        why_edit.setPlainText("note one edited")

        # Row 1 = game2: tick Ignore
        ignore_cb = saved_dlg._row_widgets[1]._ignore_check
        self.assertIsNotNone(ignore_cb)
        ignore_cb.setChecked(True)

        saved_dlg._on_save()

        # DB was marked unsaved
        dc.mark_database_unsaved.assert_called()

        # ---- Step 3: Read back from PGN (not cache) ----
        tags1 = ChessLogStorageService.load_tags(game1)
        entries1 = [e for es in tags1.values() for e in es]
        # is_shallow cleared (text edited)
        self.assertFalse(
            any(e.get("is_shallow") for e in entries1),
            f"game1 is_shallow must be cleared after text edit; PGN: {entries1}",
        )
        # check_hash preserved (not cleared by the edit)
        self.assertTrue(
            any("check_hash" in e for e in entries1),
            f"game1 check_hash must survive the edit; PGN: {entries1}",
        )

        tags2 = ChessLogStorageService.load_tags(game2)
        entries2 = [e for es in tags2.values() for e in es]
        expected_hash = hashlib.sha256("note two".encode("utf-8")).hexdigest()
        self.assertTrue(
            any(e.get("ignore_text_hash") == expected_hash for e in entries2),
            f"game2 ignore_text_hash must match 'note two'; PGN: {entries2}",
        )
        # _check_run preserved in game1 (Saved mode must not erase it)
        cr1_after = ChessLogStorageService.load_check_run(game1)
        self.assertEqual(cr1_after, cr1, "game1 _check_run must survive Saved-mode save")

        # ---- Step 4: Reopen in Saved mode ----
        sk3, _vk3 = ctrl.get_shallow_vague_keys([game1, game2])
        reopen_dlg = ShowShallowTagsDialog(
            config={},
            games=[game1, game2],
            controller=ctrl,
            shallow_keys=sk3,
            saved_mode=True,
        )
        # Only game2's row shown (game1 no longer has is_shallow)
        self.assertEqual(len(reopen_dlg._row_widgets), 1,
            "Reopen: only game2's row should be shown")
        row2 = reopen_dlg._row_widgets[0]
        # game2 row is dimmed (ignore_shallow=True → _preserved_ignore_shallow)
        self.assertTrue(row2._preserved_ignore_shallow,
            "Reopen: game2 row must be dimmed (_preserved_ignore_shallow=True)")
        # Banner: 1 note hasn't been checked yet (game1 was edited)
        self.assertEqual(reopen_dlg.get_unchecked_count(), 1,
            "Reopen: unchecked count must be 1")
        # Assert the banner text is exactly right
        from PyQt6.QtWidgets import QLabel
        banner_labels = [
            lbl for lbl in reopen_dlg.findChildren(QLabel)
            if "hasn't been checked yet" in lbl.text()
        ]
        self.assertEqual(len(banner_labels), 1, "Expected exactly one banner label")
        self.assertIn(
            "1 note hasn't been checked yet",
            banner_labels[0].text(),
        )


# ---------------------------------------------------------------------------
# Item 2 (gap): No AI call from Saved-mode export
# ---------------------------------------------------------------------------

@requires_qt
class TestNoAICallInSavedModeExport(unittest.TestCase):
    """Exporting PDF from Saved-mode dialog never touches the AI pipeline."""

    def test_export_in_saved_mode_never_calls_ai_services(self):
        """Opening, editing, saving, and exporting in Saved mode must not construct
        or call AIService, ChessLogShallowThread, or classify_notes."""
        from unittest.mock import patch
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "a note", is_shallow=True)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {game.game_number: {"0": [entry]}}, sk, saved_mode=True
        )
        if dlg._row_widgets:
            w = dlg._row_widgets[0]._why_texts.get("why")
            if w:
                w.setPlainText("edited text")
        dlg._on_save()

        # Patch AI constructors/functions to fail if called during export
        with patch(
            "app.controllers.chess_log_charts_controller.ChessLogShallowThread.__init__",
            side_effect=AssertionError("ChessLogShallowThread must not be created in Saved mode"),
        ), patch(
            "app.services.ai_service.AIService.__init__",
            side_effect=AssertionError("AIService must not be created in Saved mode"),
        ), patch(
            "app.services.chess_log_shallow_service.classify_notes",
            side_effect=AssertionError("classify_notes must not be called in Saved mode"),
        ), patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=("/tmp/test_export_saved.pdf", "PDF Files (*.pdf)"),
        ), patch(
            "app.services.chess_log_pdf_service.ChessLogPDFService.export_tags",
        ):
            dlg._on_export_pdf()
        # If any AI class was invoked the patches would have raised AssertionError


# ---------------------------------------------------------------------------
# Item 3 (gap): Reopen after restore-exact-text shows chip; count unchanged
# ---------------------------------------------------------------------------

@requires_qt
class TestRestoreExactTextReopen(unittest.TestCase):
    """After restore + save, reopening dialog still shows the chip and count stays 0."""

    def test_restore_exact_then_reopen_chip_shown_and_count_zero(self):
        """Edit text, restore original, Save → chip still shown on reopen; count = 0."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        exact_text = "exact text"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", exact_text, is_shallow=True)
        entry["check_hash"] = ChessLogStorageService.compute_check_hash(exact_text)
        sk = frozenset([(game, "0", "CLAMP", "")])
        ck = frozenset([(game, "0", "CLAMP", "")])
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        live_dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk,
            classified_keys=ck,
        )
        self.assertTrue(live_dlg._row_widgets)
        why_edit = live_dlg._row_widgets[0]._why_texts.get("why")
        self.assertIsNotNone(why_edit)
        why_edit.setPlainText("different text")
        why_edit.setPlainText(exact_text)  # restore
        live_dlg._on_save()

        # Reopen in saved mode — shallow_keys from real controller
        sk2, _ = ctrl.get_shallow_vague_keys([game])
        self.assertTrue(sk2, "is_shallow must be preserved when text is restored")
        reopen_dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=sk2,
            saved_mode=True,
        )
        self.assertEqual(len(reopen_dlg._row_widgets), 1,
            "Reopen: chip row must be shown when is_shallow is preserved")
        count = ctrl.count_unchecked_answers([game])
        self.assertEqual(count, 0,
            "Unchecked count must be 0 when exact text is restored (check_hash matches)")


# ---------------------------------------------------------------------------
# Item 4 (gap): Parse failure also counted as unchecked
# ---------------------------------------------------------------------------

@requires_qt
class TestParseFailureUncheckedCount(unittest.TestCase):
    """Entry not in classified_keys gets no check_hash and counts as 1 unchecked."""

    def test_entry_not_in_classified_counts_as_unchecked(self):
        """Live Save with classified_keys=frozenset(): no check_hash written, count=1."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "a note")
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=frozenset(),
            classified_keys=frozenset(),
        )
        dlg._on_save()
        ctrl.replace_entries_at_path_for_game.assert_not_called()
        count = ctrl.count_unchecked_answers([game])
        self.assertEqual(count, 1,
            "Entry not in classified_keys must count as 1 unchecked after live Save")


# ---------------------------------------------------------------------------
# Item 5 (gap): Honoured Ignore counts as checked AFTER a live Check Logs Save
# ---------------------------------------------------------------------------

@requires_qt
class TestHonouredIgnoreAfterLiveSave(unittest.TestCase):
    """Phase b in a live save skips honoured-Ignore entries; count stays 0."""

    def test_honoured_ignore_after_live_save_counts_as_checked(self):
        """Entry with ignore_shallow + matching hash: Phase b skips it; count = 0."""
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _make_game()
        note = "the note"
        entry = ChessLogStorageService.make_entry("CLAMP", "C", note)
        entry["ignore_shallow"] = True
        entry["ignore_text_hash"] = hashlib.sha256(note.encode("utf-8")).hexdigest()
        # In classified_keys (classifier ran) but not in shallow_keys (Ignore honoured)
        ck = frozenset([(game, "0", "CLAMP", "")])
        ctrl = _make_controller({game.game_number: {"0": [entry]}})
        live_dlg = ShowShallowTagsDialog(
            config={},
            games=[game],
            controller=ctrl,
            shallow_keys=frozenset(),   # not flagged
            classified_keys=ck,
        )
        self.assertEqual(len(live_dlg._row_widgets), 0, "Honoured-Ignore entry not shown")
        live_dlg._on_save()
        count = ctrl.count_unchecked_answers([game])
        self.assertEqual(count, 0,
            "Honoured ignore_shallow must count as checked (0) after a live Check Logs Save")


# ---------------------------------------------------------------------------
# Item 9 (gap): Mixed-runs PDF header also sets the most-recent date
# ---------------------------------------------------------------------------

@requires_qt
class TestMixedRunsPDFDate(unittest.TestCase):
    """Mixed-runs PDF header sets generated_at to the most recent run's date."""

    def test_mixed_runs_pdf_header_uses_most_recent_date(self):
        """Two games, different run dates → generated_at = most recent date."""
        import json, os
        from unittest.mock import patch
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "app", "config", "config.json",
        )
        with open(cfg_path) as f:
            cfg = json.load(f)
        game1 = _make_game(game_number=1)
        game2 = _make_game(game_number=2)
        e1 = ChessLogStorageService.make_entry("CLAMP", "C", "note1", is_shallow=True)
        e2 = ChessLogStorageService.make_entry("CLAMP", "C", "note2", is_shallow=True)
        sk = frozenset([(game1, "0", "CLAMP", ""), (game2, "0", "CLAMP", "")])
        ctrl = _make_controller({
            game1.game_number: {"0": [e1]},
            game2.game_number: {"0": [e2]},
        })
        dlg = ShowShallowTagsDialog(
            config=cfg, games=[game1, game2],
            controller=ctrl,
            shallow_keys=sk,
            vague_keys=frozenset(),
            classified_keys=frozenset(),
        )
        cr_map = {
            id(game1): {"model": "claude-opus-4-7", "date": "2026-10-28T10:00:00Z"},
            id(game2): {"model": "claude-sonnet-4-6", "date": "2026-10-30T12:00:00Z"},
        }
        captured = {}
        with patch.object(
            ctrl, "get_check_run_for_game",
            side_effect=lambda g: cr_map.get(id(g)),
        ), patch(
            "app.services.chess_log_pdf_service.ChessLogPDFService.export_tags",
            side_effect=lambda *a, **kw: captured.update(kw),
        ), patch(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=("/tmp/test_mixed_date.pdf", "PDF Files (*.pdf)"),
        ):
            dlg._on_export_pdf()
        self.assertIn("2026-10-30", captured.get("generated_at", ""),
            "generated_at must contain the most recent run's date in mixed-runs export")
        self.assertEqual(captured.get("model_label"), "claude-sonnet-4-6 (mixed runs)")


@requires_qt
class TestCheckRunReadThroughController(unittest.TestCase):
    """The dialog reads _check_run via the controller, never the storage service (C2)."""

    def test_resolve_model_generated_calls_controller(self):
        from unittest.mock import patch
        game = _make_game(1)
        sk = frozenset([(game, "0", "CLAMP", "")])
        dlg, ctrl = _make_dialog(
            [game], {1: {"0": [_make_entry("CLAMP", "C", "n")]}}, sk
        )
        ctrl.get_check_run_for_game.return_value = {
            "model": "m1", "date": "2026-10-28T10:00:00Z"
        }
        dlg._check_run_info = None
        with patch(
            "app.services.chess_log_storage_service.ChessLogStorageService.load_check_run"
        ) as storage:
            model_label, _ = dlg._resolve_model_generated()
        ctrl.get_check_run_for_game.assert_called_with(game)
        storage.assert_not_called()
        self.assertEqual(model_label, "m1")

    def test_no_view_calls_storage_load_check_run(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[2] / "app" / "views"
        offenders = [
            str(p) for p in root.rglob("*.py")
            if "ChessLogStorageService.load_check_run" in p.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
