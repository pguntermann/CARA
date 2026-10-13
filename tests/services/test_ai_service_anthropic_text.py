"""Anthropic message text extraction and truncation messaging."""

import unittest
from unittest.mock import MagicMock, patch

from app.services.ai_service import AIService


class TestAnthropicMessageText(unittest.TestCase):
    def test_reads_a_single_text_block(self) -> None:
        data = {"content": [{"type": "text", "text": "  12. Bd2 was better.  "}]}
        self.assertEqual(AIService.anthropic_message_text(data), "12. Bd2 was better.")

    def test_skips_a_leading_thinking_block(self) -> None:
        data = {
            "content": [
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "text", "text": "White slipped with 12. Nd2."},
            ]
        }
        self.assertEqual(
            AIService.anthropic_message_text(data),
            "White slipped with 12. Nd2.",
        )

    def test_joins_text_blocks_and_ignores_an_empty_reply(self) -> None:
        data = {
            "content": [
                {"type": "text", "text": "First. "},
                {"type": "thinking", "thinking": "hidden"},
                {"type": "text", "text": "Second."},
            ]
        }
        self.assertEqual(AIService.anthropic_message_text(data), "First. Second.")
        self.assertEqual(AIService.anthropic_message_text({"content": []}), "")
        self.assertEqual(
            AIService.anthropic_message_text(
                {"content": [{"type": "thinking", "thinking": "only"}]}
            ),
            "",
        )


class TestOutputTokenLimitMessage(unittest.TestCase):
    def test_advises_max_tokens_or_different_model(self) -> None:
        message = AIService.output_token_limit_message()
        self.assertIn("Increase the max tokens setting", message)
        self.assertIn("choose a different model", message)
        self.assertNotIn("simpler question", message.lower())
        self.assertNotIn("prompt", message.lower())

    def test_includes_reasoning_token_detail_when_available(self) -> None:
        message = AIService.output_token_limit_message(
            output_tokens=2000,
            reasoning_tokens=2000,
        )
        self.assertIn("2000 of 2000", message)


class TestAnthropicMaxTokensEmptyReply(unittest.TestCase):
    @patch("app.services.ai_service.requests.post")
    def test_max_tokens_while_thinking_returns_actionable_error(
        self, mock_post: MagicMock
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"{}"
        mock_response.json.return_value = {
            "stop_reason": "max_tokens",
            "content": [{"type": "thinking", "thinking": "still going"}],
            "usage": {"output_tokens": 2000},
        }
        mock_post.return_value = mock_response

        service = AIService()
        success, message = service._send_anthropic_message(
            model="claude-sonnet-4-5",
            api_key="test-key",
            messages=[{"role": "user", "content": "hello"}],
            token_limit=3500,
        )

        self.assertFalse(success)
        self.assertIn("Increase the max tokens setting", message)
        self.assertIn("2000", message)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["max_tokens"], 3500)

    @patch("app.services.ai_service.requests.post")
    def test_empty_end_turn_keeps_generic_empty_message(
        self, mock_post: MagicMock
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"{}"
        mock_response.json.return_value = {
            "stop_reason": "end_turn",
            "content": [],
        }
        mock_post.return_value = mock_response

        service = AIService()
        success, message = service._send_anthropic_message(
            model="claude-sonnet-4-5",
            api_key="test-key",
            messages=[{"role": "user", "content": "hello"}],
        )

        self.assertFalse(success)
        self.assertEqual(message, "Empty response from API")


if __name__ == "__main__":
    unittest.main()
