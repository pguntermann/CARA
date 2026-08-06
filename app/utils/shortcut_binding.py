"""Keyboard shortcut bindings (Qt-only, same on every platform).

Capture and match use ``QKeyEvent.key()`` plus modifiers. No native virtual-key
tables and no per-OS display logic — Linux, macOS, and Windows share one path.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QKeyCombination
from PyQt6.QtGui import QKeyEvent, QKeySequence


def _shortcut_modifiers(modifiers: Qt.KeyboardModifier) -> Qt.KeyboardModifier:
    return modifiers & (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )


def format_shortcut(sequence: QKeySequence) -> str:
    """Portable storage form (Ctrl/Alt labels)."""
    if sequence is None or sequence.isEmpty():
        return ""
    return sequence.toString(QKeySequence.SequenceFormat.PortableText)


def parse_shortcut(text: str) -> QKeySequence:
    """Parse a portable shortcut string."""
    raw = (text or "").strip()
    if not raw:
        return QKeySequence()
    return QKeySequence(raw, QKeySequence.SequenceFormat.PortableText)


def format_shortcut_for_display(text: str) -> str:
    """Native UI form (⌘ / ⌥ glyphs on macOS)."""
    sequence = parse_shortcut(text)
    if sequence.isEmpty():
        return ""
    return sequence.toString(QKeySequence.SequenceFormat.NativeText)


def shortcut_match_key(text: str) -> str:
    """Canonical compare key for two portable shortcut strings."""
    sequence = parse_shortcut(text)
    if sequence.isEmpty():
        return ""
    return format_shortcut(sequence).casefold()


def shortcut_from_key_event(event: QKeyEvent) -> str:
    """Portable shortcut from a key event (capture and match)."""
    mods = _shortcut_modifiers(event.modifiers())
    key = Qt.Key(event.key())
    return format_shortcut(QKeySequence(QKeyCombination(mods, key)))


def normalize_binding(text: str) -> str:
    """Normalize a stored binding string (empty if unset/invalid)."""
    if not (text or "").strip():
        return ""
    return format_shortcut(parse_shortcut(text))
