"""Style manager for applying consistent UI element styling."""

from pathlib import Path
from typing import Dict, Any, List
from PyQt6.QtWidgets import QScrollArea, QCheckBox, QComboBox, QRadioButton, QPushButton

from app.views.style.scrollbar import (
    apply_scrollbar_styling,
    apply_table_scrollbar_styling,
    apply_table_view_scrollbar_styling
)
from app.views.style.checkbox import apply_checkbox_styling
from app.views.style.combobox import apply_combobox_styling
from app.views.style.radio_button import apply_radio_button_styling
from app.views.style.button import apply_button_styling


class StyleManager:
    """Centralized style manager for UI elements."""
    
    @staticmethod
    def style_scroll_area(
        scroll_area: QScrollArea,
        config: Dict[str, Any],
        bg_color: List[int],
        border_color: List[int],
        border_radius: int = 3
    ) -> None:
        """Apply scrollbar styling to a QScrollArea.
        
        Args:
            scroll_area: The QScrollArea to style.
            config: Configuration dictionary.
            bg_color: Background color as [R, G, B].
            border_color: Border color as [R, G, B].
            border_radius: Border radius for scroll area container (default: 3).
        """
        apply_scrollbar_styling(scroll_area, config, bg_color, border_color, border_radius)
    
    @staticmethod
    def style_table_scrollbar(
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
        apply_table_scrollbar_styling(table_widget, config, bg_color, border_color, table_style)
    
    @staticmethod
    def style_table_view_scrollbar(
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
        apply_table_view_scrollbar_styling(table_view, config, bg_color, border_color, table_style)
    
    @staticmethod
    def style_checkboxes(
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
        apply_checkbox_styling(
            checkboxes, config, text_color, font_family, font_size,
            bg_color, border_color, checkmark_path
        )
    
    @staticmethod
    def style_comboboxes(
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
        apply_combobox_styling(
            comboboxes, config, text_color, font_family, font_size,
            bg_color, border_color, focus_border_color, selection_bg_color,
            selection_text_color, border_width, border_radius, padding, editable
        )
    
    @staticmethod
    def style_radio_buttons(
        radio_buttons: List[QRadioButton],
        config: Dict[str, Any],
        text_color: List[int] = None,
        font_family: str = None,
        font_size: float = None,
        spacing: int = None
    ) -> None:
        """Apply radio button styling to a list of radio buttons.
        
        Args:
            radio_buttons: List of QRadioButton widgets to style.
            config: Configuration dictionary.
            text_color: Text color as [R, G, B]. If None, reads from centralized config.
            font_family: Font family name. If None, reads from centralized config.
            font_size: Font size in points. If None, reads from centralized config (with DPI scaling).
            spacing: Spacing between indicator and label in pixels. If None, reads from centralized config.
        """
        from app.utils.font_utils import resolve_font_family, scale_font_size
        
        # Get unified config values if parameters are not provided
        styles_config = config.get('ui', {}).get('styles', {})
        radio_button_config = styles_config.get('radio_button', {})
        
        if text_color is None:
            text_color = radio_button_config.get('text_color', [200, 200, 200])
        if font_family is None:
            font_family_raw = radio_button_config.get('font_family', 'Helvetica Neue')
            font_family = resolve_font_family(font_family_raw)
        if font_size is None:
            font_size_raw = radio_button_config.get('font_size', 11)
            font_size = scale_font_size(font_size_raw)
        if spacing is None:
            spacing = radio_button_config.get('spacing', 5)
        
        apply_radio_button_styling(
            radio_buttons, config, text_color, font_family, font_size, spacing
        )
    
    @staticmethod
    def style_buttons(
        buttons: List[QPushButton],
        config: Dict[str, Any],
        bg_color: List[int],
        border_color: List[int],
        text_color: List[int] = None,
        font_family: str = None,
        font_size: float = None,
        border_radius: int = None,
        padding: int = None,
        background_offset: int = None,
        hover_background_offset: int = None,
        pressed_background_offset: int = None,
        min_width: int = None,
        min_height: int = None
    ) -> None:
        """Apply button styling to a list of buttons.
        
        Args:
            buttons: List of QPushButton widgets to style.
            config: Configuration dictionary.
            bg_color: Base background color as [R, G, B] (from dialog/view config).
            border_color: Border color as [R, G, B] (from dialog/view config).
            text_color: Text color as [R, G, B]. If None, reads from centralized config.
            font_family: Font family name. If None, reads from centralized config (with DPI scaling).
            font_size: Font size in points. If None, reads from centralized config (with DPI scaling).
            border_radius: Border radius in pixels. If None, reads from centralized config.
            padding: Padding in pixels. If None, reads from centralized config.
            background_offset: Background color offset for normal state. If None, reads from centralized config.
            hover_background_offset: Background color offset for hover state. If None, reads from centralized config.
            pressed_background_offset: Background color offset for pressed state. If None, reads from centralized config.
            min_width: Minimum width in pixels. If None, not included in stylesheet.
            min_height: Minimum height in pixels. If None, not included in stylesheet.
        
        Note:
            - All buttons use unified font and font size from centralized config
            - Individual buttons can override height/width after styling via setMinimumHeight()/setMinimumWidth()
        """
        from app.utils.font_utils import resolve_font_family, scale_font_size
        
        # Get unified config values if parameters are not provided
        styles_config = config.get('ui', {}).get('styles', {})
        button_config = styles_config.get('button', {})
        
        if text_color is None:
            text_color = button_config.get('text_color', [200, 200, 200])
        if font_family is None:
            font_family_raw = button_config.get('font_family', 'Helvetica Neue')
            font_family = resolve_font_family(font_family_raw)
        if font_size is None:
            font_size_raw = button_config.get('font_size', 11)
            font_size = scale_font_size(font_size_raw)
        if border_radius is None:
            border_radius = button_config.get('border_radius', 3)
        if padding is None:
            padding = button_config.get('padding', 5)
        if background_offset is None:
            background_offset = button_config.get('background_offset', 20)
        if hover_background_offset is None:
            hover_background_offset = button_config.get('hover_background_offset', 30)
        if pressed_background_offset is None:
            pressed_background_offset = button_config.get('pressed_background_offset', 10)
        
        apply_button_styling(
            buttons, config, text_color, font_family, font_size,
            bg_color, border_color, background_offset,
            hover_background_offset, pressed_background_offset,
            border_radius, padding, min_width, min_height
        )

