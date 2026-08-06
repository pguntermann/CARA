"""Collect bindable keyboard shortcuts from menus and navigation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional, Set, Tuple

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenu, QMenuBar, QWidget

# Binding helpers (also re-exported for dialogs / older imports).
from app.utils.shortcut_binding import (
    format_shortcut,
    format_shortcut_for_display,
    normalize_binding,
    parse_shortcut,
    shortcut_from_key_event,
    shortcut_match_key,
)

__all__ = [
    "CARA_SHORTCUTS_EXCLUDED",
    "NAVIGATION_SHORTCUTS",
    "ShortcutEntry",
    "collect_all_shortcuts",
    "collect_menu_entries",
    "collect_navigation_entries",
    "collect_shortcuts_from_window",
    "entries_with_shortcuts",
    "find_menu_action",
    "format_shortcut",
    "format_shortcut_for_display",
    "is_shortcuts_excluded",
    "make_binding_id",
    "mark_shortcuts_excluded",
    "normalize_binding",
    "parse_shortcut",
    "shortcut_from_key_event",
    "shortcut_match_key",
    "sort_shortcut_entries",
]

# QObject property: menus/actions marked True are omitted from the shortcuts catalog.
CARA_SHORTCUTS_EXCLUDED = "cara_shortcuts_excluded"

# Global navigation shortcuts registered via ShortcutManager (not menu QActions).
# Order here is the Shortcuts dialog order within Navigation (not alphabetical).
NAVIGATION_SHORTCUTS: Tuple[Tuple[str, str, str], ...] = (
    ("Navigation", "Previous move", "Left"),
    ("Navigation", "Next move", "Right"),
    ("Navigation", "Previous game", ""),
    ("Navigation", "Next game", ""),
    ("Navigation", "Jump to start", "Shift+Left"),
    ("Navigation", "Jump to first move", ""),
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
    """Strip shortcut annotations, menu accelerators, and trailing ellipsis."""
    cleaned = (text or "").split("\t")[0].replace("&", "").strip()
    if cleaned.endswith("..."):
        cleaned = cleaned[:-3].rstrip()
    elif cleaned.endswith("…"):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


# Joins intermediate submenu titles into the action label (not the category).
_SUBMENU_PATH_SEP = " › "


def _iter_menu_actions(
    menu: QMenu,
    submenu_path: Tuple[str, ...] = (),
) -> Iterable[Tuple[QMenu, QAction, Tuple[str, ...]]]:
    """Yield (parent_menu, action, path_of_submenu_titles_above_this_action)."""
    for action in menu.actions():
        yield menu, action, submenu_path
        submenu = action.menu()
        if submenu is not None:
            title = _clean_action_text(action.text())
            next_path = submenu_path + ((title,) if title else ())
            yield from _iter_menu_actions(submenu, next_path)


def _action_label(leaf_text: str, submenu_path: Tuple[str, ...]) -> str:
    """Leaf label, prefixed with nested submenu titles when present."""
    if not submenu_path:
        return leaf_text
    return _SUBMENU_PATH_SEP.join((*submenu_path, leaf_text))


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
        for parent_menu, action, submenu_path in _iter_menu_actions(top_menu):
            if action.isSeparator():
                continue
            if action.menu() is not None:
                # Submenu opener — children are collected separately.
                continue
            if is_shortcuts_excluded(action) or _ancestor_excluded(parent_menu):
                continue
            leaf = _clean_action_text(action.text())
            if not leaf:
                continue
            # Placeholder / disabled headers such as "(No engines configured)".
            if not action.isEnabled() and leaf.startswith("("):
                continue
            label = _action_label(leaf, submenu_path)
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
    """Sort with Navigation first (catalog order), then other categories A–Z."""

    navigation_order = {
        make_binding_id(category, action): index
        for index, (category, action, _shortcut) in enumerate(NAVIGATION_SHORTCUTS)
    }

    def _sort_key(e: ShortcutEntry) -> tuple:
        if e.category == "Navigation" or e.is_navigation:
            return (
                0,
                navigation_order.get(e.binding_id or make_binding_id(e.category, e.action), 10_000),
                e.action.lower(),
            )
        return (1, e.category.lower(), e.action.lower(), e.shortcut.lower())

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
        for parent_menu, action, submenu_path in _iter_menu_actions(top_menu):
            if action.isSeparator() or action.menu() is not None:
                continue
            if is_shortcuts_excluded(action) or _ancestor_excluded(parent_menu):
                continue
            leaf = _clean_action_text(action.text())
            if not leaf:
                continue
            if _action_label(leaf, submenu_path) == action_label:
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
