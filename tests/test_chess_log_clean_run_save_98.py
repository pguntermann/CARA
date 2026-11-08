"""#98: a Check Logs run that flags nothing can be Saved (Nothing Flagged → Save / Cancel).

The AI response is stubbed throughout (no API calls).  Real ChessLogController,
real ChessLogChartsController and real PGN round-trips; only the database
controller and the message dialog's button press are faked.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = Path(__file__).resolve().parent.parent


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True, timeout=10, cwd=str(_REPO))
        return r.returncode == 0 and b"ok" in r.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

MAINLINE_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)

_CONFIG = {
    "ui": {"dialogs": {"chess_log_messages": {"shallow_notes": {
        "none_found": {
            "title": "Nothing Flagged",
            "message_template": "No shallow notes or vague lessons found — great job.",
            "save_explanation": "Save records these notes as checked, so Show Shallow/Vague Logs won't count them as new.",
        },
    }}}}
}


class _Env:
    """Two games with logged CLAMP notes, a real Chess Log controller and a real charts controller."""

    def __init__(self, notes=(("0", "note one"), ("0", "note two")), ignore_second=False):
        from app.controllers.chess_log_charts_controller import ChessLogChartsController
        from app.controllers.chess_log_controller import ChessLogController
        from app.models.database_model import GameData
        from app.services.chess_log_storage_service import ChessLogStorageService as S

        self.games = [GameData(game_number=i + 1, pgn=MAINLINE_PGN) for i in range(len(notes))]
        gm = MagicMock()
        gm.active_game = None
        gc = MagicMock()
        gc.get_game_model.return_value = gm
        self.db_model = MagicMock()
        pm = MagicMock()
        pm.get_all_database_models.return_value = [self.db_model]
        self.dc = MagicMock()
        self.dc.get_panel_model.return_value = pm
        self.dc.find_database_model_for_game.return_value = self.db_model
        self.dc.get_active_database.return_value = MagicMock(get_all_games=lambda: self.games)
        self.clc = ChessLogController({}, gc, database_controller=self.dc)
        for game, (pk, why) in zip(self.games, notes):
            entry = S.make_entry("CLAMP", "C", why)
            if ignore_second and why == "note two":
                entry = S.make_entry("CLAMP", "C", why, ignore_shallow=True)
            self.clc._multi_cache[id(game)] = {pk: [entry]}
        self.charts = ChessLogChartsController(config=_CONFIG, database_controller=self.dc)
        self.charts.set_chess_log_controller(self.clc)
        self.charts._resolve_games = lambda: list(self.games)
        self.charts._cached_shallow_model_label = "Anthropic claude-test"
        self.charts._cached_shallow_timestamp = "2026-11-07T10:00:00Z"

    def classified(self, indexes=(0, 1)):
        return frozenset((self.games[i], "0", "CLAMP", "") for i in indexes)

    def unchecked(self):
        return self.clc.count_unchecked_answers(self.games)

    def pgn_tags(self):
        """Decoded stored state per game (entry ids are random, so they are dropped)."""
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        def strip(tags):
            return {pk: [{k: v for k, v in e.items() if k != "id"} for e in es] for pk, es in tags.items()}
        return [(strip(S.load_tags(g)), S.load_check_run(g)) for g in self.games]


def _view(env):
    from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
    view = DetailChessLogChartsView(_CONFIG)
    view._controller = env.charts
    return view


def _run_view(env, view, classified, partial=None, answer=True):
    """Feed a no-flags result to the view; returns (ask_message_or_None, info_message_or_None)."""
    view._pending_partial_message = partial
    with patch("app.views.detail_chess_log_charts_view.SaveCancelMessageDialog.ask",
               return_value=answer) as ask, \
         patch("app.views.detail_chess_log_charts_view.MessageDialog.show_information") as info:
        view._on_shallow_ready(frozenset(), frozenset(), classified, None)
    return (ask.call_args[0][2] if ask.called else None,
            info.call_args[0][2] if info.called else None)


@requires_qt
class TestCleanRunSaveAndCancel(unittest.TestCase):
    def test_save_records_checked_answers_and_marks_database_unsaved(self):
        env = _Env()
        self.assertEqual(env.unchecked(), 2)
        self.assertFalse(env.clc.has_any_checked_answer(env.games))
        ask, info = _run_view(env, _view(env), env.classified(), answer=True)
        self.assertIsNotNone(ask)
        self.assertIsNone(info)
        self.assertEqual(env.unchecked(), 0)
        sk, vk = env.clc.get_shallow_vague_keys(env.games)
        self.assertEqual((sk, vk), (frozenset(), frozenset()))
        self.assertTrue(env.clc.has_any_checked_answer(env.games))
        env.dc.mark_database_unsaved.assert_called_with(env.db_model)
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        self.assertEqual(S.load_check_run(env.games[0]),
                         {"model": "Anthropic claude-test", "date": "2026-11-07T10:00:00Z"})

    def test_saved_logs_menu_data_is_nothing_flagged_with_no_unchecked_count(self):
        env = _Env()
        _run_view(env, _view(env), env.classified(), answer=True)
        # What Show Shallow/Vague Logs reads: a saved record, no flags, nothing unchecked.
        self.assertTrue(env.clc.has_any_checked_answer(env.games))
        self.assertEqual(env.clc.get_shallow_vague_keys(env.games), (frozenset(), frozenset()))
        self.assertEqual(env.clc.count_unchecked_answers(env.games), 0)

    def test_cancel_stores_nothing(self):
        env = _Env()
        before = env.pgn_tags()
        ask, _ = _run_view(env, _view(env), env.classified(), answer=False)
        self.assertIsNotNone(ask)
        self.assertEqual(env.pgn_tags(), before)
        env.dc.mark_database_unsaved.assert_not_called()
        self.assertEqual(env.unchecked(), 2)
        self.assertFalse(env.clc.has_any_checked_answer(env.games))

    def test_message_text_has_first_line_and_save_explanation(self):
        env = _Env()
        ask, _ = _run_view(env, _view(env), env.classified(), answer=False)
        self.assertIn("No shallow notes or vague lessons found — great job.", ask)
        self.assertIn("Save records these notes as checked, so Show Shallow/Vague Logs won't count them as new.", ask)

    def test_nothing_is_written_without_an_explicit_save(self):
        env = _Env()
        with patch.object(env.clc, "save_games") as save, \
             patch.object(env.clc, "set_check_run_for_game") as run:
            _run_view(env, _view(env), env.classified(), answer=False)
        save.assert_not_called()
        run.assert_not_called()


@requires_qt
class TestIgnoredAndUnreadableStayUnchecked(unittest.TestCase):
    def test_ignored_answer_not_recorded(self):
        env = _Env(ignore_second=True)
        # The classifier is never sent the Ignored note, so classified_keys lacks it.
        from app.services.chess_log_shallow_service import build_notes
        legacy, _three, _ign = build_notes(env.games, env.clc.get_tags_for_game)
        self.assertEqual([n[4] for n in legacy], ["note one"])
        _run_view(env, _view(env), env.classified(indexes=(0,)), answer=True)
        e1 = env.clc.get_tags_for_game(env.games[0])["0"][0]
        e2 = env.clc.get_tags_for_game(env.games[1])["0"][0]
        self.assertIn("check_hash", e1)
        self.assertNotIn("check_hash", e2)
        # The Ignored answer already counts as checked (honoured Ignore); no new stamp was added.
        self.assertEqual(env.unchecked(), 0)

    def test_unreadable_answer_not_recorded(self):
        env = _Env()
        _run_view(env, _view(env), env.classified(indexes=(0,)), partial="1 of 2 notes couldn't be classified", answer=True)
        e1 = env.clc.get_tags_for_game(env.games[0])["0"][0]
        e2 = env.clc.get_tags_for_game(env.games[1])["0"][0]
        self.assertIn("check_hash", e1)
        self.assertNotIn("check_hash", e2)
        self.assertEqual(env.unchecked(), 1)
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        self.assertIsNone(S.load_check_run(env.games[1]))

    def test_partial_notice_shown_in_the_same_message(self):
        env = _Env()
        ask, _ = _run_view(env, _view(env), env.classified(indexes=(0,)),
                           partial="1 of 2 notes couldn't be classified", answer=False)
        # The notice is HTML-escaped into the rich-text message (' -> &#x27;); compare the text the user sees.
        import html
        self.assertIn("1 of 2 notes couldn't be classified", html.unescape(ask))
        self.assertIn("great job", ask)
        self.assertIn("Save records these notes as checked", ask)

    def test_partial_cancel_stores_nothing(self):
        env = _Env()
        before = env.pgn_tags()
        _run_view(env, _view(env), env.classified(indexes=(0,)), partial="x", answer=False)
        self.assertEqual(env.pgn_tags(), before)
        env.dc.mark_database_unsaved.assert_not_called()


@requires_qt
class TestZeroAnswerRunHasNoSave(unittest.TestCase):
    def test_zero_checked_answers_shows_plain_message(self):
        env = _Env()
        ask, info = _run_view(env, _view(env), frozenset())
        self.assertIsNone(ask)
        self.assertIsNotNone(info)
        self.assertNotIn("Save records", info)
        env.dc.mark_database_unsaved.assert_not_called()

    def test_save_clean_check_run_with_nothing_is_a_no_op(self):
        env = _Env()
        self.assertFalse(env.charts.save_clean_check_run(frozenset()))
        env.dc.mark_database_unsaved.assert_not_called()


@requires_qt
class TestSaveCancelButtons(unittest.TestCase):
    def test_buttons_are_exactly_save_and_cancel(self):
        from PyQt6.QtWidgets import QDialog, QPushButton
        from app.views.dialogs.chess_log_save_message_dialog import SaveCancelMessageDialog
        dlg = SaveCancelMessageDialog({}, "Nothing Flagged", "msg")
        self.assertEqual(sorted(b.text() for b in dlg.findChildren(QPushButton)), ["Cancel", "Save"])
        dlg.save_button.click()
        self.assertEqual(dlg.result(), QDialog.DialogCode.Accepted)
        dlg2 = SaveCancelMessageDialog({}, "Nothing Flagged", "msg")
        dlg2.cancel_button.click()
        self.assertEqual(dlg2.result(), QDialog.DialogCode.Rejected)
        dlg3 = SaveCancelMessageDialog({}, "Nothing Flagged", "msg")
        dlg3.close()  # closing the window is Cancel
        self.assertNotEqual(dlg3.result(), QDialog.DialogCode.Accepted)


@requires_qt
class TestThreadEnding(unittest.TestCase):
    """Option B: an error only when no note could be read; N is the total sent."""

    def _run(self, result, n_notes):
        from app.controllers.chess_log_charts_controller import ChessLogShallowThread
        from app.models.database_model import GameData
        games = [GameData(game_number=i + 1) for i in range(n_notes)]
        notes = [(i, games[i], f"p/{i}", "CLAMP", f"note {i}") for i in range(n_notes)]
        thread = ChessLogShallowThread(
            games=games, provider="anthropic", model="m", api_key="k", base_url_override=None,
            config=_CONFIG, timeout_seconds=5, legacy_notes=notes, three_notes=[],
        )
        failed, partial, ready = [], [], []
        thread.shallow_failed.connect(failed.append)
        thread.shallow_partial.connect(partial.append)
        thread.shallow_ready.connect(lambda sk, vk, ck, u, ml: ready.append((sk, vk, ck)))
        with patch("app.services.chess_log_shallow_service.classify_notes", return_value=result):
            thread.run()
        return failed, partial, ready, games

    @staticmethod
    def _result(unparsed):
        from app.services.chess_log_shallow_service import ShallowResult
        from app.services.ai_service import TokenUsage
        return ShallowResult(
            success=True, shallow_keys=frozenset(), error=None,
            usage=TokenUsage(input_tokens=1, output_tokens=1, reasoning_tokens=None, reported=True),
            model="m", unparsed_indices=tuple(unparsed),
        )

    def test_nothing_readable_is_an_error_with_n_equal_to_total_sent(self):
        failed, partial, ready, _ = self._run(self._result((0, 1, 2, 3, 4)), 5)
        self.assertEqual(len(failed), 1)
        self.assertIn("None of the 5 notes", failed[0])
        self.assertEqual((partial, ready), ([], []))

    def test_some_readable_none_flagged_emits_partial_then_ready_with_classified_keys(self):
        failed, partial, ready, games = self._run(self._result((1, 3)), 5)
        self.assertEqual(failed, [])
        self.assertEqual(len(partial), 1)
        self.assertEqual(len(ready), 1)
        sk, vk, ck = ready[0]
        self.assertEqual((sk, vk), (frozenset(), frozenset()))
        self.assertEqual(ck, frozenset((games[i], f"p/{i}", "CLAMP", "") for i in (0, 2, 4)))

    def test_all_readable_none_flagged_is_ready_only(self):
        failed, partial, ready, games = self._run(self._result(()), 3)
        self.assertEqual((failed, partial), ([], []))
        self.assertEqual(len(ready[0][2]), 3)


@requires_qt
class TestDialogSaveAndCleanSaveShareOneWriter(unittest.TestCase):
    def test_dialog_save_calls_commit_check_record(self):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        env = _Env()
        sk = frozenset({(env.games[0], "0", "CLAMP", "")})
        dlg = ShowShallowTagsDialog(
            config={}, games=env.games, controller=env.clc, shallow_keys=sk,
            classified_keys=env.classified(), check_run_info={"model": "m", "date": "d"},
        )
        with patch("app.views.dialogs.show_shallow_tags_dialog.commit_check_record") as commit:
            dlg._on_save()
        commit.assert_called_once()
        args = commit.call_args[0]
        self.assertIs(args[0], env.clc)
        self.assertEqual(len(args[2]), 1)               # one shown row decision
        self.assertEqual(args[5], env.classified())     # classified_keys

    def test_clean_save_calls_commit_check_record_with_no_rows(self):
        env = _Env()
        with patch("app.services.chess_log_check_record_service.commit_check_record") as commit:
            self.assertTrue(env.charts.save_clean_check_run(env.classified()))
        commit.assert_called_once()
        args = commit.call_args[0]
        self.assertIs(args[0], env.clc)
        self.assertEqual(list(args[2]), [])
        self.assertEqual(args[5], env.classified())
        self.assertEqual(args[6], {"model": "Anthropic claude-test", "date": "2026-11-07T10:00:00Z"})

    def test_clean_save_equals_dialog_save_with_no_flagged_rows(self):
        """Same data, same writer: the Nothing Flagged Save and a dialog Save of a no-flag run agree."""
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        a, b = _Env(), _Env()
        a.charts.save_clean_check_run(a.classified())
        dlg = ShowShallowTagsDialog(
            config={}, games=b.games, controller=b.clc, shallow_keys=frozenset(),
            classified_keys=b.classified(), check_run_info={"model": "Anthropic claude-test", "date": "2026-11-07T10:00:00Z"},
        )
        dlg._on_save()
        self.assertEqual(a.pgn_tags(), b.pgn_tags())


@requires_qt
class TestDialogSaveUnchangedByExtraction(unittest.TestCase):
    """Fixed fixture → exact entries the dialog's Save writes (pinned from the pre-extraction code)."""

    def test_mixed_run_writes_flags_hashes_and_clears_stale(self):
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        env = _Env(notes=(("0", "shallow note"), ("0", "good note"), ("0", "unread note")))
        # Stale flag on the 'good' note, which this run now judges clean.
        env.clc._multi_cache[id(env.games[1])] = {"0": [S.make_entry("CLAMP", "C", "good note", is_shallow=True)]}
        sk = frozenset({(env.games[0], "0", "CLAMP", "")})
        ck = env.classified(indexes=(0, 1))     # game 3's note is unread
        dlg = ShowShallowTagsDialog(
            config={}, games=env.games, controller=env.clc, shallow_keys=sk,
            classified_keys=ck, check_run_info={"model": "m", "date": "d"},
        )
        dlg._on_save()
        e0 = env.clc.get_tags_for_game(env.games[0])["0"][0]
        e1 = env.clc.get_tags_for_game(env.games[1])["0"][0]
        e2 = env.clc.get_tags_for_game(env.games[2])["0"][0]
        self.assertTrue(e0["is_shallow"])
        self.assertEqual(e0["check_hash"], S.compute_check_hash("shallow note"))
        self.assertFalse(e1.get("is_shallow"))
        self.assertEqual(e1["check_hash"], S.compute_check_hash("good note"))
        self.assertNotIn("check_hash", e2)
        self.assertIsNotNone(S.load_check_run(env.games[0]))
        self.assertIsNotNone(S.load_check_run(env.games[1]))
        self.assertIsNone(S.load_check_run(env.games[2]))


