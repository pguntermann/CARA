"""Tests for portable vs native keyboard-shortcut formatting."""

import sys
import unittest

from PyQt6.QtGui import QKeySequence

from app.utils.keyboard_shortcuts_catalog import (
    format_shortcut,
    format_shortcut_for_display,
    parse_shortcut,
)


class TestKeyboardShortcutFormatting(unittest.TestCase):
    def test_format_shortcut_uses_portable_text(self) -> None:
        sequence = parse_shortcut("Ctrl+Shift+O")
        self.assertEqual(
            format_shortcut(sequence),
            sequence.toString(QKeySequence.SequenceFormat.PortableText),
        )
        self.assertIn("Ctrl", format_shortcut(sequence))

    def test_format_shortcut_for_display_uses_native_text(self) -> None:
        portable = "Ctrl+O"
        display = format_shortcut_for_display(portable)
        expected = parse_shortcut(portable).toString(
            QKeySequence.SequenceFormat.NativeText
        )
        self.assertEqual(display, expected)

    def test_format_shortcut_for_display_empty(self) -> None:
        self.assertEqual(format_shortcut_for_display(""), "")
        self.assertEqual(format_shortcut_for_display("   "), "")

    @unittest.skipUnless(sys.platform == "darwin", "macOS native glyphs only")
    def test_macos_display_uses_command_glyph(self) -> None:
        display = format_shortcut_for_display("Ctrl+O")
        self.assertIn("⌘", display)
        self.assertNotIn("Ctrl", display)

    @unittest.skipUnless(sys.platform == "darwin", "macOS native glyphs only")
    def test_macos_display_uses_option_glyph(self) -> None:
        display = format_shortcut_for_display("Alt+C")
        self.assertIn("⌥", display)
        self.assertNotIn("Alt", display)


if __name__ == "__main__":
    unittest.main()
