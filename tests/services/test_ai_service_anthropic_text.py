"""Anthropic message text extraction."""

import unittest

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


if __name__ == "__main__":
    unittest.main()