class TestOwnerGuards98(unittest.TestCase):
    """Only commit_check_record writes a run's check record; only two callers reach it."""

    @staticmethod
    def _trees():
        for path in sorted((_REPO / "app").rglob("*.py")):
            yield path.relative_to(_REPO).as_posix(), ast.parse(path.read_text(encoding="utf-8"))

    def _uses(self, name):
        hits = set()
        for rel, tree in self._trees():
            for node in ast.walk(tree):
                if ((isinstance(node, ast.Attribute) and node.attr == name)
                        or (isinstance(node, ast.Name) and node.id == name)):
                    hits.add(rel)
        return hits

    def test_commit_check_record_is_used_only_by_its_two_callers(self):
        self.assertEqual(self._uses("commit_check_record"), {
            "app/views/dialogs/show_shallow_tags_dialog.py",
            "app/controllers/chess_log_charts_controller.py",
        })

    def test_check_run_is_queued_only_by_the_service(self):
        # Calls only (the method definition is not an attribute use).
        self.assertEqual(self._uses("set_check_run_for_game"), {
            "app/services/chess_log_check_record_service.py",
        })

    def test_check_hash_is_stamped_only_by_the_service_and_edit_paths(self):
        stampers = set()
        for rel, tree in self._trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                                and t.slice.value == "check_hash"):
                            stampers.add(rel)
        self.assertEqual(stampers, {
            "app/services/chess_log_check_record_service.py",   # Check Logs runs
            "app/services/chess_log_storage_service.py",        # make_entry
            "app/views/dialogs/show_tags_dialog.py",            # Show Logged Moments edits
        })

    def test_dialog_save_does_not_write_the_store_itself(self):
        src = (_REPO / "app/views/dialogs/show_shallow_tags_dialog.py").read_text(encoding="utf-8")
        for name in ("replace_entries_at_path_for_game", "set_check_run_for_game", "save_games"):
            self.assertNotIn(name, src)


if __name__ == "__main__":
    unittest.main()
