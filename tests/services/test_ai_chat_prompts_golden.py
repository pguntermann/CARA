"""Golden-fixture tests for AI Chat system prompt assembly.

Captures the EXACT system_prompt assembled for both the first-message and
subsequent-message paths using fixed, deterministic inputs (pinned FEN, PGN,
ply index).  When commit 7 moves system_preamble and formatting_rules to
config.json, these fixtures are the acceptance gate: the assembled
system_prompt must be byte-identical before and after the move.

Bootstrap: set AI_CHAT_PROMPT_BOOTSTRAP=1 to write fixture files under
tests/fixtures/ai_chat_prompts/.  On every subsequent run the tests assert
byte-identical output.

Assembly-method reference (for commit 7 brace-escaping work):
  - system_preamble  : static string literal at ai_chat_controller.py:530,541;
                       zero literal { or } — safe with any interpolation method.
  - formatting_rules : static string literal at ai_chat_controller.py:515-524;
                       zero literal { or } (uses [%move] bracket syntax, not
                       curly braces); safe with any interpolation method.
  - _generate_initial_prompt() : stays in Python; embeds live FEN, PGN,
                                  ply_index via f-strings; not moved to config.
  - The assembled system_prompt is an f-string:
      f\"\"\"{preamble}\\n\\n{formatting_rules}\\n\\n{initial_prompt}\"\"\"
    No .format() calls on either config value — no brace-escaping needed.

Paths under test:
  - first_message  : len(conversation)==1 at assembly time; uses fresh pgn.
  - subsequent_msg : len(conversation)>1 at assembly time; uses stored_pgn,
                     which may differ from the live pgn.
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

from app.controllers.ai_chat_controller import AIChatController
from app.utils.path_resolver import get_app_resource_path

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "ai_chat_prompts"
BOOTSTRAP = os.getenv("AI_CHAT_PROMPT_BOOTSTRAP") == "1"

import json as _json
_CONFIG_PATH = get_app_resource_path("app/config/config.json")
with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _CONFIG = _json.load(_f)

# ---------------------------------------------------------------------------
# Pinned deterministic inputs
# ---------------------------------------------------------------------------

# Initial position after 1.e4 — Black to move.
_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

# PGN used for the first message (live game state).
_PGN_FIRST = (
    '[Event "Test"]\n'
    '[Site "?"]\n'
    '[Date "2026.09.28"]\n'
    '[Round "?"]\n'
    '[White "Alice"]\n'
    '[Black "Bob"]\n'
    '[Result "*"]\n'
    '\n1. e4 *\n'
)

# PGN used as stored_pgn for subsequent messages (game has progressed further).
_PGN_STORED = (
    '[Event "Test"]\n'
    '[Site "?"]\n'
    '[Date "2026.09.28"]\n'
    '[Round "?"]\n'
    '[White "Alice"]\n'
    '[Black "Bob"]\n'
    '[Result "*"]\n'
    '\n1. e4 e5 2. Nf3 *\n'
)

_PLY_INDEX = 1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_AI_SUMMARY_SETTINGS = {
    "ai_summary": {
        "include_metadata_in_preprompt": True,
        "include_analysis_data_in_preprompt": False,
        "request_timeout_seconds": 60,
    }
}


def _make_controller() -> AIChatController:
    """Build an AIChatController with minimal mocked dependencies.

    game_controller=None avoids Qt signal wiring.  include_analysis_data=False
    (the default) means the game_controller is never accessed during prompt
    assembly.  _played_move_sequence=[] omits the [%move] rider.
    """
    mock_settings = MagicMock()
    mock_settings.get_settings.return_value = _MOCK_AI_SUMMARY_SETTINGS

    with patch("app.controllers.ai_chat_controller.UserSettingsService") as MockUSS:
        MockUSS.get_instance.return_value = mock_settings
        controller = AIChatController(
            config=_CONFIG,
            game_controller=None,
            app_controller=MagicMock(),
        )
    # Rebind the live service reference so calls inside send_message see it too.
    controller.user_settings_service = mock_settings
    controller._played_move_sequence = []
    return controller


def _capture_system_prompt(controller: AIChatController, pgn_live: str) -> str:
    """Call send_message() and capture the system_prompt passed to AIRequestThread.

    AIRequestThread receives system_prompt as its 5th positional argument
    (index 4): AIRequestThread(provider, model, api_key, messages, system_prompt, …).
    """
    with patch("app.controllers.ai_chat_controller.AIRequestThread") as MockThread:
        controller._get_model_config = MagicMock(
            return_value=("openai", "gpt-4o", "sk-test", None)
        )
        controller._get_position_info = MagicMock(
            return_value=(_FEN, pgn_live, _PLY_INDEX)
        )
        controller.send_message("analyze this position")
        args, _kwargs = MockThread.call_args
        return args[4]


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestAIChatPromptsGolden(unittest.TestCase):
    """Golden-fixture tests for AI Chat system_prompt assembly."""

    def _load_fixture(self, name: str) -> str:
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")

    def _save_fixture(self, name: str, content: str) -> None:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        (FIXTURE_DIR / name).write_text(content, encoding="utf-8")

    def test_first_message_system_prompt(self):
        """First-message path: conversation has 1 item, uses fresh pgn."""
        controller = _make_controller()
        # _conversation starts empty; send_message appends once → len==1 → first path.
        assembled = _capture_system_prompt(controller, _PGN_FIRST)

        fixture_name = "first_message_system_prompt.txt"
        if BOOTSTRAP:
            self._save_fixture(fixture_name, assembled)
            self.skipTest("Bootstrapped — re-run without AI_CHAT_PROMPT_BOOTSTRAP=1")

        expected = self._load_fixture(fixture_name)
        self.assertEqual(
            assembled, expected,
            "First-message system_prompt differs from golden fixture.\n"
            "If this is expected (e.g. after commit 7 config move), re-bootstrap.",
        )

    def test_subsequent_message_system_prompt(self):
        """Subsequent-message path: conversation has >1 items, uses stored_pgn."""
        controller = _make_controller()
        # Pre-seed conversation with one prior message and set the stored PGN.
        controller._conversation = [{"role": "user", "content": "previous question"}]
        controller._stored_pgn = _PGN_STORED
        # send_message appends one more → len==2 → subsequent path.
        assembled = _capture_system_prompt(controller, _PGN_FIRST)

        fixture_name = "subsequent_message_system_prompt.txt"
        if BOOTSTRAP:
            self._save_fixture(fixture_name, assembled)
            self.skipTest("Bootstrapped — re-run without AI_CHAT_PROMPT_BOOTSTRAP=1")

        expected = self._load_fixture(fixture_name)
        self.assertEqual(
            assembled, expected,
            "Subsequent-message system_prompt differs from golden fixture.\n"
            "If this is expected (e.g. after commit 7 config move), re-bootstrap.",
        )


class TestAIChatMissingConfig(unittest.TestCase):
    """Missing prompts config emits error_occurred — no request made."""

    def _make_empty_config_controller(self) -> AIChatController:
        mock_settings = MagicMock()
        mock_settings.get_settings.return_value = _MOCK_AI_SUMMARY_SETTINGS
        with patch("app.controllers.ai_chat_controller.UserSettingsService") as MockUSS:
            MockUSS.get_instance.return_value = mock_settings
            controller = AIChatController(
                config={},
                game_controller=None,
                app_controller=MagicMock(),
            )
        controller.user_settings_service = mock_settings
        controller._played_move_sequence = []
        return controller

    def test_empty_config_emits_error_not_request(self):
        controller = self._make_empty_config_controller()
        errors: list = []
        controller.error_occurred.connect(errors.append)
        with patch("app.controllers.ai_chat_controller.AIRequestThread") as MockThread:
            controller._get_model_config = MagicMock(
                return_value=("openai", "gpt-4o", "sk-test", None)
            )
            controller._get_position_info = MagicMock(
                return_value=(_FEN, _PGN_FIRST, _PLY_INDEX)
            )
            controller.send_message("analyze this position")
        self.assertFalse(MockThread.called, "AIRequestThread must not be called when config is empty")
        self.assertEqual(len(errors), 1)
        self.assertIn("config.json", errors[0])


if __name__ == "__main__":
    unittest.main()
