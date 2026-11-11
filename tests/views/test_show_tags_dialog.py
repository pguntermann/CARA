"""Tests for ShowTagsDialog.

Requires a working Qt platform plugin (CI uses QT_QPA_PLATFORM=offscreen).
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


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel, QPlainTextEdit, QScrollArea
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

# ---------------------------------------------------------------------------
# Minimal PGN helpers
# ---------------------------------------------------------------------------

MAINLINE_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)

SECOND_PGN = (
    '[Event "T"][Site "?"][Date "2026.02.01"]'
    '[Round "?"][White "X"][Black "Y"][Result "1-0"]\n\n'
    "1. d4 d5 *\n"
)


def _make_game_data(pgn: str = MAINLINE_PGN, game_number: int = 1):
    from app.models.database_model import GameData
    return GameData(game_number=game_number, pgn=pgn)


def _make_controller(paths_data: dict):
    ctrl = MagicMock()
    ctrl.get_tags_for_game.return_value = paths_data
    ctrl.game_has_any_tags.return_value = bool(paths_data)
    ctrl.replace_entries_at_path_for_game = MagicMock()
    return ctrl


def _make_entry(preset, cat, why="", ignore_shallow=False):
    from app.services.chess_log_storage_service import ChessLogStorageService
    return ChessLogStorageService.make_entry(preset, cat, why, ignore_shallow=ignore_shallow)


def _make_dialog(paths_data: dict, pgn: str = MAINLINE_PGN):
    from app.views.dialogs.show_tags_dialog import ShowTagsDialog
    game_data = _make_game_data(pgn)
    ctrl = _make_controller(paths_data)
    return ShowTagsDialog({}, [game_data], ctrl), ctrl


# ---------------------------------------------------------------------------
# Row count and ordering
# ---------------------------------------------------------------------------

@requires_qt
class TestRowCount(unittest.TestCase):
    def test_one_row_per_move_preset_pair(self):
        # Move at path "0" has CLAMP, move at "0.0" has CLAMP+CCT → 3 rows
        paths_data = {
            "0": [_make_entry("CLAMP", "C")],
            "0.0": [
                _make_entry("CLAMP", "L"),
                _make_entry("CCT", "Threats"),
            ],
        }
        dlg, _ = _make_dialog(paths_data)
        # "0" → 1 row (CLAMP); "0.0" → 2 rows (CLAMP + CCT)
        self.assertEqual(len(dlg._row_widgets), 3)

    def test_three_clamp_rows_plus_one_cct(self):
        paths_data = {
            "0": [_make_entry("CLAMP", "C")],
            "0.0": [_make_entry("CLAMP", "L")],
            "0.0.0": [
                _make_entry("CLAMP", "M"),
                _make_entry("CCT", "Checks"),
            ],
        }
        dlg, _ = _make_dialog(paths_data)
        self.assertEqual(len(dlg._row_widgets), 4)

    def test_empty_tags_means_zero_rows(self):
        dlg, _ = _make_dialog({})
        self.assertEqual(len(dlg._row_widgets), 0)


@requires_qt
class TestRowOrdering(unittest.TestCase):
    def test_rows_sorted_by_ply_ascending(self):
        # "0" = ply 1 (White's first move), "0.0.0" = ply 3
        paths_data = {
            "0.0.0": [_make_entry("CLAMP", "A")],
            "0": [_make_entry("CLAMP", "C")],
            "0.0": [_make_entry("CLAMP", "L")],
        }
        dlg, _ = _make_dialog(paths_data)
        preset_labels = [rw._preset for rw in dlg._row_widgets]
        # All CLAMP rows sorted by ply — label is CLAMP for all; check via rows_data paths
        paths = [r[0] for r in dlg._rows_data]
        self.assertEqual(paths, ["0", "0.0", "0.0.0"])

    def test_preset_order_within_same_ply(self):
        # One move ("0") tagged with CLAMP and CCT
        paths_data = {
            "0": [
                _make_entry("CCT", "Threats"),
                _make_entry("CLAMP", "C"),
            ],
        }
        dlg, _ = _make_dialog(paths_data)
        presets = [r[1] for r in dlg._rows_data]
        # Should be CLAMP first, CCT second
        self.assertEqual(presets, ["CLAMP", "CCT"])


# ---------------------------------------------------------------------------
# 3x3 rows
# ---------------------------------------------------------------------------

@requires_qt
class TestThreeXThreeRow(unittest.TestCase):
    def test_3x3_row_counts_as_one_row(self):
        paths_data = {
            "0": [
                _make_entry("3x3", "Why1", "I wanted to develop"),
                _make_entry("3x3", "Why2", "It lost tempo"),
                _make_entry("3x3", "Why3", "Engine prefers Nf3"),
            ],
        }
        dlg, _ = _make_dialog(paths_data)
        self.assertEqual(len(dlg._row_widgets), 1)

    def test_3x3_row_has_no_checkboxes(self):
        paths_data = {
            "0": [_make_entry("3x3", "Why1", "text")],
        }
        dlg, _ = _make_dialog(paths_data)
        row = dlg._row_widgets[0]
        self.assertEqual(len(row._checkboxes), 0)

    def test_3x3_row_text_contains_all_four_sentences(self):
        paths_data = {
            "0": [
                _make_entry("3x3", "Why1", "I wanted to develop"),
                _make_entry("3x3", "Why2", "It lost tempo"),
                _make_entry("3x3", "Why3", "Engine prefers Nf3"),
                _make_entry("3x3", "Why4", "Slow down next time"),
            ],
        }
        dlg, _ = _make_dialog(paths_data)
        row = dlg._row_widgets[0]
        self.assertIn("Why1", row._why_texts)
        self.assertIn("Why2", row._why_texts)
        self.assertIn("Why3", row._why_texts)
        self.assertIn("Why4", row._why_texts)
        self.assertIn("develop", row._why_texts["Why1"].toPlainText())
        self.assertIn("tempo", row._why_texts["Why2"].toPlainText())
        self.assertIn("Nf3", row._why_texts["Why3"].toPlainText())
        self.assertIn("Slow down", row._why_texts["Why4"].toPlainText())


# ---------------------------------------------------------------------------
# Always-editable: checkboxes and text are editable on open
# ---------------------------------------------------------------------------

@requires_qt
class TestAlwaysEditable(unittest.TestCase):
    def test_checkboxes_enabled_on_open(self):
        paths_data = {"0": [_make_entry("CLAMP", "C")]}
        dlg, _ = _make_dialog(paths_data)
        row = dlg._row_widgets[0]
        for cb in row._checkboxes.values():
            self.assertTrue(cb.isEnabled())

    def test_text_editable_on_open(self):
        paths_data = {"0": [_make_entry("CLAMP", "C", "missed it")]}
        dlg, _ = _make_dialog(paths_data)
        row = dlg._row_widgets[0]
        for te in row._why_texts.values():
            self.assertFalse(te.isReadOnly())

    def test_no_edit_button(self):
        paths_data = {"0": [_make_entry("CLAMP", "C")]}
        dlg, _ = _make_dialog(paths_data)
        self.assertFalse(hasattr(dlg, "_edit_btn"))

    def test_tag_row_widget_has_no_set_flagged(self):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        paths_data = {"0": [_make_entry("CLAMP", "C")]}
        dlg, _ = _make_dialog(paths_data)
        row = dlg._row_widgets[0]
        self.assertFalse(hasattr(row, "set_flagged"))


# ---------------------------------------------------------------------------
# OK and Cancel persistence
# ---------------------------------------------------------------------------

@requires_qt
class TestPersistence(unittest.TestCase):
    def test_ok_with_no_changes_does_not_write(self):
        paths_data = {"0": [_make_entry("CLAMP", "C")]}
        dlg, ctrl = _make_dialog(paths_data)
        dlg._save_btn.click()
        ctrl.replace_entries_at_path_for_game.assert_not_called()

    def test_ok_after_edit_persists_changed_row(self):
        paths_data = {"0": [_make_entry("CLAMP", "C", "old why")]}
        dlg, ctrl = _make_dialog(paths_data)
        # Change the why text (fields always editable — no edit button needed)
        row = dlg._row_widgets[0]
        row._why_texts["why"].setPlainText("new why")
        dlg._save_btn.click()
        ctrl.replace_entries_at_path_for_game.assert_called_once()
        call_args = ctrl.replace_entries_at_path_for_game.call_args
        _game, path_key, preset, new_entries = call_args[0]
        self.assertEqual(path_key, "0")
        self.assertEqual(preset, "CLAMP")
        self.assertTrue(any(e.get("why") == "new why" for e in new_entries))

    def test_ok_writes_only_changed_rows(self):
        paths_data = {
            "0": [_make_entry("CLAMP", "C", "unchanged")],
            "0.0": [_make_entry("CLAMP", "L", "will change")],
        }
        dlg, ctrl = _make_dialog(paths_data)
        # Modify only the second row
        dlg._row_widgets[1]._why_texts["why"].setPlainText("changed!")
        dlg._save_btn.click()
        self.assertEqual(ctrl.replace_entries_at_path_for_game.call_count, 1)
        call_args = ctrl.replace_entries_at_path_for_game.call_args
        self.assertEqual(call_args[0][1], "0.0")

    def test_ok_preserves_other_preset_at_same_path(self):
        """Editing CLAMP row must NOT write to the CCT preset at the same path."""
        paths_data = {
            "0": [
                _make_entry("CLAMP", "C", "clamp why"),
                _make_entry("CCT", "Threats", "cct why"),
            ],
        }
        dlg, ctrl = _make_dialog(paths_data)
        # Edit only the CLAMP row
        clamp_row_idx = next(
            i for i, r in enumerate(dlg._rows_data) if r[1] == "CLAMP"
        )
        dlg._row_widgets[clamp_row_idx]._why_texts["why"].setPlainText("new clamp")
        dlg._save_btn.click()
        # Only one replace call (for CLAMP)
        self.assertEqual(ctrl.replace_entries_at_path_for_game.call_count, 1)
        call_args = ctrl.replace_entries_at_path_for_game.call_args
        self.assertEqual(call_args[0][2], "CLAMP")

    def test_cancel_after_edit_does_not_write(self):
        paths_data = {"0": [_make_entry("CLAMP", "C", "original")]}
        dlg, ctrl = _make_dialog(paths_data)
        dlg._row_widgets[0]._why_texts["why"].setPlainText("changed but cancelled")
        dlg._cancel_btn.click()
        ctrl.replace_entries_at_path_for_game.assert_not_called()


# ---------------------------------------------------------------------------
# Scrollability
# ---------------------------------------------------------------------------

@requires_qt
class TestScrollability(unittest.TestCase):
    def test_dialog_has_scroll_area_for_many_rows(self):
        paths_data = {}
        for i in range(40):
            path = ".".join(["0"] * (i + 1))
            paths_data[path] = [_make_entry("CLAMP", "C", f"moment {i}")]
        dlg, _ = _make_dialog(paths_data)
        scroll_areas = dlg.findChildren(QScrollArea)
        self.assertTrue(len(scroll_areas) >= 1)


# ---------------------------------------------------------------------------
# Checkbox state reflects saved data
# ---------------------------------------------------------------------------

@requires_qt
class TestCheckboxState(unittest.TestCase):
    def test_clamp_checkbox_ticks_reflect_saved_cat(self):
        paths_data = {
            "0": [_make_entry("CLAMP", "C")],
        }
        dlg, _ = _make_dialog(paths_data)
        row = dlg._row_widgets[0]
        self.assertTrue(row._checkboxes["C"].isChecked())
        for cat in ("L", "A", "M", "P"):
            self.assertFalse(row._checkboxes[cat].isChecked())

    def test_multiple_clamp_cats_all_ticked(self):
        paths_data = {
            "0": [
                _make_entry("CLAMP", "C"),
                _make_entry("CLAMP", "L"),
            ],
        }
        dlg, _ = _make_dialog(paths_data)
        row = dlg._row_widgets[0]
        self.assertTrue(row._checkboxes["C"].isChecked())
        self.assertTrue(row._checkboxes["L"].isChecked())
        for cat in ("A", "M", "P"):
            self.assertFalse(row._checkboxes[cat].isChecked())


# ---------------------------------------------------------------------------
# Zero-category round-trip (cat="" legitimate saves must not be deleted on OK)
# ---------------------------------------------------------------------------

@requires_qt
class TestZeroCategoryRoundtrip(unittest.TestCase):
    def test_zero_category_moment_edit_preserves_entry(self):
        """A moment stored with cat='' survives OK when why text is edited."""
        paths_data = {"0": [_make_entry("CLAMP", "", "original note")]}
        dlg, ctrl = _make_dialog(paths_data)
        dlg._row_widgets[0]._why_texts["why"].setPlainText("updated note")
        dlg._save_btn.click()
        ctrl.replace_entries_at_path_for_game.assert_called_once()
        _, _, _, new_entries = ctrl.replace_entries_at_path_for_game.call_args[0]
        self.assertEqual(len(new_entries), 1)
        self.assertEqual(new_entries[0]["cat"], "")
        self.assertEqual(new_entries[0]["why"], "updated note")

    def test_uncheck_last_box_keeps_why_as_zero_category(self):
        """Unchecking the last box but leaving why text saves as cat='' (mirrors MomentDialog)."""
        paths_data = {"0": [_make_entry("CLAMP", "C", "note")]}
        dlg, ctrl = _make_dialog(paths_data)
        dlg._row_widgets[0]._checkboxes["C"].setChecked(False)
        dlg._save_btn.click()
        ctrl.replace_entries_at_path_for_game.assert_called_once()
        _, _, _, new_entries = ctrl.replace_entries_at_path_for_game.call_args[0]
        self.assertEqual(len(new_entries), 1)
        self.assertEqual(new_entries[0]["cat"], "")
        self.assertEqual(new_entries[0]["why"], "note")

    def test_uncheck_all_and_clear_why_is_intentional_delete(self):
        """Unchecking all boxes AND clearing why text deletes the moment (explicit gesture)."""
        paths_data = {"0": [_make_entry("CLAMP", "C", "note")]}
        dlg, ctrl = _make_dialog(paths_data)
        dlg._row_widgets[0]._checkboxes["C"].setChecked(False)
        dlg._row_widgets[0]._why_texts["why"].setPlainText("")
        dlg._save_btn.click()
        ctrl.replace_entries_at_path_for_game.assert_called_once()
        _, _, _, new_entries = ctrl.replace_entries_at_path_for_game.call_args[0]
        self.assertEqual(new_entries, [])


# ---------------------------------------------------------------------------
# Multi-game dialog shows game headers
# ---------------------------------------------------------------------------

@requires_qt
class TestMultiGameDialog(unittest.TestCase):
    def _make_multi_game_dialog(self, paths1=None, paths2=None):
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        from app.models.database_model import GameData

        game1 = GameData(game_number=1, pgn=MAINLINE_PGN, white="Alice", black="Bob")
        game2 = GameData(game_number=2, pgn=SECOND_PGN, white="Carol", black="Dave")
        paths1 = paths1 or {"0": [_make_entry("CLAMP", "C")]}
        paths2 = paths2 or {"0": [_make_entry("CLAMP", "L")]}

        ctrl = MagicMock()
        ctrl.get_tags_for_game.side_effect = lambda g: paths1 if g is game1 else paths2
        ctrl.replace_entries_at_path_for_game = MagicMock()

        dlg = ShowTagsDialog({}, [game1, game2], ctrl)
        return dlg, ctrl, game1, game2

    def test_multi_game_title(self):
        dlg, _, _, _ = self._make_multi_game_dialog()
        self.assertIn("all games", dlg.windowTitle().lower())

    def test_single_game_title_is_not_multi(self):
        dlg, _ = _make_dialog({"0": [_make_entry("CLAMP", "C")]})
        self.assertNotIn("all games", dlg.windowTitle().lower())

    def test_multi_game_has_game_header_labels(self):
        dlg, _, game1, game2 = self._make_multi_game_dialog()
        # Game headers are QLabel children containing player names
        labels = dlg.findChildren(QLabel)
        label_texts = [lbl.text() for lbl in labels]
        # At least one label should contain Alice (game1 header)
        self.assertTrue(any("Alice" in t for t in label_texts))
        # At least one label should contain Carol (game2 header)
        self.assertTrue(any("Carol" in t for t in label_texts))

    def test_single_game_shows_game_header(self):
        from app.models.database_model import GameData
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog

        game = GameData(game_number=1, pgn=MAINLINE_PGN, white="UniqueNameXYZ", black="Bob")
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = {"0": [_make_entry("CLAMP", "C")]}
        dlg = ShowTagsDialog({}, [game], ctrl)
        labels = dlg.findChildren(QLabel)
        label_texts = [lbl.text() for lbl in labels]
        self.assertTrue(
            any("UniqueNameXYZ" in t for t in label_texts),
            "Single-game Show Logged Moments must show the game header",
        )

    def test_multi_game_row_count_spans_all_games(self):
        dlg, _, _, _ = self._make_multi_game_dialog(
            paths1={"0": [_make_entry("CLAMP", "C")]},
            paths2={"0": [_make_entry("CLAMP", "L")], "0.0": [_make_entry("CLAMP", "M")]},
        )
        self.assertEqual(len(dlg._row_widgets), 3)

    def test_multi_game_ok_writes_to_correct_game(self):
        dlg, ctrl, game1, game2 = self._make_multi_game_dialog()
        # Edit the second row (game2's row)
        dlg._row_widgets[1]._why_texts["why"].setPlainText("edited g2")
        dlg._save_btn.click()
        ctrl.replace_entries_at_path_for_game.assert_called_once()
        call_args = ctrl.replace_entries_at_path_for_game.call_args[0]
        # First arg should be game2
        self.assertIs(call_args[0], game2)

    def test_single_game_pdf_export_sets_header(self):
        """Issue #55: single-game PDF export must pass a non-None header to the PDF service."""
        from app.models.database_model import GameData
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog

        game = GameData(game_number=1, pgn=MAINLINE_PGN, white="PDFWhite", black="PDFBlack",
                        result="1-0", date="2026.01.01", moves=10)
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = {"0": [_make_entry("CLAMP", "C", "note")]}
        ctrl.replace_entries_at_path_for_game = MagicMock()
        dlg = ShowTagsDialog({}, [game], ctrl)

        captured = {}

        def fake_export(path, groups, **kwargs):
            captured["groups"] = groups

        with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                   return_value=("/tmp/test_show_tags.pdf", "")):
            with patch("app.services.chess_log_pdf_service.ChessLogPDFService.export_tags",
                       side_effect=fake_export):
                dlg._on_export_pdf()

        self.assertIn("groups", captured, "export_tags must have been called")
        groups = captured["groups"]
        self.assertEqual(len(groups), 1)
        header = groups[0]["header"]
        self.assertIsNotNone(header, "Single-game PDF must have a non-None header")
        self.assertIn("PDFWhite", header)


