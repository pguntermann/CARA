"""Checkbox styling utilities."""

from pathlib import Path
from typing import Dict, Any, List
from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtGui import QColor, QPalette


def generate_checkbox_stylesheet(
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    checkmark_path: Path
) -> str:
    """Generate QSS stylesheet for checkboxes.
    
    Args:
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Background color for indicator as [R, G, B].
        border_color: Border color for indicator as [R, G, B].
        checkmark_path: Path to checkmark.svg icon.
    
    Returns:
        A string containing the QSS stylesheet for checkboxes.
    """
    styles_config = config.get('ui', {}).get('styles', {})
    checkbox_config = styles_config.get('checkbox', {})
    
    spacing = checkbox_config.get('spacing', 5)
    indicator_width = checkbox_config.get('indicator_width', 16)
    indicator_height = checkbox_config.get('indicator_height', 16)
    indicator_border_radius = checkbox_config.get('indicator_border_radius', 3)
    checked_bg = checkbox_config.get('checked_background_color', [70, 90, 130])
    checked_border = checkbox_config.get('checked_border_color', [100, 120, 160])
    hover_border_offset = checkbox_config.get('hover_border_offset', 20)
    margin_top = checkbox_config.get('margin_top', 2)
    margin_bottom = checkbox_config.get('margin_bottom', 2)
    
    # Get checkmark URL
    checkmark_url = str(checkmark_path).replace("\\", "/") if checkmark_path.exists() else ""
    
    stylesheet = (
        f"QCheckBox {{"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"font-family: {font_family};"
        f"font-size: {font_size}pt;"
        f"spacing: {spacing}px;"
        f"margin-top: {margin_top}px;"
        f"margin-bottom: {margin_bottom}px;"
        f"background-color: transparent;"
        f"}}"
        f"QCheckBox::indicator {{"
        f"width: {indicator_width}px;"
        f"height: {indicator_height}px;"
        f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {indicator_border_radius}px;"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"}}"
        f"QCheckBox::indicator:hover {{"
        f"border: 1px solid rgb({min(255, border_color[0] + hover_border_offset)}, {min(255, border_color[1] + hover_border_offset)}, {min(255, border_color[2] + hover_border_offset)});"
        f"}}"
        f"QCheckBox::indicator:checked {{"
        f"background-color: rgb({checked_bg[0]}, {checked_bg[1]}, {checked_bg[2]});"
        f"border: 1px solid rgb({checked_border[0]}, {checked_border[1]}, {checked_border[2]});"
        f"image: url({checkmark_url});"
        f"}}"
    )
    
    return stylesheet


def apply_checkbox_styling(
    checkboxes: List[QCheckBox],
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    bg_color: List[int],
    border_color: List[int],
    checkmark_path: Path
) -> None:
    """Apply checkbox styling to a list of checkboxes.
    
    Args:
        checkboxes: List of QCheckBox widgets to style.
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        bg_color: Background color for indicator as [R, G, B].
        border_color: Border color for indicator as [R, G, B].
        checkmark_path: Path to checkmark.svg icon.
    """
    checkbox_style = generate_checkbox_stylesheet(
        config, text_color, font_family, font_size, bg_color, border_color, checkmark_path
    )
    
    for checkbox in checkboxes:
        checkbox.setStyleSheet(checkbox_style)

