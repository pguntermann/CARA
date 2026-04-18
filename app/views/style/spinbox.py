"""Spinbox styling utilities."""

from typing import Dict, Any, List, Optional, Tuple
from PyQt6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox, QSpinBox


def _inner_line_edit_text_margins(padding: Optional[List[int]]) -> Tuple[int, int, int, int]:
    """Map style padding to QLineEdit.setTextMargins (left, top, right, bottom).

    Same [horizontal, vertical] convention as line_edit / generate_spinbox_stylesheet.
    QSS padding on ``QSpinBox QLineEdit`` is unreliable on macOS; margins fix the text inset.
    """
    if padding is None:
        padding = [8, 6]
    if len(padding) == 2:
        h, v = int(padding[0]), int(padding[1])
        return (h, v, h, v)
    if len(padding) >= 4:
        return (
            int(padding[0]),
            int(padding[1]),
            int(padding[2]),
            int(padding[3]),
        )
    return (8, 6, 8, 6)


def generate_spinbox_stylesheet(
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
    disabled_brightness_factor: float = 0.5,
) -> str:
    """Generate QSS stylesheet for QSpinBox and QDoubleSpinBox widgets.

    Button visibility is handled in ``apply_spinbox_styling`` via ``setButtonSymbols``,
    not zero-width QSS (which can break keyboard input on some platforms).

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
        disabled_brightness_factor: Brightness factor for disabled state (default: 0.5).

    Returns:
        QSS stylesheet string.
    """
    # Default padding if not provided (used for inner text margins in apply_spinbox_styling)
    if padding is None:
        padding = [8, 6]
    
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
    
    # Base stylesheet
    stylesheet = (
        f"QSpinBox, QDoubleSpinBox {{"
        f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
        f"border-radius: {border_radius}px;"
        # Padding is applied on the inner QLineEdit to prevent vertical text clipping
        # that can occur when QSpinBox padding reduces the available text rect.
        f"padding: 0px;"
        f"font-family: \"{font_family}\";"
        f"font-size: {font_size}pt;"
        f"margin: 0px;"
        f"}}"
        f"QSpinBox:focus, QDoubleSpinBox:focus {{"
        f"border: {border_width}px solid rgb({focus_border_color[0]}, {focus_border_color[1]}, {focus_border_color[2]});"
        f"}}"
        f"QSpinBox:disabled, QDoubleSpinBox:disabled {{"
        f"background-color: rgb({disabled_bg[0]}, {disabled_bg[1]}, {disabled_bg[2]});"
        f"color: rgb({disabled_text[0]}, {disabled_text[1]}, {disabled_text[2]});"
        f"}}"
    )

    # Inner QLineEdit must be styled explicitly when the spin box uses QSS; otherwise
    # some platforms accept the wheel but ignore keyboard input. Transparent fill lets
    # the outer spin box background show through.
    # Do not rely on QSS padding here: on macOS it often does not inset text (esp. left edge).
    # apply_spinbox_styling applies QLineEdit.setTextMargins from the same padding values.
    stylesheet += (
        f"QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{"
        f"background-color: transparent;"
        f"border: none;"
        f"padding: 0px;"
        f"margin: 0px;"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"font-family: \"{font_family}\";"
        f"font-size: {font_size}pt;"
        f"}}"
    )

    return stylesheet


def apply_spinbox_styling(
    spinboxes: List,
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
    disabled_brightness_factor: float = 0.5,
    hide_buttons: bool = True,
    minimum_height: int = 0,
) -> None:
    """Apply styling to QSpinBox and QDoubleSpinBox widgets.
    
    Args:
        spinboxes: List of QSpinBox or QDoubleSpinBox widgets to style.
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
        disabled_brightness_factor: Brightness factor for disabled state (default: 0.5).
        hide_buttons: Whether to hide up/down buttons (default: True).
        minimum_height: If > 0, set ``setMinimumHeight`` on each spin box (helps Linux/Fusion layout).
    """
    eff_padding = padding if padding is not None else [8, 6]
    stylesheet = generate_spinbox_stylesheet(
        config, text_color, font_family, font_size, bg_color, border_color,
        focus_border_color, border_width, border_radius, eff_padding,
        disabled_brightness_factor,
    )
    margins = _inner_line_edit_text_margins(eff_padding)
    
    for spinbox in spinboxes:
        if hide_buttons:
            spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        else:
            spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        spinbox.setStyleSheet(stylesheet)
        if minimum_height > 0:
            spinbox.setMinimumHeight(minimum_height)
        le = spinbox.lineEdit()
        if le is not None:
            le.setReadOnly(False)
            le.setTextMargins(*margins)

