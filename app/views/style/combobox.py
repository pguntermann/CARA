"""Combobox styling utilities."""

from typing import Dict, Any, List
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtGui import QColor, QPalette
from app.views.style.scrollbar import generate_scrollbar_stylesheet


def generate_combobox_stylesheet(
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    focus_border_color: List[int],
    selection_bg_color: List[int],
    selection_text_color: List[int],
    border_width: int = 1,
    border_radius: int = 3,
    padding: List[int] = None
) -> str:
    """Generate QSS stylesheet for comboboxes.
    
    Args:
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        focus_border_color: Focus border color as [R, G, B].
        selection_bg_color: Selection background color as [R, G, B].
        selection_text_color: Selection text color as [R, G, B].
        border_width: Border width in pixels (default: 1).
        border_radius: Border radius in pixels (default: 3).
        padding: Padding as [horizontal, vertical] (default: [8, 6]).
    
    Returns:
        A string containing the QSS stylesheet for comboboxes.
    """
    styles_config = config.get('ui', {}).get('styles', {})
    combobox_config = styles_config.get('combobox', {})
    
    # Get combobox-specific config values, with fallbacks
    dropdown_border_radius = combobox_config.get('dropdown_border_radius', border_radius)
    
    # Get padding from config, parameter, or default
    if padding is None:
        # Try to get from combobox config first
        config_padding = combobox_config.get('padding', None)
        if config_padding is not None:
            padding = config_padding if isinstance(config_padding, list) else [config_padding, config_padding]
        else:
            # Default fallback
            padding = [8, 6]
    
    padding_h = padding[0] if isinstance(padding, list) and len(padding) > 0 else 8
    padding_v = padding[1] if isinstance(padding, list) and len(padding) > 1 else 6
    
    stylesheet = (
        f"QComboBox {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {border_radius}px;"
        f"padding: {padding_v}px {padding_h}px;"
        f"font-family: {font_family};"
        f"font-size: {font_size}pt;"
        f"}}"
        f"QComboBox:!editable {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {border_radius}px;"
        f"padding: {padding_v}px {padding_h}px;"
        f"}}"
        f"QComboBox:editable {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {border_radius}px;"
        f"}}"
        f"QComboBox:focus {{"
        f"border-color: rgb({focus_border_color[0]}, {focus_border_color[1]}, {focus_border_color[2]});"
        f"}}"
        f"QComboBox:!editable:focus {{"
        f"border-color: rgb({focus_border_color[0]}, {focus_border_color[1]}, {focus_border_color[2]});"
        f"}}"
        f"QComboBox:editable:focus {{"
        f"border-color: rgb({focus_border_color[0]}, {focus_border_color[1]}, {focus_border_color[2]});"
        f"}}"
        f"QComboBox:pressed {{"
        f"border-color: rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"}}"
        f"QComboBox:!editable:pressed {{"
        f"border-color: rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"}}"
        f"QComboBox QAbstractItemView::item {{"
        f"min-height: 20px;"
        f"}}"
    )
    
    # Style the QLineEdit inside editable comboboxes to match the combobox appearance
    stylesheet += (
        f"QComboBox:editable QLineEdit {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"border: none;"
        f"padding: {padding_v}px {padding_h}px;"
        f"font-family: {font_family};"
        f"font-size: {font_size}pt;"
        f"}}"
        f"QComboBox:editable QLineEdit:focus {{"
        f"border: none;"
        f"}}"
    )
    
    # Don't style ::drop-down or ::down-arrow at all
    # Any styling of ::drop-down interferes with Qt's default arrow rendering
    # The black border on press is a macOS native behavior that cannot be removed
    # via stylesheets without breaking arrow visibility
    
    # Dropdown list styling
    stylesheet += (
        f"QComboBox QAbstractItemView {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"selection-background-color: rgb({selection_bg_color[0]}, {selection_bg_color[1]}, {selection_bg_color[2]});"
        f"selection-color: rgb({selection_text_color[0]}, {selection_text_color[1]}, {selection_text_color[2]});"
        f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {dropdown_border_radius}px;"
        f"}}"
        f"QComboBox QAbstractItemView::item {{"
        f"min-height: 20px;"
        f"}}"
        f"QComboBox QAbstractScrollArea::viewport {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"}}"
    )
    
    # Add scrollbar styling for dropdown list
    scrollbar_style = generate_scrollbar_stylesheet(
        config, bg_color, border_color, widget_selector="QComboBox QAbstractItemView QScrollBar"
    )
    stylesheet += scrollbar_style
    
    # Disabled state
    stylesheet += (
        f"QComboBox:disabled {{"
        f"background-color: rgb({bg_color[0] // 2}, {bg_color[1] // 2}, {bg_color[2] // 2});"
        f"color: rgb({text_color[0] // 2}, {text_color[1] // 2}, {text_color[2] // 2});"
        f"}}"
    )
    
    return stylesheet


