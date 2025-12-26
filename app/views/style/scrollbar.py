"""Scrollbar styling utilities."""

from PyQt6.QtWidgets import QScrollArea, QWidget
from PyQt6.QtGui import QColor, QPalette
from typing import List, Dict, Any


def generate_scrollbar_stylesheet(
    config: Dict[str, Any],
    bg_color: List[int],
    border_color: List[int],
    widget_selector: str = "QScrollBar"
) -> str:
    """Generate QSS stylesheet for scrollbar.
    
    Args:
        config: Configuration dictionary.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        widget_selector: CSS selector for the scrollbar (default: "QScrollBar").
                        Use "QTableWidget QScrollBar" for table scrollbars.
    
    Returns:
        QSS stylesheet string.
    """
    styles_config = config.get('ui', {}).get('styles', {})
    scrollbar_config = styles_config.get('scrollbar', {})
    
    scrollbar_width = scrollbar_config.get('width', 8)
    scrollbar_border_radius = scrollbar_config.get('border_radius', 4)
    scrollbar_min_height = scrollbar_config.get('min_height', 20)
    scrollbar_hover_offset = scrollbar_config.get('hover_offset', 20)
    scrollbar_add_line_height = scrollbar_config.get('add_line_height', 0)
    
    stylesheet = (
        f"{widget_selector}:vertical {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"width: {scrollbar_width}px !important;"
        f"max-width: {scrollbar_width}px !important;"
        f"min-width: {scrollbar_width}px !important;"
        f"border: none;"
        f"}}"
        f"{widget_selector}::add-line:vertical, {widget_selector}::sub-line:vertical {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"border: none;"
        f"height: {scrollbar_add_line_height}px;"
        f"}}"
        f"{widget_selector}::add-page:vertical, {widget_selector}::sub-page:vertical {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"}}"
        f"{widget_selector}::handle:vertical {{"
        f"background-color: rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {scrollbar_border_radius}px;"
        f"min-height: {scrollbar_min_height}px;"
        f"border: none;"
        f"}}"
        f"{widget_selector}::handle:vertical:hover {{"
        f"background-color: rgb({min(255, border_color[0] + scrollbar_hover_offset)}, {min(255, border_color[1] + scrollbar_hover_offset)}, {min(255, border_color[2] + scrollbar_hover_offset)});"
        f"}}"
        f"{widget_selector}:horizontal {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"height: {scrollbar_width}px !important;"
        f"max-height: {scrollbar_width}px !important;"
        f"min-height: {scrollbar_width}px !important;"
        f"border: none;"
        f"}}"
        f"{widget_selector}::add-line:horizontal, {widget_selector}::sub-line:horizontal {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"border: none;"
        f"width: {scrollbar_add_line_height}px;"
        f"}}"
        f"{widget_selector}::add-page:horizontal, {widget_selector}::sub-page:horizontal {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"}}"
        f"{widget_selector}::handle:horizontal {{"
        f"background-color: rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {scrollbar_border_radius}px;"
        f"min-width: {scrollbar_min_height}px;"
        f"border: none;"
        f"}}"
        f"{widget_selector}::handle:horizontal:hover {{"
        f"background-color: rgb({min(255, border_color[0] + scrollbar_hover_offset)}, {min(255, border_color[1] + scrollbar_hover_offset)}, {min(255, border_color[2] + scrollbar_hover_offset)});"
        f"}}"
    )
    
    return stylesheet


def generate_scroll_area_stylesheet(
    bg_color: List[int],
    border_color: List[int],
    border_radius: int
) -> str:
    """Generate QSS stylesheet for scroll area container.
    
    Args:
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        border_radius: Border radius in pixels.
    
    Returns:
        QSS stylesheet string.
    """
    stylesheet = (
        f"QScrollArea {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"border: none;"
        f"border-radius: {border_radius}px;"
        f"}}"
        f"QScrollArea QWidget {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"}}"
    )
    
    return stylesheet