# ---------------------------------------------------------------------------
# Ignore checkbox on _TagRowWidget
# ---------------------------------------------------------------------------

@requires_qt
class TestIgnoreCheckbox(unittest.TestCase):
    def _make_row(self, entries, show_ignore=False):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def test_no_ignore_checkbox_by_default(self):
        row = self._make_row([_make_entry("CLAMP", "C")])
        self.assertIsNone(row._ignore_check)

    def test_ignore_checkbox_rendered_when_requested(self):
        row = self._make_row([_make_entry("CLAMP", "C")], show_ignore=True)
        self.assertIsNotNone(row._ignore_check)
        self.assertIsInstance(row._ignore_check, QCheckBox)

    def test_ignore_checkbox_starts_unchecked_when_entry_has_no_flag(self):
        row = self._make_row([_make_entry("CLAMP", "C")], show_ignore=True)
        self.assertFalse(row._ignore_check.isChecked())

    def test_ignore_checkbox_starts_checked_when_entry_flagged(self):
        entry = _make_entry("CLAMP", "C", ignore_shallow=True)
        row = self._make_row([entry], show_ignore=True)
        self.assertTrue(row._ignore_check.isChecked())

    def test_get_current_entries_includes_ignore_shallow_when_checked(self):
        row = self._make_row([_make_entry("CLAMP", "C")], show_ignore=True)
        row._ignore_check.setChecked(True)
        entries = row.get_current_entries()
        self.assertTrue(all(e.get("ignore_shallow") for e in entries))

    def test_get_current_entries_omits_ignore_shallow_when_unchecked(self):
        row = self._make_row([_make_entry("CLAMP", "C")], show_ignore=True)
        row._ignore_check.setChecked(False)
        entries = row.get_current_entries()
        self.assertFalse(any(e.get("ignore_shallow") for e in entries))

    def test_show_tags_dialog_rows_have_no_ignore_checkbox(self):
        """ShowTagsDialog never passes show_ignore_checkbox=True to rows."""
        paths_data = {"0": [_make_entry("CLAMP", "C")]}
        dlg, _ = _make_dialog(paths_data)
        for row in dlg._row_widgets:
            self.assertIsNone(row._ignore_check)


# ---------------------------------------------------------------------------
# ignore_shallow preservation when show_ignore_checkbox=False
# ---------------------------------------------------------------------------

@requires_qt
class TestIgnoreShallowPreservation(unittest.TestCase):
    def _make_row(self, entries):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=False,
        )

    def test_ignore_shallow_cleared_when_text_changes(self):
        """Editing why-text in Show Tags clears the ignore_shallow flag."""
        import hashlib
        entry = _make_entry("CLAMP", "C", "original note", ignore_shallow=True)
        entry["ignore_text_hash"] = hashlib.sha256(b"original note").hexdigest()
        row = self._make_row([entry])
        row._why_texts["why"].setPlainText("edited note")
        entries = row.get_current_entries()
        self.assertFalse(any(e.get("ignore_shallow") for e in entries))

    def test_ignore_shallow_preserved_when_text_unchanged(self):
        """No text change → ignore_shallow is preserved through get_current_entries."""
        import hashlib
        entry = _make_entry("CLAMP", "C", "same note", ignore_shallow=True)
        entry["ignore_text_hash"] = hashlib.sha256(b"same note").hexdigest()
        row = self._make_row([entry])
        # Text unchanged — widget was initialised with "same note"
        entries = row.get_current_entries()
        self.assertTrue(all(e.get("ignore_shallow") for e in entries))

    def test_no_ignore_shallow_when_entry_never_had_it(self):
        entry = _make_entry("CLAMP", "C", "note")
        row = self._make_row([entry])
        entries = row.get_current_entries()
        self.assertFalse(any(e.get("ignore_shallow") for e in entries))


@requires_qt
class TestBestMoveArrow(unittest.TestCase):
    """Tests confirming best_move is resolved and threaded into _TagRowWidget."""

    def _make_row_with_best(self, best_move=None):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        import chess
        entry = _make_entry("CLAMP", "C", "note")
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=[entry],
            move_label="1. e4",
            fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            played_move=chess.Move.from_uci("e2e4"),
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            best_move=best_move,
        )

    def test_row_widget_stores_best_move_none(self):
        row = self._make_row_with_best(None)
        self.assertIsNone(row._best_move)

    def test_row_widget_stores_best_move(self):
        import chess
        best = chess.Move.from_uci("d2d4")
        row = self._make_row_with_best(best)
        self.assertEqual(row._best_move, best)

    def test_snapshot_carries_best_move(self):
        import chess
        best = chess.Move.from_uci("d2d4")
        row = self._make_row_with_best(best)
        snap = row.snapshot()
        self.assertEqual(snap.best_move, best)

    def test_snapshot_best_move_none_when_unset(self):
        row = self._make_row_with_best(None)
        snap = row.snapshot()
        self.assertIsNone(snap.best_move)

    def test_dialog_calls_resolve_best_move(self):
        """ShowTagsDialog calls resolve_best_move_for_path for each row."""
        from unittest.mock import patch
        import chess
        paths_data = {"0": [_make_entry("CLAMP", "C", "note")]}
        fake_best = chess.Move.from_uci("d2d4")
        with patch(
            "app.views.dialogs.show_tags_dialog.resolve_best_move_for_path",
            return_value=fake_best,
        ) as mock_resolve:
            dlg, _ = _make_dialog(paths_data)
        self.assertTrue(mock_resolve.called)
        # The one row widget should carry the resolved best move.
        self.assertEqual(dlg._row_widgets[0]._best_move, fake_best)

    def test_dialog_passes_none_best_move_when_resolver_returns_none(self):
        from unittest.mock import patch
        paths_data = {"0": [_make_entry("CLAMP", "C", "note")]}
        with patch(
            "app.views.dialogs.show_tags_dialog.resolve_best_move_for_path",
            return_value=None,
        ):
            dlg, _ = _make_dialog(paths_data)
        self.assertIsNone(dlg._row_widgets[0]._best_move)


