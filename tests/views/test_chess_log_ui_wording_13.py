"""#13: exact Chess Log UI wording — four Whys, tab name, log wording, menu case, Pawn Promotion.

Each test pins one user-visible string so the manual's quotes stay in step with the app.
Menu labels and the dialog titles that echo them use sentence case (the Notes menu's style);
Chess Log, Moves List, CLAMP, CCT, 3x3, PDF, AI, Narrative Summary and the Shallow/Vague chip
names keep their capitals.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parents[2]


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = subprocess.run([sys.executable, "-c", probe], capture_output=True, timeout=10, cwd=str(_ROOT))
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

MAINLINE_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"]'
    '[Round "?"][White "W"][Black "B"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *\n"
)


def _config() -> dict:
    return json.loads((_ROOT / "app" / "config" / "config.json").read_text(encoding="utf-8"))


def _labels(widget) -> list:
    return [lbl.text() for lbl in widget.findChildren(QLabel)]


@requires_qt
class TestSettingsDialogWording(unittest.TestCase):
    def _dialog(self):
        from app.views.dialogs.chess_log_settings_dialog import ChessLogSettingsDialog
        uss = MagicMock()
        uss.get_chess_log.return_value = {"active_preset": "CLAMP"}
        return ChessLogSettingsDialog({}, uss)

    def test_3x3_description_says_four_whys(self):
        self.assertIn("Four guided Whys per game moment", _labels(self._dialog()))

    def test_clamp_description_says_pawn_promotion(self):
        self.assertIn("Checks · Loose Pieces · Alignment · Mobility · Pawn Promotion", _labels(self._dialog()))

    def test_window_title_sentence_case(self):
        self.assertEqual(self._dialog().windowTitle(), "Chess Log settings")

    def test_config_title_sentence_case(self):
        self.assertEqual(_config()["ui"]["dialogs"]["chess_log_settings"]["title"], "Chess Log settings")


@requires_qt
class TestChessLogMenuLabels(unittest.TestCase):
    def test_menu_bar_labels(self):
        from app.views.menus.chess_log_menu import setup_chess_log_menu
        mw = QMainWindow()
        for name in ("_show_chess_log_settings", "_clear_chess_log_for_current_game",
                     "_save_chess_log_for_current_game", "_save_chess_logs_for_all_games",
                     "_show_chess_logs_for_all_games", "_show_saved_shallow_logs"):
            setattr(mw, name, lambda *a, **k: None)
        mw._on_highlight_chess_log_moves_toggled = lambda checked=False: None
        mw._apply_menu_styling = lambda menu: None
        mw.config = {}
        setup_chess_log_menu(mw, mw.menuBar())
        self.assertEqual(mw.chess_log_settings_action.text(), "Chess Log settings…")
        self.assertEqual(mw.clear_chess_log_action.text(), "Clear Chess Log for current game")
        self.assertEqual(mw.save_chess_log_action.text(), "Save Chess Log to current game")
        self.assertEqual(mw.save_all_chess_logs_action.text(), "Save Chess Logs for all games")
        self.assertEqual(mw.show_all_chess_logs_action.text(), "Show logged moments for all games")
        self.assertEqual(mw.show_saved_shallow_logs_action.text(), "Show Shallow/Vague logs")
        self.assertEqual(mw.highlight_chess_log_moves_action.text(), "Highlight logged moments in Moves List")

    def test_tab_context_menu_labels(self):
        from PyQt6.QtWidgets import QWidget
        from app.views.menus.chess_log_charts_context_menu import build_chess_log_charts_context_menu
        view = QWidget()
        view._config = {}
        for name in ("_copy_section_to_clipboard", "_copy_log_to_clipboard",
                     "_export_pdf_report", "_export_narrative_pdf"):
            setattr(view, name, lambda *a, **k: None)
        menu = build_chess_log_charts_context_menu(view, section_name="chart_CLAMP")
        texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        self.assertEqual(texts, ["Copy section to clipboard", "Copy log to clipboard",
                                 "Export PDF report", "Export Narrative Summary"])

    def test_moves_list_context_menu_source(self):
        """The Moves List context menu builds its Chess Log entries from these literals."""
        src = (_ROOT / "app" / "views" / "detail_moveslist_view.py").read_text(encoding="utf-8")
        self.assertIn('menu.addAction("Log this moment…")', src)
        self.assertIn('menu.addAction("Show logged moments")', src)
        self.assertNotIn('"Show Logged Moments"', src)


@requires_qt
class TestLogWording(unittest.TestCase):
    def test_also_logged_line(self):
        from app.views.dialogs.moment_dialog import MomentDialog
        dlg = MomentDialog(config={}, active_preset="CLAMP", move_number=2, san="e5", is_white=False,
                           existing_entries=[{"preset": "3x3", "cat": "Why1", "why": "Reason"}])
        lines = [t for t in _labels(dlg) if t.startswith("Also ")]
        self.assertEqual(lines, ["Also logged: Why1 (3x3)"])

    def test_extra_moment_confirmation_body(self):
        from app.controllers.chess_log_controller import ChessLogController
        with patch("app.views.dialogs.confirmation_dialog.ConfirmationDialog.show_confirmation",
                   return_value=True) as conf:
            ChessLogController._confirm_extra_moment(types.SimpleNamespace(config={}))
        _cfg, title, message, _parent = conf.call_args[0]
        self.assertEqual(title, "Chess Log — More than three moments?")
        self.assertTrue(message.startswith("You already have three logged moments in this game. "), message)

    def _show_tags(self, paths_data):
        from app.models.database_model import GameData
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = paths_data
        ctrl.game_has_any_tags.return_value = bool(paths_data)
        return ShowTagsDialog({}, [GameData(game_number=1, pgn=MAINLINE_PGN)], ctrl)

    def test_no_logged_moments_found(self):
        self.assertIn("No logged moments found.", _labels(self._show_tags({})))

    def test_logged_moments_single_game_title(self):
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        dlg = self._show_tags({"0": [S.make_entry("CLAMP", "M", "x")]})
        self.assertEqual(dlg.windowTitle(), "Logged moments")

    def test_logged_moments_all_games_title(self):
        from app.models.database_model import GameData
        from app.views.dialogs.show_tags_dialog import ShowTagsDialog
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = {}
        games = [GameData(game_number=1, pgn=MAINLINE_PGN), GameData(game_number=2, pgn=MAINLINE_PGN)]
        self.assertEqual(ShowTagsDialog({}, games, ctrl).windowTitle(), "Show logged moments for all games")

    def test_orphan_notice_logged_moments(self):
        from app.services.chess_log_storage_service import ChessLogStorageService as S
        dlg = self._show_tags({"0": [S.make_entry("CLAMP", "M", "ok")],
                               "99.0": [S.make_entry("CCT", "Checks", "orphan")],
                               "98.0": [S.make_entry("CCT", "Checks", "orphan 2")]})
        notices = [t for t in _labels(dlg) if "could not be located" in t]
        self.assertEqual(notices, ["Note: 2 logged moments could not be located "
                                   "— the game's moves may have been edited after logging."])

    def test_orphan_notice_source_in_check_logs_dialog(self):
        src = (_ROOT / "app" / "views" / "dialogs" / "show_shallow_tags_dialog.py").read_text(encoding="utf-8")
        self.assertIn('f"Note: {orphan_count} logged moment{s} could not be located "', src)
        self.assertIn("may have been edited after logging.", src)
        self.assertNotIn("tagged moment", src)


@requires_qt
class TestShallowVagueLogsTitles(unittest.TestCase):
    def _fake(self, games, ctrl):
        db = MagicMock()
        db.get_all_games.return_value = games
        fake = MagicMock()
        fake.config = _config()
        fake.controller.get_database_controller.return_value.get_active_database.return_value = db
        fake.controller.get_chess_log_controller.return_value = ctrl
        return fake

    def test_no_logged_games_message_title(self):
        from app.main_window import MainWindow
        from app.models.database_model import GameData
        fake = self._fake([GameData(game_number=1, pgn=MAINLINE_PGN)], MagicMock())
        with patch("app.views.dialogs.message_dialog.MessageDialog.show_information") as info:
            MainWindow._show_saved_shallow_logs(fake)
        self.assertEqual(info.call_args[0][1], "Shallow/Vague logs")

    def test_no_saved_results_message_title(self):
        from app.main_window import MainWindow
        from app.models.database_model import GameData
        game = GameData(game_number=1, pgn=MAINLINE_PGN)
        game.has_chess_log_tags = True
        ctrl = MagicMock()
        ctrl.has_any_checked_answer.return_value = False
        with patch("app.views.dialogs.message_dialog.MessageDialog.show_information") as info:
            MainWindow._show_saved_shallow_logs(self._fake([game], ctrl))
        self.assertEqual(info.call_args[0][1], "Shallow/Vague logs")

    def test_dialog_window_title(self):
        from app.main_window import MainWindow
        from app.models.database_model import GameData
        game = GameData(game_number=1, pgn=MAINLINE_PGN)
        game.has_chess_log_tags = True
        ctrl = MagicMock()
        ctrl.has_any_checked_answer.return_value = True
        ctrl.get_shallow_vague_keys.return_value = (frozenset({("k",)}), frozenset())
        with patch("app.views.dialogs.show_shallow_tags_dialog.ShowShallowTagsDialog") as dlg:
            MainWindow._show_saved_shallow_logs(self._fake([game], ctrl))
        self.assertEqual(dlg.call_args.kwargs["window_title"], "Shallow/Vague logs")


class TestConfigWording(unittest.TestCase):
    def test_save_explanation_names_menu_item(self):
        msg = _config()["ui"]["dialogs"]["chess_log_messages"]["shallow_notes"]["none_found"]["save_explanation"]
        self.assertEqual(msg, "Save records these notes as checked, so Show Shallow/Vague logs won't count them as new.")

    def test_help_text_names_menu_item(self):
        help_text = _config()["ui"]["dialogs"]["shallow"]["help_text"]
        self.assertIn("untick Ignore in Show logged moments and click Save.", help_text)
        self.assertNotIn("Show Logged Moments", help_text)


@requires_qt
class TestChartCopyLine(unittest.TestCase):
    def test_copy_section_chart_line(self):
        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        view = DetailChessLogChartsView(config={})
        with patch.object(QApplication.clipboard(), "setText") as set_text:
            view._copy_section_to_clipboard("chart_CCT")
        set_text.assert_called_once_with("Category chart — CCT: see Chess Log tab in CARA.")

    def test_html_chart_line(self):
        from app.services.chess_log_html_service import ChessLogHTMLService
        html = ChessLogHTMLService({}).charts_log_html("P", "Active Database", ["CLAMP"], "", [])
        self.assertIn("Category chart — CLAMP: see Chess Log tab in CARA.", html.replace("&#8212;", "—"))
        self.assertNotIn("Charts tab", html)

    def test_copy_log_source_line(self):
        src = (_ROOT / "app" / "views" / "detail_chess_log_charts_view.py").read_text(encoding="utf-8")
        self.assertEqual(src.count('see Chess Log tab in CARA."'), 2)
        self.assertNotIn("Chess Log Charts tab in CARA", src)

    def test_export_pdf_file_dialog_title(self):
        src = (_ROOT / "app" / "views" / "detail_chess_log_charts_view.py").read_text(encoding="utf-8")
        self.assertIn('self, "Export PDF report", suggested', src)
        self.assertIn('self, "Export Narrative Summary", suggested', src)


if __name__ == "__main__":
    unittest.main()
