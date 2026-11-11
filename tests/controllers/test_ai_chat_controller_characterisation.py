"""Characterisation tests for AIRequestThread — baseline before AIResult refactor.

These tests capture the EXACT call signature that AIRequestThread.run() sends
to AIService.send_message and the exact (bool, str) semantics of response_received.

After commit 3 changes AIService.send_message to return AIResult instead of
Tuple[bool, str], AIRequestThread must unpack AIResult back to (bool, str) before
emitting response_received.emit(success, response).  These tests are the safety net:
they fail loudly if the unpack is missing or wrong.

All assertions here describe PRE-REFACTOR behavior, intentionally.  When the
refactor is correct they must still pass — if they don't, the regression is in
AIRequestThread, not in these tests.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# AIRequestThread is defined in ai_chat_controller.py and uses QThread.
# A QApplication must exist before importing Qt classes.
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

from app.controllers.ai_chat_controller import AIRequestThread
from app.services.ai_service import AIResult, TokenUsage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_thread(
    provider: str = "openai",
    model: str = "gpt-4o",
    api_key: str = "sk-test",
    messages: list | None = None,
    system_prompt: str | None = "You are a chess coach.",
    token_limit: int | None = 2000,
    config: dict | None = None,
    base_url_override: str | None = None,
    timeout_seconds: int = 60,
) -> AIRequestThread:
    return AIRequestThread(
        provider=provider,
        model=model,
        api_key=api_key,
        messages=messages or [{"role": "user", "content": "What should I do?"}],
        system_prompt=system_prompt,
        token_limit=token_limit,
        config=config or {},
        base_url_override=base_url_override,
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Call-signature characterisation
# ---------------------------------------------------------------------------

class TestAIRequestThreadCallSignature(unittest.TestCase):
    """Verify that run() passes the right keyword arguments to send_message.

    After the AIResult refactor, AIRequestThread unpacks AIResult into
    (bool, str).  The call SIGNATURE must remain identical — only the
    return type changes.  These tests fail if any argument is dropped,
    renamed, or reordered.
    """

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_provider_passed_as_positional(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="Great move!", error=None, usage=None, model="gpt-4o")
        thread = _make_thread(provider="anthropic")
        thread.run()
        args, kwargs = mock_svc.send_message.call_args
        self.assertEqual(args[0], "anthropic")

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_model_passed_as_positional(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        thread = _make_thread(model="claude-3-5-sonnet-20241022")
        thread.run()
        args, kwargs = mock_svc.send_message.call_args
        self.assertEqual(args[1], "claude-3-5-sonnet-20241022")

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_api_key_passed_as_positional(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        thread = _make_thread(api_key="sk-secret")
        thread.run()
        args, kwargs = mock_svc.send_message.call_args
        self.assertEqual(args[2], "sk-secret")

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_messages_passed_as_positional(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        msgs = [{"role": "user", "content": "Is e4 good here?"}]
        thread = _make_thread(messages=msgs)
        thread.run()
        args, kwargs = mock_svc.send_message.call_args
        self.assertEqual(args[3], msgs)

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_system_prompt_passed(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        sysp = "You are a grandmaster."
        thread = _make_thread(system_prompt=sysp)
        thread.run()
        args, kwargs = mock_svc.send_message.call_args
        # system_prompt is the 5th positional arg
        self.assertEqual(args[4], sysp)

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_token_limit_passed_as_keyword(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        thread = _make_thread(token_limit=4096)
        thread.run()
        _args, kwargs = mock_svc.send_message.call_args
        self.assertEqual(kwargs["token_limit"], 4096)

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_base_url_override_passed_as_keyword(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        thread = _make_thread(base_url_override="http://localhost:1234/v1")
        thread.run()
        _args, kwargs = mock_svc.send_message.call_args
        self.assertEqual(kwargs["base_url_override"], "http://localhost:1234/v1")

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_timeout_seconds_passed_as_keyword(self, MockAIService):
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        thread = _make_thread(timeout_seconds=90)
        thread.run()
        _args, kwargs = mock_svc.send_message.call_args
        self.assertEqual(kwargs["timeout_seconds"], 90)

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_no_thinking_parameter(self, MockAIService):
        """AI Chat never passes thinking= — unlike the Chess Log narrative service."""
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        thread = _make_thread()
        thread.run()
        _args, kwargs = mock_svc.send_message.call_args
        self.assertNotIn("thinking", kwargs)

    @patch("app.controllers.ai_chat_controller.AIService")
    def test_config_forwarded_to_ai_service_constructor(self, MockAIService):
        """AIService is constructed with self.config, not the default config."""
        mock_svc = MockAIService.return_value
        mock_svc.send_message.return_value = AIResult(success=True, text="OK", error=None, usage=None, model="gpt-4o")
        cfg = {"version": "9.9"}
        thread = _make_thread(config=cfg)
        thread.run()
        MockAIService.assert_called_once_with(cfg)


# ---------------------------------------------------------------------------
# Response-semantics characterisation
# ---------------------------------------------------------------------------

class TestAIRequestThreadResponseSemantics(unittest.TestCase):
    """Verify that response_received always emits (bool, str) — never AIResult.

    After the refactor, AIRequestThread must unpack AIResult and emit
    response_received.emit(bool(result.success), str(result.text)).
    These tests assert the PRE-REFACTOR (bool, str) contract that the signal
    consumers expect.
    """

    def _run_and_collect_signal(self, mock_return_value):
        received = []

        with patch("app.controllers.ai_chat_controller.AIService") as MockAIService:
            mock_svc = MockAIService.return_value
            mock_svc.send_message.return_value = mock_return_value
            thread = _make_thread()
            thread.response_received.connect(lambda s, r: received.append((s, r)))
            thread.run()

        return received

    def test_success_emits_true_and_response_string(self):
        rv = AIResult(success=True, text="Excellent positional play.", error=None, usage=None, model="gpt-4o")
        received = self._run_and_collect_signal(rv)
        self.assertEqual(len(received), 1)
        success, response = received[0]
        self.assertIs(type(success), bool)
        self.assertIs(type(response), str)
        self.assertTrue(success)
        self.assertEqual(response, "Excellent positional play.")

    def test_failure_emits_false_and_error_string(self):
        rv = AIResult(success=False, text="", error="Connection refused.", usage=None, model="gpt-4o")
        received = self._run_and_collect_signal(rv)
        self.assertEqual(len(received), 1)
        success, response = received[0]
        self.assertIs(type(success), bool)
        self.assertIs(type(response), str)
        self.assertFalse(success)
        self.assertEqual(response, "Connection refused.")

    def test_response_received_emitted_exactly_once(self):
        rv = AIResult(success=True, text="Once only.", error=None, usage=None, model="gpt-4o")
        received = self._run_and_collect_signal(rv)
        self.assertEqual(len(received), 1)

    def test_empty_response_string_forwarded(self):
        rv = AIResult(success=True, text="", error=None, usage=None, model="gpt-4o")
        received = self._run_and_collect_signal(rv)
        self.assertEqual(len(received), 1)
        _success, response = received[0]
        self.assertEqual(response, "")


class TestAIChatControllerGetAvailableModels(unittest.TestCase):
    """Characterisation tests for AIChatController.get_available_models().

    Returns "Provider: model" prefixed strings — same provider-selection logic
    as ChessLogChartsController.get_available_models() but with a label prefix.
    """

    def _make_controller(self, settings: dict) -> "AIChatController":
        from app.controllers.ai_chat_controller import AIChatController
        from unittest.mock import MagicMock, patch

        game_model = MagicMock()
        game_model.active_game = None  # prevents _build_move_label_cache from parsing PGN
        game_model.get_active_move_ply.return_value = -1
        game_ctrl = MagicMock()
        game_ctrl.get_game_model.return_value = game_model

        settings_svc = MagicMock()
        settings_svc.get_settings.return_value = settings

        with patch(
            "app.controllers.ai_chat_controller.UserSettingsService"
        ) as mock_uss:
            mock_uss.get_instance.return_value = settings_svc
            with patch("app.controllers.ai_chat_controller.AIService"):
                ctrl = AIChatController(
                    config={},
                    game_controller=game_ctrl,
                    app_controller=MagicMock(),
                )
        ctrl.user_settings_service = settings_svc
        return ctrl

    # --- settings helpers (parallel to the Chess Log test helpers) ---

    @staticmethod
    def _s_openai(api_key="sk-abc", models=None):
        models = models if models is not None else ["gpt-4o", "gpt-4-turbo"]
        return {"ai_models": {"openai": {"api_key": api_key, "models": models}}}

    @staticmethod
    def _s_anthropic(api_key="ant-key", models=None):
        models = models if models is not None else ["claude-opus-4-7"]
        return {
            "ai_models": {"anthropic": {"api_key": api_key, "models": models}},
            "ai_summary": {
                "use_openai_models": False,
                "use_anthropic_models": True,
                "use_custom_models": False,
            },
        }

    @staticmethod
    def _s_custom(enabled=True, base_url="http://localhost:11434", models=None):
        models = models if models is not None else ["llama3", "mistral"]
        return {
            "ai_models": {
                "custom": {
                    "enabled": enabled,
                    "base_url": base_url,
                    "models": models,
                    "api_key": "",
                }
            },
            "ai_summary": {
                "use_openai_models": False,
                "use_anthropic_models": False,
                "use_custom_models": True,
            },
        }

    # --- test cases ---

    def test_openai_active_returns_prefixed_model_strings(self):
        ctrl = self._make_controller(self._s_openai())
        result = ctrl.get_available_models()
        self.assertEqual(result, ["OpenAI: gpt-4o", "OpenAI: gpt-4-turbo"])

    def test_anthropic_active_returns_prefixed_model_strings(self):
        ctrl = self._make_controller(self._s_anthropic())
        result = ctrl.get_available_models()
        self.assertEqual(result, ["Anthropic: claude-opus-4-7"])

    def test_custom_active_returns_prefixed_model_strings(self):
        ctrl = self._make_controller(self._s_custom())
        result = ctrl.get_available_models()
        self.assertEqual(result, ["Custom: llama3", "Custom: mistral"])

    def test_no_toggles_falls_back_to_openai(self):
        s = self._s_openai()
        s["ai_summary"] = {
            "use_openai_models": False,
            "use_anthropic_models": False,
            "use_custom_models": False,
        }
        ctrl = self._make_controller(s)
        result = ctrl.get_available_models()
        self.assertEqual(result, ["OpenAI: gpt-4o", "OpenAI: gpt-4-turbo"])

    def test_multiple_toggles_falls_back_to_openai(self):
        s = self._s_openai()
        s["ai_summary"] = {
            "use_openai_models": True,
            "use_anthropic_models": True,
            "use_custom_models": False,
        }
        ctrl = self._make_controller(s)
        result = ctrl.get_available_models()
        self.assertEqual(result, ["OpenAI: gpt-4o", "OpenAI: gpt-4-turbo"])

    def test_openai_no_api_key_returns_empty(self):
        ctrl = self._make_controller(self._s_openai(api_key=""))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_openai_empty_models_list_returns_empty(self):
        ctrl = self._make_controller(self._s_openai(models=[]))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_custom_disabled_returns_empty(self):
        ctrl = self._make_controller(self._s_custom(enabled=False))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_custom_no_base_url_returns_empty(self):
        ctrl = self._make_controller(self._s_custom(base_url=""))
        result = ctrl.get_available_models()
        self.assertEqual(result, [])

    def test_empty_settings_returns_empty(self):
        ctrl = self._make_controller({})
        result = ctrl.get_available_models()
        self.assertEqual(result, [])
