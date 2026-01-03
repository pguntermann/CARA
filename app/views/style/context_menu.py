"""Context menu styling utilities."""

from typing import Dict, Any, List
from PyQt6.QtWidgets import QMenu
from app.utils.font_utils import resolve_font_family, scale_font_size


def apply_context_menu_styling(
    menu: QMenu,
    config: Dict[str, Any],
    bg_color: List[int],
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
        bg_color: Base background color as [R, G, B] (from view/dialog config).
        text_color: Text color as [R, G, B]. If None, reads from centralized config.
        font_family: Font family name. If None, reads from centralized config.
        font_size: Font size in points. If None, reads from centralized config (with DPI scaling).
        border_color: Border color as [R, G, B]. If None, reads from centralized config.
        border_width: Border width in pixels. If None, reads from centralized config.
        border_radius: Border radius in pixels. If None, reads from centralized config.
        hover_bg_color: Hover background color as [R, G, B]. If None, reads from centralized config.
        hover_text_color: Hover text color as [R, G, B]. If None, reads from centralized config.
        item_padding: Item padding as [top, right, bottom, left]. If None, reads from centralized config.
        separator_height: Separator height in pixels. If None, reads from centralized config.
        separator_color: Separator color as [R, G, B]. If None, reads from centralized config.
        separator_margin: Separator margin as [vertical, horizontal]. If None, reads from centralized config.
    """
    # Get unified config values if parameters are not provided
    styles_config = config.get('ui', {}).get('styles', {})
    context_menu_config = styles_config.get('context_menu', {})
    
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
        item_padding = context_menu_config.get('item_padding', [4, 20, 4, 8])
    if separator_height is None:
        separator_height = context_menu_config.get('separator_height', 1)
    if separator_color is None:
        separator_color = context_menu_config.get('separator_color', [60, 60, 65])
    if separator_margin is None:
        separator_margin = context_menu_config.get('separator_margin', [2, 4])
    
    # Build stylesheet
    stylesheet = f"""
        QMenu {{
            background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
            color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
            border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
            border-radius: {border_radius}px;
            font-family: "{font_family}";
            font-size: {font_size}pt;
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

