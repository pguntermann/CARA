"""Tests for per-call INFO logging in chess_log_shallow_service (#53 / #56).

Asserts:
  - dispatch line carries model, prompt body_bytes, and timeout value
  - completion line carries elapsed time and outcome for an ok result
  - completion line carries elapsed time and "timeout" outcome for a timed-out result
  - no line contains the test API key string
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.chess_log_shallow_service import classify_notes


def _notes(n: int = 3):
    return [(i, 1, f"p{i}", "CLAMP", f"note text {i}") for i in range(n)]


def _config():
    return {"prompts": {"chess_log": {"classifier": "Classify these notes:\n"}}}


def _ok_result(model: str = "claude-sonnet-5") -> MagicMock:
    r = MagicMock()
    r.success = True
    r.text = "\n".join(f"{i}: DEEP" for i in range(3))
    r.error = None
    r.usage = MagicMock(input_tokens=80, output_tokens=12)
    r.model = model
    r.stop_reason = "end_turn"
    r.content_block_count = 1
    r.content_block_types = ("text",)
    return r


def _timeout_result(model: str = "claude-sonnet-5") -> MagicMock:
    r = MagicMock()
    r.success = False
    r.text = ""
    r.error = "Request timed out after 60s (https://api.anthropic.com/v1/messages)"
    r.usage = None
    r.model = model
    r.stop_reason = None
    r.content_block_count = None
    r.content_block_types = None
    return r


class TestDispatchLine(unittest.TestCase):

    @patch("app.services.chess_log_shallow_service.AIService")
    @patch("app.services.chess_log_shallow_service.LoggingService")
    def test_dispatch_carries_model(self, mock_logging_cls, mock_ai_cls):
        mock_logger = MagicMock()
        mock_logging_cls.get_instance.return_value = mock_logger
        mock_ai_cls.return_value.send_message.return_value = _ok_result("claude-sonnet-5")

        classify_notes(
            notes=_notes(),
            provider="anthropic",
            model="claude-sonnet-5",
            api_key="sk-test-key",
            base_url_override=None,
            config=_config(),
            timeout_seconds=60,
        )

        dispatch = mock_logger.info.call_args_list[0].args[0]
        self.assertIn("claude-sonnet-5", dispatch)

    @patch("app.services.chess_log_shallow_service.AIService")
    @patch("app.services.chess_log_shallow_service.LoggingService")
    def test_dispatch_carries_body_bytes(self, mock_logging_cls, mock_ai_cls):
        mock_logger = MagicMock()
        mock_logging_cls.get_instance.return_value = mock_logger
        mock_ai_cls.return_value.send_message.return_value = _ok_result()

        classify_notes(
            notes=_notes(),
            provider="anthropic",
            model="claude-sonnet-5",
            api_key="sk-test-key",
            base_url_override=None,
            config=_config(),
            timeout_seconds=60,
        )

        import re
        dispatch = mock_logger.info.call_args_list[0].args[0]
        self.assertRegex(dispatch, r"body_bytes=\d+")

    @patch("app.services.chess_log_shallow_service.AIService")
    @patch("app.services.chess_log_shallow_service.LoggingService")
    def test_dispatch_carries_timeout(self, mock_logging_cls, mock_ai_cls):
        mock_logger = MagicMock()
        mock_logging_cls.get_instance.return_value = mock_logger
        mock_ai_cls.return_value.send_message.return_value = _ok_result()

        classify_notes(
            notes=_notes(),
            provider="anthropic",
            model="claude-sonnet-5",
            api_key="sk-test-key",
            base_url_override=None,
            config=_config(),
            timeout_seconds=42,
        )

        dispatch = mock_logger.info.call_args_list[0].args[0]
        self.assertIn("42s", dispatch)


class TestCompletionLine(unittest.TestCase):

    @patch("app.services.chess_log_shallow_service.AIService")
    @patch("app.services.chess_log_shallow_service.LoggingService")
    def test_completion_ok_carries_elapsed_and_outcome(self, mock_logging_cls, mock_ai_cls):
        mock_logger = MagicMock()
        mock_logging_cls.get_instance.return_value = mock_logger
        mock_ai_cls.return_value.send_message.return_value = _ok_result()

        classify_notes(
            notes=_notes(),
            provider="anthropic",
            model="claude-sonnet-5",
            api_key="sk-test-key",
            base_url_override=None,
            config=_config(),
            timeout_seconds=60,
        )

        import re
        all_info = [c.args[0] for c in mock_logger.info.call_args_list]
        completion = next((m for m in all_info if "elapsed=" in m), None)
        self.assertIsNotNone(completion, f"No completion line found; got: {all_info}")
        self.assertRegex(completion, r"elapsed=\d+\.\d+s")
        self.assertIn("ok", completion)

    @patch("app.services.chess_log_shallow_service.AIService")
    @patch("app.services.chess_log_shallow_service.LoggingService")
    def test_completion_timeout_carries_elapsed_and_outcome(self, mock_logging_cls, mock_ai_cls):
        mock_logger = MagicMock()
        mock_logging_cls.get_instance.return_value = mock_logger
        mock_ai_cls.return_value.send_message.return_value = _timeout_result()

        classify_notes(
            notes=_notes(),
            provider="anthropic",
            model="claude-sonnet-5",
            api_key="sk-test-key",
            base_url_override=None,
            config=_config(),
            timeout_seconds=60,
        )

        import re
        all_info = [c.args[0] for c in mock_logger.info.call_args_list]
        completion = next((m for m in all_info if "elapsed=" in m), None)
        self.assertIsNotNone(completion, f"No completion line found; got: {all_info}")
        self.assertRegex(completion, r"elapsed=\d+\.\d+s")
        self.assertIn("timeout", completion)


class TestNoKeyInLogs(unittest.TestCase):

    @patch("app.services.chess_log_shallow_service.AIService")
    @patch("app.services.chess_log_shallow_service.LoggingService")
    def test_api_key_never_logged(self, mock_logging_cls, mock_ai_cls):
        mock_logger = MagicMock()
        mock_logging_cls.get_instance.return_value = mock_logger
        mock_ai_cls.return_value.send_message.return_value = _ok_result()

        secret = "sk-ant-api03-VERY-SECRET-KEY-XYZ"
        classify_notes(
            notes=_notes(1),
            provider="anthropic",
            model="claude-sonnet-5",
            api_key=secret,
            base_url_override=None,
            config=_config(),
            timeout_seconds=60,
        )

        all_info = " ".join(c.args[0] for c in mock_logger.info.call_args_list)
        self.assertNotIn(secret, all_info)


if __name__ == "__main__":
    unittest.main()
