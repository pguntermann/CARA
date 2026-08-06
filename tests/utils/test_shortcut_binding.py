"""Tests for physical shortcut binding helpers."""

import sys
import unittest

from PyQt6.QtCore import Qt, QKeyCombination
from PyQt6.QtGui import QKeySequence

from app.utils.shortcut_binding import (
    format_shortcut,
    format_shortcut_for_display,
    normalize_binding,
    parse_shortcut,
    shortcut_match_key,
)


class TestShortcutBinding(unittest.TestCase):
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

    def test_normalize_and_match_key(self) -> None:
        self.assertEqual(normalize_binding(" ctrl+o "), normalize_binding("Ctrl+O"))
        self.assertEqual(
            shortcut_match_key("Ctrl+O"),
            shortcut_match_key("ctrl+o"),
        )
        self.assertEqual(normalize_binding(""), "")

    def test_shift_period_portable_form(self) -> None:
        stored = format_shortcut(
            QKeySequence(
                QKeyCombination(
                    Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_Period
                )
            )
        )
        self.assertEqual(stored, "Shift+.")
        self.assertEqual(shortcut_match_key(stored), shortcut_match_key("Shift+."))

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