@requires_qt
class TestShowTagsDialogThemeColors(unittest.TestCase):
    """ShowTagsDialog must route separator and text-editor colors through config."""

    def _make_themed_dialog(self, moment_cfg: dict):
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        config = {"ui": {"dialogs": {"moment": moment_cfg}}}
        paths_data = {
            "0": [_make_entry("CLAMP", "C", "first")],
            "0.0": [_make_entry("CLAMP", "L", "second")],
        }
        game_data = _make_game_data(MAINLINE_PGN)
        ctrl = _make_controller(paths_data)
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.views.dialogs.show_tags_dialog.resolve_best_move_for_path",
            return_value=None,
        ):
            dlg = ShowTagsDialog(config, [game_data], ctrl)
        return dlg

    def test_separator_uses_config_color(self):
        dlg = self._make_themed_dialog({"separator_color": [10, 20, 30]})
        sep = dlg._make_separator()
        self.assertIn("rgb(10,20,30)", sep.styleSheet())

    def test_separator_fallback_dark(self):
        dlg = self._make_themed_dialog({})
        sep = dlg._make_separator()
        self.assertIn("rgb(70,70,75)", sep.styleSheet())

    def test_text_widget_uses_input_bg_from_config(self):
        from PyQt6.QtWidgets import QPlainTextEdit
        dlg = self._make_themed_dialog({"inputs": {"background_color": [5, 6, 7], "border_color": [8, 9, 10]}})
        te = QPlainTextEdit()
        dlg._row_widgets[0]._style_text_widget(te)
        self.assertIn("rgb(5,6,7)", te.styleSheet())


# ---------------------------------------------------------------------------
# Mini-board orientation follows the mover at the tagged ply, per row
# ---------------------------------------------------------------------------

@requires_qt
class TestMiniBoardOrientationMoverAtPly(unittest.TestCase):
    """Row orientation comes from pre_board.turn at the tagged ply, not player selection."""

    def test_white_ply_row_not_flipped(self):
        # MAINLINE_PGN: path "0" is 1.e4 — White to move → not flipped
        dlg, _ = _make_dialog({"0": [_make_entry("CLAMP", "C")]})
        self.assertFalse(dlg._row_widgets[0]._is_flipped)

    def test_black_ply_row_is_flipped(self):
        # MAINLINE_PGN: path "0.0" is 1...e5 — Black to move → flipped
        dlg, _ = _make_dialog({"0.0": [_make_entry("CLAMP", "C")]})
        self.assertTrue(dlg._row_widgets[0]._is_flipped)

    def test_snapshot_carries_flip_for_black_ply(self):
        dlg, _ = _make_dialog({"0.0": [_make_entry("CLAMP", "C")]})
        self.assertTrue(dlg._row_widgets[0].snapshot().is_flipped)

    def test_snapshot_carries_false_for_white_ply(self):
        dlg, _ = _make_dialog({"0": [_make_entry("CLAMP", "C")]})
        self.assertFalse(dlg._row_widgets[0].snapshot().is_flipped)


# ---------------------------------------------------------------------------
# Font and height wiring — reads from ui.dialogs.show_tags.*
# ---------------------------------------------------------------------------

@requires_qt
class TestShowTagsFontAndHeightWiring(unittest.TestCase):
    """_TagRowWidget reads font family/size and text-edit heights from the
    ui.dialogs.show_tags namespace, never from ui.dialogs.moment."""

    def _make_row(self, show_tags_cfg: dict, preset: str = "CLAMP"):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        config = {"ui": {"dialogs": {"show_tags": show_tags_cfg}}}
        entry = _make_entry(preset, "C" if preset != "3x3" else "Why1", "note")
        return _TagRowWidget(
            config=config,
            preset=preset,
            entries=[entry],
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )

    def test_label_font_size_from_config(self):
        row = self._make_row({"label_font_size": 14})
        self.assertEqual(row._label_font_size, 14)

    def test_label_font_family_from_config(self):
        row = self._make_row({"label_font_family": "Courier New"})
        self.assertIn("Courier New", row._label_font_family)

    def test_input_font_size_from_config(self):
        row = self._make_row({"inputs": {"font_size": 13}})
        self.assertEqual(row._input_font_size, 13)

    def test_input_font_family_from_config(self):
        row = self._make_row({"inputs": {"font_family": "Monaco"}})
        self.assertIn("Monaco", row._input_font_family)

    def test_fit_min_lines_from_config(self):
        row = self._make_row({"fit_min_lines": 1, "fit_max_lines": 6})
        self.assertEqual(row._fit_min_lines, 1)
        self.assertEqual(row._fit_max_lines, 6)
        te = row._why_texts.get("why")
        self.assertIsNotNone(te)
        self.assertGreater(te.minimumHeight(), 0)

    def test_fit_max_lines_caps_height(self):
        from app.views.dialogs.show_tags_dialog import _FitTextEdit
        te = _FitTextEdit("", fit_min_lines=1, fit_max_lines=3)
        te.setFixedWidth(400)
        long_text = "\n".join(f"Line {i}" for i in range(10))
        te.setPlainText(long_text)
        te_max = _FitTextEdit("", fit_min_lines=1, fit_max_lines=6)
        te_max.setFixedWidth(400)
        te_max.setPlainText(long_text)
        self.assertLessEqual(te.height(), te_max.height())

    def test_fit_min_lines_3x3_from_config(self):
        row = self._make_row({"fit_min_lines": 2, "fit_max_lines": 6}, preset="3x3")
        self.assertEqual(row._fit_min_lines, 2)
        te = list(row._why_texts.values())[0]
        self.assertGreater(te.minimumHeight(), 0)

    def test_why_text_edit_has_font_applied(self):
        row = self._make_row({"inputs": {"font_size": 13}})
        te = row._why_texts.get("why")
        self.assertIsNotNone(te)
        self.assertEqual(te.font().pointSize(), 13)

    def test_3x3_text_edit_has_font_applied(self):
        row = self._make_row({"inputs": {"font_size": 12}}, preset="3x3")
        for te in row._why_texts.values():
            self.assertEqual(te.font().pointSize(), 12)

    def test_defaults_used_when_config_empty(self):
        row = self._make_row({})
        self.assertEqual(row._label_font_size, 11)
        self.assertEqual(row._input_font_size, 11)
        self.assertEqual(row._fit_min_lines, 1)
        self.assertEqual(row._fit_max_lines, 6)
        te_why = row._why_texts.get("why")
        self.assertIsNotNone(te_why)
        self.assertGreater(te_why.minimumHeight(), 0)
        row3 = self._make_row({}, preset="3x3")
        te_3x3 = list(row3._why_texts.values())[0]
        # Both use same defaults; same empty content gives same height
        self.assertEqual(te_why.minimumHeight(), te_3x3.minimumHeight())

    def test_moment_namespace_not_read_for_fonts(self):
        """A moment config with different font sizes must NOT affect _TagRowWidget."""
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        config = {
            "ui": {
                "dialogs": {
                    "moment": {"label_font_size": 99, "inputs": {"font_size": 88}},
                    "show_tags": {"label_font_size": 11, "inputs": {"font_size": 11}},
                }
            }
        }
        entry = _make_entry("CLAMP", "C", "note")
        row = _TagRowWidget(
            config=config,
            preset="CLAMP",
            entries=[entry],
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )
        self.assertEqual(row._label_font_size, 11)
        self.assertEqual(row._input_font_size, 11)


# ---------------------------------------------------------------------------
# Resize grip
# ---------------------------------------------------------------------------

@requires_qt
class TestShowTagsDialogResizeGrip(unittest.TestCase):
    def test_resize_grip_installed(self):
        dlg, _ = _make_dialog({"0": [_make_entry("CLAMP", "C")]})
        self.assertTrue(hasattr(dlg, "_cara_themed_resize_grip"))

    def test_resize_grip_installed_empty_dialog(self):
        dlg, _ = _make_dialog({})
        self.assertTrue(hasattr(dlg, "_cara_themed_resize_grip"))


# ---------------------------------------------------------------------------
# A3 / B2: is_shallow and is_vague survive the Ignore → Save → untick → Save cycle
# ---------------------------------------------------------------------------

