"""Issue #91: the Chess Log tab keeps its results in one place (the controller),
and every export lists only *saved* Check Logs flags.

Covers:
  - Cancelled / unsaved classifier verdicts are never exported
  - Saved vague-only results are exported
  - Copy log as text, Copy log as HTML and the PDF report list the same moments
    with the same chip flags
  - Theme rebuild: the new view reads the same results from the controller
  - The no-notes Check Logs run leaves no stale result anywhere
  - Guard: the view keeps no result copies and never reads the combo boxes to export
"""

from __future__ import annotations

import inspect
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
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication, QWidget
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"][Round "?"]'
    '[White "Alice"][Black "Bob"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 *\n"
)

SHALLOW_CHIP = "#9a4400"
VAGUE_CHIP = "#1d4ed8"


def _entry(preset, cat, why, **flags):
    from app.services.chess_log_storage_service import ChessLogStorageService
    e = ChessLogStorageService.make_entry(preset, cat, why)
    e.update(flags)
    return e


def _game(tags, white="Alice", black="Bob"):
    """A game whose PGN carries *tags* ({path_key: [entries]})."""
    from app.models.database_model import GameData
    from app.services.chess_log_storage_service import ChessLogStorageService
    pgn = _PGN.replace("Alice", white).replace("Bob", black)
    game = GameData(game_number=1, pgn=pgn, white=white, black=black, has_chess_log_tags=True)
    ChessLogStorageService.store_tags(game, tags, {})
    return game


class _Harness:
    """A real charts controller + real ChessLogController over *games*."""

    def __init__(self, games, player="Alice"):
        from app.controllers.chess_log_charts_controller import ChessLogChartsController
        from app.controllers.chess_log_controller import ChessLogController
        self.games = games
        self.owner = ChessLogController(config={}, game_controller=MagicMock(), database_controller=None)
        self.ctrl = ChessLogChartsController({}, MagicMock())
        self.ctrl.set_chess_log_controller(self.owner)
        self.ctrl._source_selection = 1
        self.ctrl._current_player = player
        self.ctrl._player_explicit_selected = bool(player)
        self._patches = [
            patch.object(self.ctrl, "_resolve_games", return_value=games),
            patch.object(self.ctrl, "get_current_source_filenames", return_value=[]),
        ]
        for p in self._patches:
            p.start()

    def view(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        view = DetailChessLogChartsView({})
        with patch.object(self.ctrl, "_start_dropdown_worker"):
            view.set_controller(self.ctrl)
        return view

    def close(self):
        for p in self._patches:
            p.stop()


def _clipboard():
    mime = QApplication.clipboard().mimeData()
    return mime.text(), mime.html()


@requires_qt
class TestOnlySavedFlagsAreExported(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def test_cancelled_check_logs_result_is_not_exported(self):
        game = _game({"0": [_entry("CLAMP", "C", "I attacked too early")]})  # no saved flag
        self.h = _Harness([game])
        # The classifier flagged it, but the dialog was Cancelled: nothing was written.
        self.h.ctrl._on_shallow_thread_ready(
            frozenset({(game, "0", "CLAMP", "")}), frozenset(), frozenset({(game, "0", "CLAMP", "")}), None,
        )
        self.assertEqual(self.h.ctrl.get_check_log_moments(), [])
        view = self.h.view()
        view._copy_log_to_clipboard()
        text, html = _clipboard()
        self.assertNotIn("Check Logs:", text)
        self.assertNotIn(SHALLOW_CHIP, html)
        self.assertNotIn("I attacked too early", html)

    def test_saved_vague_only_result_is_exported(self):
        game = _game({"0": [_entry("3x3", "Why4", "Calculate next time", is_vague=True)]})
        self.h = _Harness([game])
        moments = self.h.ctrl.get_check_log_moments()
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0].vague_cats, frozenset({"Why4"}))
        self.assertEqual(moments[0].shallow_cats, frozenset())
        view = self.h.view()
        view._copy_log_to_clipboard()
        text, html = _clipboard()
        self.assertIn("Check Logs:", text)
        self.assertIn("Calculate next time", text)
        self.assertIn(VAGUE_CHIP, html)

    def test_session_result_is_irrelevant_to_exports(self):
        """A saved flag is exported even when this session ran no Check Logs at all."""
        game = _game({"0": [_entry("CLAMP", "C", "note", is_shallow=True)]})
        self.h = _Harness([game])
        self.assertEqual(self.h.ctrl.get_last_shallow_result()[:2], (frozenset(), frozenset()))
        self.assertEqual(len(self.h.ctrl.get_check_log_moments()), 1)


