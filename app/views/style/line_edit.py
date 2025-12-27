"""Line edit styling utilities."""

from typing import Dict, Any, List


def generate_line_edit_stylesheet(
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    focus_border_color: List[int],
    border_width: int = 1,
    border_radius: int = 3,
    padding: List[int] = None,
    hover_border_offset: int = 20,
    disabled_brightness_factor: float = 0.5
) -> str:
    """Generate QSS stylesheet for QLineEdit widgets.
    
    Args:
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        focus_border_color: Focus border color as [R, G, B].
        border_width: Border width in pixels (default: 1).
        border_radius: Border radius in pixels (default: 3).
        padding: Padding as [horizontal, vertical] or [left, top, right, bottom] (default: [8, 6]).
        hover_border_offset: Brightness offset for hover border (default: 20).
        disabled_brightness_factor: Brightness factor for disabled state (default: 0.5).
        
    Returns:
        QSS stylesheet string.
    """
    # Default padding if not provided
    if padding is None:
        padding = [8, 6]
    
    # Handle padding format: [horizontal, vertical] or [left, top, right, bottom]
    if len(padding) == 2:
        padding_str = f"{padding[1]}px {padding[0]}px"
    else:
        padding_str = f"{padding[1]}px {padding[0]}px {padding[3]}px {padding[2]}px"
    
    # Calculate hover border color
    hover_border = [
        min(255, border_color[0] + hover_border_offset),
        min(255, border_color[1] + hover_border_offset),
        min(255, border_color[2] + hover_border_offset)
    ]
    
    # Calculate disabled colors
    disabled_bg = [
        int(bg_color[0] * disabled_brightness_factor),
        int(bg_color[1] * disabled_brightness_factor),
        int(bg_color[2] * disabled_brightness_factor)
    ]
    disabled_text = [
        int(text_color[0] * disabled_brightness_factor),
        int(text_color[1] * disabled_brightness_factor),
        int(text_color[2] * disabled_brightness_factor)
    ]
    
    stylesheet = (
        f"QLineEdit {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {border_radius}px;"
        f"padding: {padding_str};"
        f"font-family: \"{font_family}\";"
        f"font-size: {font_size}pt;"
        f"margin: 0px;"
        f"}}"
        f"QLineEdit:hover {{"
        f"border: {border_width}px solid rgb({hover_border[0]}, {hover_border[1]}, {hover_border[2]});"
        f"}}"
        f"QLineEdit:focus {{"
        f"border: {border_width}px solid rgb({focus_border_color[0]}, {focus_border_color[1]}, {focus_border_color[2]});"
        f"}}"
        f"QLineEdit:disabled {{"
        f"background-color: rgb({disabled_bg[0]}, {disabled_bg[1]}, {disabled_bg[2]});"
        f"color: rgb({disabled_text[0]}, {disabled_text[1]}, {disabled_text[2]});"
        f"}}"
    )
    
    return stylesheet


def apply_line_edit_styling(
    line_edits: List,
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    focus_border_color: List[int],
    border_width: int = 1,
    border_radius: int = 3,
    padding: List[int] = None,
    hover_border_offset: int = 20,
    disabled_brightness_factor: float = 0.5
) -> None:
    """Apply styling to QLineEdit widgets.
    
    Args:
        line_edits: List of QLineEdit widgets to style.
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Background color as [R, G, B].
        border_color: Border color as [R, G, B].
        focus_border_color: Focus border color as [R, G, B].
        border_width: Border width in pixels (default: 1).
        border_radius: Border radius in pixels (default: 3).
        padding: Padding as [horizontal, vertical] or [left, top, right, bottom] (default: [8, 6]).
        hover_border_offset: Brightness offset for hover border (default: 20).
        disabled_brightness_factor: Brightness factor for disabled state (default: 0.5).
    """
    stylesheet = generate_line_edit_stylesheet(
        config, text_color, font_family, font_size, bg_color, border_color,
        focus_border_color, border_width, border_radius, padding,
        hover_border_offset, disabled_brightness_factor
    )
    
    for line_edit in line_edits:
        line_edit.setStyleSheet(stylesheet)