@requires_qt
class TestIgnoreFlagsPreservation3x3(unittest.TestCase):
    """A3: is_shallow / is_vague must survive the tick-Ignore → Save → untick → Save round-trip."""

    def _make_row(self, entries, show_ignore=True):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="3x3",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _by_cat(self, entries):
        return {e["cat"]: e for e in entries}

    def test_a3_why4_vague_preserved_after_ignore_then_untick(self):
        """A3 core: is_vague on Why4 must survive tick Ignore → Save → untick → Save."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "I attacked too early", is_shallow=True),
            ChessLogStorageService.make_entry("3x3", "Why2", "Missed the fork"),
            ChessLogStorageService.make_entry("3x3", "Why3", "Engine prefers Nf3"),
            ChessLogStorageService.make_entry("3x3", "Why4", "I need to slow down", is_vague=True),
        ]

        # Step 1 (Check Logs dialog): tick Ignore on Why4, Save
        row = self._make_row(entries, show_ignore=True)
        self.assertIn("Why4", row._ignore_checks)
        row._ignore_checks["Why4"].setChecked(True)
        saved = row.get_current_entries()

        by_cat = self._by_cat(saved)
        self.assertEqual(by_cat["Why4"]["why"], "I need to slow down")
        self.assertTrue(by_cat["Why4"].get("ignore_shallow"), "ignore_shallow must be set after tick")
        self.assertTrue(by_cat["Why4"].get("is_vague"), "is_vague must survive first Save")

        # Step 2 (Show Logged Moments): is_ignored=True so checkbox appears; untick, Save
        row2 = self._make_row(saved, show_ignore=False)
        self.assertIn("Why4", row2._ignore_checks,
                      "checkbox must be shown for already-ignored entry")
        row2._ignore_checks["Why4"].setChecked(False)
        final = row2.get_current_entries()

        by_cat2 = self._by_cat(final)
        self.assertEqual(by_cat2["Why4"]["why"], "I need to slow down")
        self.assertFalse(by_cat2["Why4"].get("ignore_shallow"),
                         "ignore_shallow must be cleared after untick")
        self.assertTrue(by_cat2["Why4"].get("is_vague"),
                        "is_vague must survive the untick (Bug B)")

    def test_why1_is_shallow_preserved_after_ignore_untick(self):
        """is_shallow on Why1 must survive tick Ignore → untick round-trip."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "Attacked too early", is_shallow=True),
            ChessLogStorageService.make_entry("3x3", "Why4", "Lesson text"),
        ]

        row = self._make_row(entries, show_ignore=True)
        row._ignore_checks["Why1"].setChecked(True)
        saved = row.get_current_entries()
        self.assertTrue(self._by_cat(saved)["Why1"].get("is_shallow"))

        row2 = self._make_row(saved, show_ignore=False)
        row2._ignore_checks["Why1"].setChecked(False)
        final = row2.get_current_entries()
        self.assertTrue(self._by_cat(final)["Why1"].get("is_shallow"),
                        "is_shallow must survive untick")

    def test_all_four_texts_unchanged_through_ignore_untick_cycle(self):
        """All four Why texts must be byte-identical after tick-Ignore → Save → untick → Save."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        texts = {
            "Why1": "I attacked too early — rushed development",
            "Why2": "I missed the knight fork on d5",
            "Why3": "Engine recommends Nf3 before castling",
            "Why4": "Next time I need to slow down and calculate",
        }
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", texts["Why1"], is_shallow=True),
            ChessLogStorageService.make_entry("3x3", "Why2", texts["Why2"]),
            ChessLogStorageService.make_entry("3x3", "Why3", texts["Why3"]),
            ChessLogStorageService.make_entry("3x3", "Why4", texts["Why4"], is_vague=True),
        ]

        # Tick Ignore on both Why1 and Why4, Save
        row = self._make_row(entries, show_ignore=True)
        for k in ("Why1", "Why4"):
            if k in row._ignore_checks:
                row._ignore_checks[k].setChecked(True)
        saved = row.get_current_entries()
        for cat, text in texts.items():
            m = next((e for e in saved if e["cat"] == cat), None)
            self.assertIsNotNone(m, f"{cat} missing after first Save")
            self.assertEqual(m["why"], text, f"{cat} text changed after first Save")

        # Untick all, Save again
        row2 = self._make_row(saved, show_ignore=False)
        for cb in row2._ignore_checks.values():
            cb.setChecked(False)
        final = row2.get_current_entries()
        for cat, text in texts.items():
            m = next((e for e in final if e["cat"] == cat), None)
            self.assertIsNotNone(m, f"{cat} missing after second Save")
            self.assertEqual(m["why"], text, f"{cat} text changed after second Save")


@requires_qt
class TestOrphanRowSkipped(unittest.TestCase):
    """Dialog must skip rows whose path_key doesn't resolve in the game's move tree
    and never render the raw path_key string (e.g. '99.0') as a move label."""

    def test_tag_row_skips_orphan_path_key_with_notice(self):
        """A game whose paths dict contains one resolvable key ('0') and one orphan
        ('99.0') must produce exactly one row widget — for the valid move — and
        surface a single notice QLabel, never rendering '99.0' verbatim."""
        paths_data = {
            "0": [_make_entry("CLAMP", "M", "good tag")],
            "99.0": [_make_entry("CCT", "C", "orphan tag")],
        }
        dlg, _ = _make_dialog(paths_data)

        # Exactly one row widget built (the orphan is silently skipped)
        self.assertEqual(len(dlg._row_widgets), 1)

        # The row that was built must NOT use the raw path_key as its label
        row = dlg._row_widgets[0]
        label_text = row._header_label.text() if row._header_label else ""
        self.assertNotEqual(label_text, "99.0")
        self.assertNotEqual(label_text, "0")  # must be a human-readable move string

        # A notice QLabel must be present
        from PyQt6.QtWidgets import QLabel
        labels = dlg.findChildren(QLabel)
        notice_texts = [lbl.text() for lbl in labels if "could not be located" in lbl.text()]
        self.assertEqual(len(notice_texts), 1, "Expected exactly one orphan notice label")
        self.assertIn("1 logged moment", notice_texts[0])
        # Straight apostrophe, as in the rest of CARA's UI text
        self.assertIn("the game's moves may have been edited", notice_texts[0])
        self.assertNotIn("’", notice_texts[0])


# ---------------------------------------------------------------------------
# Save model: plan tests 9-12
# ---------------------------------------------------------------------------

@requires_qt
class TestSaveModelShowTags(unittest.TestCase):
    """Plan tests 9-12: ShowTagsDialog Save/Cancel model."""

    def _make_two_game_dialog(self):
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        from app.models.database_model import GameData
        game1 = GameData(game_number=1, pgn=MAINLINE_PGN)
        game2 = GameData(game_number=2, pgn=SECOND_PGN)
        paths1 = {"0": [_make_entry("CLAMP", "C", "note1")]}
        paths2 = {"0": [_make_entry("CLAMP", "L", "note2")]}
        ctrl = MagicMock()
        ctrl.get_tags_for_game.side_effect = lambda g: paths1 if g is game1 else paths2
        ctrl.replace_entries_at_path_for_game = MagicMock()
        ctrl.save_games = MagicMock()
        dlg = ShowTagsDialog({}, [game1, game2], ctrl)
        return dlg, ctrl, game1, game2

    def test_save_persists_edits_to_each_games_pgn(self):
        """Plan test 9: Save writes both games and calls save_games with both."""
        dlg, ctrl, game1, game2 = self._make_two_game_dialog()
        dlg._row_widgets[0]._why_texts["why"].setPlainText("edited note1")
        dlg._row_widgets[1]._why_texts["why"].setPlainText("edited note2")

        dlg._on_save()

        self.assertEqual(ctrl.replace_entries_at_path_for_game.call_count, 2)
        ctrl.save_games.assert_called_once()
        saved_games = set(ctrl.save_games.call_args[0][0])
        self.assertIn(game1, saved_games)
        self.assertIn(game2, saved_games)

    def test_cancel_discards_all_edits(self):
        """Plan test 10: reject() makes no writes."""
        dlg, ctrl, _, _ = self._make_two_game_dialog()
        dlg._row_widgets[0]._why_texts["why"].setPlainText("changed")
        dlg._row_widgets[1]._why_texts["why"].setPlainText("also changed")

        dlg.reject()

        ctrl.replace_entries_at_path_for_game.assert_not_called()
        ctrl.save_games.assert_not_called()

    def test_close_button_equivalent_to_cancel(self):
        """Plan test 11: close() routes to reject, no writes."""
        dlg, ctrl, _, _ = self._make_two_game_dialog()
        dlg._row_widgets[0]._why_texts["why"].setPlainText("will be closed")

        dlg.close()

        ctrl.replace_entries_at_path_for_game.assert_not_called()
        ctrl.save_games.assert_not_called()

    def test_save_only_touches_rows_that_actually_changed(self):
        """Plan test 12: only changed rows call replace; save_games covers only that game."""
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        from app.models.database_model import GameData
        game = GameData(game_number=1, pgn=MAINLINE_PGN)
        paths = {
            "0": [_make_entry("CLAMP", "C", "row1")],
            "0.0": [_make_entry("CLAMP", "L", "row2")],
            "0.0.0": [_make_entry("CLAMP", "M", "row3")],
        }
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = paths
        ctrl.replace_entries_at_path_for_game = MagicMock()
        ctrl.save_games = MagicMock()
        dlg = ShowTagsDialog({}, [game], ctrl)

        # Edit only the second row
        dlg._row_widgets[1]._why_texts["why"].setPlainText("changed row2")
        dlg._on_save()

        self.assertEqual(ctrl.replace_entries_at_path_for_game.call_count, 1)
        ctrl.save_games.assert_called_once()
        saved_games = set(ctrl.save_games.call_args[0][0])
        self.assertIn(game, saved_games)


# ---------------------------------------------------------------------------
# B10a — Show Logged Moments: dimmed chip + Ignore for ignored 3x3 entries
# ---------------------------------------------------------------------------

@requires_qt
class TestShowTagsDialogB10a(unittest.TestCase):
    """B10a: ignored entries render dimmed chip + ticked Ignore in ShowTagsDialog."""

    def _make_3x3_dialog_with_ignored(self, why1_text="I moved impulsively"):
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        # Entry with is_shallow=True + ignore_shallow=True + matching hash
        h = hashlib.sha256(why1_text.encode()).hexdigest()
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why1", why1_text,
            ignore_shallow=True, is_shallow=True, ignore_text_hash=h,
        )
        paths = {"0": [entry]}
        return _make_dialog(paths)

    def test_ignored_entry_has_ticked_ignore_checkbox(self):
        """B10a: ignored entry renders with Ignore checkbox pre-ticked."""
        from PyQt6.QtWidgets import QCheckBox
        dlg, _ = self._make_3x3_dialog_with_ignored()
        row = dlg._row_widgets[0]
        self.assertIn("Why1", row._ignore_checks)
        self.assertTrue(row._ignore_checks["Why1"].isChecked())

    def test_ignored_entry_chip_is_present(self):
        """B10a: ignored entry still shows the chip (dimmed)."""
        dlg, _ = self._make_3x3_dialog_with_ignored()
        row = dlg._row_widgets[0]
        # Chip exists (dimmed, but present as a QLabel)
        self.assertIsNotNone(row._shallow_chip)

    def test_untick_ignore_and_save_clears_ignore_flags_preserves_is_shallow(self):
        """B10a / Bug B: unticking Ignore clears ignore_shallow and ignore_text_hash
        but PRESERVES is_shallow — chip must remain visible after re-opening."""
        dlg, ctrl = self._make_3x3_dialog_with_ignored()
        ctrl.save_games = MagicMock()
        row = dlg._row_widgets[0]
        # Untick Ignore
        row._ignore_checks["Why1"].setChecked(False)
        dlg._on_save()
        # Check what was written
        calls = ctrl.replace_entries_at_path_for_game.call_args_list
        self.assertTrue(len(calls) > 0, "Expected replace call after untick+save")
        written = calls[0][0][3]
        why1 = next((e for e in written if e.get("cat") == "Why1"), None)
        self.assertIsNotNone(why1)
        self.assertFalse(why1.get("ignore_shallow", False), "ignore_shallow must be cleared")
        self.assertIsNone(why1.get("ignore_text_hash"), "ignore_text_hash must be cleared")
        self.assertTrue(why1.get("is_shallow", False), "is_shallow must be preserved after untick")

    def test_non_ignored_entry_has_unticked_ignore(self):
        """B10a: entry with chip but no Ignore has unticked checkbox."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "I moved impulsively", is_shallow=True)
        paths = {"0": [entry]}
        dlg, _ = _make_dialog(paths)
        row = dlg._row_widgets[0]
        self.assertIn("Why1", row._ignore_checks)
        self.assertFalse(row._ignore_checks["Why1"].isChecked())

    def test_entry_without_chip_has_no_ignore_checkbox(self):
        """Entry with no chip (Why2, not flagged) shows no Ignore checkbox."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        # Why1 has chip, Why2 does not
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "I moved fast", is_shallow=True),
            ChessLogStorageService.make_entry("3x3", "Why2", "It lost the center"),
        ]
        paths = {"0": entries}
        dlg, _ = _make_dialog(paths)
        row = dlg._row_widgets[0]
        self.assertIn("Why1", row._ignore_checks)
        self.assertNotIn("Why2", row._ignore_checks)


# ---------------------------------------------------------------------------
# B3: chip opacity updates in real time when Ignore is ticked / unticked
# ---------------------------------------------------------------------------

@requires_qt
class TestChipRealTimeOpacity(unittest.TestCase):
    """B3: Ignore checkbox must dim the chip immediately; unticking restores full opacity."""

    def _make_3x3_row(self, entries, show_ignore=True):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="3x3",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _make_clamp_row(self, entries, show_ignore=True):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _has_opacity_effect(self, chip) -> bool:
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        eff = chip.graphicsEffect()
        return isinstance(eff, QGraphicsOpacityEffect) and abs(eff.opacity() - 0.4) < 0.01

    def test_3x3_shallow_chip_dims_when_ignore_ticked(self):
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "Moved impulsively", is_shallow=True)
        row = self._make_3x3_row([entry], show_ignore=True)
        chip = row._chips_per_cat.get("Why1")
        self.assertIsNotNone(chip)
        self.assertFalse(self._has_opacity_effect(chip), "chip must start undimmed")
        row._ignore_checks["Why1"].setChecked(True)
        self.assertTrue(self._has_opacity_effect(chip), "chip must dim when Ignore ticked")

    def test_3x3_shallow_chip_undims_when_ignore_unticked(self):
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why1", "Moved impulsively", is_shallow=True, ignore_shallow=True,
            ignore_text_hash=__import__("hashlib").sha256(b"Moved impulsively").hexdigest()
        )
        row = self._make_3x3_row([entry], show_ignore=True)
        chip = row._chips_per_cat.get("Why1")
        self.assertIsNotNone(chip)
        self.assertTrue(self._has_opacity_effect(chip), "chip must start dimmed for ignored entry")
        row._ignore_checks["Why1"].setChecked(False)
        self.assertFalse(self._has_opacity_effect(chip), "chip must undim when Ignore unticked")

    def test_3x3_vague_chip_dims_when_ignore_ticked(self):
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why4", "Need to slow down", is_vague=True)
        row = self._make_3x3_row([entry], show_ignore=True)
        chip = row._chips_per_cat.get("Why4")
        self.assertIsNotNone(chip)
        row._ignore_checks["Why4"].setChecked(True)
        self.assertTrue(self._has_opacity_effect(chip), "vague chip must dim when Ignore ticked")

    def test_3x3_vague_chip_undims_when_ignore_unticked(self):
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why4", "Need to slow down", is_vague=True, ignore_shallow=True,
            ignore_text_hash=__import__("hashlib").sha256(b"Need to slow down").hexdigest()
        )
        row = self._make_3x3_row([entry], show_ignore=True)
        chip = row._chips_per_cat.get("Why4")
        self.assertIsNotNone(chip)
        self.assertTrue(self._has_opacity_effect(chip), "vague chip must start dimmed")
        row._ignore_checks["Why4"].setChecked(False)
        self.assertFalse(self._has_opacity_effect(chip), "vague chip must undim on untick")

    def test_clamp_chip_dims_when_ignore_ticked(self):
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "Rushed", is_shallow=True)
        row = self._make_clamp_row([entry], show_ignore=True)
        chip = row._shallow_chip
        self.assertIsNotNone(chip)
        self.assertFalse(self._has_opacity_effect(chip), "CLAMP chip must start undimmed")
        row._ignore_check.setChecked(True)
        self.assertTrue(self._has_opacity_effect(chip), "CLAMP chip must dim when Ignore ticked")

    def test_clamp_chip_undims_when_ignore_unticked(self):
        from app.services.chess_log_storage_service import ChessLogStorageService
        text = "Rushed development"
        entry = ChessLogStorageService.make_entry(
            "CLAMP", "C", text, is_shallow=True, ignore_shallow=True,
            ignore_text_hash=__import__("hashlib").sha256(text.encode()).hexdigest()
        )
        row = self._make_clamp_row([entry], show_ignore=True)
        chip = row._shallow_chip
        self.assertIsNotNone(chip)
        self.assertTrue(self._has_opacity_effect(chip), "CLAMP chip must start dimmed")
        row._ignore_check.setChecked(False)
        self.assertFalse(self._has_opacity_effect(chip), "CLAMP chip must undim on untick")

    def test_3x3_chip_already_dimmed_on_open_when_ignored(self):
        """Chip renders dimmed immediately on dialog open when entry is already ignored."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why1", "Moved impulsively", is_shallow=True, ignore_shallow=True,
            ignore_text_hash=__import__("hashlib").sha256(b"Moved impulsively").hexdigest()
        )
        row = self._make_3x3_row([entry])
        chip = row._chips_per_cat.get("Why1")
        self.assertIsNotNone(chip)
        self.assertTrue(self._has_opacity_effect(chip), "chip must be dimmed at open for ignored entry")