@requires_qt
class TestExportScope(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def test_other_players_games_and_opponent_moves_are_excluded(self):
        mine = _game({
            "0": [_entry("CLAMP", "C", "my move", is_shallow=True)],         # White just moved: Alice
            "0.0": [_entry("CLAMP", "L", "opp move", is_shallow=True)],      # Black just moved: Bob
        })
        theirs = _game({"0": [_entry("CLAMP", "C", "other game", is_shallow=True)]},
                       white="Carol", black="Dave")
        self.h = _Harness([mine, theirs])
        moments = self.h.ctrl.get_check_log_moments()
        self.assertEqual([m.path_key for m in moments], ["0"])
        self.assertIs(moments[0].game, mine)

    def test_count_agrees_with_narrative_header(self):
        from app.services.chess_log_stats_service import compute_narrative_counts
        game = _game({
            "0": [_entry("CLAMP", "C", "a", is_shallow=True)],
            "0.0.0": [_entry("3x3", "Why4", "b", is_vague=True)],
            "0.0": [_entry("CLAMP", "L", "not flagged")],
        })
        self.h = _Harness([game])
        _n, _g, _m, s_flagged, _x = compute_narrative_counts(
            [game], "Alice", "both", self.h.owner.get_tags_for_game,
        )
        self.assertEqual(len(self.h.ctrl.get_check_log_moments()), s_flagged)

    def test_no_player_selected_exports_nothing(self):
        game = _game({"0": [_entry("CLAMP", "C", "a", is_shallow=True)]})
        self.h = _Harness([game], player="")
        self.assertEqual(self.h.ctrl.get_check_log_moments(), [])

    def test_agrees_with_show_shallow_vague_logs(self):
        game = _game({
            "0": [_entry("CLAMP", "C", "a", is_shallow=True)],
            "0.0.0": [_entry("3x3", "Why2", "b", is_shallow=True), _entry("3x3", "Why4", "c", is_vague=True)],
        })
        self.h = _Harness([game])
        shallow, vague = self.h.owner.get_shallow_vague_keys([game])
        listed = {(k[1], k[2]) for k in shallow | vague}
        exported = {(m.path_key, m.preset) for m in self.h.ctrl.get_check_log_moments()}
        self.assertEqual(listed, exported)


@requires_qt
class TestThreeFormatsAgree(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def test_text_html_and_pdf_list_the_same_moments_with_the_same_flags(self):
        from app.services.chess_log_pdf_service import ChessLogPDFService
        game = _game({
            "0": [_entry("CLAMP", "C", "clamp shallow note", is_shallow=True)],
            "0.0.0": [
                _entry("3x3", "Why1", "why one"),
                _entry("3x3", "Why2", "why two generic", is_shallow=True),
                _entry("3x3", "Why4", "vague lesson", is_vague=True),
            ],
        })
        self.h = _Harness([game])
        moments = self.h.ctrl.get_check_log_moments()
        self.assertEqual(len(moments), 2)
        view = self.h.view()

        view._copy_log_to_clipboard()
        text, html = _clipboard()

        captured = {}

        def _fake_export(_svc, path, player, source, pixmaps, narrative, rows, **kw):
            captured["rows"] = rows

        with patch.object(ChessLogPDFService, "export_charts_report", _fake_export), \
                patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=("x.pdf", "")):
            view._export_pdf_report()
        pdf_rows = captured["rows"]

        # Same moments, in the same order, in all three.
        # Text (#93): each flagged moment is listed whole; flagged answers carry a marker.
        marked = [ln for ln in text.splitlines() if ln.endswith("[Shallow]") or ln.endswith("[Vague]")]
        self.assertEqual(len(marked), 3)    # CLAMP note; 3x3 Why2; 3x3 Why4
        self.assertIn("clamp shallow note", marked[0])
        self.assertIn("why two generic", marked[1])
        self.assertIn("vague lesson", marked[2])
        self.assertIn("why one", text)      # the whole moment is listed, unflagged answers too
        self.assertEqual(len(pdf_rows), len(moments))
        for row, mo in zip(pdf_rows, moments):
            self.assertEqual(row.preset, mo.preset)
            self.assertEqual(row.entries, mo.entries)
            # Same chip flags in the PDF rows as the controller computed (and HTML uses).
            self.assertEqual(
                (row.is_shallow, row.is_vague, row.shallow_cats, row.vague_cats),
                (mo.is_shallow, mo.is_vague, mo.shallow_cats, mo.vague_cats),
            )
        html_rows = [r for g in view._build_check_log_tag_groups() for r in g["rows"]]
        self.assertEqual(
            [(r.preset, r.is_shallow, r.is_vague, r.shallow_cats, r.vague_cats) for r in html_rows],
            [(r.preset, r.is_shallow, r.is_vague, r.shallow_cats, r.vague_cats) for r in pdf_rows],
        )
        # The flags the PDF carries are the ones the HTML draws as chips.
        self.assertEqual(html.count(SHALLOW_CHIP), 2)   # CLAMP moment + 3x3 Why2
        self.assertEqual(html.count(VAGUE_CHIP), 1)     # 3x3 Why4
        self.assertTrue(pdf_rows[0].is_shallow)
        self.assertEqual(pdf_rows[1].shallow_cats, frozenset({"Why2"}))
        self.assertEqual(pdf_rows[1].vague_cats, frozenset({"Why4"}))


@requires_qt
class TestPlayerAndSourceComeFromController(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def test_labels(self):
        self.h = _Harness([])
        from app.controllers.chess_log_charts_controller import SOURCE_LABELS
        for i, label in enumerate(SOURCE_LABELS):
            self.h.ctrl._source_selection = i
            self.assertEqual(self.h.ctrl.get_source_label(), label)
        self.assertEqual(self.h.ctrl.get_player_display_name(), "Alice")

    def test_description_appends_database_names(self):
        self.h = _Harness([])
        with patch.object(self.h.ctrl, "get_current_source_filenames", return_value=["a.pgn", "b.pgn"]):
            self.assertEqual(self.h.ctrl.get_source_description(), "Active Database: a.pgn, b.pgn")

    def test_export_header_survives_a_blank_rebuilt_combo(self):
        """The export names the player and source from the controller, not the combos."""
        game = _game({"0": [_entry("CLAMP", "C", "n", is_shallow=True)]})
        self.h = _Harness([game])
        view = self.h.view()
        for combo, index in ((view._player_combo, -1), (view._source_combo, 0)):
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        view._copy_log_to_clipboard()
        text, html = _clipboard()
        self.assertIn("Chess Log — Alice", text)
        self.assertIn("Source: Active Database", text)


@requires_qt
class TestThemeRebuildReadsFromController(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def test_rebuilt_view_shows_the_same_results(self):
        from app.services.ai_service import TokenUsage
        game = _game({"0": [_entry("CLAMP", "C", "n", is_shallow=True)]})
        self.h = _Harness([game])
        usage = TokenUsage(input_tokens=5, output_tokens=9, reasoning_tokens=None, reported=True)
        self.h.ctrl._on_narrative_thread_ready("Narrative.", [], usage)
        self.h.ctrl._on_shallow_thread_ready(
            frozenset({(game, "0", "CLAMP", "")}), frozenset(), frozenset(), usage,
        )
        before = self.h.view()
        before._copy_log_to_clipboard()
        text_before, html_before = _clipboard()

        after = self.h.view()   # what apply_theme() does: a fresh view on the same controller
        after._copy_log_to_clipboard()
        text_after, html_after = _clipboard()

        self.assertEqual(text_after, text_before)
        self.assertEqual(html_after, html_before)
        self.assertEqual(after._narrative_edit.toPlainText(), before._narrative_edit.toPlainText())
        self.assertEqual(after._shallow_token_label.text(), before._shallow_token_label.text())
        self.assertIn("9", after._shallow_token_label.text())
        self.assertIn("Narrative.", text_after)

    def test_vague_only_session_result_is_restored(self):
        game = _game({"0": [_entry("3x3", "Why4", "lesson", is_vague=True)]})
        self.h = _Harness([game])
        vague = frozenset({(game, "0", "3x3", "Why4")})
        self.h.ctrl._on_shallow_thread_ready(frozenset(), vague, frozenset(vague), None)
        self.h.view()
        self.assertEqual(self.h.ctrl.get_last_shallow_result()[:2], (frozenset(), vague))


@requires_qt
class TestThemeRebuildRestoresSelectors(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def test_source_player_and_timeout_shown_without_side_effects(self):
        game = _game({"0": [_entry("CLAMP", "C", "n")]})
        self.h = _Harness([game])
        self.h.ctrl._source_selection = 2
        self.h.ctrl._last_players = [("Alice", 3), ("Bob", 1)]
        fired = []
        for sig in ("results_invalidated", "player_selection_cleared", "charts_loading",
                    "charts_unavailable", "charts_updated"):
            getattr(self.h.ctrl, sig).connect(lambda *a, n=sig: fired.append(n))
        with patch.object(self.h.ctrl, "_kick_debounce") as kick, \
                patch.object(self.h.ctrl, "set_source_selection") as set_src, \
                patch.object(self.h.ctrl, "set_player_selection") as set_pl, \
                patch.object(self.h.ctrl, "get_narrative_timeout_seconds", return_value=90):
            view = self.h.view()
        self.assertEqual(view._source_combo.currentIndex(), 2)
        self.assertEqual(view._player_combo.currentText(), "Alice (3 logged)")
        self.assertEqual(view._player_combo.currentData(), "Alice")
        self.assertEqual(view._timeout_spin.value(), 90)
        self.assertEqual(fired, [])
        kick.assert_not_called()
        set_src.assert_not_called()
        set_pl.assert_not_called()
        self.assertEqual(self.h.ctrl.get_player_display_name(), "Alice")
        self.assertEqual(self.h.ctrl.get_source_selection(), 2)

    def test_charts_outcome_replayed_on_rebuilt_view(self):
        self.h = _Harness([])
        series = {"CLAMP": MagicMock()}
        with patch("app.views.detail_chess_log_charts_view.ChessLogCategoryChartWidget") as widget:
            widget.return_value = QWidget()
            widget.return_value.set_series = MagicMock()
            self.h.ctrl.charts_updated.emit(series)
            self.h.ctrl.charts_skipped.emit(1)
            view = self.h.view()
        self.assertEqual(len(view._chart_widgets), 1)
        self.assertIn("1 game not charted", view._skip_note.text())
        self.h.ctrl.charts_unavailable.emit("no_player")
        view = self.h.view()
        self.assertEqual(len(view._chart_widgets), 0)
        self.assertIn("Select a player", view._placeholder.text())
        self.h.ctrl.charts_loading.emit()
        self.assertEqual(self.h.ctrl.get_last_chart_events(), [])

    def test_no_player_selected_shows_placeholder(self):
        self.h = _Harness([], player="")
        self.h.ctrl._source_selection = 1
        self.h.ctrl._last_players = [("Alice", 3)]
        view = self.h.view()
        self.assertEqual(view._source_combo.currentIndex(), 1)
        self.assertEqual(view._player_combo.currentIndex(), -1)
        self.assertEqual(view._player_combo.lineEdit().placeholderText(), "Select player")

    def test_player_kept_when_list_not_delivered_yet(self):
        self.h = _Harness([])
        view = self.h.view()
        self.assertEqual(view._player_combo.currentData(), "Alice")

    def test_controller_remembers_list_and_drops_it_on_source_change(self):
        self.h = _Harness([])
        self.h.ctrl._on_players_ready([("Alice", 2)])
        self.assertEqual(self.h.ctrl.get_last_players(), [("Alice", 2)])
        with patch.object(self.h.ctrl, "_start_dropdown_worker"):
            self.h.ctrl.set_source_selection(2)
        self.assertEqual(self.h.ctrl.get_last_players(), [])


@requires_qt
class TestNoNotesRunLeavesNothingStale(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def test_empty_run_clears_the_result_everywhere(self):
        from app.services.ai_service import TokenUsage
        game = _game({"0": [_entry("CLAMP", "C", "n")]})
        self.h = _Harness([game])
        usage = TokenUsage(input_tokens=5, output_tokens=9, reasoning_tokens=None, reported=True)
        # A previous run left a result behind.
        self.h.ctrl._on_shallow_thread_ready(
            frozenset({(game, "0", "CLAMP", "")}), frozenset(), frozenset(), usage,
        )
        view = self.h.view()
        self.assertIn("9", view._shallow_token_label.text())

        received = []
        self.h.ctrl.shallow_ready.connect(lambda *a: received.append(a))
        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider",
                   return_value=("openai", "m", "k", None)), \
                patch("app.services.chess_log_shallow_service.build_notes", return_value=({}, {}, {})), \
                patch("app.views.dialogs.message_dialog.MessageDialog.show_information"):
            self.h.ctrl.request_flag_shallow_notes()

        self.assertEqual(len(received), 1)
        # Controller: empty sets, never None, and no leftover usage.
        self.assertEqual(self.h.ctrl.get_last_shallow_result(), (frozenset(), frozenset(), None))
        # View: no token label; a rebuilt view shows none either.
        self.assertEqual(view._shallow_token_label.text(), "")
        rebuilt = self.h.view()
        self.assertEqual(rebuilt._shallow_token_label.text(), "")
        # Exports: nothing flagged was saved, so no Check Logs section.
        view._copy_log_to_clipboard()
        self.assertNotIn("Check Logs:", _clipboard()[0])


@requires_qt
class TestViewKeepsNoCopiesGuard(unittest.TestCase):
    EXPORT_METHODS = (
        "_copy_section_to_clipboard", "_narrative_html_for_copy", "_copy_log_to_clipboard",
        "_charts_log_html_for_copy", "_build_check_log_tag_groups", "_check_log_moments",
        "_export_pdf_report", "_export_narrative_pdf", "_export_header", "_narrative_text",
        "_narrative_metadata",
    )

    def test_view_has_no_result_copy_attributes(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        view = DetailChessLogChartsView({})
        for attr in ("_last_shallow_keys", "_last_vague_keys", "_last_narrative"):
            self.assertFalse(hasattr(view, attr), attr)

    def test_view_source_never_assigns_result_copies(self):
        from app.views import detail_chess_log_charts_view as mod
        src = inspect.getsource(mod)
        for attr in ("_last_shallow_keys", "_last_vague_keys", "_last_narrative"):
            self.assertNotRegex(src, r"self\." + attr + r"\b")

    def test_export_methods_never_read_the_combo_boxes(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        for name in self.EXPORT_METHODS:
            src = inspect.getsource(getattr(DetailChessLogChartsView, name))
            self.assertNotIn("_player_combo", src, name)
            self.assertNotIn("_source_combo", src, name)

    def test_only_the_controller_clear_method_resets_results(self):
        """Exactly one place in the controller drops stored results."""
        from app.controllers import chess_log_charts_controller as mod
        src = inspect.getsource(mod)
        self.assertEqual(src.count("self.results_invalidated.emit()"), 1)


if __name__ == "__main__":
    unittest.main()
