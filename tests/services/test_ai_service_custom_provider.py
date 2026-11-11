"""Tests for AIService with the CUSTOM (OpenAI-compatible local) provider.

CUSTOM reuses _send_openai_message with a base_url_override.  These tests
verify that the URL is constructed correctly, usage is extracted when present
and flagged as not-reported when absent, and all failure modes produce a clear
AIResult.success=False with a descriptive error.

No real network calls — requests.post is mocked throughout.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests as _requests_lib

from app.services.ai_service import AIService

_BASE_URL = "http://localhost:1234/v1"
_EXPECTED_URL = "http://localhost:1234/v1/chat/completions"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_response(text: str, usage: object = "present") -> MagicMock:
    """Build a 200 mock response.  usage='present' adds a real block; None omits it."""
    mock = MagicMock()
    mock.status_code = 200
    mock.content = b"x"
    body: dict = {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}]
    }
    if usage == "present":
        body["usage"] = {"prompt_tokens": 80, "completion_tokens": 40}
    elif usage == "null":
        body["usage"] = None
    # elif usage is None → key absent from body entirely
    mock.json.return_value = body
    return mock


def _error_response(status: int, message: str) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status
    mock.content = b"x"
    mock.json.return_value = {"error": {"message": message}}
    return mock


def _call(mock_post_return_value, base_url: str = _BASE_URL, **kwargs) -> "AIResult":
    mock_post_return_value  # already set on mock_post in the caller
    return AIService().send_message(
        provider="custom",
        model="local-model",
        api_key="",
        messages=[{"role": "user", "content": "hello"}],
        base_url_override=base_url,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------

class TestCustomProviderUrl(unittest.TestCase):

    @patch("app.services.ai_service.requests.post")
    def test_url_appends_chat_completions(self, mock_post):
        mock_post.return_value = _ok_response("hi")
        AIService().send_message(
            provider="custom",
            model="local-model",
            api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        called_url = mock_post.call_args[0][0]
        self.assertEqual(called_url, _EXPECTED_URL)

    @patch("app.services.ai_service.requests.post")
    def test_trailing_slash_on_base_url_stripped(self, mock_post):
        mock_post.return_value = _ok_response("hi")
        AIService().send_message(
            provider="custom",
            model="local-model",
            api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override="http://localhost:1234/v1/",
        )
        called_url = mock_post.call_args[0][0]
        self.assertEqual(called_url, _EXPECTED_URL)

    @patch("app.services.ai_service.requests.post")
    def test_no_base_url_returns_failure(self, mock_post):
        result = AIService().send_message(
            provider="custom",
            model="local-model",
            api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=None,
        )
        mock_post.assert_not_called()
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# Successful replies — usage variants
# ---------------------------------------------------------------------------

class TestCustomProviderUsage(unittest.TestCase):

    @patch("app.services.ai_service.requests.post")
    def test_usage_present_reported_true(self, mock_post):
        mock_post.return_value = _ok_response("ok", usage="present")
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.usage)
        self.assertTrue(result.usage.reported)
        self.assertEqual(result.usage.input_tokens, 80)
        self.assertEqual(result.usage.output_tokens, 40)

    @patch("app.services.ai_service.requests.post")
    def test_usage_null_reported_false(self, mock_post):
        mock_post.return_value = _ok_response("ok", usage="null")
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.usage)
        self.assertFalse(result.usage.reported)

    @patch("app.services.ai_service.requests.post")
    def test_usage_absent_reported_false(self, mock_post):
        mock_post.return_value = _ok_response("ok", usage=None)
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.usage)
        self.assertFalse(result.usage.reported)

    @patch("app.services.ai_service.requests.post")
    def test_successful_reply_text_returned(self, mock_post):
        mock_post.return_value = _ok_response("narrative text here")
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.text, "narrative text here")


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

class TestCustomProviderFailures(unittest.TestCase):

    @patch("app.services.ai_service.requests.post")
    def test_4xx_returns_failure_with_status(self, mock_post):
        mock_post.return_value = _error_response(400, "model not found")
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertFalse(result.success)
        self.assertIn("400", result.error)
        self.assertIn("model not found", result.error)

    @patch("app.services.ai_service.requests.post")
    def test_5xx_returns_failure_with_status(self, mock_post):
        mock_post.return_value = _error_response(500, "internal server error")
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertFalse(result.success)
        self.assertIn("500", result.error)
        self.assertIn("internal server error", result.error)

    @patch("app.services.ai_service.requests.post")
    def test_timeout_returns_failure_naming_timeout(self, mock_post):
        mock_post.side_effect = _requests_lib.exceptions.Timeout("timed out after 30s")
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
            timeout_seconds=30,
        )
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        error_lower = result.error.lower()
        self.assertTrue(
            "timeout" in error_lower or "timed out" in error_lower,
            f"Expected timeout in error, got: {result.error!r}",
        )

    @patch("app.services.ai_service.requests.post")
    def test_connection_refused_returns_failure_naming_endpoint(self, mock_post):
        mock_post.side_effect = _requests_lib.exceptions.ConnectionError(
            f"Connection refused: {_BASE_URL}"
        )
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertFalse(result.success)
        self.assertIn(_BASE_URL, result.error)

    @patch("app.services.ai_service.requests.post")
    def test_empty_choices_returns_failure(self, mock_post):
        mock = MagicMock()
        mock.status_code = 200
        mock.content = b"x"
        mock.json.return_value = {"choices": []}
        mock_post.return_value = mock
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertFalse(result.success)

    @patch("app.services.ai_service.requests.post")
    def test_non_json_response_returns_failure(self, mock_post):
        mock = MagicMock()
        mock.status_code = 200
        mock.content = b"x"
        mock.json.side_effect = ValueError("not json")
        mock_post.return_value = mock
        result = AIService().send_message(
            provider="custom", model="local-model", api_key="",
            messages=[{"role": "user", "content": "hello"}],
            base_url_override=_BASE_URL,
        )
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