# ---------------------------------------------------------------------------
# Editing an answer clears its chip and Ignore
# ---------------------------------------------------------------------------

@requires_qt
class TestClearVerdictOnEdit(unittest.TestCase):
    """When why-text changes, chip + Ignore fields are wiped on get_current_entries."""

    def _make_3x3_row(self, entries, show_ignore=False):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="3x3",
            entries=entries,
            move_label="5. d4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _make_clamp_row(self, entries, show_ignore=False):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=entries,
            move_label="5. d4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _why4_honoured_entry(self):
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        text = "Need to slow down"
        return ChessLogStorageService.make_entry(
            "3x3", "Why4", text, is_vague=True, ignore_shallow=True,
            ignore_text_hash=hashlib.sha256(text.encode()).hexdigest(),
        )

    def _why1_honoured_entry(self):
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        text = "Moved impulsively"
        return ChessLogStorageService.make_entry(
            "3x3", "Why1", text, is_shallow=True, ignore_shallow=True,
            ignore_text_hash=hashlib.sha256(text.encode()).hexdigest(),
        )

    def _clamp_honoured_entry(self):
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        text = "Calculation error"
        return ChessLogStorageService.make_entry(
            "CLAMP", "C", text, is_shallow=True, ignore_shallow=True,
            ignore_text_hash=hashlib.sha256(text.encode()).hexdigest(),
        )

    # --- 3x3 Why4 (Vague chip) ---

    def test_3x3_why4_edit_clears_is_vague(self):
        row = self._make_3x3_row([self._why4_honoured_entry()], show_ignore=True)
        row._why_texts["Why4"].setPlainText("Actually a good lesson")
        entries = row.get_current_entries()
        why4 = next((e for e in entries if e.get("cat") == "Why4"), None)
        self.assertIsNotNone(why4)
        self.assertNotIn("is_vague", why4)
        self.assertNotIn("ignore_shallow", why4)
        self.assertNotIn("ignore_text_hash", why4)
        self.assertNotIn("is_shallow", why4)

    def test_3x3_why4_edit_leaves_why1_untouched(self):
        """Only the edited answer is cleared; other Why answers keep their flags."""
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        why1_text = "Moved impulsively"
        why1 = ChessLogStorageService.make_entry(
            "3x3", "Why1", why1_text, is_shallow=True, ignore_shallow=True,
            ignore_text_hash=hashlib.sha256(why1_text.encode()).hexdigest(),
        )
        row = self._make_3x3_row([why1, self._why4_honoured_entry()], show_ignore=True)
        # Only edit Why4
        row._why_texts["Why4"].setPlainText("Actually a good lesson")
        entries = row.get_current_entries()
        why1_out = next((e for e in entries if e.get("cat") == "Why1"), None)
        self.assertIsNotNone(why1_out)
        self.assertTrue(why1_out.get("is_shallow"), "Why1 chip must be untouched")
        self.assertTrue(why1_out.get("ignore_shallow"), "Why1 Ignore must be untouched")

    # --- 3x3 Why1 (Shallow chip) ---

    def test_3x3_why1_edit_clears_is_shallow(self):
        row = self._make_3x3_row([self._why1_honoured_entry()], show_ignore=True)
        row._why_texts["Why1"].setPlainText("Actually fine")
        entries = row.get_current_entries()
        why1 = next((e for e in entries if e.get("cat") == "Why1"), None)
        self.assertIsNotNone(why1)
        self.assertNotIn("is_shallow", why1)
        self.assertNotIn("ignore_shallow", why1)
        self.assertNotIn("ignore_text_hash", why1)

    # --- CLAMP/CCT note ---

    def test_clamp_edit_clears_is_shallow(self):
        row = self._make_clamp_row([self._clamp_honoured_entry()], show_ignore=True)
        row._why_texts["why"].setPlainText("Better explanation")
        entries = row.get_current_entries()
        self.assertFalse(any(e.get("is_shallow") for e in entries))
        self.assertFalse(any(e.get("ignore_shallow") for e in entries))
        self.assertFalse(any("ignore_text_hash" in e for e in entries))

    # --- Unchanged text ---

    def test_3x3_unchanged_text_preserves_chip(self):
        entry = self._why4_honoured_entry()
        row = self._make_3x3_row([entry], show_ignore=True)
        entries = row.get_current_entries()
        why4 = next((e for e in entries if e.get("cat") == "Why4"), None)
        self.assertTrue(why4.get("is_vague"), "chip must survive when text unchanged")

    def test_3x3_whitespace_only_diff_preserves_chip(self):
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        text = "Need to slow down"
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why4", text, is_vague=True, ignore_shallow=True,
            ignore_text_hash=hashlib.sha256(text.encode()).hexdigest(),
        )
        row = self._make_3x3_row([entry], show_ignore=True)
        # The QPlainTextEdit was initialised with the stored text; no change needed.
        entries = row.get_current_entries()
        why4 = next((e for e in entries if e.get("cat") == "Why4"), None)
        self.assertTrue(why4.get("is_vague"), "chip must survive whitespace-only non-change")

    def test_clamp_unchanged_text_preserves_chip(self):
        entry = self._clamp_honoured_entry()
        row = self._make_clamp_row([entry], show_ignore=True)
        entries = row.get_current_entries()
        self.assertTrue(any(e.get("is_shallow") for e in entries))

    # --- Display: mismatched hash shows unticked box ---

    def test_3x3_mismatched_hash_shows_unticked_ignore_box(self):
        """Entry with stale hash (outside edit) → Ignore box unticked on open."""
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry(
            "3x3", "Why4", "New text after outside edit", is_vague=True,
            ignore_shallow=True,
            ignore_text_hash=hashlib.sha256(b"old text before outside edit").hexdigest(),
        )
        row = self._make_3x3_row([entry], show_ignore=True)
        ign_cb = row._ignore_checks.get("Why4")
        self.assertIsNotNone(ign_cb, "Ignore checkbox must be present when chip exists")
        self.assertFalse(ign_cb.isChecked(), "Ignore box must be unticked when hash does not match")


@requires_qt
class TestPaulSequenceEndToEnd(unittest.TestCase):
    """End-to-end: Ignore → Save → edit lesson → save game → Show Logged Moments."""

    def setUp(self):
        import hashlib
        from app.services.chess_log_storage_service import ChessLogStorageService
        self.hashlib = hashlib
        self.CSvc = ChessLogStorageService

    def _make_3x3_row(self, entries, show_ignore=False):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="3x3",
            entries=entries,
            move_label="7. Nf3",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def test_paul_sequence(self):
        hashlib = self.hashlib
        CSvc = self.CSvc

        # Step 1: initial entry — vague lesson, Ignore honoured.
        original_lesson = "Need to slow down and check candidate moves"
        h1 = hashlib.sha256(original_lesson.encode()).hexdigest()
        entry_after_ignore = CSvc.make_entry(
            "3x3", "Why4", original_lesson, is_vague=True,
            ignore_shallow=True, ignore_text_hash=h1,
        )
        print("\n[Step 1] After Ignore + Save:")
        why4 = entry_after_ignore
        print(f"  is_vague={why4.get('is_vague')} ignore_shallow={why4.get('ignore_shallow')}"
              f" has_hash={bool(why4.get('ignore_text_hash'))} text='{why4.get('why')}'")
        self.assertTrue(why4.get("is_vague"))
        self.assertTrue(why4.get("ignore_shallow"))
        self.assertEqual(why4.get("ignore_text_hash"), h1)

        # Step 2: Check Logs correctly skips it (Ignore honoured → not sent to classifier).
        self.assertTrue(CSvc.is_entry_ignore_honoured(entry_after_ignore))
        print("[Step 2] Check Logs: entry is ignored → classifier skips it. Correct.")

        # Step 3: user edits the lesson in Show Logged Moments → Save.
        new_lesson = "This move was fine — analysed the line thoroughly"
        row = self._make_3x3_row([entry_after_ignore], show_ignore=True)
        ign_cb = row._ignore_checks.get("Why4")
        # Ignore box was ticked from stored honoured entry
        self.assertTrue(ign_cb.isChecked(), "Ignore box must start ticked for honoured entry")
        row._why_texts["Why4"].setPlainText(new_lesson)
        new_entries = row.get_current_entries()
        why4_saved = next(e for e in new_entries if e.get("cat") == "Why4")
        print("[Step 3] After editing lesson + Save:")
        print(f"  is_vague={why4_saved.get('is_vague')} ignore_shallow={why4_saved.get('ignore_shallow')}"
              f" has_hash={bool(why4_saved.get('ignore_text_hash'))} text='{why4_saved.get('why')}'")
        self.assertNotIn("is_vague", why4_saved, "is_vague must be cleared after text edit")
        self.assertNotIn("ignore_shallow", why4_saved)
        self.assertNotIn("ignore_text_hash", why4_saved)
        self.assertEqual(why4_saved.get("why"), new_lesson)

        # Step 4: Check Logs — entry has no chip and no Ignore → processed fresh.
        self.assertFalse(CSvc.is_entry_ignore_honoured(why4_saved))
        print("[Step 4] Check Logs: entry has no chip, not ignored → classifier sees it fresh.")

        # Step 5: Show Logged Moments reopens with the saved entry.
        row2 = self._make_3x3_row([why4_saved], show_ignore=True)
        ign_cb2 = row2._ignore_checks.get("Why4")
        # No chip → no Ignore checkbox rendered
        chip2 = row2._chips_per_cat.get("Why4")
        print("[Step 5] Show Logged Moments after edit:")
        print(f"  chip_present={chip2 is not None}  ignore_cb_present={ign_cb2 is not None}")
        self.assertIsNone(chip2, "no chip must be shown for the cleared entry")
        self.assertIsNone(ign_cb2, "no Ignore checkbox must be shown without a chip")
        print("[Step 5] PASS — new text, no chip, no Ignore box.")


@requires_qt
class TestChessLogMiniatureBoardSettings(unittest.TestCase):
    """Chess Log boards follow View → Miniature Boards → Chess Log settings."""

    def _make_row(self, scale_factor=1.25, show_played=True, show_best=True):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entry = _make_entry("CLAMP", "C", "note")
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=[entry],
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            scale_factor=scale_factor,
            show_played=show_played,
            show_best=show_best,
        )

    def test_scale_175_gives_larger_placeholder_than_125(self):
        from PyQt6.QtWidgets import QLabel
        row_125 = self._make_row(scale_factor=1.25)
        row_175 = self._make_row(scale_factor=1.75)
        # Find the placeholder QLabel (empty string, fixed size)
        def _placeholder_size(row):
            for w in row.findChildren(QLabel):
                if w.text() == "" and w.minimumWidth() == w.maximumWidth():
                    return w.width()
            return None
        size_125 = _placeholder_size(row_125)
        size_175 = _placeholder_size(row_175)
        self.assertIsNotNone(size_125, "Expected a fixed-size placeholder at 1.25x")
        self.assertIsNotNone(size_175, "Expected a fixed-size placeholder at 1.75x")
        self.assertGreater(size_175, size_125, "1.75x placeholder must be larger than 1.25x")

    def test_placeholder_tracks_scale(self):
        """Placeholder size at 1.25x should equal int(163 * 1.25 + 0.5) = 204."""
        from PyQt6.QtWidgets import QLabel
        row = self._make_row(scale_factor=1.25)
        sizes = [w.width() for w in row.findChildren(QLabel)
                 if w.text() == "" and w.minimumWidth() == w.maximumWidth()]
        self.assertIn(204, sizes, "1.25x placeholder must be 204px")

    def test_scale_stored_on_row(self):
        row = self._make_row(scale_factor=1.75)
        self.assertAlmostEqual(row._scale_factor, 1.75)

    def test_default_scale_is_125(self):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entry = _make_entry("CLAMP", "C", "note")
        row = _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=[entry],
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )
        self.assertAlmostEqual(row._scale_factor, 1.25)

    def test_show_played_false_stored(self):
        row = self._make_row(show_played=False)
        self.assertFalse(row._show_played)

    def test_show_best_false_stored(self):
        row = self._make_row(show_best=False)
        self.assertFalse(row._show_best)

    def test_dialog_with_scale_175_rows_have_that_scale(self):
        """ShowTagsDialog reads scale from UserSettingsService and passes it to rows."""
        from unittest.mock import patch, MagicMock
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        paths_data = {"0": [_make_entry("CLAMP", "C", "note")]}
        game_data = _make_game_data(MAINLINE_PGN)
        ctrl = _make_controller(paths_data)

        mock_uss = MagicMock()
        mock_uss.get_miniature_boards.return_value = {"chess_log": 1.75}
        mock_uss.get_miniature_board_arrows.return_value = {
            "chess_log_played": True,
            "chess_log_best_alternative": True,
        }

        with patch(
            "app.services.user_settings_service.UserSettingsService.get_instance",
            return_value=mock_uss,
        ):
            dlg = ShowTagsDialog({}, [game_data], ctrl)

        self.assertTrue(len(dlg._row_widgets) > 0)
        for row in dlg._row_widgets:
            self.assertAlmostEqual(row._scale_factor, 1.75)

    def test_dialog_arrows_off_passed_to_rows(self):
        """ShowTagsDialog passes show_played=False when toggle is off."""
        from unittest.mock import patch, MagicMock
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        paths_data = {"0": [_make_entry("CLAMP", "C", "note")]}
        game_data = _make_game_data(MAINLINE_PGN)
        ctrl = _make_controller(paths_data)

        mock_uss = MagicMock()
        mock_uss.get_miniature_boards.return_value = {"chess_log": 1.25}
        mock_uss.get_miniature_board_arrows.return_value = {
            "chess_log_played": False,
            "chess_log_best_alternative": False,
        }

        with patch(
            "app.services.user_settings_service.UserSettingsService.get_instance",
            return_value=mock_uss,
        ):
            dlg = ShowTagsDialog({}, [game_data], ctrl)

        for row in dlg._row_widgets:
            self.assertFalse(row._show_played)
            self.assertFalse(row._show_best)


