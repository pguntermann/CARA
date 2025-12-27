"""Button styling utilities."""

from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import QPushButton


def generate_button_stylesheet(
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    background_offset: int,
    hover_background_offset: int,
    pressed_background_offset: int,
    border_radius: int,
    padding: int,
    min_width: Optional[int] = None,
    min_height: Optional[int] = None
) -> str:
    """Generate QSS stylesheet for buttons.
    
    Args:
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Base background color as [R, G, B].
        border_color: Border color as [R, G, B].
        background_offset: Background color offset for normal state.
        hover_background_offset: Background color offset for hover state.
        pressed_background_offset: Background color offset for pressed state.
        border_radius: Border radius in pixels.
        padding: Padding in pixels.
        min_width: Minimum width in pixels. If None, not included in stylesheet.
        min_height: Minimum height in pixels. If None, not included in stylesheet.
    
    Returns:
        A string containing the QSS stylesheet for buttons.
    """
    # Calculate color values for different states
    normal_bg = [
        min(255, bg_color[0] + background_offset),
        min(255, bg_color[1] + background_offset),
        min(255, bg_color[2] + background_offset)
    ]
    hover_bg = [
        min(255, bg_color[0] + hover_background_offset),
        min(255, bg_color[1] + hover_background_offset),
        min(255, bg_color[2] + hover_background_offset)
    ]
    pressed_bg = [
        min(255, bg_color[0] + pressed_background_offset),
        min(255, bg_color[1] + pressed_background_offset),
        min(255, bg_color[2] + pressed_background_offset)
    ]
    disabled_bg = bg_color
    disabled_text = [
        text_color[0] // 2,
        text_color[1] // 2,
        text_color[2] // 2
    ]
    
    # Build base stylesheet
    base_styles = [
        f"background-color: rgb({normal_bg[0]}, {normal_bg[1]}, {normal_bg[2]});",
        f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});",
        f"border-radius: {border_radius}px;",
        f"padding: {padding}px;",
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});",
        f"font-family: \"{font_family}\";",
        f"font-size: {font_size}pt;"
    ]
    
    # Add min-width and min-height if provided
    if min_width is not None:
        base_styles.append(f"min-width: {min_width}px;")
    if min_height is not None:
        base_styles.append(f"min-height: {min_height}px;")
    
    stylesheet = (
        f"QPushButton {{"
        f"{' '.join(base_styles)}"
        f"}}"
        f"QPushButton:hover {{"
        f"background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});"
        f"border-color: rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"}}"
        f"QPushButton:pressed {{"
        f"background-color: rgb({pressed_bg[0]}, {pressed_bg[1]}, {pressed_bg[2]});"
        f"border-color: rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"}}"
        f"QPushButton:disabled {{"
        f"background-color: rgb({disabled_bg[0]}, {disabled_bg[1]}, {disabled_bg[2]});"
        f"color: rgb({disabled_text[0]}, {disabled_text[1]}, {disabled_text[2]});"
        f"}}"
        f"QPushButton:focus {{"
        f"outline: none;"
        f"}}"
    )
    
    return stylesheet


def apply_button_styling(
    buttons: List[QPushButton],
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    background_offset: int,
    hover_background_offset: int,
    pressed_background_offset: int,
    border_radius: int,
    padding: int,
    min_width: Optional[int] = None,
    min_height: Optional[int] = None
) -> None:
    """Apply styling to a list of buttons.
    
    Args:
        buttons: List of QPushButton widgets to style.
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Base background color as [R, G, B].
        border_color: Border color as [R, G, B].
        background_offset: Background color offset for normal state.
        hover_background_offset: Background color offset for hover state.
        pressed_background_offset: Background color offset for pressed state.
        border_radius: Border radius in pixels.
        padding: Padding in pixels.
        min_width: Minimum width in pixels. If None, not included in stylesheet.
        min_height: Minimum height in pixels. If None, not included in stylesheet.
    
    This function:
    1. Generates a QSS stylesheet for buttons
    2. Applies the stylesheet to all buttons
    """
    if not buttons:
        return
    
    # Generate stylesheet
    button_style = generate_button_stylesheet(
        config, text_color, font_family, font_size,
        bg_color, border_color, background_offset,
        hover_background_offset, pressed_background_offset,
        border_radius, padding, min_width, min_height
    )
    
    # Apply stylesheet to all buttons
    for button in buttons:
        button.setStyleSheet(button_style)