def apply_scrollbar_styling(
    scroll_area: QScrollArea,
    config: Dict[str, Any],
    bg_color: List[int],
    border_color: List[int],
    border_radius: int = 3
) -> None:
    """Apply complete scrollbar styling to a QScrollArea.
    
    This includes:
    - Scroll area container styling
    - Scrollbar stylesheet
    - Direct scrollbar widget styling (to override macOS native styling)
    - Palette settings
    - Fixed width
    
    Args:
        scroll_area: The QScrollArea to style.
        config: Configuration dictionary.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        border_radius: Border radius for scroll area container.
    """
    # Generate scroll area stylesheet (container + scrollbar)
    scroll_area_style = generate_scroll_area_stylesheet(bg_color, border_color, border_radius)
    scrollbar_style = generate_scrollbar_stylesheet(config, bg_color, border_color)
    combined_style = scroll_area_style + scrollbar_style
    
    scroll_area.setStyleSheet(combined_style)
    
    # Set palette on scroll area viewport to prevent macOS override
    viewport = scroll_area.viewport()
    if viewport:
        viewport_palette = viewport.palette()
        viewport_palette.setColor(viewport.backgroundRole(), QColor(*bg_color))
        viewport.setPalette(viewport_palette)
        viewport.setAutoFillBackground(True)
    
    # Apply scrollbar stylesheet directly to scrollbar widget to prevent macOS override
    scrollbar = scroll_area.verticalScrollBar()
    if scrollbar:
        scrollbar_stylesheet = generate_scrollbar_stylesheet(config, bg_color, border_color)
        scrollbar.setStyleSheet(scrollbar_stylesheet)
        
        # Get scrollbar width from config
        styles_config = config.get('ui', {}).get('styles', {})
        scrollbar_config = styles_config.get('scrollbar', {})
        scrollbar_width = scrollbar_config.get('width', 8)
        
        # Set fixed width programmatically to override macOS native styling
        scrollbar.setFixedWidth(scrollbar_width)
        
        # Set palette to prevent macOS override
        scrollbar_palette = scrollbar.palette()
        scrollbar_palette.setColor(scrollbar.backgroundRole(), QColor(*bg_color))
        scrollbar_palette.setColor(scrollbar_palette.ColorRole.Base, QColor(*bg_color))
        scrollbar_palette.setColor(scrollbar_palette.ColorRole.Window, QColor(*bg_color))
        scrollbar.setPalette(scrollbar_palette)
        scrollbar.setAutoFillBackground(True)


def apply_table_scrollbar_styling(
    table_widget,
    config: Dict[str, Any],
    bg_color: List[int],
    border_color: List[int],
    table_style: str
) -> None:
    """Apply scrollbar styling to a QTableWidget.
    
    Args:
        table_widget: The QTableWidget to style.
        config: Configuration dictionary.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        table_style: Existing table stylesheet to append scrollbar styles to.
    """
    # Generate table scrollbar stylesheet with QTableWidget selector
    table_scrollbar_style = generate_scrollbar_stylesheet(
        config, bg_color, border_color, widget_selector="QTableWidget QScrollBar"
    )
    
    # Append scrollbar styling to table style
    combined_table_style = table_style + table_scrollbar_style
    table_widget.setStyleSheet(combined_table_style)
    
    # Apply scrollbar stylesheet directly to table scrollbar widgets to prevent macOS override
    # Style vertical scrollbar
    vertical_scrollbar = table_widget.verticalScrollBar()
    if vertical_scrollbar:
        scrollbar_stylesheet = generate_scrollbar_stylesheet(config, bg_color, border_color)
        vertical_scrollbar.setStyleSheet(scrollbar_stylesheet)
        
        # Get scrollbar width from config
        styles_config = config.get('ui', {}).get('styles', {})
        scrollbar_config = styles_config.get('scrollbar', {})
        scrollbar_width = scrollbar_config.get('width', 6)
        
        # Set fixed width programmatically to override macOS native styling
        vertical_scrollbar.setFixedWidth(scrollbar_width)
        
        # Set palette to prevent macOS override (using input colors to match left side)
        vertical_scrollbar_palette = vertical_scrollbar.palette()
        vertical_scrollbar_palette.setColor(vertical_scrollbar.backgroundRole(), QColor(*bg_color))
        vertical_scrollbar_palette.setColor(vertical_scrollbar_palette.ColorRole.Base, QColor(*bg_color))
        vertical_scrollbar_palette.setColor(vertical_scrollbar_palette.ColorRole.Window, QColor(*bg_color))
        vertical_scrollbar.setPalette(vertical_scrollbar_palette)
        vertical_scrollbar.setAutoFillBackground(True)
    
    # Style horizontal scrollbar
    horizontal_scrollbar = table_widget.horizontalScrollBar()
    if horizontal_scrollbar:
        scrollbar_stylesheet = generate_scrollbar_stylesheet(config, bg_color, border_color)
        horizontal_scrollbar.setStyleSheet(scrollbar_stylesheet)
        
        # Get scrollbar width from config (use same width for height of horizontal scrollbar)
        styles_config = config.get('ui', {}).get('styles', {})
        scrollbar_config = styles_config.get('scrollbar', {})
        scrollbar_width = scrollbar_config.get('width', 6)
        
        # Set fixed height programmatically to override macOS native styling
        horizontal_scrollbar.setFixedHeight(scrollbar_width)
        
        # Set palette to prevent macOS override
        horizontal_scrollbar_palette = horizontal_scrollbar.palette()
        horizontal_scrollbar_palette.setColor(horizontal_scrollbar.backgroundRole(), QColor(*bg_color))
        horizontal_scrollbar_palette.setColor(horizontal_scrollbar_palette.ColorRole.Base, QColor(*bg_color))
        horizontal_scrollbar_palette.setColor(horizontal_scrollbar_palette.ColorRole.Window, QColor(*bg_color))
        horizontal_scrollbar.setPalette(horizontal_scrollbar_palette)
        horizontal_scrollbar.setAutoFillBackground(True)
    


