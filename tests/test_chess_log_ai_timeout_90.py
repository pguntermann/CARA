"""#90: Chess Log has its own AI timeout (chess_log.ai_timeout_seconds), separate from AI Summary's."""

import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.chess_log_ai_settings_helper import current_service, isolate_module

try:
    from PyQt6.QtWidgets import QApplication
    _QApp = QApplication.instance() or QApplication([])
    from app.controllers.chess_log_charts_controller import ChessLogChartsController
    _QT = True
except Exception:  # pragma: no cover
    _QT = False

from app.config.config_loader import ConfigLoader
from app.services.user_settings_service import UserSettingsService

_REPO = Path(__file__).resolve().parent.parent
_PROVIDER = ("anthropic", "claude-opus-4-5", "fake-key", None)


def setUpModule():
    isolate_module(globals())


def _config():
    return ConfigLoader().load()


def _controller(config=None):
    ctrl = ChessLogChartsController(config=_config() if config is None else config, database_controller=MagicMock())
    ctrl._source_selection = 1
    ctrl._current_player = "Alice"
    ctrl._resolve_games = MagicMock(return_value=[MagicMock()])
    ctrl._start_dropdown_worker = MagicMock()
    ctrl._cancel_dropdown_worker = MagicMock()
    return ctrl


class TestNoSharedKeyInChessLogCode(unittest.TestCase):
    """Guard: Chess Log code never touches ai_summary.request_timeout_seconds."""

    def test_chess_log_app_files_do_not_reference_shared_key(self):
        offenders = []
        for path in (_REPO / "app").rglob("*.py"):
            if "chess_log" not in path.name and "show_tags" not in path.name and "show_shallow" not in path.name \
                    and "moment_dialog" not in path.name:
                continue
            if "request_timeout_seconds" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(_REPO)))
        self.assertEqual(offenders, [])

    def test_charts_view_does_not_reference_shared_key(self):
        text = (_REPO / "app/views/detail_chess_log_charts_view.py").read_text(encoding="utf-8")
        self.assertNotIn("request_timeout_seconds", text)
        self.assertNotIn("update_ai_summary_settings", text)

    def test_controller_has_no_literal_default_timeout(self):
        text = (_REPO / "app/controllers/chess_log_charts_controller.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b120\b", text))


@unittest.skipUnless(_QT, "Qt not available")
class TestChessLogTimeoutSetting(unittest.TestCase):

    def test_default_from_config_is_120_when_key_absent(self):
        svc = current_service()
        self.assertNotIn("ai_timeout_seconds", svc.get_chess_log())
        self.assertEqual(_controller().get_narrative_timeout_seconds(), 120)

    def test_default_not_copied_from_ai_summary(self):
        current_service().update_ai_summary_settings({"request_timeout_seconds": 45})
        self.assertEqual(_controller().get_narrative_timeout_seconds(), 120)

    def test_default_comes_from_config_value(self):
        cfg = _config()
        cfg["ui"]["panels"]["detail"]["chess_log_charts"]["ai"]["default_timeout_seconds"] = 77
        self.assertEqual(_controller(cfg).get_narrative_timeout_seconds(), 77)

    def test_default_falls_back_to_loaded_config_for_empty_config(self):
        self.assertEqual(_controller({}).get_narrative_timeout_seconds(), 120)

    def test_persists_through_settings_service_fresh_read(self):
        svc = current_service()
        _controller().set_narrative_timeout_seconds(150)
        self.assertEqual(svc.get_chess_log()["ai_timeout_seconds"], 150)
        self.assertEqual(_controller().get_narrative_timeout_seconds(), 150)
        self.assertTrue(svc.save())
        fresh = UserSettingsService(svc.settings_path)
        fresh.load()
        self.assertEqual(fresh.get_chess_log()["ai_timeout_seconds"], 150)

    def test_chess_log_change_leaves_ai_summary_unchanged(self):
        svc = current_service()
        svc.update_ai_summary_settings({"request_timeout_seconds": 45})
        _controller().set_narrative_timeout_seconds(150)
        self.assertEqual(svc.get_settings()["ai_summary"]["request_timeout_seconds"], 45)

    def test_ai_summary_change_leaves_chess_log_unchanged(self):
        svc = current_service()
        ctrl = _controller()
        ctrl.set_narrative_timeout_seconds(150)
        svc.update_ai_summary_settings({"request_timeout_seconds": 45})
        self.assertEqual(ctrl.get_narrative_timeout_seconds(), 150)

    def test_setting_preserves_other_chess_log_keys(self):
        svc = current_service()
        svc.update_chess_log_settings({"active_preset": "CCT"})
        _controller().set_narrative_timeout_seconds(200)
        self.assertEqual(svc.get_chess_log()["active_preset"], "CCT")

    def test_narrative_request_receives_chess_log_timeout(self):
        current_service().update_ai_summary_settings({"request_timeout_seconds": 45})
        ctrl = _controller()
        ctrl.set_narrative_timeout_seconds(150)
        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider", return_value=_PROVIDER), \
             patch("app.controllers.chess_log_charts_controller.ChessLogNarrativeThread") as thread_cls:
            ctrl.request_narrative()
        self.assertEqual(thread_cls.call_args.kwargs["timeout_seconds"], 150)

    def test_check_logs_request_receives_chess_log_timeout(self):
        current_service().update_ai_summary_settings({"request_timeout_seconds": 45})
        ctrl = _controller()
        ctrl.set_narrative_timeout_seconds(150)
        with patch("app.controllers.chess_log_charts_controller.resolve_default_provider", return_value=_PROVIDER), \
             patch("app.services.chess_log_shallow_service.build_notes",
                   return_value=([("n", "why")], [], [])), \
             patch("app.controllers.chess_log_charts_controller.ChessLogShallowThread") as thread_cls:
            ctrl.request_flag_shallow_notes()
        self.assertEqual(thread_cls.call_args.kwargs["timeout_seconds"], 150)


if __name__ == "__main__":
    unittest.main()
