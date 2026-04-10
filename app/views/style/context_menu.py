"""Context menu styling utilities."""

from typing import Any, Dict, List, Optional

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QApplication, QMenu

from app.utils.font_utils import resolve_font_family, scale_font_size


def apply_context_menu_styling(
    menu: QMenu,
    config: Dict[str, Any],
    bg_color: Optional[List[int]] = None,
    text_color: List[int] = None,
    font_family: str = None,
    font_size: float = None,
    border_color: List[int] = None,
    border_width: int = None,
    border_radius: int = None,
    hover_bg_color: List[int] = None,
    hover_text_color: List[int] = None,
    item_padding: List[int] = None,
    separator_height: int = None,
    separator_color: List[int] = None,
    separator_margin: List[int] = None
) -> None:
    """Apply styling to a context menu.
    
    Args:
        menu: The QMenu instance to style.
        config: Configuration dictionary.
        bg_color: Background color as [R, G, B]. If None, reads from centralized config.
        text_color: Text color as [R, G, B]. If None, reads from centralized config.
        font_family: Font family name. If None, reads from centralized config.
        font_size: Font size in points. If None, reads from centralized config (with DPI scaling).
        border_color: Border color as [R, G, B]. If None, reads from centralized config.
        border_width: Border width in pixels. If None, reads from centralized config.
        border_radius: Border radius in pixels. If None, reads from centralized config.
        hover_bg_color: Hover background color as [R, G, B]. If None, reads from centralized config.
        hover_text_color: Hover text color as [R, G, B]. If None, reads from centralized config.
        item_padding: Item padding as [top, right, bottom, left] (left also clears icons from the menu edge;
            Qt has no separate icon-column alignment in QSS). If None, reads from centralized config.
        separator_height: Separator height in pixels. If None, reads from centralized config.
        separator_color: Separator color as [R, G, B]. If None, reads from centralized config.
        separator_margin: Separator margin as [vertical, horizontal]. If None, reads from centralized config.
    """
    # Get unified config values if parameters are not provided
    styles_config = config.get('ui', {}).get('styles', {})
    context_menu_config = styles_config.get('context_menu', {})

    if bg_color is None:
        bg_color = context_menu_config.get('background_color', [45, 45, 50])
    
    if text_color is None:
        text_color = context_menu_config.get('text_color', [200, 200, 200])
    if font_family is None:
        font_family_raw = context_menu_config.get('font_family', 'Helvetica Neue')
        font_family = resolve_font_family(font_family_raw)
    if font_size is None:
        font_size_raw = context_menu_config.get('font_size', 11)
        font_size = scale_font_size(font_size_raw)
    if border_color is None:
        border_color = context_menu_config.get('border_color', [60, 60, 65])
    if border_width is None:
        border_width = context_menu_config.get('border_width', 1)
    if border_radius is None:
        border_radius = context_menu_config.get('border_radius', 3)
    if hover_bg_color is None:
        hover_bg_color = context_menu_config.get('hover_background_color', [55, 55, 60])
    if hover_text_color is None:
        hover_text_color = context_menu_config.get('hover_text_color', [230, 230, 230])
    if item_padding is None:
        item_padding = context_menu_config.get('item_padding', [4, 20, 4, 14])
    if separator_height is None:
        separator_height = context_menu_config.get('separator_height', 1)
    if separator_color is None:
        separator_color = context_menu_config.get('separator_color', [60, 60, 65])
    if separator_margin is None:
        separator_margin = context_menu_config.get('separator_margin', [2, 4])

    menu_hpad_raw = context_menu_config.get("menu_horizontal_padding", 4)
    try:
        menu_hpad = max(0, int(menu_hpad_raw))
    except (TypeError, ValueError):
        menu_hpad = 4

    # Build stylesheet
    stylesheet = f"""
        QMenu {{
            background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
            color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
            border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
            border-radius: {border_radius}px;
            font-family: "{font_family}";
            font-size: {font_size}pt;
            padding: 0px {menu_hpad}px;
        }}
        QMenu::item {{
            padding: {item_padding[0]}px {item_padding[1]}px {item_padding[2]}px {item_padding[3]}px;
        }}
        QMenu::item:selected {{
            background-color: rgb({hover_bg_color[0]}, {hover_bg_color[1]}, {hover_bg_color[2]});
            color: rgb({hover_text_color[0]}, {hover_text_color[1]}, {hover_text_color[2]});
        }}
        QMenu::separator {{
            height: {separator_height}px;
            background-color: rgb({separator_color[0]}, {separator_color[1]}, {separator_color[2]});
            margin: {separator_margin[0]}px {separator_margin[1]}px;
        }}
    """
    
    menu.setStyleSheet(stylesheet)


