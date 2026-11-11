"""Tests for Export to PDF additions to ShowTagsDialog and _TagRowWidget.snapshot()."""

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
    from app.views.dialogs.show_tags_dialog import _TagRowWidget, ShowTagsDialog

MAINLINE_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)


def _make_game_data(pgn: str = MAINLINE_PGN, game_number: int = 1):
    from app.models.database_model import GameData
    return GameData(game_number=game_number, pgn=pgn)


def _make_mock_controller(game):
    ctrl = MagicMock()
    ctrl.get_tags_for_game.return_value = {
        "0": [{"preset": "CLAMP", "cat": "C", "why": "test", "id": "x", "created": "y"}]
    }
    return ctrl


@requires_qt
class TestTagRowWidgetSnapshot(unittest.TestCase):
    def _make_row(self, preset="CLAMP", entries=None, show_ignore=False):
        if entries is None:
            entries = [{"preset": preset, "cat": "C", "why": "a note", "id": "x", "created": "y"}]
        return _TagRowWidget(
            config={},
            preset=preset,
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            show_ignore_checkbox=show_ignore,
        )

    def test_snapshot_returns_tag_row_snapshot(self):
        row = self._make_row()
        snap = row.snapshot()
        self.assertIsInstance(snap, TagRowSnapshot)

    def test_snapshot_move_label(self):
        row = self._make_row()
        snap = row.snapshot()
        self.assertEqual(snap.move_label, "1. e4")

    def test_snapshot_preset(self):
        row = self._make_row(preset="CCT")
        snap = row.snapshot()
        self.assertEqual(snap.preset, "CCT")

    def test_snapshot_fen_none(self):
        row = self._make_row()
        snap = row.snapshot()
        self.assertIsNone(snap.fen)

    def test_snapshot_show_ignore_false(self):
        row = self._make_row(show_ignore=False)
        snap = row.snapshot()
        self.assertFalse(snap.show_ignore)

    def test_snapshot_show_ignore_true(self):
        row = self._make_row(
            entries=[{"preset": "CLAMP", "cat": "C", "why": "", "id": "x", "created": "y", "is_shallow": True}],
            show_ignore=True,
        )
        snap = row.snapshot()
        self.assertTrue(snap.show_ignore)

    def test_snapshot_entries_reflects_current_state(self):
        row = self._make_row()
        snap = row.snapshot()
        # entries should be non-empty since "C" checkbox is checked
        self.assertTrue(any(e.get("cat") == "C" for e in snap.entries))

    def test_fen_and_played_move_stored(self):
        import chess
        move = chess.Move.from_uci("e2e4")
        fen = chess.STARTING_FEN
        row = _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=[],
            move_label="1. e4",
            fen=fen,
            played_move=move,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )
        self.assertEqual(row._fen, fen)
        self.assertEqual(row._played_move, move)
        snap = row.snapshot()
        self.assertEqual(snap.fen, fen)
        self.assertEqual(snap.played_move, move)


@requires_qt
class TestShowTagsDialogExportButton(unittest.TestCase):
    def _make_dialog(self):
        game = _make_game_data()
        ctrl = _make_mock_controller(game)
        return ShowTagsDialog(config={}, games=[game], controller=ctrl)

    def test_export_pdf_button_exists(self):
        dlg = self._make_dialog()
        export_btn = dlg.findChild(QPushButton, "", options=Qt.FindChildOption.FindChildrenRecursively)
        buttons = [w for w in dlg.findChildren(QPushButton) if "Export" in w.text()]
        self.assertTrue(len(buttons) >= 1, "No Export button found in ShowTagsDialog")

    def test_export_pdf_button_enabled_when_rows_present(self):
        dlg = self._make_dialog()
        export_btn = next(
            (w for w in dlg.findChildren(QPushButton) if "Export" in w.text()), None
        )
        self.assertIsNotNone(export_btn)
        # Dialog has rows (the mock controller returns one row), so button should be enabled
        self.assertTrue(export_btn.isEnabled())


if _QT_OK:
    from PyQt6.QtCore import Qt


