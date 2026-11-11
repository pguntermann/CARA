"""Tests for AIService.send_message thinking parameter forwarding."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.ai_service import AIService


def _make_anthropic_response(text: str = "ok") -> MagicMock:
    mock = MagicMock()
    mock.status_code = 200
    mock.content = b"x"
    mock.json.return_value = {
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
    }
    return mock


def _captured_payload(mock_post) -> dict:
    """Extract the JSON body sent to requests.post."""
    args, kwargs = mock_post.call_args
    return kwargs.get("json") or (args[1] if len(args) > 1 else {})


class TestSendMessageThinkingForwarding(unittest.TestCase):
    """thinking parameter must reach the Anthropic payload when set."""

    @patch("app.services.ai_service.requests.post")
    def test_thinking_disabled_in_anthropic_payload(self, mock_post):
        mock_post.return_value = _make_anthropic_response()
        AIService().send_message(
            provider="anthropic",
            model="claude-sonnet-5",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hello"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(_captured_payload(mock_post).get("thinking"), {"type": "disabled"})

    @patch("app.services.ai_service.requests.post")
    def test_thinking_none_absent_from_anthropic_payload(self, mock_post):
        mock_post.return_value = _make_anthropic_response()
        AIService().send_message(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hello"}],
        )
        self.assertNotIn("thinking", _captured_payload(mock_post))

    @patch("app.services.ai_service.requests.post")
    def test_thinking_not_forwarded_to_openai(self, mock_post):
        mock_openai = MagicMock()
        mock_openai.status_code = 200
        mock_openai.content = b"x"
        mock_openai.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
        }
        mock_post.return_value = mock_openai
        AIService().send_message(
            provider="openai",
            model="gpt-4",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hello"}],
            thinking={"type": "disabled"},
        )
        self.assertNotIn("thinking", _captured_payload(mock_post))


class TestSendAnthropicMessageThinking(unittest.TestCase):
    """Direct _send_anthropic_message tests for thinking kwarg."""

    @patch("app.services.ai_service.requests.post")
    def test_thinking_in_payload_when_set(self, mock_post):
        mock_post.return_value = _make_anthropic_response()
        AIService()._send_anthropic_message(
            model="claude-opus-5",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hello"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(_captured_payload(mock_post).get("thinking"), {"type": "disabled"})

    @patch("app.services.ai_service.requests.post")
    def test_thinking_absent_when_none(self, mock_post):
        mock_post.return_value = _make_anthropic_response()
        AIService()._send_anthropic_message(
            model="claude-sonnet-4-6",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hello"}],
        )
        self.assertNotIn("thinking", _captured_payload(mock_post))


def _make_anthropic_400(message: str) -> MagicMock:
    mock = MagicMock()
    mock.status_code = 400
    mock.content = b"x"
    mock.json.return_value = {"error": {"message": message}}
    return mock


_THINKING_DISABLED_400_MESSAGE = (
    '"thinking.type.disabled" is not supported for this model. '
    'Use "thinking.type.adaptive" and "output_config.effort" to control thinking behavior.'
)

_BETWEEN_TOOLS_400_MESSAGE = (
    'To turn thinking off on this model, send "thinking": {"type": "between_tools"} '
    'instead of {"type": "disabled"}. The model does not think before responding. '
    'The short updates it writes between tool calls come back as thinking blocks.'
)


class TestAdaptiveThinkingFallback(unittest.TestCase):
    """When a model rejects thinking.type.disabled, retry once with the right replacement."""

    def setUp(self):
        AIService._models_thinking_override.clear()

    def tearDown(self):
        AIService._models_thinking_override.clear()

    @patch("app.services.ai_service.requests.post")
    def test_model_accepting_disabled_no_retry(self, mock_post):
        """Sonnet 5 / Opus 5: 200 on first try, no retry, payload keeps disabled."""
        mock_post.return_value = _make_anthropic_response()
        result = AIService().send_message(
            provider="anthropic",
            model="claude-sonnet-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 1)
        payload = _captured_payload(mock_post)
        self.assertEqual(payload.get("thinking"), {"type": "disabled"})
        self.assertNotIn("output_config", payload)
        self.assertTrue(result.success)

    @patch("app.services.ai_service.requests.post")
    def test_model_rejecting_disabled_retries_with_adaptive(self, mock_post):
        """Opus 5.5: 400 on first try → retry with adaptive + low effort → success."""
        mock_post.side_effect = [
            _make_anthropic_400(_THINKING_DISABLED_400_MESSAGE),
            _make_anthropic_response("great answer"),
        ]
        result = AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 2)
        # First attempt sent disabled
        first_payload = mock_post.call_args_list[0][1].get("json") or mock_post.call_args_list[0][0][1]
        self.assertEqual(first_payload.get("thinking"), {"type": "disabled"})
        self.assertNotIn("output_config", first_payload)
        # Retry sent adaptive + effort:low
        retry_payload = mock_post.call_args_list[1][1].get("json") or mock_post.call_args_list[1][0][1]
        self.assertEqual(retry_payload.get("thinking"), {"type": "adaptive"})
        self.assertEqual(retry_payload.get("output_config"), {"effort": "low"})
        self.assertTrue(result.success)
        self.assertEqual(result.text, "great answer")

    @patch("app.services.ai_service.requests.post")
    def test_session_cache_skips_disabled_attempt(self, mock_post):
        """After a successful retry, subsequent calls go straight to adaptive (one request, no 400)."""
        # Seed the cache as if a prior call already discovered this model.
        AIService._models_thinking_override["claude-opus-5-5-20251101"] = {
            "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}
        }
        mock_post.return_value = _make_anthropic_response("cached path answer")
        result = AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 1)
        payload = _captured_payload(mock_post)
        self.assertEqual(payload.get("thinking"), {"type": "adaptive"})
        self.assertEqual(payload.get("output_config"), {"effort": "low"})
        self.assertTrue(result.success)

    @patch("app.services.ai_service.requests.post")
    def test_cache_is_per_model_id(self, mock_post):
        """Caching opus-5-5 does not affect the unversioned opus-5 model."""
        AIService._models_thinking_override["claude-opus-5-5-20251101"] = {
            "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}
        }
        mock_post.return_value = _make_anthropic_response()
        AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        payload = _captured_payload(mock_post)
        self.assertEqual(payload.get("thinking"), {"type": "disabled"})
        self.assertNotIn("output_config", payload)

    @patch("app.services.ai_service.requests.post")
    def test_other_400_not_retried(self, mock_post):
        """An unrelated 400 error is returned immediately with no retry."""
        mock_post.return_value = _make_anthropic_400("max_tokens exceeded")
        result = AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 1)
        self.assertFalse(result.success)
        self.assertIn("max_tokens exceeded", result.error)

    @patch("app.services.ai_service.requests.post")
    def test_retry_failure_propagates_api_message(self, mock_post):
        """When the retry also fails, the retry's API message is returned intact."""
        mock_post.side_effect = [
            _make_anthropic_400(_THINKING_DISABLED_400_MESSAGE),
            _make_anthropic_400("some other server error on retry"),
        ]
        result = AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 2)
        self.assertFalse(result.success)
        self.assertIn("some other server error on retry", result.error)

    @patch("app.services.ai_service.requests.post")
    def test_thinking_blocks_before_text_block_ignored(self, mock_post):
        """Response with a thinking block before the text block returns only the text."""
        mock = MagicMock()
        mock.status_code = 200
        mock.content = b"x"
        mock.json.return_value = {
            "content": [
                {"type": "thinking", "thinking": "internal reasoning here"},
                {"type": "text", "text": "final answer"},
            ],
            "stop_reason": "end_turn",
        }
        mock_post.return_value = mock
        result = AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
        )
        self.assertTrue(result.success)
        self.assertEqual(result.text, "final answer")

    @patch("app.services.ai_service.requests.post")
    def test_openai_path_no_thinking_or_output_config(self, mock_post):
        """OpenAI path never sends thinking or output_config, even when thinking kwarg is passed."""
        mock_openai = MagicMock()
        mock_openai.status_code = 200
        mock_openai.content = b"x"
        mock_openai.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
        }
        mock_post.return_value = mock_openai
        AIService().send_message(
            provider="openai",
            model="gpt-4",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        payload = _captured_payload(mock_post)
        self.assertNotIn("thinking", payload)
        self.assertNotIn("output_config", payload)

    @patch("app.services.ai_service.requests.post")
    def test_custom_path_no_thinking_or_output_config(self, mock_post):
        """CUSTOM path (OpenAI-compatible) never sends thinking or output_config."""
        mock_custom = MagicMock()
        mock_custom.status_code = 200
        mock_custom.content = b"x"
        mock_custom.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]
        }
        mock_post.return_value = mock_custom
        AIService().send_message(
            provider="custom",
            model="llama3",
            api_key="",
            messages=[{"role": "user", "content": "hi"}],
            base_url_override="http://localhost:11434/v1",
            thinking={"type": "disabled"},
        )
        payload = _captured_payload(mock_post)
        self.assertNotIn("thinking", payload)
        self.assertNotIn("output_config", payload)

    # ------------------------------------------------------------------
    # Sonnet 5.5 — between_tools trigger
    # ------------------------------------------------------------------

    @patch("app.services.ai_service.requests.post")
    def test_sonnet_5_5_retries_with_between_tools(self, mock_post):
        """Sonnet 5.5: 400 with between_tools message → retry with between_tools, no output_config."""
        mock_post.side_effect = [
            _make_anthropic_400(_BETWEEN_TOOLS_400_MESSAGE),
            _make_anthropic_response("sonnet answer"),
        ]
        result = AIService().send_message(
            provider="anthropic",
            model="claude-sonnet-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 2)
        first_payload = mock_post.call_args_list[0][1].get("json") or mock_post.call_args_list[0][0][1]
        self.assertEqual(first_payload.get("thinking"), {"type": "disabled"})
        self.assertNotIn("output_config", first_payload)
        retry_payload = mock_post.call_args_list[1][1].get("json") or mock_post.call_args_list[1][0][1]
        self.assertEqual(retry_payload.get("thinking"), {"type": "between_tools"})
        # API default effort is "high" which is within the allowed range; no output_config needed.
        self.assertNotIn("output_config", retry_payload)
        self.assertTrue(result.success)
        self.assertEqual(result.text, "sonnet answer")

    @patch("app.services.ai_service.requests.post")
    def test_sonnet_5_5_session_memory_skips_disabled(self, mock_post):
        """After caching Sonnet 5.5, subsequent call goes straight to between_tools."""
        AIService._models_thinking_override["claude-sonnet-5-5-20251101"] = {
            "thinking": {"type": "between_tools"}
        }
        mock_post.return_value = _make_anthropic_response("fast path")
        result = AIService().send_message(
            provider="anthropic",
            model="claude-sonnet-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 1)
        payload = _captured_payload(mock_post)
        self.assertEqual(payload.get("thinking"), {"type": "between_tools"})
        self.assertNotIn("output_config", payload)
        self.assertTrue(result.success)

    @patch("app.services.ai_service.requests.post")
    def test_sonnet_5_5_cache_independent_of_sonnet_5(self, mock_post):
        """Caching Sonnet 5.5 (between_tools) does not affect plain Sonnet 5 (stays disabled)."""
        AIService._models_thinking_override["claude-sonnet-5-5-20251101"] = {
            "thinking": {"type": "between_tools"}
        }
        mock_post.return_value = _make_anthropic_response()
        AIService().send_message(
            provider="anthropic",
            model="claude-sonnet-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        payload = _captured_payload(mock_post)
        self.assertEqual(payload.get("thinking"), {"type": "disabled"})
        self.assertNotIn("output_config", payload)

    @patch("app.services.ai_service.requests.post")
    def test_sonnet_5_5_cache_independent_of_opus_5_5(self, mock_post):
        """Caching Sonnet 5.5 (between_tools) does not affect Opus 5.5 (still adaptive+low)."""
        AIService._models_thinking_override["claude-sonnet-5-5-20251101"] = {
            "thinking": {"type": "between_tools"}
        }
        AIService._models_thinking_override["claude-opus-5-5-20251101"] = {
            "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}
        }
        mock_post.return_value = _make_anthropic_response()
        AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        payload = _captured_payload(mock_post)
        self.assertEqual(payload.get("thinking"), {"type": "adaptive"})
        self.assertEqual(payload.get("output_config"), {"effort": "low"})

    @patch("app.services.ai_service.requests.post")
    def test_between_tools_in_message_without_instead_of_not_retried(self, mock_post):
        """A 400 mentioning between_tools but not 'instead of' is not retried."""
        mock_post.return_value = _make_anthropic_400(
            "between_tools is only supported on Claude Sonnet 5.5"
        )
        result = AIService().send_message(
            provider="anthropic",
            model="claude-opus-5-5-20251101",
            api_key="sk-test",
            messages=[{"role": "user", "content": "hi"}],
            thinking={"type": "disabled"},
        )
        self.assertEqual(mock_post.call_count, 1)
        self.assertFalse(result.success)


class TestDisableThinkingFor(unittest.TestCase):
    """disable_thinking_for — per-family probe results (2026-09-27).

    Empirically verified via real API calls:
    - sonnet-5 and opus-5: {"type": "disabled"} accepted silently.
    - fable-5-1: {"type": "disabled"} returns HTTP 400 — must return None.
    - opus-4-7 (control): {"type": "disabled"} accepted; returns None anyway
      (not in _THINKING_DISABLE_MODELS — thinking not on by default).
    No model triggered thinking without an explicit thinking parameter.
    """

    def test_sonnet_5_returns_disabled(self):
        self.assertEqual(AIService.disable_thinking_for("claude-sonnet-5-20251101"), {"type": "disabled"})

    def test_opus_5_returns_disabled(self):
        self.assertEqual(AIService.disable_thinking_for("claude-opus-5-20251101"), {"type": "disabled"})

    def test_fable_5_returns_none(self):
        self.assertIsNone(AIService.disable_thinking_for("claude-fable-5-1-20251101"))

    def test_opus_4_7_returns_none(self):
        self.assertIsNone(AIService.disable_thinking_for("claude-opus-4-7-20250514"))

    def test_sonnet_4_6_returns_none(self):
        self.assertIsNone(AIService.disable_thinking_for("claude-sonnet-4-6-20250514"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(AIService.disable_thinking_for(""))

    def test_none_model_returns_none(self):
        self.assertIsNone(AIService.disable_thinking_for(None))


def _make_openai_400(message: str) -> MagicMock:
    mock = MagicMock()
    mock.status_code = 400
    mock.content = b"x"
    mock.json.return_value = {"error": {"message": message, "type": "invalid_request_error"}}
    return mock


def _make_openai_200(text: str = "ok") -> MagicMock:
    mock = MagicMock()
    mock.status_code = 200
    mock.content = b"x"
    mock.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "model": "gpt-4o",
    }
    return mock


class TestTimeoutLogging(unittest.TestCase):
    """Timeout branches log at ERROR with model, configured timeout, elapsed, and endpoint."""

    def _service(self) -> AIService:
        return AIService()

    def _patch_logging(self):
        mock_logger = MagicMock()
        patcher = patch("app.services.ai_service.LoggingService.get_instance",
                        return_value=mock_logger)
        return patcher, mock_logger

    def test_openai_timeout_logs_error(self):
        """Initial OpenAI request timeout → ERROR log with model, timeout=<n>s, elapsed=, endpoint=openai."""
        svc = self._service()
        patcher, mock_logger = self._patch_logging()
        with patcher:
            with patch("requests.post", side_effect=__import__("requests").exceptions.Timeout):
                result = svc._send_openai_message(
                    model="gpt-4o",
                    api_key="sk-test",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout_seconds=5,
                )
        self.assertFalse(result.success)
        self.assertIn("timed out", result.error)
        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args[0][0]
        self.assertIn("gpt-4o", msg)
        self.assertIn("timeout=5s", msg)
        self.assertIn("elapsed=", msg)
        self.assertIn("endpoint=openai", msg)

    def test_anthropic_timeout_logs_error_and_returns_structured_error(self):
        """Initial Anthropic timeout → ERROR log; AIResult.success=False, error contains 'timed out'."""
        svc = self._service()
        patcher, mock_logger = self._patch_logging()
        with patcher:
            with patch("requests.post", side_effect=__import__("requests").exceptions.Timeout):
                result = svc._send_anthropic_message(
                    model="claude-sonnet-4-6",
                    api_key="ant-test",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout_seconds=10,
                )
        self.assertFalse(result.success)
        self.assertIn("timed out", result.error)
        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args[0][0]
        self.assertIn("claude-sonnet-4-6", msg)
        self.assertIn("timeout=10s", msg)
        self.assertIn("elapsed=", msg)
        self.assertIn("endpoint=anthropic", msg)

    def test_custom_endpoint_timeout_logs_error(self):
        """Custom endpoint timeout → ERROR log with endpoint=custom."""
        svc = self._service()
        patcher, mock_logger = self._patch_logging()
        with patcher:
            with patch("requests.post", side_effect=__import__("requests").exceptions.Timeout):
                result = svc._send_openai_message(
                    model="llama3",
                    api_key="",
                    messages=[{"role": "user", "content": "hi"}],
                    chat_url="http://localhost:11434/v1/chat/completions",
                    timeout_seconds=3,
                )
        self.assertFalse(result.success)
        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args[0][0]
        self.assertIn("endpoint=custom", msg)

    def test_openai_retry_timeout_logs_error_with_retry_label(self):
        """OpenAI retry (temperature error → retry) times out → ERROR with endpoint=<label>-retry."""
        import requests as req
        svc = self._service()
        patcher, mock_logger = self._patch_logging()
        temp_error = "Unsupported value: 'temperature' does not support 0.7"
        with patcher:
            with patch("requests.post", side_effect=[
                _make_openai_400(temp_error),
                req.exceptions.Timeout(),
            ]):
                result = svc._send_openai_message(
                    model="gpt-4o",
                    api_key="sk-test",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout_seconds=5,
                )
        self.assertFalse(result.success)
        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args[0][0]
        self.assertIn("endpoint=openai-retry", msg)

    def test_anthropic_retry_timeout_logs_error_with_retry_label(self):
        """Anthropic retry (thinking.type.disabled rejected → retry) times out → endpoint=anthropic-retry."""
        import requests as req
        svc = self._service()
        patcher, mock_logger = self._patch_logging()
        thinking_err = "thinking.type.disabled is not supported for this model"
        with patcher:
            with patch("requests.post", side_effect=[
                _make_anthropic_400(thinking_err),
                req.exceptions.Timeout(),
            ]):
                result = svc._send_anthropic_message(
                    model="claude-sonnet-4-6",
                    api_key="ant-test",
                    messages=[{"role": "user", "content": "hi"}],
                    timeout_seconds=5,
                    thinking={"type": "disabled"},
                )
        self.assertFalse(result.success)
        mock_logger.error.assert_called_once()
        msg = mock_logger.error.call_args[0][0]
        self.assertIn("endpoint=anthropic-retry", msg)


if __name__ == "__main__":
    unittest.main()