def apply_combobox_styling(
    comboboxes: List[QComboBox],
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    focus_border_color: List[int],
    selection_bg_color: List[int],
    selection_text_color: List[int],
    border_width: int = 1,
    border_radius: int = 3,
    padding: List[int] = None,
    editable: bool = False
) -> None:
    """Apply combobox styling to a list of comboboxes.
    
    This includes:
    - Combobox stylesheet
    - Editable state setting
    - Palette settings for dropdown view (to prevent macOS override)
    
    Args:
        comboboxes: List of QComboBox widgets to style.
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        focus_border_color: Focus border color as [R, G, B].
        selection_bg_color: Selection background color as [R, G, B].
        selection_text_color: Selection text color as [R, G, B].
        border_width: Border width in pixels (default: 1).
        border_radius: Border radius in pixels (default: 3).
        padding: Padding as [horizontal, vertical] (default: [8, 6]).
        editable: Whether comboboxes should be editable (default: False).
    """
    combobox_style = generate_combobox_stylesheet(
        config, text_color, font_family, font_size, bg_color, border_color,
        focus_border_color, selection_bg_color, selection_text_color,
        border_width, border_radius, padding
    )
    
    for combobox in comboboxes:
        # Always make combobox editable for consistent behavior on macOS
        # If editable=False, we'll make the inner QLineEdit read-only to prevent text input
        combobox.setEditable(True)
        
        # If we don't want user input, make the line edit read-only
        if not editable:
            line_edit = combobox.lineEdit()
            if line_edit:
                line_edit.setReadOnly(True)
        
        combobox.setStyleSheet(combobox_style)
        
        # Set palette on combobox view to prevent macOS override
        # The view should exist after setEditable is called
        view = combobox.view()
        if view:
            view_palette = view.palette()
            view_palette.setColor(view.backgroundRole(), QColor(*bg_color))
            view_palette.setColor(view.foregroundRole(), QColor(*text_color))
            view.setPalette(view_palette)
            view.setAutoFillBackground(True)
            
            # Style scrollbars in dropdown list
            # Get scrollbar stylesheet
            scrollbar_stylesheet = generate_scrollbar_stylesheet(config, bg_color, border_color)
            
            # Style vertical scrollbar
            vertical_scrollbar = view.verticalScrollBar()
            if vertical_scrollbar:
                vertical_scrollbar.setStyleSheet(scrollbar_stylesheet)
                
                # Get scrollbar width from config
                styles_config = config.get('ui', {}).get('styles', {})
                scrollbar_config = styles_config.get('scrollbar', {})
                scrollbar_width = scrollbar_config.get('width', 8)
                
                # Set fixed width programmatically to override macOS native styling
                vertical_scrollbar.setFixedWidth(scrollbar_width)
                
                # Set palette to prevent macOS override
                scrollbar_palette = vertical_scrollbar.palette()
                scrollbar_palette.setColor(vertical_scrollbar.backgroundRole(), QColor(*bg_color))
                scrollbar_palette.setColor(scrollbar_palette.ColorRole.Base, QColor(*bg_color))
                scrollbar_palette.setColor(scrollbar_palette.ColorRole.Window, QColor(*bg_color))
                vertical_scrollbar.setPalette(scrollbar_palette)
                vertical_scrollbar.setAutoFillBackground(True)
            
            # Style horizontal scrollbar (if present)
            horizontal_scrollbar = view.horizontalScrollBar()
            if horizontal_scrollbar:
                horizontal_scrollbar.setStyleSheet(scrollbar_stylesheet)
                
                # Get scrollbar width from config (use same width for height of horizontal scrollbar)
                styles_config = config.get('ui', {}).get('styles', {})
                scrollbar_config = styles_config.get('scrollbar', {})
                scrollbar_width = scrollbar_config.get('width', 8)
                
                # Set fixed height programmatically to override macOS native styling
                horizontal_scrollbar.setFixedHeight(scrollbar_width)
                
                # Set palette to prevent macOS override
                scrollbar_palette = horizontal_scrollbar.palette()
                scrollbar_palette.setColor(horizontal_scrollbar.backgroundRole(), QColor(*bg_color))
                scrollbar_palette.setColor(scrollbar_palette.ColorRole.Base, QColor(*bg_color))
                scrollbar_palette.setColor(scrollbar_palette.ColorRole.Window, QColor(*bg_color))
                horizontal_scrollbar.setPalette(scrollbar_palette)
                horizontal_scrollbar.setAutoFillBackground(True)
            
            # Set viewport palette to prevent white background in popup
            # The viewport is the scrollable area inside the view and needs its own palette
            viewport = view.viewport()
            if viewport:
                viewport.setAutoFillBackground(True)
                viewport_palette = viewport.palette()
                viewport_palette.setColor(viewport.backgroundRole(), QColor(*bg_color))
                viewport.setPalette(viewport_palette)
        
        # Set palette on combobox itself to prevent macOS override
        combobox_palette = combobox.palette()
        combobox_palette.setColor(combobox.backgroundRole(), QColor(*bg_color))
        combobox_palette.setColor(combobox.foregroundRole(), QColor(*text_color))
        # Also set base and window colors to prevent border artifacts
        combobox_palette.setColor(combobox_palette.ColorRole.Base, QColor(*bg_color))
        combobox_palette.setColor(combobox_palette.ColorRole.Window, QColor(*bg_color))
        combobox.setPalette(combobox_palette)
        combobox.setAutoFillBackground(True)