@requires_qt
class TestSnapshot3x3PerCatFields(unittest.TestCase):
    """B5 — snapshot() populates shallow_cats and vague_cats for 3x3 rows."""

    def _make_3x3_row(self, entries):
        return _TagRowWidget(
            config={},
            preset="3x3",
            entries=entries,
            move_label="5. d4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )

    def test_shallow_cats_empty_when_no_flags(self):
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "a", "id": "1", "created": "c"},
            {"preset": "3x3", "cat": "Why2", "why": "b", "id": "2", "created": "c"},
            {"preset": "3x3", "cat": "Why3", "why": "c", "id": "3", "created": "c"},
            {"preset": "3x3", "cat": "Why4", "why": "d", "id": "4", "created": "c"},
        ]
        snap = self._make_3x3_row(entries).snapshot()
        self.assertEqual(snap.shallow_cats, frozenset())
        self.assertEqual(snap.vague_cats, frozenset())

    def test_shallow_cats_populated_for_generic_why1(self):
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "a", "id": "1", "created": "c", "is_shallow": True},
            {"preset": "3x3", "cat": "Why2", "why": "b", "id": "2", "created": "c"},
            {"preset": "3x3", "cat": "Why3", "why": "c", "id": "3", "created": "c"},
            {"preset": "3x3", "cat": "Why4", "why": "d", "id": "4", "created": "c"},
        ]
        snap = self._make_3x3_row(entries).snapshot()
        self.assertIn("Why1", snap.shallow_cats)
        self.assertNotIn("Why2", snap.shallow_cats)
        self.assertNotIn("Why3", snap.shallow_cats)
        self.assertEqual(snap.vague_cats, frozenset())

    def test_vague_cats_populated_for_filler_why4(self):
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "a", "id": "1", "created": "c"},
            {"preset": "3x3", "cat": "Why2", "why": "b", "id": "2", "created": "c"},
            {"preset": "3x3", "cat": "Why3", "why": "c", "id": "3", "created": "c"},
            {"preset": "3x3", "cat": "Why4", "why": "d", "id": "4", "created": "c", "is_vague": True},
        ]
        snap = self._make_3x3_row(entries).snapshot()
        self.assertEqual(snap.shallow_cats, frozenset())
        self.assertIn("Why4", snap.vague_cats)

    def test_all_cats_flagged_populates_all(self):
        entries = [
            {"preset": "3x3", "cat": "Why1", "why": "a", "id": "1", "created": "c", "is_shallow": True},
            {"preset": "3x3", "cat": "Why2", "why": "b", "id": "2", "created": "c", "is_shallow": True},
            {"preset": "3x3", "cat": "Why3", "why": "c", "id": "3", "created": "c", "is_shallow": True},
            {"preset": "3x3", "cat": "Why4", "why": "d", "id": "4", "created": "c", "is_vague": True},
        ]
        snap = self._make_3x3_row(entries).snapshot()
        self.assertEqual(snap.shallow_cats, frozenset({"Why1", "Why2", "Why3"}))
        self.assertEqual(snap.vague_cats, frozenset({"Why4"}))

    def test_clamp_row_has_empty_per_cat_fields(self):
        entries = [
            {"preset": "CLAMP", "cat": "C", "why": "a", "id": "1", "created": "c", "is_shallow": True},
        ]
        row = _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=entries,
            move_label="1. e4",
            fen=None,
            played_move=None,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
        )
        snap = row.snapshot()
        self.assertEqual(snap.shallow_cats, frozenset(), "CLAMP must not populate shallow_cats")
        self.assertEqual(snap.vague_cats, frozenset(), "CLAMP must not populate vague_cats")