def apply_table_view_scrollbar_styling(
    table_view,
    config: Dict[str, Any],
    bg_color: List[int],
    border_color: List[int],
    table_style: str
) -> None:
    """Apply scrollbar styling to a QTableView.
    
    Args:
        table_view: The QTableView to style.
        config: Configuration dictionary.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        table_style: Existing table stylesheet to append scrollbar styles to.
    """
    # Generate table scrollbar stylesheet with QTableView selector
    table_scrollbar_style = generate_scrollbar_stylesheet(
        config, bg_color, border_color, widget_selector="QTableView QScrollBar"
    )
    
    # Append scrollbar styling to table style
    combined_table_style = table_style + table_scrollbar_style
    table_view.setStyleSheet(combined_table_style)
    
    # Apply scrollbar stylesheet directly to table scrollbar widgets to prevent macOS override
    # Style vertical scrollbar
    vertical_scrollbar = table_view.verticalScrollBar()
    if vertical_scrollbar:
        scrollbar_stylesheet = generate_scrollbar_stylesheet(config, bg_color, border_color)
        vertical_scrollbar.setStyleSheet(scrollbar_stylesheet)
        
        # Get scrollbar width from config
        styles_config = config.get('ui', {}).get('styles', {})
        scrollbar_config = styles_config.get('scrollbar', {})
        scrollbar_width = scrollbar_config.get('width', 6)
        
        # Set fixed width programmatically to override macOS native styling
        vertical_scrollbar.setFixedWidth(scrollbar_width)
        
        # Set palette to prevent macOS override
        vertical_scrollbar_palette = vertical_scrollbar.palette()
        vertical_scrollbar_palette.setColor(vertical_scrollbar.backgroundRole(), QColor(*bg_color))
        vertical_scrollbar_palette.setColor(vertical_scrollbar_palette.ColorRole.Base, QColor(*bg_color))
        vertical_scrollbar_palette.setColor(vertical_scrollbar_palette.ColorRole.Window, QColor(*bg_color))
        vertical_scrollbar.setPalette(vertical_scrollbar_palette)
        vertical_scrollbar.setAutoFillBackground(True)
    
    # Style horizontal scrollbar
    horizontal_scrollbar = table_view.horizontalScrollBar()
    if horizontal_scrollbar:
        scrollbar_stylesheet = generate_scrollbar_stylesheet(config, bg_color, border_color)
        horizontal_scrollbar.setStyleSheet(scrollbar_stylesheet)
        
        # Get scrollbar width from config (use same width for height of horizontal scrollbar)
        styles_config = config.get('ui', {}).get('styles', {})
        scrollbar_config = styles_config.get('scrollbar', {})
        scrollbar_width = scrollbar_config.get('width', 6)
        
        # Set fixed height programmatically to override macOS native styling
        horizontal_scrollbar.setFixedHeight(scrollbar_width)
        
        # Set palette to prevent macOS override
        horizontal_scrollbar_palette = horizontal_scrollbar.palette()
        horizontal_scrollbar_palette.setColor(horizontal_scrollbar.backgroundRole(), QColor(*bg_color))
        horizontal_scrollbar_palette.setColor(horizontal_scrollbar_palette.ColorRole.Base, QColor(*bg_color))
        horizontal_scrollbar_palette.setColor(horizontal_scrollbar_palette.ColorRole.Window, QColor(*bg_color))
        horizontal_scrollbar.setPalette(horizontal_scrollbar_palette)
        horizontal_scrollbar.setAutoFillBackground(True)
