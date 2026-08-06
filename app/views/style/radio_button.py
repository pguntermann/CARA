"""Radio button styling utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List

from PyQt6.QtWidgets import QRadioButton
from PyQt6.QtGui import QPalette, QColor

from app.utils.path_resolver import get_app_resource_path


def _qss_url(path: Path) -> str:
    return str(path).replace("\\", "/") if path.is_file() else ""


def generate_radio_button_stylesheet(
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    spacing: int = None,
) -> str:
    """Generate QSS stylesheet for radio buttons including indicators.

    Explicit ``::indicator`` rules are required: once any stylesheet is set on a
    ``QRadioButton``, Qt stops using the native indicator painter. Without these
    rules, Linux (Fusion) often draws checked and unchecked as the same solid
    disc — especially on light themes.

    Checked/unchecked artwork comes from theme-specific SVGs under
    ``ui.styles.radio_button.indicator_svg_path`` (same pattern as chess pieces).
    """
    styles_config = config.get('ui', {}).get('styles', {})
    radio_button_config = styles_config.get('radio_button', {})

    if spacing is None:
        spacing = radio_button_config.get('spacing', 5)

    indicator_width = int(radio_button_config.get('indicator_width', 13))
    indicator_height = int(radio_button_config.get('indicator_height', 13))
    margin_top = int(radio_button_config.get('margin_top', 2))
    margin_bottom = int(radio_button_config.get('margin_bottom', 2))

    svg_dir = radio_button_config.get(
        'indicator_svg_path',
        'app/resources/icons/radio/default',
    )
    svg_root = get_app_resource_path(str(svg_dir))
    unchecked_url = _qss_url(svg_root / 'unchecked.svg')
    checked_url = _qss_url(svg_root / 'checked.svg')

    stylesheet = (
        f"QRadioButton {{"
        f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        f"font-family: \"{font_family}\";"
        f"font-size: {font_size}pt;"
        f"spacing: {spacing}px;"
        f"margin-top: {margin_top}px;"
        f"margin-bottom: {margin_bottom}px;"
        f"background-color: transparent;"
        f"}}"
        f"QRadioButton::indicator {{"
        f"width: {indicator_width}px;"
        f"height: {indicator_height}px;"
        f"border: none;"
        f"background-color: transparent;"
        f"image: url({unchecked_url});"
        f"}}"
        f"QRadioButton::indicator:checked {{"
        f"image: url({checked_url});"
        f"}}"
    )

    return stylesheet


def apply_radio_button_styling(
    radio_buttons: List[QRadioButton],
    config: Dict[str, Any],
    text_color: List[int],
    font_family: str,
    font_size: float,
    spacing: int = None,
) -> None:
    """Apply styling to a list of radio buttons.

    Args:
        radio_buttons: List of QRadioButton widgets to style.
        config: Configuration dictionary.
        text_color: Text color as [R, G, B].
        font_family: Font family name.
        font_size: Font size in points.
        spacing: Spacing between indicator and label in pixels. If None, reads from config.
    """
    if not radio_buttons:
        return

    radio_button_style = generate_radio_button_stylesheet(
        config, text_color, font_family, font_size, spacing,
    )

    for radio_button in radio_buttons:
        radio_button.setStyleSheet(radio_button_style)

        # Also set palette to ensure color is applied (macOS sometimes ignores stylesheet)
        palette = radio_button.palette()
        palette.setColor(
            radio_button.foregroundRole(),
            QColor(text_color[0], text_color[1], text_color[2]),
        )
        radio_button.setPalette(palette)
        radio_button.update()