# ---------------------------------------------------------------------------
# Item 1: Fit-to-text answer boxes
# ---------------------------------------------------------------------------

@requires_qt
class TestFitTextEdit(unittest.TestCase):
    """_FitTextEdit sizes to content: exact pixel-equality checks at fixed widths."""

    def _make(self, text="", fit_min_lines=1, fit_max_lines=6, width=400):
        from app.views.dialogs.show_tags_dialog import _FitTextEdit
        te = _FitTextEdit(text, fit_min_lines=fit_min_lines, fit_max_lines=fit_max_lines)
        te.setFixedWidth(width)
        te._update_height()
        return te

    def _make_shown(self, text="", fit_min_lines=1, fit_max_lines=6, width=400):
        """Create, show, and process events so wrapping is computed."""
        from app.views.dialogs.show_tags_dialog import _FitTextEdit
        te = _FitTextEdit(text, fit_min_lines=fit_min_lines, fit_max_lines=fit_max_lines)
        te.setFixedWidth(width)
        te.show()
        _APP.processEvents()
        te._update_height()
        return te

    def test_short_text_height_equals_one_line(self):
        te = self._make("Short", fit_min_lines=1, fit_max_lines=6)
        self.assertEqual(te.height(), te._height_for_lines(1))

    def test_three_newline_paragraphs_height_equals_three_lines(self):
        te = self._make("a\nb\nc", fit_min_lines=1, fit_max_lines=6)
        self.assertEqual(te.height(), te._height_for_lines(3))

    def test_wrapping_paragraph_height(self):
        """Long single paragraph wraps to 2+ lines at width=200; height reflects wrap count."""
        long_para = "This is a deliberately long sentence that will wrap to multiple lines at a narrow width."
        te = self._make_shown(long_para, fit_min_lines=1, fit_max_lines=6, width=200)
        wrapped_lines = max(1, int(te.document().size().height()))
        self.assertGreater(wrapped_lines, 1, "text should wrap to more than 1 line at width=200")
        self.assertEqual(te.height(), te._height_for_lines(wrapped_lines))
        self.assertGreater(te.height(), te._height_for_lines(1))

    def test_ten_lines_capped_at_max_with_scrollbar(self):
        ten_lines = "\n".join(f"Line {i}" for i in range(10))
        te = self._make(ten_lines, fit_min_lines=1, fit_max_lines=6)
        self.assertEqual(te.height(), te._height_for_lines(6))
        self.assertEqual(
            te.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )

    def test_typing_from_one_line_to_three_grows_strictly(self):
        te = self._make("Short", fit_min_lines=1, fit_max_lines=6)
        h1 = te.height()
        te.setPlainText("Line 1\nLine 2\nLine 3")
        _APP.processEvents()
        h3 = te.height()
        self.assertGreater(h3, h1, "3 lines must be strictly taller than 1 line")

    def test_deleting_back_to_one_line_shrinks_strictly(self):
        te = self._make("Line 1\nLine 2\nLine 3", fit_min_lines=1, fit_max_lines=6)
        h3 = te.height()
        te.setPlainText("Short")
        _APP.processEvents()
        h1 = te.height()
        self.assertLess(h1, h3, "back to 1 line must be strictly shorter than 3 lines")

    def test_narrowing_widget_grows_height_due_to_wrapping(self):
        """Resize from 600px to 200px; a long line that now wraps must be taller."""
        long_para = "This is a long sentence that wraps when the widget is narrowed."
        te = self._make_shown(long_para, fit_min_lines=1, fit_max_lines=6, width=600)
        h_wide = te.height()
        te.setFixedWidth(200)
        _APP.processEvents()
        h_narrow = te.height()
        self.assertGreater(h_narrow, h_wide, "narrowing must increase height when text wraps")

    def test_empty_text_gives_minimum_height(self):
        te1 = self._make("", fit_min_lines=1)
        te3 = self._make("", fit_min_lines=3)
        self.assertEqual(te1.height(), te1._height_for_lines(1))
        self.assertEqual(te3.height(), te3._height_for_lines(3))
        self.assertGreater(te3.height(), te1.height())

    def test_clamp_row_te_is_fit_text_edit(self):
        from app.views.dialogs.show_tags_dialog import _FitTextEdit, _TagRowWidget
        row = _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=[_make_entry("CLAMP", "C", "note")],
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )
        te = row._why_texts.get("why")
        self.assertIsInstance(te, _FitTextEdit)

    def test_3x3_row_te_is_fit_text_edit(self):
        from app.views.dialogs.show_tags_dialog import _FitTextEdit, _TagRowWidget
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "test")
        row = _TagRowWidget(
            config={},
            preset="3x3",
            entries=[entry],
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )
        te = row._why_texts.get("Why1")
        self.assertIsInstance(te, _FitTextEdit)


# ---------------------------------------------------------------------------
# Item 2: Chip and Ignore column layout (3x3 only)
# ---------------------------------------------------------------------------

@requires_qt
class TestChipColumnLayout(unittest.TestCase):
    """Issue B: 3x3 chip and Ignore sit right of the answer box, not on the question line."""

    def _make_3x3_row(self, entries, show_ignore=False):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="3x3",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _make_clamp_row(self, entries, show_ignore=False):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _make_cct_row(self, entries, show_ignore=False):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config={},
            preset="CCT",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def test_3x3_chip_not_in_question_label_parent(self):
        """Chip must NOT be a sibling of the prompt QLabel in the question row layout."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        from PyQt6.QtWidgets import QLabel, QHBoxLayout
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "attacked", is_shallow=True)
        row = self._make_3x3_row([entry], show_ignore=True)
        chip = row._chips_per_cat.get("Why1")
        self.assertIsNotNone(chip)
        # Chip's parent must NOT be the same row widget whose direct children include prompt labels
        # (i.e. chip lives in the answer row, not in the question row).
        # We verify by checking that chip's parent is NOT the _TagRowWidget itself
        # but a QWidget chip column container.
        from PyQt6.QtWidgets import QWidget
        chip_parent = chip.parent()
        self.assertIsNotNone(chip_parent)
        # The chip column widget is a plain QWidget, not the row frame
        self.assertIsNot(chip_parent, row)

    def test_3x3_chip_above_ignore_same_column(self):
        """Chip and Ignore must be in the same parent container widget."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "attacked", is_shallow=True)
        row = self._make_3x3_row([entry], show_ignore=True)
        chip = row._chips_per_cat.get("Why1")
        ign_cb = row._ignore_checks.get("Why1")
        self.assertIsNotNone(chip)
        self.assertIsNotNone(ign_cb)
        self.assertIs(chip.parent(), ign_cb.parent(), "Chip and Ignore must share the same container")

    def test_3x3_chipless_why_has_no_chip_column(self):
        """A Why without a chip should produce no entry in _chips_per_cat."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why2", "plain answer")
        row = self._make_3x3_row([entry])
        self.assertNotIn("Why2", row._chips_per_cat)

    def test_clamp_chip_in_header_row(self):
        """CLAMP chip must still be stored in _shallow_chip (on the header row)."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", is_shallow=True)
        row = self._make_clamp_row([entry], show_ignore=True)
        self.assertIsNotNone(row._shallow_chip, "CLAMP shallow chip must be in header")
        # CLAMP chip is NOT in _chips_per_cat (that dict is for 3x3 per-answer chips)
        self.assertNotIn("C", row._chips_per_cat)

    def test_3x3_chip_opacity_with_new_layout(self):
        """Chip opacity mechanics must still work after layout refactor."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "attacked", is_shallow=True)
        row = self._make_3x3_row([entry], show_ignore=True)
        chip = row._chips_per_cat.get("Why1")
        self.assertIsNotNone(chip)
        row._ignore_checks["Why1"].setChecked(True)
        eff = chip.graphicsEffect()
        self.assertIsInstance(eff, QGraphicsOpacityEffect)
        self.assertAlmostEqual(eff.opacity(), 0.4, places=2)

    def test_chip_above_ignore_by_position(self):
        """chip.y() < ignore_cb.y() within their shared container after layout."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "attacked", is_shallow=True)
        row = self._make_3x3_row([entry], show_ignore=True)
        row.show()
        _APP.processEvents()
        chip = row._chips_per_cat["Why1"]
        ign_cb = row._ignore_checks["Why1"]
        self.assertLess(chip.pos().y(), ign_cb.pos().y(),
                        "chip must sit above the Ignore checkbox in the chip column")

    def test_chip_top_aligned_with_answer_box(self):
        """Chip column top y must equal answer box top y (within 2px) after layout."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "attacked", is_shallow=True)
        row = self._make_3x3_row([entry], show_ignore=True)
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        chip_col = row._chips_per_cat["Why1"].parent()  # the chip_col_widget
        te = row._why_texts["Why1"]
        # Both chip_col and te share _TagRowWidget as parent; compare their y positions.
        self.assertAlmostEqual(
            chip_col.pos().y(), te.pos().y(), delta=2,
            msg="chip column must be top-aligned with the answer box",
        )

    def test_chipless_why_answer_wider_than_chipped_answer(self):
        """A chipless Why's answer box must be wider than a chipped Why's in the same row."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        e_chipped = ChessLogStorageService.make_entry("3x3", "Why1", "attacked", is_shallow=True)
        e_chipless = ChessLogStorageService.make_entry("3x3", "Why2", "plain answer")
        row = self._make_3x3_row([e_chipped, e_chipless])
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        te_chipped = row._why_texts["Why1"]
        te_chipless = row._why_texts["Why2"]
        self.assertGreater(
            te_chipless.width(), te_chipped.width(),
            "chipless answer box must be wider than chipped one (no chip column steals space)",
        )

    def test_shallow_chip_fits_in_chip_column(self):
        """Shallow chip sizeHint width must not exceed the chip column's fixed width."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "attacked", is_shallow=True)
        row = self._make_3x3_row([entry])
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        chip = row._chips_per_cat["Why1"]
        col_widget = chip.parent()
        self.assertLessEqual(
            chip.sizeHint().width(), col_widget.width(),
            f"Shallow chip sizeHint.width()={chip.sizeHint().width()} must not exceed "
            f"chip column width={col_widget.width()}",
        )

    def test_vague_chip_fits_in_chip_column(self):
        """Vague chip sizeHint width must not exceed the chip column's fixed width."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("3x3", "Why4", "Think more", is_vague=True)
        row = self._make_3x3_row([entry])
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        chip = row._chips_per_cat["Why4"]
        col_widget = chip.parent()
        self.assertLessEqual(
            chip.sizeHint().width(), col_widget.width(),
            f"Vague chip sizeHint.width()={chip.sizeHint().width()} must not exceed "
            f"chip column width={col_widget.width()}",
        )

    def _note_top_y_equals_first_checkbox_y(self, row, delta=2):
        """Assert FitTextEdit top y ≈ first checkbox top y (within delta px)."""
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        te = row._why_texts["why"]
        first_cb = list(row._checkboxes.values())[0]
        self.assertAlmostEqual(
            te.pos().y(), first_cb.pos().y(), delta=delta,
            msg=f"note box y={te.pos().y()} must be top-aligned with "
                f"first checkbox y={first_cb.pos().y()} (within {delta}px)",
        )

    def test_clamp_short_note_top_aligned_with_first_checkbox(self):
        """CLAMP note box must be top-aligned with first checkbox (short note)."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "brief note")
        row = self._make_clamp_row([entry])
        self._note_top_y_equals_first_checkbox_y(row)

    def test_clamp_long_note_top_aligned_with_first_checkbox(self):
        """CLAMP note box must be top-aligned with first checkbox (long multi-line note)."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        long_note = "Line one.\nLine two.\nLine three.\nLine four.\nLine five."
        entry = ChessLogStorageService.make_entry("CLAMP", "C", long_note)
        row = self._make_clamp_row([entry])
        self._note_top_y_equals_first_checkbox_y(row)

    def test_cct_short_note_top_aligned_with_first_checkbox(self):
        """CCT note box must be top-aligned with first checkbox (short note)."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("CCT", "Checks", "brief note")
        row = self._make_cct_row([entry])
        self._note_top_y_equals_first_checkbox_y(row)

    def test_cct_long_note_top_aligned_with_first_checkbox(self):
        """CCT note box must be top-aligned with first checkbox (long multi-line note)."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        long_note = "Line one.\nLine two.\nLine three.\nLine four.\nLine five."
        entry = ChessLogStorageService.make_entry("CCT", "Checks", long_note)
        row = self._make_cct_row([entry])
        self._note_top_y_equals_first_checkbox_y(row)

    def test_show_logged_moments_has_800px_minimum_width(self):
        """ShowTagsDialog must enforce ≥800px minimum width (confirms no regression)."""
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        game = _make_game_data(MAINLINE_PGN)
        ctrl = _make_controller({"0": [_make_entry("CLAMP", "C", "note")]})
        dlg = ShowTagsDialog({}, [game], ctrl)
        self.assertGreaterEqual(dlg.minimumWidth(), 800)