def apply_dark_standard_textedit_context_menu_icons(menu: QMenu, config: Dict[str, Any]) -> None:
    """Use themed icons on ``QTextEdit.createStandardContextMenu()`` actions.

    Qt's built-in icons ignore our dark ``QMenu`` stylesheet; this assigns SVG-based
    icons tinted with :func:`app.utils.themed_icon.menu_icon_dark_tint_rgb` (not
    OS color-scheme reactive). Call after :func:`apply_context_menu_styling` and
    before merging shared menubar actions.

    Matching prefers ``QKeySequence.StandardKey`` on the action shortcut, then
    common English menu labels as a fallback.
    """
    from app.utils.themed_icon import (
        menu_icon_dark_tint_rgb,
        themed_icon_from_svg,
        SVG_CONTEXT_DELETE,
        SVG_CONTEXT_REDO,
        SVG_CONTEXT_SELECT_ALL,
        SVG_CONTEXT_UNDO,
        SVG_MENU_COPY,
        SVG_MENU_CUT,
        SVG_MENU_PASTE_CLIPBOARD,
    )

    tint = menu_icon_dark_tint_rgb(config)
    icons = {
        "undo": themed_icon_from_svg(SVG_CONTEXT_UNDO, tint),
        "redo": themed_icon_from_svg(SVG_CONTEXT_REDO, tint),
        "cut": themed_icon_from_svg(SVG_MENU_CUT, tint),
        "copy": themed_icon_from_svg(SVG_MENU_COPY, tint),
        "paste": themed_icon_from_svg(SVG_MENU_PASTE_CLIPBOARD, tint),
        "delete": themed_icon_from_svg(SVG_CONTEXT_DELETE, tint),
        "select_all": themed_icon_from_svg(SVG_CONTEXT_SELECT_ALL, tint),
    }

    sk = QKeySequence.StandardKey
    std_pairs = (
        (sk.Undo, "undo"),
        (sk.Redo, "redo"),
        (sk.Cut, "cut"),
        (sk.Copy, "copy"),
        (sk.Paste, "paste"),
        (sk.Delete, "delete"),
        (sk.SelectAll, "select_all"),
    )

    def _icon_for_action(action: QAction):
        seq = action.shortcut()
        if not seq.isEmpty():
            for standard_key, name in std_pairs:
                if seq == QKeySequence(standard_key):
                    return icons[name]
        label = action.text().replace("&", "").strip().lower()
        label = label.replace("…", "").replace("...", "").strip()
        text_checks = (
            ("select all", "select_all"),
            ("undo", "undo"),
            ("redo", "redo"),
            ("cut", "cut"),
            ("copy", "copy"),
            ("paste", "paste"),
            ("delete", "delete"),
        )
        for phrase, name in text_checks:
            if label == phrase or label.startswith(phrase + " "):
                return icons[name]
        return None

    def _walk(m: QMenu) -> None:
        for action in m.actions():
            if action.isSeparator():
                continue
            sub = action.menu()
            if sub is not None:
                _walk(sub)
                continue
            icon = _icon_for_action(action)
            if icon is not None and not icon.isNull():
                action.setIcon(icon)

    _walk(menu)


def _leaf_actions_in_menu_tree(menu: QMenu) -> List[QAction]:
    out: List[QAction] = []
    for action in menu.actions():
        if action.isSeparator():
            continue
        sub = action.menu()
        if sub is not None:
            out.extend(_leaf_actions_in_menu_tree(sub))
        else:
            out.append(action)
    return out


def apply_registry_icons_for_menu_tree(menu: QMenu, mw: Any, *, dark_surface: bool) -> None:
    """Re-tint menubar-registered actions present under ``menu`` for dark or menubar chrome."""
    from app.utils.themed_icon import (
        menu_icon_dark_tint_rgb,
        menu_icon_tint_rgb,
        themed_icon_from_svg,
    )

    reg: Dict[Any, str] = getattr(mw, "_menubar_action_icon_svgs", None) or {}
    if not reg:
        return
    tint = menu_icon_dark_tint_rgb(mw.config) if dark_surface else menu_icon_tint_rgb(mw.config)
    for act in _leaf_actions_in_menu_tree(menu):
        path = reg.get(act)
        if path:
            act.setIcon(themed_icon_from_svg(path, tint))


def wire_context_menu_icon_retheming(menu: QMenu, mw: Any) -> None:
    """While this menu is visible, use dark-surface icon tints for registered menubar actions; restore on hide."""
    if getattr(menu, "_cara_context_icon_retheme_connected", False):
        return
    menu._cara_context_icon_retheme_connected = True

    def _on_show() -> None:
        apply_registry_icons_for_menu_tree(menu, mw, dark_surface=True)

    def _on_hide() -> None:
        apply_registry_icons_for_menu_tree(menu, mw, dark_surface=False)

    menu.aboutToShow.connect(_on_show)
    menu.aboutToHide.connect(_on_hide)


def try_wire_context_menu_shared_action_icons(menu: QMenu) -> None:
    """Attach icon re-tinting if the active window is a main window with a registry."""
    win = QApplication.activeWindow()
    if win is not None and hasattr(win, "_menubar_action_icon_svgs"):
        wire_context_menu_icon_retheming(menu, win)

