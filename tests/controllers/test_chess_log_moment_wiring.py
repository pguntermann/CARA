"""Wiring and pre-fill tests for Log this Moment (#76).

Tests here drive the real entry point (_on_tag_moment) and the real MomentDialog
offscreen to confirm the correct preset is passed end-to-end.

Requires Qt (offscreen).  All tests are gated on _QT_AVAILABLE.
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
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QModelIndex

    _app = QApplication.instance() or QApplication(sys.argv[:1])

    from app.controllers.chess_log_controller import ChessLogController
    from app.models.database_model import GameData
    from app.views.detail_moveslist_view import DetailMovesListView
    from app.views.dialogs.moment_dialog import MomentDialog


MINIMAL_PGN = (
    '[Event "Test"]\n[Site "?"]\n[Date "2026.08.24"]\n'
    '[Round "?"]\n[White "White"]\n[Black "Black"]\n[Result "*"]\n\n'
    '1. e4 ( 1. d4 ) e5 2. Nf3 Nc6 *\n'
)


def _make_game(pgn: str = MINIMAL_PGN) -> "GameData":
    return GameData(game_number=1, pgn=pgn)


def _make_chess_log_ctrl(game: "GameData", active_preset: str = "3x3"):
    from app.models.database_model import GameData  # noqa: F401
    gm = MagicMock()
    gm.active_game = game
    gm.get_active_path.return_value = (0,)
    gm.active_game_changed = MagicMock()
    gm.active_game_changed.connect = MagicMock()
    gm.metadata_updated = MagicMock()
    gm.metadata_updated.emit = MagicMock()

    gc = MagicMock()
    gc.get_game_model.return_value = gm

    uss = MagicMock()
    uss.get_chess_log.return_value = {"active_preset": active_preset}

    ctrl = ChessLogController({}, gc, user_settings_service=uss)
    ctrl._cached_game_id = id(game)
    return ctrl, gm, gc


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available")
class TestTagMomentWiring(unittest.TestCase):
    """_on_tag_moment passes the preset from preset_for_logging() to MomentDialog.

    Fail-before: revert detail_moveslist_view.py:523 to get_active_preset().
    The test still calls MomentDialog.tag_moment but gets '3x3' (the setting)
    instead of 'CLAMP' (from game data) → AssertionError, not AttributeError.
    """

    def _make_view_with_clamp_game(self):
        """Return a view wired to a game that has a CLAMP entry, setting=3x3."""
        game = _make_game()
        ctrl, gm, gc = _make_chess_log_ctrl(game, active_preset="3x3")

        # Seed the in-memory cache with a CLAMP entry at path "0" (e4)
        ctrl._cached_paths_data = {"0": [{"preset": "CLAMP", "cat": "M", "why": ""}]}

        view = DetailMovesListView(config={})
        view._chess_log_controller = ctrl
        view._game_model = gm
        view._game_controller = gc

        # Minimal moves-list model mock: one row, white move "e4"
        move_data = MagicMock()
        move_data.white_move = "e4"
        move_data.black_move = None
        move_data.move_number = 1

        mlm = MagicMock()
        mlm.get_move.return_value = move_data
        view._moveslist_model = mlm

        return view, gc

    def test_preset_for_logging_result_reaches_moment_dialog(self):
        """preset_for_logging() returns CLAMP; MomentDialog.tag_moment is called
        with active_preset='CLAMP', not the setting '3x3'."""
        view, gc = self._make_view_with_clamp_game()

        captured: list = []

        def fake_tag_moment(config, active_preset, *args, **kwargs):
            captured.append(active_preset)
            return None  # simulate Cancel — no entries saved

        index = MagicMock(spec=QModelIndex)
        index.isValid.return_value = True
        index.row.return_value = 0
        from app.models.moveslist_model import MovesListModel
        index.column.return_value = MovesListModel.COL_WHITE

        gc.navigate_to_ply.return_value = True

        with patch("app.controllers.chess_log_controller.encode_path", return_value="0"):
            with patch(
                "app.views.dialogs.moment_dialog.MomentDialog.tag_moment",
                side_effect=fake_tag_moment,
            ):
                with patch.object(
                    view._chess_log_controller,
                    "should_confirm_extra_moment",
                    return_value=True,
                ):
                    view._on_tag_moment(index)

        self.assertEqual(len(captured), 1, "MomentDialog.tag_moment was not called")
        self.assertEqual(
            captured[0],
            "CLAMP",
            f"Expected active_preset='CLAMP' but got {captured[0]!r}",
        )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available")
class TestMomentDialogPrefill(unittest.TestCase):
    """MomentDialog pre-fills CLAMP entries when opened with active_preset='CLAMP'.

    This is the real mechanism: once preset_for_logging() returns 'CLAMP' and
    that value is passed to MomentDialog, the existing entries are pre-filled.
    The test replaces the tautological save test (test_new_moment_on_clamp_game_stored_as_clamp)
    which only verified add_moment_at_active_path.  Both tests are kept: this one
    tests MomentDialog behavior directly; the save test covers the storage path.
    """

    def test_clamp_entries_prefilled_and_returned(self):
        """Construct MomentDialog with CLAMP preset and a CLAMP existing entry.
        The 'M' chip must be pre-checked, and get_entries() must carry preset='CLAMP'."""
        existing = [{"preset": "CLAMP", "cat": "M", "why": "Loose bishop"}]
        dlg = MomentDialog(
            config={},
            active_preset="CLAMP",
            move_number=1,
            san="e4",
            is_white=True,
            existing_entries=existing,
        )

        # The 'M' chip must be checked (pre-filled from existing entries)
        checked_cats = [cat for cat, btn in dlg._chip_buttons if btn.isChecked()]
        self.assertIn("M", checked_cats, f"'M' chip not pre-filled; checked={checked_cats}")

        # Simulate accepting the dialog (chip already checked)
        entries = dlg.get_entries()
        self.assertTrue(entries, "get_entries() returned empty after pre-fill")
        self.assertTrue(
            all(e["preset"] == "CLAMP" for e in entries),
            f"Expected all presets='CLAMP', got {entries}",
        )
        self.assertIn("M", [e["cat"] for e in entries])

    def test_3x3_entries_not_shown_as_clamp(self):
        """3x3 existing entries are shown in 'Also tagged:' line, not pre-filled."""
        existing = [
            {"preset": "3x3", "cat": "Why1", "why": "Reason"},
            {"preset": "CLAMP", "cat": "A", "why": ""},
        ]
        dlg = MomentDialog(
            config={},
            active_preset="CLAMP",
            move_number=2,
            san="e5",
            is_white=False,
            existing_entries=existing,
        )
        # Only 'A' should be pre-filled (CLAMP entry); Why1 is a 3x3 entry
        checked_cats = [cat for cat, btn in dlg._chip_buttons if btn.isChecked()]
        self.assertIn("A", checked_cats)
        # 'M' should not be checked
        self.assertNotIn("M", checked_cats)


if __name__ == "__main__":
    unittest.main()