@requires_qt
class TestChessLogPDFIgnoresDialogSettings(unittest.TestCase):
    """PDF export ignores View → Miniature Boards → Chess Log scale and arrow toggles.

    Proved in two parts:
    (a) snapshot() preserves both moves even when the dialog arrows are off —
        the snapshot is the source of truth for the PDF, and its played_move /
        best_move fields are never filtered by show_played / show_best.
    (b) ChessLogPDFService._render_board uses a fixed size_override
        (_BOARD_DISPLAY_PT * _BOARD_RENDER_SCALE) independent of any user
        setting — patching MiniChessBoardWidget confirms the argument.
    """

    def _make_row_with_moves(self, show_played=True, show_best=True, scale_factor=1.25):
        import chess
        played = chess.Move.from_uci("e2e4")
        best = chess.Move.from_uci("d2d4")
        fen = chess.STARTING_FEN
        entries = [{"preset": "CLAMP", "cat": "C", "why": "note", "id": "x", "created": "y"}]
        return _TagRowWidget(
            config={},
            preset="CLAMP",
            entries=entries,
            move_label="1. e4",
            fen=fen,
            played_move=played,
            bg_rgb=[40, 40, 45],
            text_color=[200, 200, 200],
            best_move=best,
            show_played=show_played,
            show_best=show_best,
            scale_factor=scale_factor,
        )

    def test_snapshot_preserves_played_move_when_show_played_false(self):
        """snapshot() carries played_move regardless of show_played toggle."""
        row = self._make_row_with_moves(show_played=False, show_best=False)
        snap = row.snapshot()
        import chess
        self.assertEqual(snap.played_move, chess.Move.from_uci("e2e4"))

    def test_snapshot_preserves_best_move_when_show_best_false(self):
        """snapshot() carries best_move regardless of show_best toggle."""
        row = self._make_row_with_moves(show_played=False, show_best=False)
        snap = row.snapshot()
        import chess
        self.assertEqual(snap.best_move, chess.Move.from_uci("d2d4"))

    def test_pdf_board_size_fixed_at_400px(self):
        """PDF render always uses 400px (100pt * 4) regardless of Chess Log scale."""
        from app.services.chess_log_pdf_service import ChessLogPDFService
        expected_px = int(ChessLogPDFService._BOARD_DISPLAY_PT * ChessLogPDFService._BOARD_RENDER_SCALE)
        self.assertEqual(expected_px, 400)

    def test_pdf_render_passes_fixed_size_not_dialog_scale(self):
        """_render_board uses size_override=400, never the Chess Log dialog scale."""
        import chess
        from unittest.mock import patch, MagicMock
        from app.services.chess_log_pdf_service import ChessLogPDFService

        captured = {}

        class FakeWidget:
            def __init__(self, *a, **kw):
                captured["size_override"] = kw.get("size_override")
                captured["scale_factor"] = kw.get("scale_factor")
            def set_played_and_best(self, played, best):
                captured["played"] = played
                captured["best"] = best
            def size(self):
                from PyQt6.QtCore import QSize
                return QSize(400, 400)
            def render(self, image):
                pass

        svc = ChessLogPDFService({})
        played = chess.Move.from_uci("e2e4")
        best = chess.Move.from_uci("d2d4")
        fen = chess.STARTING_FEN

        with patch("app.views.widgets.mini_chessboard_widget.MiniChessBoardWidget", FakeWidget):
            svc._render_board(fen, played, best, is_flipped=False)

        # size_override must be the fixed PDF size (400px), not derived from dialog scale
        self.assertEqual(captured.get("size_override"), 400,
                         "PDF must use fixed 400px, not Chess Log dialog scale")
        # scale_factor must NOT be passed (PDF uses size_override instead)
        self.assertIsNone(captured.get("scale_factor"),
                          "PDF must not pass scale_factor to MiniChessBoardWidget")

    def test_pdf_render_passes_both_arrows_when_arrows_off_in_dialog(self):
        """PDF calls set_played_and_best with both moves even if dialog arrows were off.

        The dialog's show_played / show_best flags only affect the live dialog board.
        snapshot() always carries the original moves, so the PDF always gets both.
        """
        import chess
        from unittest.mock import patch
        from app.services.chess_log_pdf_service import ChessLogPDFService

        captured = {}

        class FakeWidget:
            def __init__(self, *a, **kw):
                pass
            def set_played_and_best(self, played, best):
                captured["played"] = played
                captured["best"] = best
            def size(self):
                from PyQt6.QtCore import QSize
                return QSize(400, 400)
            def render(self, image):
                pass

        svc = ChessLogPDFService({})
        played = chess.Move.from_uci("e2e4")
        best = chess.Move.from_uci("d2d4")
        fen = chess.STARTING_FEN

        # Simulate a snapshot taken from a row where arrows were OFF: the snapshot
        # still carries both moves (they come from _played_move / _best_move, not
        # filtered by show_played / show_best).
        row = self._make_row_with_moves(show_played=False, show_best=False, scale_factor=1.75)
        snap = row.snapshot()

        with patch("app.views.widgets.mini_chessboard_widget.MiniChessBoardWidget", FakeWidget):
            svc._render_board(snap.fen, snap.played_move, snap.best_move)

        self.assertEqual(captured.get("played"), played,
                         "PDF must receive played_move even when dialog show_played=False")
        self.assertEqual(captured.get("best"), best,
                         "PDF must receive best_move even when dialog show_best=False")


if __name__ == "__main__":
    unittest.main()
