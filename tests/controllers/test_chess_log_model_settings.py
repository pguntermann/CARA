"""Tests for fix #56: changing the Anthropic model in AI Model Settings now clears
the Chess Log Charts dropdown override so the new default takes effect immediately.

Requires Qt (offscreen).  Uses real controller + real view, driven as a user would.
"""

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


_QT_AVAILABLE = _qt_starts_cleanly()

if _QT_AVAILABLE:
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)

    from app.controllers.chess_log_charts_controller import ChessLogChartsController
    from app.views.detail_chess_log_charts_view import DetailChessLogChartsView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(model: str, api_key: str = "sk-test") -> dict:
    """Minimal user_settings with Anthropic active and one model as the default."""
    all_models = ["claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-sonnet-5"]
    return {
        "ai_summary": {
            "use_anthropic_models": True,
            "use_openai_models": False,
            "use_custom_models": False,
        },
        "ai_models": {
            "anthropic": {
                "api_key": api_key,
                "model": model,
                "models": all_models,
            }
        },
    }


def _make_pair(initial_settings: dict):
    """Return a (controller, view) pair wired together."""
    db_ctrl = MagicMock()
    db_ctrl.get_active_database.return_value = MagicMock(get_all_database_models=MagicMock(return_value=[]))
    db_ctrl.get_panel_model.return_value = None

    ctrl = ChessLogChartsController(config={}, database_controller=db_ctrl)
    _set_user_settings(ctrl, initial_settings)

    view = DetailChessLogChartsView(config={})
    view.set_controller(ctrl)
    return ctrl, view


def _will_pass(ctrl: "ChessLogChartsController") -> str:
    """The model that request_flag_shallow_notes would actually send."""
    return ctrl._narrative_model_override or ctrl.get_default_narrative_model() or ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@unittest.skipUnless(_QT_AVAILABLE, "Qt platform unavailable")
class TestModelSettingsOverrideCleared(unittest.TestCase):
    """Changing the default model in AI Settings clears the dropdown override."""

    def test_settings_change_updates_dropdown_and_clears_override(self):
        """Select opus-5 in dropdown, save settings with opus-5-5 → dropdown shows opus-5-5."""
        ctrl, view = _make_pair(_settings("claude-sonnet-5"))

        # User selects claude-opus-5 in the dropdown.
        view._model_combo.setCurrentText("claude-opus-5")
        self.assertEqual(ctrl._narrative_model_override, "claude-opus-5")

        # AI Model Settings saved with a new default: claude-opus-5-5.
        _set_user_settings(ctrl, _settings("claude-opus-5-5"))

        self.assertIsNone(ctrl._narrative_model_override,
                          "Override must be cleared when default model changes")
        self.assertEqual(view._model_combo.currentText(), "claude-opus-5-5",
                         "Dropdown must reflect the new default after settings change")
        self.assertEqual(_will_pass(ctrl), "claude-opus-5-5",
                         "Model passed to classifier must be the new default")

    def test_dropdown_selection_after_settings_change_takes_effect(self):
        """After settings change clears override, a new dropdown pick overrides again."""
        ctrl, view = _make_pair(_settings("claude-sonnet-5"))
        view._model_combo.setCurrentText("claude-opus-5")

        _set_user_settings(ctrl, _settings("claude-opus-5-5"))
        # Dropdown now shows claude-opus-5-5; user picks claude-sonnet-5-5.
        view._model_combo.setCurrentText("claude-sonnet-5-5")

        self.assertEqual(ctrl._narrative_model_override, "claude-sonnet-5-5")
        self.assertEqual(_will_pass(ctrl), "claude-sonnet-5-5")

    def test_settings_save_with_same_default_keeps_override(self):
        """Saving settings with the same default does NOT clear the override."""
        ctrl, view = _make_pair(_settings("claude-sonnet-5"))
        view._model_combo.setCurrentText("claude-opus-5")
        self.assertEqual(ctrl._narrative_model_override, "claude-opus-5")

        # Save settings again with the same default model.
        _set_user_settings(ctrl, _settings("claude-sonnet-5"))

        self.assertEqual(ctrl._narrative_model_override, "claude-opus-5",
                         "Override must be preserved when default model is unchanged")
        self.assertEqual(view._model_combo.currentText(), "claude-opus-5",
                         "Dropdown must still show the user's earlier selection")
        self.assertEqual(_will_pass(ctrl), "claude-opus-5")

    def test_api_key_only_change_keeps_override(self):
        """Saving settings where only the API key changes keeps the dropdown override."""
        ctrl, view = _make_pair(_settings("claude-sonnet-5", api_key="key-A"))
        view._model_combo.setCurrentText("claude-opus-5")
        self.assertEqual(ctrl._narrative_model_override, "claude-opus-5")

        # Same model, different key.
        _set_user_settings(ctrl, _settings("claude-sonnet-5", api_key="key-B"))

        self.assertEqual(ctrl._narrative_model_override, "claude-opus-5",
                         "Override must be preserved when only the API key changes")
        self.assertEqual(_will_pass(ctrl), "claude-opus-5")


@unittest.skipUnless(_QT_AVAILABLE, "Qt platform unavailable")
class TestModelSelectionRegressions(unittest.TestCase):
    """Regression: source/player changes must not lose an explicit model selection."""

    def test_source_change_preserves_dropdown_selection(self):
        """Changing the Source dropdown (which calls _refresh_ai_state) must not
        reset a model that the user explicitly picked."""
        ctrl, view = _make_pair(_settings("claude-sonnet-5"))

        # User picks claude-opus-5.
        view._model_combo.setCurrentText("claude-opus-5")
        self.assertEqual(ctrl._narrative_model_override, "claude-opus-5")

        # Simulate source/player change triggering _refresh_ai_state.
        view._refresh_ai_state()

        self.assertEqual(view._model_combo.currentText(), "claude-opus-5",
                         "Dropdown must keep the user's selection after _refresh_ai_state")
        self.assertEqual(_will_pass(ctrl), "claude-opus-5")


if __name__ == "__main__":
    unittest.main()


from tests.chess_log_ai_settings_helper import (  # noqa: E402
    isolate_module as _isolate_module,
    set_user_settings as _set_user_settings,
)

_isolate_module(globals())
