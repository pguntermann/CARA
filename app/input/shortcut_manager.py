"""Global keyboard shortcut manager for routing key commands."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from app.utils.shortcut_binding import (
    normalize_binding,
    shortcut_from_key_event,
    shortcut_match_key,
)

# Keys editable text widgets use for caret movement / editing.
_TEXT_EDITING_KEYS = frozenset(
    {
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Home,
        Qt.Key.Key_End,
        Qt.Key.Key_PageUp,
        Qt.Key.Key_PageDown,
        Qt.Key.Key_Backspace,
        Qt.Key.Key_Delete,
        Qt.Key.Key_Tab,
        Qt.Key.Key_Backtab,
        Qt.Key.Key_Return,
        Qt.Key.Key_Enter,
    }
)

# Ctrl/Meta edit chords a focused editable field must keep (copy/paste/cut/…).
# App shortcuts with the same keys (e.g. Paste PGN on Ctrl+V) still apply when
# focus is not in an editable text widget. Alt is excluded so Ctrl+Alt+V keeps
# Paste PGN to Clipboard DB.
_TEXT_EDIT_CHORD_KEYS = frozenset(
    {
        Qt.Key.Key_C,  # copy
        Qt.Key.Key_V,  # paste
        Qt.Key.Key_X,  # cut
        Qt.Key.Key_A,  # select all
        Qt.Key.Key_Z,  # undo / redo (with Shift)
        Qt.Key.Key_Y,  # redo
    }
)


def _editable_text_widget(widget: Optional[QWidget]) -> Optional[QWidget]:
    """Return the focused editable text widget, if any (skips read-only)."""
    current = widget
    while current is not None:
        if isinstance(current, QLineEdit):
            return None if current.isReadOnly() else current
        if isinstance(current, (QTextEdit, QPlainTextEdit)):
            return None if current.isReadOnly() else current
        if isinstance(current, QAbstractSpinBox):
            return current
        if isinstance(current, QComboBox) and current.isEditable():
            return current
        current = current.parentWidget()
    return None


def _matches_standard_text_edit_key(event: QKeyEvent) -> bool:
    """True if the event is a text-edit chord (copy/paste/cut/select-all/undo/redo)."""
    mods = event.modifiers()
    has_ctrl_or_meta = bool(
        mods
        & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.MetaModifier
        )
    )
    has_alt = bool(mods & Qt.KeyboardModifier.AltModifier)
    return (
        has_ctrl_or_meta
        and not has_alt
        and event.key() in _TEXT_EDIT_CHORD_KEYS
    )


def _text_editing_should_receive(event: QKeyEvent) -> bool:
    """True when an editable text field should handle this key itself."""
    key = event.key()
    if key in _TEXT_EDITING_KEYS:
        return True
    if _matches_standard_text_edit_key(event):
        return True
    mods = event.modifiers() & (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.MetaModifier
        | Qt.KeyboardModifier.AltModifier
    )
    # Plain typing (and Shift for capitals).
    if not mods and event.text():
        return True
    return False


class ShortcutManager(QObject):
    """Activates all application shortcuts from key bindings.

    Menu QActions keep a display shortcut for the menu bar label; this manager
    is the sole activator (event filter consumes matches so Qt does not also
    fire character-based QAction shortcuts).

    Editable text fields (notes, inputs) keep typing, caret keys, and standard
    edit chords (copy/paste/cut/select-all/undo/redo). The same keys still
    activate app shortcuts when focus is not in an editable field. Read-only
    views such as the PGN pane still receive navigation shortcuts.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.parent_window = parent
        self._handlers: Dict[str, Callable[[], None]] = {}
        self._keys: Dict[str, str] = {}
        self._match_keys: Dict[str, str] = {}
        self._enabled = True
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def register_shortcut(
        self,
        binding_id: str,
        key: str,
        handler: Callable[[], None],
    ) -> None:
        """Register (or replace) a binding and its handler."""
        self._handlers[binding_id] = handler
        self.set_key(binding_id, key)

    def has_binding(self, binding_id: str) -> bool:
        return binding_id in self._handlers

    def get_key(self, binding_id: str) -> str:
        return self._keys.get(binding_id, "")

    def get_all_keys(self) -> Dict[str, str]:
        return dict(self._keys)

    def set_shortcuts_enabled(self, enabled: bool) -> None:
        """Enable/disable activation (e.g. while capturing a new shortcut)."""
        self._enabled = bool(enabled)

    def set_key(self, binding_id: str, key: str) -> None:
        """Update the key for an existing binding. Empty key disables it."""
        if binding_id not in self._handlers:
            return
        normalized = normalize_binding(key)
        self._keys[binding_id] = normalized
        if normalized:
            self._match_keys[binding_id] = shortcut_match_key(normalized)
        else:
            self._match_keys.pop(binding_id, None)

    def unregister_shortcut(self, binding_id: str) -> None:
        """Remove a binding entirely."""
        self._handlers.pop(binding_id, None)
        self._keys.pop(binding_id, None)
        self._match_keys.pop(binding_id, None)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if not self._enabled or event.type() != QEvent.Type.KeyPress:
            return False
        if not isinstance(event, QKeyEvent):
            return False

        key = event.key()
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return False

        try:
            window = self.parent_window
            if window is None or not window.isVisible() or not window.isActiveWindow():
                return False
        except Exception:
            return False

        focus = QApplication.focusWidget()
        if focus is not None and obj is not focus:
            return False
        if focus is None and obj is not self.parent_window:
            return False

        if _editable_text_widget(focus) is not None and _text_editing_should_receive(
            event
        ):
            return False

        pressed = shortcut_match_key(shortcut_from_key_event(event))
        if not pressed:
            return False

        for binding_id, match in self._match_keys.items():
            if match != pressed:
                continue
            handler = self._handlers.get(binding_id)
            if handler is None:
                return False
            handler()
            return True
        return False