# ---------------------------------------------------------------------------
# Chip text alignment (#58)
# ---------------------------------------------------------------------------

@requires_qt
class TestChipTextAlignment(unittest.TestCase):
    """_make_chip must produce a QLabel with centered text alignment (#58)."""

    def _make_row(self, **kw):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        from app.services.chess_log_storage_service import ChessLogStorageService
        entries = [ChessLogStorageService.make_entry("3x3", "Why1", "test", is_shallow=True)]
        return _TagRowWidget(
            config={}, preset="3x3", entries=entries,
            move_label="1. e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
            **kw,
        )

    def test_shallow_chip_alignment_is_center(self):
        """Shallow chip label alignment must include AlignHCenter and AlignVCenter."""
        from PyQt6.QtCore import Qt
        row = self._make_row()
        chip = row._chips_per_cat.get("Why1")
        self.assertIsNotNone(chip)
        self.assertTrue(
            bool(chip.alignment() & Qt.AlignmentFlag.AlignHCenter),
            f"chip.alignment()={int(chip.alignment())} must include AlignHCenter",
        )
        self.assertTrue(
            bool(chip.alignment() & Qt.AlignmentFlag.AlignVCenter),
            f"chip.alignment()={int(chip.alignment())} must include AlignVCenter",
        )

    def test_vague_chip_alignment_is_center(self):
        """Vague chip label alignment must include AlignHCenter and AlignVCenter."""
        from PyQt6.QtCore import Qt
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entries = [ChessLogStorageService.make_entry("3x3", "Why4", "lesson", is_vague=True)]
        row = _TagRowWidget(
            config={}, preset="3x3", entries=entries,
            move_label="1. e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
        )
        chip = row._chips_per_cat.get("Why4")
        self.assertIsNotNone(chip)
        self.assertTrue(
            bool(chip.alignment() & Qt.AlignmentFlag.AlignHCenter),
            f"chip.alignment()={int(chip.alignment())} must include AlignHCenter",
        )

    def test_clamp_header_chip_alignment_is_center(self):
        """CLAMP header Shallow chip must also have AlignCenter (#58 applies to _make_chip)."""
        from PyQt6.QtCore import Qt
        from app.services.chess_log_storage_service import ChessLogStorageService
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "note", is_shallow=True)
        row = _TagRowWidget(
            config={}, preset="CLAMP", entries=[entry],
            move_label="1. e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
        )
        chip = row._shallow_chip
        self.assertIsNotNone(chip)
        self.assertTrue(
            bool(chip.alignment() & Qt.AlignmentFlag.AlignHCenter),
            f"CLAMP chip alignment={int(chip.alignment())} must include AlignHCenter",
        )


# ---------------------------------------------------------------------------
# chip_col_widget width must cover every child sizeHint (#58)
# ---------------------------------------------------------------------------

