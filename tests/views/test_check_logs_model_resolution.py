"""Test that the Check Logs click logs the combo's displayed text and the controller's
_narrative_model_override separately, so a mismatch is visible in the log.

Requires Qt (offscreen).  The test asserts only what the code does today;
it does not change or verify the selection behaviour itself.
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
    _app = QApplication.instance() or QApplication(sys.argv)

    from app.views.detail_chess_log_charts_view import DetailChessLogChartsView


@unittest.skipUnless(_QT_AVAILABLE, "Qt platform unavailable")
class TestCheckLogsModelResolutionLog(unittest.TestCase):
    """Click-time model resolution: combo shows A, override is B → both in log line."""

    @patch("app.views.detail_chess_log_charts_view.LoggingService")
    def test_combo_and_override_both_appear_when_they_differ(self, mock_logging_cls):
        mock_logger = MagicMock()
        mock_logging_cls.get_instance.return_value = mock_logger

        # Stub controller: override=B while combo will display A
        mock_ctrl = MagicMock()
        mock_ctrl.is_ai_configured.return_value = True
        mock_ctrl.get_narrative_model_override.return_value = "claude-opus-5"        # B
        mock_ctrl.get_default_narrative_model.return_value = "claude-sonnet-5-5"
        mock_ctrl.get_available_models.return_value = ["claude-sonnet-5-5", "claude-opus-5"]
        mock_ctrl.get_narrative_timeout_seconds.return_value = 60
        mock_ctrl.get_narrative_token_limit = MagicMock(return_value=12000)
        mock_ctrl.get_last_narrative_result.return_value = ("", [], None)
        mock_ctrl.get_last_shallow_result.return_value = (frozenset(), frozenset(), None)
        mock_ctrl.get_cached_shallow_model_label.return_value = ""
        mock_ctrl.get_source_selection.return_value = 0
        mock_ctrl.get_last_players.return_value = []
        mock_ctrl.has_player_selected.return_value = False

        view = DetailChessLogChartsView(config={})
        view.set_controller(mock_ctrl)

        # Force the combo to display model A without triggering the model-changed signal,
        # so _narrative_model_override stays as B (the mismatch scenario).
        view._model_combo.blockSignals(True)
        view._model_combo.clear()
        view._model_combo.addItem("claude-sonnet-5-5")   # A
        view._model_combo.addItem("claude-opus-5")
        view._model_combo.setCurrentText("claude-sonnet-5-5")  # combo shows A
        view._model_combo.blockSignals(False)

        # Invoke the click handler directly (bypasses button enable state).
        view._on_show_shallow_clicked()

        # The resolution line must carry both model A (combo_text) and model B (override).
        resolution_lines = [
            c.args[0] for c in mock_logger.info.call_args_list
            if "model resolution" in c.args[0]
        ]
        self.assertTrue(resolution_lines, "Expected at least one 'model resolution' INFO log line")
        line = resolution_lines[0]
        self.assertIn("claude-sonnet-5-5", line,
                      "combo_text (model A) must appear in the resolution log line")
        self.assertIn("claude-opus-5", line,
                      "override (model B) must appear in the resolution log line")


if __name__ == "__main__":
    unittest.main()
