"""Group box styling utilities."""

from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import QGroupBox
from PyQt6.QtGui import QColor, QPalette


def generate_group_box_stylesheet(
    config: Dict[str, Any],
    border_color: List[int],
    border_width: int,
    border_radius: int,
    bg_color: Optional[List[int]],
    margin_top: int,
    padding_top: int,
    title_font_family: str,
    title_font_size: float,
    title_font_weight: Optional[str],
    title_color: List[int],
    title_left: int,
    title_padding: List[int]
) -> str:
    """Generate QSS stylesheet for QGroupBox widgets.
    
    Args:
        config: Configuration dictionary.
        border_color: Border color as [R, G, B].
        border_width: Border width in pixels.
        border_radius: Border radius in pixels.
        bg_color: Background color as [R, G, B]. If None, uses transparent.
        margin_top: Top margin in pixels.
        padding_top: Top padding in pixels.
        title_font_family: Title font family name.
        title_font_size: Title font size in points.
        title_font_weight: Title font weight (e.g., 'bold', 'normal'). If None, not included.
        title_color: Title text color as [R, G, B].
        title_left: Left offset for title in pixels.
        title_padding: Title padding as [left, right] in pixels.
        
    Returns:
        QSS stylesheet string.
    """
    # Background color - use transparent if not provided
    if bg_color is None:
        bg_color_str = "transparent"
    else:
        bg_color_str = f"rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]})"
    
    # Title font weight
    font_weight_str = ""
    if title_font_weight:
        font_weight_str = f"font-weight: {title_font_weight};"
    
    # Title padding format: [left, right]
    title_padding_str = f"{title_padding[0]} {title_padding[1]}px"
    
    stylesheet = (
        f"QGroupBox {{"
        f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {border_radius}px;"
        f"margin-top: {margin_top}px;"
        f"padding-top: {padding_top}px;"
        f"background-color: {bg_color_str};"
        f"}}"
        f"QGroupBox::title {{"
        f"subcontrol-origin: margin;"
        f"subcontrol-position: top left;"
        f"left: {title_left}px;"
        f"padding: {title_padding_str};"
        f"font-family: \"{title_font_family}\";"
        f"font-size: {title_font_size}pt;"
        f"{font_weight_str}"
        f"color: rgb({title_color[0]}, {title_color[1]}, {title_color[2]});"
        f"}}"
    )
    
    return stylesheet


def apply_group_box_styling(
    group_boxes: List[QGroupBox],
    config: Dict[str, Any],
    border_color: List[int],
    border_width: int,
    border_radius: int,
    bg_color: Optional[List[int]],
    margin_top: int,
    padding_top: int,
    title_font_family: str,
    title_font_size: float,
    title_font_weight: Optional[str],
    title_color: List[int],
    title_left: int,
    title_padding: List[int],
    content_margins: Optional[List[int]] = None,
    use_transparent_palette: bool = False
) -> None:
    """Apply styling to QGroupBox widgets.
    
    Args:
        group_boxes: List of QGroupBox widgets to style.
        config: Configuration dictionary.
        border_color: Border color as [R, G, B].
        border_width: Border width in pixels.
        border_radius: Border radius in pixels.
        bg_color: Background color as [R, G, B]. If None, uses transparent.
        margin_top: Top margin in pixels.
        padding_top: Top padding in pixels.
        title_font_family: Title font family name.
        title_font_size: Title font size in points.
        title_font_weight: Title font weight (e.g., 'bold', 'normal'). If None, not included.
        title_color: Title text color as [R, G, B].
        title_left: Left offset for title in pixels.
        title_padding: Title padding as [left, right] in pixels.
        content_margins: Content margins as [left, top, right, bottom] for layout. If None, not set.
        use_transparent_palette: If True and bg_color is None, sets palette for transparent background (macOS).
    """
    stylesheet = generate_group_box_stylesheet(
        config, border_color, border_width, border_radius, bg_color,
        margin_top, padding_top, title_font_family, title_font_size,
        title_font_weight, title_color, title_left, title_padding
    )
    
    for group_box in group_boxes:
        group_box.setStyleSheet(stylesheet)
        
        # Set content margins on layout if provided
        if content_margins is not None:
            layout = group_box.layout()
            if layout:
                layout.setContentsMargins(
                    content_margins[0],
                    content_margins[1],
                    content_margins[2],
                    content_margins[3]
                )
        
        # Set palette for transparent background on macOS if needed
        if use_transparent_palette and bg_color is None:
            palette = group_box.palette()
            palette.setColor(group_box.backgroundRole(), QColor(0, 0, 0, 0))  # Transparent
            palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0, 0))  # Transparent
            group_box.setPalette(palette)


