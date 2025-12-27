"""Radio button styling utilities."""

from typing import Dict, Any, List
from PyQt6.QtWidgets import QRadioButton
from PyQt6.QtGui import QPalette, QColor


def generate_radio_button_stylesheet(
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    spacing: int = None
) -> str:
    """Generate QSS stylesheet for radio buttons.
    
    Args:
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        spacing: Spacing between indicator and label in pixels. If None, reads from config.
    
    Returns:
        A string containing the QSS stylesheet for radio buttons.
    """
    styles_config = config.get('ui', {}).get('styles', {})
    radio_button_config = styles_config.get('radio_button', {})
    
    # Get spacing from parameter, config, or default
    if spacing is None:
        spacing = radio_button_config.get('spacing', 5)
    
    stylesheet = (
        f"QRadioButton {{"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"font-family: \"{font_family}\";"
        f"font-size: {font_size}pt;"
        f"spacing: {spacing}px;"
        f"}}"
    )
    
    return stylesheet


def apply_radio_button_styling(
    radio_buttons: List[QRadioButton],
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    spacing: int = None
) -> None:
    """Apply styling to a list of radio buttons.
    
    Args:
        radio_buttons: List of QRadioButton widgets to style.
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        spacing: Spacing between indicator and label in pixels. If None, reads from config.
    
    This function:
    1. Generates a QSS stylesheet for radio buttons
    2. Applies the stylesheet to all radio buttons
    3. Sets palette to ensure color is applied (macOS sometimes ignores stylesheet)
    """
    if not radio_buttons:
        return
    
    # Generate stylesheet
    radio_button_style = generate_radio_button_stylesheet(
        config, text_color, font_family, font_size, spacing
    )
    
    # Apply stylesheet and palette to all radio buttons
    for radio_button in radio_buttons:
        radio_button.setStyleSheet(radio_button_style)
        
        # Also set palette to ensure color is applied (macOS sometimes ignores stylesheet)
        palette = radio_button.palette()
        palette.setColor(radio_button.foregroundRole(), 
                        QColor(text_color[0], text_color[1], text_color[2]))
        radio_button.setPalette(palette)
        
        # Force update to ensure styling is applied
        radio_button.update()

