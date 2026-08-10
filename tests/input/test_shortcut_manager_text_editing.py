"""Unit tests for ShortcutManager text-edit key bypass."""

import unittest

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent

from app.input.shortcut_manager import _text_editing_should_receive


def _key_press(
    key: Qt.Key,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    text: str = "",
) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, int(key), modifiers, text)


class TestTextEditingShouldReceive(unittest.TestCase):
    """Editable fields keep caret keys, typing, and standard edit chords."""

    def test_arrow_keys_are_received(self):
        event = _key_press(Qt.Key.Key_Left)
        self.assertTrue(_text_editing_should_receive(event))

    def test_plain_typing_is_received(self):
        event = _key_press(Qt.Key.Key_A, text="a")
        self.assertTrue(_text_editing_should_receive(event))

    def test_ctrl_v_paste_chord_is_received(self):
        event = _key_press(
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier,
            text="v",
        )
        self.assertTrue(_text_editing_should_receive(event))

    def test_ctrl_c_copy_chord_is_received(self):
        event = _key_press(
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
            text="c",
        )
        self.assertTrue(_text_editing_should_receive(event))

    def test_ctrl_a_select_all_is_received(self):
        event = _key_press(
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
            text="a",
        )
        self.assertTrue(_text_editing_should_receive(event))

    def test_ctrl_x_cut_chord_is_received(self):
        event = _key_press(
            Qt.Key.Key_X,
            Qt.KeyboardModifier.ControlModifier,
            text="x",
        )
        self.assertTrue(_text_editing_should_receive(event))

    def test_unrelated_app_chord_is_not_claimed_by_text_editing(self):
        # Ctrl+P is Copy PGN by default — not a standard text-edit chord.
        event = _key_press(
            Qt.Key.Key_P,
            Qt.KeyboardModifier.ControlModifier,
            text="p",
        )
        self.assertFalse(_text_editing_should_receive(event))

    def test_ctrl_alt_v_is_not_claimed_by_text_editing(self):
        # Paste PGN to Clipboard DB uses Ctrl+Alt+V — keep for app shortcut.
        event = _key_press(
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
            text="v",
        )
        self.assertFalse(_text_editing_should_receive(event))


if __name__ == "__main__":
    unittest.main()
