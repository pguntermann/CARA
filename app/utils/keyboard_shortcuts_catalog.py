"""Collect bindable keyboard shortcuts from menus and navigation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional, Set, Tuple

from PyQt6.QtCore import Qt, QKeyCombination
from PyQt6.QtGui import QAction, QKeyEvent, QKeySequence
from PyQt6.QtWidgets import QMenu, QMenuBar, QWidget

# QObject property: menus/actions marked True are omitted from the shortcuts catalog.
CARA_SHORTCUTS_EXCLUDED = "cara_shortcuts_excluded"

# Global navigation shortcuts registered via ShortcutManager (not menu QActions).
NAVIGATION_SHORTCUTS: Tuple[Tuple[str, str, str], ...] = (
    ("Navigation", "Previous move", "Left"),
    ("Navigation", "Next move", "Right"),
    ("Navigation", "Jump to start", "Shift+Left"),
    ("Navigation", "Jump to last move", "Shift+Right"),
)


@dataclass(frozen=True)
class ShortcutEntry:
    """One shortcut row for display and editing."""

    category: str
    action: str
    shortcut: str
    # Stable id: "Category/Action"
    binding_id: str = ""
    # True for ShortcutManager navigation bindings (not QAction-backed).
    is_navigation: bool = False


def make_binding_id(category: str, action: str) -> str:
    """Build a stable binding id from category + action labels."""
    return f"{category}/{action}"


def mark_shortcuts_excluded(obj) -> None:
    """Mark a QMenu or QAction so it is skipped by the shortcuts catalog."""
    try:
        obj.setProperty(CARA_SHORTCUTS_EXCLUDED, True)
    except Exception:
        pass


def is_shortcuts_excluded(obj) -> bool:
    try:
        return bool(obj.property(CARA_SHORTCUTS_EXCLUDED))
    except Exception:
        return False


def _clean_action_text(text: str) -> str:
    """Strip menu accelerators and trailing ellipsis for display/ids."""
    cleaned = (text or "").replace("&", "").strip()
    if cleaned.endswith("..."):
        cleaned = cleaned[:-3].rstrip()
    elif cleaned.endswith("…"):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


# Shift+digit/punctuation is reported as the shifted glyph (e.g. Key_Exclam for
# Shift+1). Shortcut matching expects the physical base key + ShiftModifier.
_SHIFT_SYMBOL_TO_BASE_KEY: Dict[Qt.Key, Qt.Key] = {
    Qt.Key.Key_Exclam: Qt.Key.Key_1,
    Qt.Key.Key_At: Qt.Key.Key_2,
    Qt.Key.Key_NumberSign: Qt.Key.Key_3,
    Qt.Key.Key_Dollar: Qt.Key.Key_4,
    Qt.Key.Key_Percent: Qt.Key.Key_5,
    Qt.Key.Key_AsciiCircum: Qt.Key.Key_6,
    Qt.Key.Key_Ampersand: Qt.Key.Key_7,
    Qt.Key.Key_Asterisk: Qt.Key.Key_8,
    Qt.Key.Key_ParenLeft: Qt.Key.Key_9,
    Qt.Key.Key_ParenRight: Qt.Key.Key_0,
    Qt.Key.Key_Underscore: Qt.Key.Key_Minus,
    Qt.Key.Key_Plus: Qt.Key.Key_Equal,
    Qt.Key.Key_BraceLeft: Qt.Key.Key_BracketLeft,
    Qt.Key.Key_BraceRight: Qt.Key.Key_BracketRight,
    Qt.Key.Key_Bar: Qt.Key.Key_Backslash,
    Qt.Key.Key_Colon: Qt.Key.Key_Semicolon,
    Qt.Key.Key_QuoteDbl: Qt.Key.Key_Apostrophe,
    Qt.Key.Key_Less: Qt.Key.Key_Comma,
    Qt.Key.Key_Greater: Qt.Key.Key_Period,
    Qt.Key.Key_Question: Qt.Key.Key_Slash,
    Qt.Key.Key_AsciiTilde: Qt.Key.Key_QuoteLeft,
}


def _shortcut_modifiers(modifiers: Qt.KeyboardModifier) -> Qt.KeyboardModifier:
    """Keep only modifiers that belong in a stored shortcut."""
    return modifiers & (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )


def _normalize_key_with_modifiers(
    key: Qt.Key,
    modifiers: Qt.KeyboardModifier,
) -> Tuple[Qt.Key, Qt.KeyboardModifier]:
    """Map Shift+shifted-glyph keys back to base keys for reliable matching."""
    mods = _shortcut_modifiers(modifiers)
    if mods & Qt.KeyboardModifier.ShiftModifier:
        base = _SHIFT_SYMBOL_TO_BASE_KEY.get(key)
        if base is not None:
            key = base
    return key, mods


def format_shortcut(sequence: QKeySequence) -> str:
    """Format a key sequence for storage/display (portable Ctrl/Shift labels)."""
    if sequence is None or sequence.isEmpty():
        return ""
    normalized = normalize_key_sequence(sequence)
    return normalized.toString(QKeySequence.SequenceFormat.PortableText)


def parse_shortcut(text: str) -> QKeySequence:
    """Parse a portable shortcut string into a QKeySequence."""
    raw = (text or "").strip()
    if not raw:
        return QKeySequence()
    return normalize_key_sequence(
        QKeySequence(raw, QKeySequence.SequenceFormat.PortableText)
    )


def normalize_key_sequence(sequence: QKeySequence) -> QKeySequence:
    """Normalize Shift+symbol combos (e.g. Shift+! → Shift+1) for matching."""
    if sequence is None or sequence.isEmpty():
        return QKeySequence()
    try:
        combo = sequence[0]
    except Exception:
        return sequence
    if not isinstance(combo, QKeyCombination):
        # Older/alternate representation: integer key+mods.
        try:
            key_int = int(combo)
            key = Qt.Key(key_int & ~int(Qt.KeyboardModifier.KeyboardModifierMask))
            mods = Qt.KeyboardModifier(
                key_int & int(Qt.KeyboardModifier.KeyboardModifierMask)
            )
        except Exception:
            return sequence
    else:
        key = combo.key()
        mods = combo.keyboardModifiers()

    key, mods = _normalize_key_with_modifiers(Qt.Key(key), Qt.KeyboardModifier(mods))
    return QKeySequence(QKeyCombination(mods, key))


def shortcut_from_key_event(event: QKeyEvent) -> str:
    """Build a portable shortcut string from a key event (capture-safe)."""
    key, mods = _normalize_key_with_modifiers(
        Qt.Key(event.key()),
        event.modifiers(),
    )
    return format_shortcut(QKeySequence(QKeyCombination(mods, key)))


def _iter_menu_actions(menu: QMenu) -> Iterable[Tuple[QMenu, QAction]]:
    for action in menu.actions():
        yield menu, action
        submenu = action.menu()
        if submenu is not None:
            yield from _iter_menu_actions(submenu)


def _ancestor_excluded(menu: QMenu) -> bool:
    current: Optional[QMenu] = menu
    seen: Set[int] = set()
    while current is not None:
        cid = id(current)
        if cid in seen:
            break
        seen.add(cid)
        if is_shortcuts_excluded(current):
            return True
        parent = current.parent()
        current = parent if isinstance(parent, QMenu) else None
    return False


def collect_menu_entries(
    menu_bar: QMenuBar,
    *,
    include_unbound: bool = True,
) -> List[ShortcutEntry]:
    """Walk the menu bar and collect bindable leaf QActions."""
    entries: List[ShortcutEntry] = []
    seen_ids: Set[str] = set()

    for top_action in menu_bar.actions():
        top_menu = top_action.menu()
        if top_menu is None:
            continue
        if is_shortcuts_excluded(top_menu):
            continue
        category = _clean_action_text(top_action.text()) or "Menu"
        for parent_menu, action in _iter_menu_actions(top_menu):
            if action.isSeparator():
                continue
            if action.menu() is not None:
                # Submenu opener — children are collected separately.
                continue
            if is_shortcuts_excluded(action) or _ancestor_excluded(parent_menu):
                continue
            label = _clean_action_text(action.text())
            if not label:
                continue
            # Placeholder / disabled headers such as "(No engines configured)".
            if not action.isEnabled() and label.startswith("("):
                continue
            shortcut = format_shortcut(action.shortcut())
            if not shortcut and not include_unbound:
                continue
            binding_id = make_binding_id(category, label)
            if binding_id in seen_ids:
                continue
            seen_ids.add(binding_id)
            entries.append(
                ShortcutEntry(
                    category=category,
                    action=label,
                    shortcut=shortcut,
                    binding_id=binding_id,
                    is_navigation=False,
                )
            )
    return entries


def collect_navigation_entries() -> List[ShortcutEntry]:
    """Return the fixed Navigation category bindings."""
    return [
        ShortcutEntry(
            category=category,
            action=action,
            shortcut=shortcut,
            binding_id=make_binding_id(category, action),
            is_navigation=True,
        )
        for category, action, shortcut in NAVIGATION_SHORTCUTS
    ]


def sort_shortcut_entries(entries: List[ShortcutEntry]) -> List[ShortcutEntry]:
    """Sort with Navigation first, then category/action."""

    def _sort_key(e: ShortcutEntry) -> tuple:
        category_rank = 0 if e.category == "Navigation" else 1
        return (category_rank, e.category.lower(), e.action.lower(), e.shortcut.lower())

    return sorted(entries, key=_sort_key)


def collect_all_shortcuts(
    menu_bar: Optional[QMenuBar],
    *,
    include_unbound: bool = True,
) -> List[ShortcutEntry]:
    """Navigation bindings plus bindable menu actions."""
    entries = collect_navigation_entries()
    if menu_bar is not None:
        entries.extend(collect_menu_entries(menu_bar, include_unbound=include_unbound))
    return sort_shortcut_entries(entries)


def collect_shortcuts_from_window(
    window: QWidget,
    *,
    include_unbound: bool = True,
) -> List[ShortcutEntry]:
    """Convenience: collect from a main window that has a menu bar."""
    menu_bar = window.menuBar() if hasattr(window, "menuBar") else None
    return collect_all_shortcuts(menu_bar, include_unbound=include_unbound)


def find_menu_action(
    menu_bar: Optional[QMenuBar],
    binding_id: str,
) -> Optional[QAction]:
    """Resolve a menu QAction by binding id (Category/Action)."""
    if menu_bar is None or not binding_id or "/" not in binding_id:
        return None
    category, _, action_label = binding_id.partition("/")
    category = category.strip()
    action_label = action_label.strip()
    if not category or not action_label:
        return None

    for top_action in menu_bar.actions():
        top_menu = top_action.menu()
        if top_menu is None:
            continue
        if _clean_action_text(top_action.text()) != category:
            continue
        if is_shortcuts_excluded(top_menu):
            continue
        for parent_menu, action in _iter_menu_actions(top_menu):
            if action.isSeparator() or action.menu() is not None:
                continue
            if is_shortcuts_excluded(action) or _ancestor_excluded(parent_menu):
                continue
            if _clean_action_text(action.text()) == action_label:
                return action
    return None


def entries_with_shortcuts(
    entries: Iterable[ShortcutEntry],
    bindings: Dict[str, str],
) -> List[ShortcutEntry]:
    """Return copies of entries with shortcut text taken from ``bindings``."""
    result: List[ShortcutEntry] = []
    for entry in entries:
        shortcut = bindings.get(entry.binding_id, entry.shortcut)
        result.append(replace(entry, shortcut=shortcut or ""))
    return sort_shortcut_entries(result)