@requires_qt
class TestThreeByThreeChipColumnWidth(unittest.TestCase):
    """chip_col_widget fixed width must be >= every child's sizeHint.width() (#58).

    The old formula used QFontMetrics.horizontalAdvance() + hand-tuned fudges
    that missed stylesheet padding (QLabel chip) and platform checkbox-indicator
    size (QCheckBox Ignore), clipping "Shallow" and "Ignore" on macOS.
    The fix probes real widget sizeHint().width() values instead.
    """

    def _make_row(self, config=None, entries=None, show_ignore=True):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        if entries is None:
            from app.services.chess_log_storage_service import ChessLogStorageService
            entries = [
                ChessLogStorageService.make_entry("3x3", "Why1", "test", is_shallow=True),
                ChessLogStorageService.make_entry("3x3", "Why4", "lesson", is_vague=True),
            ]
        return _TagRowWidget(
            config=config or {},
            preset="3x3",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def test_chip_col_width_fits_shallow_chip(self):
        """chip_col_widget fixed width >= shallow chip sizeHint.width()."""
        row = self._make_row()
        chip = row._chips_per_cat.get("Why1")
        col_widget = row._chip_col_widgets.get("Why1")
        self.assertIsNotNone(chip)
        self.assertIsNotNone(col_widget)
        chip.ensurePolished()
        self.assertGreaterEqual(
            col_widget.minimumWidth(), chip.sizeHint().width(),
            f"chip_col_widget min width={col_widget.minimumWidth()} must be >= "
            f"shallow chip sizeHint.width()={chip.sizeHint().width()}",
        )

    def test_chip_col_width_fits_vague_chip(self):
        """chip_col_widget fixed width >= vague chip sizeHint.width()."""
        row = self._make_row()
        chip = row._chips_per_cat.get("Why4")
        col_widget = row._chip_col_widgets.get("Why4")
        self.assertIsNotNone(chip)
        self.assertIsNotNone(col_widget)
        chip.ensurePolished()
        self.assertGreaterEqual(
            col_widget.minimumWidth(), chip.sizeHint().width(),
            f"chip_col_widget min width={col_widget.minimumWidth()} must be >= "
            f"vague chip sizeHint.width()={chip.sizeHint().width()}",
        )

    def test_chip_col_width_fits_ignore_checkbox(self):
        """chip_col_widget fixed width >= Ignore checkbox sizeHint.width().

        Regression for #58: old formula gave _chip_col_w = 66 but
        QCheckBox('Ignore').sizeHint().width() = 68 on the offscreen platform
        (indicator+spacing = ~31px >> the 24px fudge), clipping "Ignore" on every
        platform.
        """
        row = self._make_row(show_ignore=True)
        ign_cb = row._ignore_checks.get("Why1")
        col_widget = row._chip_col_widgets.get("Why1")
        self.assertIsNotNone(ign_cb, "Why1 Ignore checkbox must exist (show_ignore=True)")
        self.assertIsNotNone(col_widget)
        ign_cb.ensurePolished()
        self.assertGreaterEqual(
            col_widget.minimumWidth(), ign_cb.sizeHint().width(),
            f"chip_col_widget min width={col_widget.minimumWidth()} must be >= "
            f"Ignore checkbox sizeHint.width()={ign_cb.sizeHint().width()} (#58)",
        )

    def test_chip_not_squeezed_shallow(self):
        """Placed shallow chip.width() >= chip.sizeHint().width() after layout.

        Root cause of #58: chip_col QVBoxLayout has default 9px content margins
        on each side.  With col_widget=72px, available = 72-9-9 = 54px, but
        Shallow chip sizeHint = 63px → placed chip.width() = 54 < 63.
        Fix: chip_col.setContentsMargins(0,0,0,0) so available = full 72px.
        """
        row = self._make_row()
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        chip = row._chips_per_cat["Why1"]
        chip.ensurePolished()
        self.assertGreaterEqual(
            chip.width(), chip.sizeHint().width(),
            f"placed chip.width()={chip.width()} must be >= sizeHint.width()={chip.sizeHint().width()} "
            f"(default layout margins would steal 18px, leaving chip squeezed — #58)",
        )

    def test_chip_not_squeezed_vague(self):
        """Placed vague chip.width() >= chip.sizeHint().width() after layout."""
        row = self._make_row()
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        chip = row._chips_per_cat["Why4"]
        chip.ensurePolished()
        self.assertGreaterEqual(
            chip.width(), chip.sizeHint().width(),
            f"placed chip.width()={chip.width()} must be >= sizeHint.width()={chip.sizeHint().width()}",
        )

    def test_ignore_not_squeezed(self):
        """Placed Ignore checkbox.width() >= checkbox.sizeHint().width() after layout.

        With default 9px margins the Ignore checkbox (sizeHint=68) is squeezed
        to 54px available and clips.  Fix: zero layout margins.
        """
        row = self._make_row(show_ignore=True)
        row.setFixedWidth(600)
        row.show()
        _APP.processEvents()
        ign_cb = row._ignore_checks.get("Why1")
        self.assertIsNotNone(ign_cb)
        ign_cb.ensurePolished()
        self.assertGreaterEqual(
            ign_cb.width(), ign_cb.sizeHint().width(),
            f"placed Ignore cb.width()={ign_cb.width()} must be >= "
            f"sizeHint.width()={ign_cb.sizeHint().width()} (#58)",
        )

    def test_chip_not_squeezed_long_label(self):
        """A chip with a long configured label ('Shallowwwww') must not be squeezed.

        Proves test sensitivity: with old formula (advance+20 fudge) AND default
        layout margins, col_width - 18px < sizeHint('Shallowwwww') → chip clips.
        With probe-based sizing + zero margins, col_width = max(sizeHints) + 4,
        avail = col_width, chip fits.
        """
        from app.services.chess_log_storage_service import ChessLogStorageService
        long_config = {
            "ui": {"dialogs": {"shallow": {"labels": {
                "shallow": {"text": "Shallowwwww"},
            }}}}
        }
        entry = ChessLogStorageService.make_entry("3x3", "Why1", "test", is_shallow=True)
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        row = _TagRowWidget(
            config=long_config, preset="3x3",
            entries=[entry],
            move_label="1. e4", fen=None, played_move=None,
            bg_rgb=[40, 40, 45], text_color=[200, 200, 200],
            show_ignore_checkbox=True,
        )
        row.setFixedWidth(800)
        row.show()
        _APP.processEvents()
        chip = row._chips_per_cat["Why1"]
        chip.ensurePolished()
        self.assertGreaterEqual(
            chip.width(), chip.sizeHint().width(),
            f"long-label chip.width()={chip.width()} must be >= "
            f"sizeHint.width()={chip.sizeHint().width()} ('Shallowwwww')",
        )

    def test_chip_col_widgets_populated_for_chipped_keys(self):
        """_chip_col_widgets must have entries for every Why key that has a chip."""
        row = self._make_row()
        for key in row._chips_per_cat:
            self.assertIn(key, row._chip_col_widgets,
                          f"_chip_col_widgets missing key {key!r} that has a chip")

    def test_chip_col_widgets_not_populated_for_chipless_keys(self):
        """_chip_col_widgets must NOT have entries for Why keys without a chip."""
        from app.services.chess_log_storage_service import ChessLogStorageService
        entries = [
            ChessLogStorageService.make_entry("3x3", "Why1", "no chip here"),
            ChessLogStorageService.make_entry("3x3", "Why2", "no chip here either"),
        ]
        row = self._make_row(entries=entries)
        self.assertEqual(row._chip_col_widgets, {},
                         "_chip_col_widgets must be empty when no chips exist")


# ---------------------------------------------------------------------------
# Item 4: AI hint text points to correct menu
# ---------------------------------------------------------------------------

@requires_qt
class TestAIHintMenuPath(unittest.TestCase):
    """Both AI hint strings must say 'AI Summary → AI Model Settings'."""

    def test_narrative_hint_says_ai_summary(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        view = DetailChessLogChartsView(config={})
        self.assertIn("AI Summary", view._ai_hint.text())
        self.assertIn("AI Model Settings", view._ai_hint.text())

    def test_narrative_hint_has_link(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        view = DetailChessLogChartsView(config={})
        self.assertIn('<a href=', view._ai_hint.text())
        self.assertIn('ai-model-settings', view._ai_hint.text())

    def test_shallow_hint_says_ai_summary_when_no_ai(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        from unittest.mock import MagicMock
        view = DetailChessLogChartsView(config={})
        # Attach an unconfigured controller to trigger _refresh_ai_state
        ctrl = MagicMock()
        ctrl.is_ai_configured.return_value = False
        ctrl.get_last_narrative_result.return_value = ("", [], None)
        ctrl.get_last_shallow_result.return_value = (frozenset(), frozenset(), None)
        ctrl.get_available_models.return_value = []
        ctrl.get_default_narrative_model.return_value = ""
        ctrl.get_narrative_timeout_seconds.return_value = 60
        ctrl.get_narrative_token_limit.return_value = 12000
        ctrl.get_narrative_model_override.return_value = ""
        # Connect signals manually would be complex; call _refresh_ai_state directly
        view._controller = ctrl
        view._refresh_ai_state()
        self.assertIn("AI Summary", view._shallow_hint.text())
        self.assertIn("AI Model Settings", view._shallow_hint.text())


# ---------------------------------------------------------------------------
# #67: chip-fade — editing an answer fades and hides its chip presentation
# ---------------------------------------------------------------------------

@requires_qt
class TestChipFade(unittest.TestCase):
    """#67: editing an answer fades and hides its chip and Ignore (presentation-only).
    Data clearing still happens at Save via clear_verdict_if_text_changed."""

    _FADE_CFG = {"ui": {"dialogs": {"show_tags": {"chip_fade_ms": 0}}}}
    _LONG_FADE_CFG = {"ui": {"dialogs": {"show_tags": {"chip_fade_ms": 10000}}}}

    def _make_3x3_row(self, entries, show_ignore=True, config=None):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config=config or self._FADE_CFG,
            preset="3x3",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _make_clamp_row(self, entries, show_ignore=True):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        return _TagRowWidget(
            config=self._FADE_CFG,
            preset="CLAMP",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def _pump(self):
        for _ in range(5):
            _APP.processEvents()

    def _shallow_3x3_entry(self, cat="Why1", why="my answer"):
        from app.services.chess_log_storage_service import ChessLogStorageService
        return ChessLogStorageService.make_entry(
            "3x3", cat, why,
            is_shallow=(cat in ("Why1", "Why2", "Why3")),
            is_vague=(cat == "Why4"),
        )

    def _shallow_clamp_entry(self, why="my note"):
        from app.services.chess_log_storage_service import ChessLogStorageService
        return ChessLogStorageService.make_entry("CLAMP", "C", why, is_shallow=True)

    # --- chip hidden after first edit ---

    def test_3x3_chip_col_hidden_after_edit(self):
        """Editing a 3x3 answer starts a fade; chip column is explicitly hidden once done."""
        row = self._make_3x3_row([self._shallow_3x3_entry()])
        chip_col = row._chip_col_widgets.get("Why1")
        self.assertIsNotNone(chip_col)
        self.assertFalse(chip_col.isHidden(), "chip column must not be hidden before edit")

        row._why_texts["Why1"].setPlainText("edited text")
        self._pump()

        self.assertTrue(chip_col.isHidden(), "chip column must be explicitly hidden after fade")

    def test_3x3_ignore_checkbox_hidden_with_chip_col(self):
        """The Ignore checkbox (inside chip_col_widget) is hidden together with the chip."""
        row = self._make_3x3_row([self._shallow_3x3_entry()])
        self.assertIn("Why1", row._ignore_checks)
        chip_col = row._chip_col_widgets["Why1"]

        row._why_texts["Why1"].setPlainText("edited")
        self._pump()

        self.assertTrue(chip_col.isHidden())

    def test_3x3_text_edit_not_hidden_after_fade(self):
        """The answer text box is not hidden; only the chip column is hidden."""
        row = self._make_3x3_row([self._shallow_3x3_entry()])
        row._why_texts["Why1"].setPlainText("edited")
        self._pump()

        self.assertFalse(row._why_texts["Why1"].isHidden(), "text edit must not be hidden after fade")

    # --- second edit does not retrigger ---

    def test_3x3_second_edit_does_not_retrigger(self):
        """A second edit on the same answer does not start another animation."""
        row = self._make_3x3_row([self._shallow_3x3_entry()])
        row._why_texts["Why1"].setPlainText("first edit")
        self._pump()
        chip_col = row._chip_col_widgets["Why1"]
        self.assertTrue(chip_col.isHidden())

        row._why_texts["Why1"].setPlainText("second edit")
        self._pump()
        self.assertTrue(chip_col.isHidden(), "chip column must remain hidden after second edit")
        self.assertIn("Why1", row._faded_cats)

    # --- edit then Save: chip gone on reopen ---

    def test_edit_then_save_chip_absent_on_reopen(self):
        """After editing and saving, the chip is gone on reopen (is_shallow cleared)."""
        entry = self._shallow_3x3_entry()
        row = self._make_3x3_row([entry])
        row._why_texts["Why1"].setPlainText("edited text")
        self._pump()

        saved = row.get_current_entries()
        why1 = next((e for e in saved if e.get("cat") == "Why1"), None)
        self.assertIsNotNone(why1)
        self.assertNotIn("is_shallow", why1)

        row2 = self._make_3x3_row(saved)
        self.assertNotIn("Why1", row2._chip_col_widgets)

    # --- restore original text then Save: chip back on reopen ---

    def test_restore_original_text_then_save_chip_back(self):
        """Restoring the exact original text preserves is_shallow; chip reappears on reopen."""
        entry = self._shallow_3x3_entry(why="my answer")
        row = self._make_3x3_row([entry])

        row._why_texts["Why1"].setPlainText("different text")
        self._pump()
        chip_col = row._chip_col_widgets.get("Why1")
        self.assertTrue(chip_col.isHidden(), "chip must be hidden in current session")

        row._why_texts["Why1"].setPlainText("my answer")  # restore

        saved = row.get_current_entries()
        why1 = next((e for e in saved if e.get("cat") == "Why1"), None)
        self.assertIsNotNone(why1)
        self.assertTrue(why1.get("is_shallow"), "is_shallow preserved when text matches original")

        row2 = self._make_3x3_row(saved)
        self.assertIn("Why1", row2._chip_col_widgets)
        self.assertFalse(row2._chip_col_widgets["Why1"].isHidden(), "chip must not be hidden on reopen")

    # --- edit then Cancel: chip back on reopen ---

    def test_edit_then_cancel_chip_back_on_reopen(self):
        """Cancel discards edits; original entry is unchanged; chip reappears on reopen."""
        entry = self._shallow_3x3_entry()
        row = self._make_3x3_row([entry])
        row._why_texts["Why1"].setPlainText("edited but cancelled")
        self._pump()

        # Cancel = don't save; reopen with original entry unchanged
        row2 = self._make_3x3_row([entry])
        chip_col = row2._chip_col_widgets.get("Why1")
        self.assertIsNotNone(chip_col)
        self.assertFalse(chip_col.isHidden(), "chip must not be hidden on reopen after cancel")

    # --- closing mid-fade raises nothing ---

    def test_close_during_fade_raises_nothing(self):
        """Destroying a row widget mid-fade does not raise RuntimeError."""
        entry = self._shallow_3x3_entry()
        row = self._make_3x3_row([entry], config=self._LONG_FADE_CFG)

        row._why_texts["Why1"].setPlainText("edit during long fade")
        # Animation is still running (10 s duration); delete the row
        row.deleteLater()
        self._pump()
        # No exception = pass

    # --- CLAMP/CCT fade, no resize ---

    def test_clamp_chip_fades_and_hides_on_edit(self):
        """Editing a CLAMP note fades and hides the chip."""
        row = self._make_clamp_row([self._shallow_clamp_entry()])
        chip = row._shallow_chip
        self.assertIsNotNone(chip)
        self.assertFalse(chip.isHidden(), "chip must not be hidden before edit")

        row._why_texts["why"].setPlainText("edited note")
        self._pump()

        self.assertTrue(chip.isHidden(), "chip must be explicitly hidden after fade")

    def test_clamp_ignore_checkbox_hidden_after_fade(self):
        """CLAMP Ignore checkbox is hidden together with the chip."""
        row = self._make_clamp_row([self._shallow_clamp_entry()])
        self.assertIsNotNone(row._ignore_check)

        row._why_texts["why"].setPlainText("edited note")
        self._pump()

        self.assertTrue(row._ignore_check.isHidden())

    def test_clamp_second_edit_does_not_retrigger(self):
        """Second edit on a CLAMP note does not restart the fade."""
        row = self._make_clamp_row([self._shallow_clamp_entry()])
        row._why_texts["why"].setPlainText("first edit")
        self._pump()
        chip = row._shallow_chip
        self.assertTrue(chip.isHidden())

        row._why_texts["why"].setPlainText("second edit")
        self._pump()
        self.assertTrue(chip.isHidden(), "chip must remain hidden after second edit")
        self.assertIn("why", row._faded_cats)

    # --- fade also works in ShowShallowTagsDialog (show_ignore_checkbox=True) ---

    def test_fade_works_with_show_ignore_checkbox_true(self):
        """Fade works when show_ignore_checkbox=True (ShowShallowTagsDialog path)."""
        row = self._make_3x3_row([self._shallow_3x3_entry()], show_ignore=True)
        chip_col = row._chip_col_widgets.get("Why1")
        self.assertIsNotNone(chip_col)

        row._why_texts["Why1"].setPlainText("edited in check logs")
        self._pump()

        self.assertTrue(chip_col.isHidden())


# ---------------------------------------------------------------------------
# Regression: debounce timer must not fire against a destroyed _TagRowWidget
# (the edited() signal crash: 'does not have a signal with the signature edited()')
# ---------------------------------------------------------------------------

@requires_qt
class TestDebounceCrashAfterDestroy(unittest.TestCase):
    """Guard against use-after-free in _TagRowWidget._edit_debounce.

    Before the fix, timer.timeout.connect(self.edited.emit) stored a strong-
    reference bound method.  If the C++ widget was destroyed (e.g. by its Qt
    parent) while the Python wrapper was kept alive by that bound method, the
    300 ms timer could fire against a dead — or reused — C++ object and raise
    "does not have a signal with the signature edited()" from inside a Qt callback.

    We reproduce the condition with sip.delete(), which destroys the C++ object
    immediately while leaving the Python wrapper alive (exactly what happens when
    a parent widget destroys its children before Python GC runs).
    """

    def setUp(self):
        import gc
        self._gc = gc
        self._unraisable: list = []
        self._orig_unraisable = sys.unraisablehook

        def _capture(args):
            self._unraisable.append(args)

        sys.unraisablehook = _capture

    def tearDown(self):
        sys.unraisablehook = self._orig_unraisable

    def _make_row(self):
        from app.views.dialogs.show_tags_dialog import _TagRowWidget
        from app.services.chess_log_storage_service import ChessLogStorageService
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "some note")
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=[entry],
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )

    def test_no_crash_after_widget_destroyed_with_pending_debounce(self):
        """sip.delete destroys C++ object while Python wrapper lives; timer must not crash."""
        from PyQt6 import sip
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtTest import QTest

        rows = [self._make_row() for _ in range(4)]

        # Trigger the debounce on every row (simulates user typing).
        for row in rows:
            row._schedule_edited()

        # Destroy C++ objects immediately (as Qt parent teardown would do), but keep
        # the Python wrappers alive in `rows`.  This is the exact crash scenario.
        for row in rows:
            sip.delete(row)

        # Wait longer than the 300 ms debounce so any pending timer can fire.
        QTest.qWait(400)
        QCoreApplication.processEvents()

        rows.clear()
        self._gc.collect()

        # Any exception in a Qt callback surfaces via unraisablehook.
        self.assertEqual(
            self._unraisable, [],
            "unexpected exception in Qt callback after widget destruction: "
            + "; ".join(str(u.exc_value) for u in self._unraisable),
        )


if __name__ == "__main__":
    unittest.main()
