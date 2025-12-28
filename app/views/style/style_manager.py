"""Style manager for applying consistent UI element styling."""

from pathlib import Path
from typing import Dict, Any, List
from PyQt6.QtWidgets import QScrollArea, QCheckBox, QComboBox, QRadioButton, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit, QGroupBox, QTextEdit

from app.views.style.scrollbar import (
    apply_scrollbar_styling,
    apply_table_scrollbar_styling,
    apply_table_view_scrollbar_styling,
    apply_text_edit_scrollbar_styling
)
from app.views.style.checkbox import apply_checkbox_styling
from app.views.style.combobox import apply_combobox_styling
from app.views.style.radio_button import apply_radio_button_styling
from app.views.style.button import apply_button_styling
from app.views.style.line_edit import apply_line_edit_styling
from app.views.style.spinbox import apply_spinbox_styling
from app.views.style.date_edit import apply_date_edit_styling
from app.views.style.group_box import apply_group_box_styling


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
    def style_text_edit_scrollbar(
        text_edit: QTextEdit,
        config: Dict[str, Any],
        bg_color: List[int],
        border_color: List[int],
        text_edit_style: str
    ) -> None:
        """Apply scrollbar styling to a QTextEdit.
        
        Args:
            text_edit: The QTextEdit to style.
            config: Configuration dictionary.
            bg_color: Background color as [R, G, B].
            border_color: Border color as [R, G, B].
            text_edit_style: Existing text edit stylesheet to append scrollbar styles to.
        """
        apply_text_edit_scrollbar_styling(text_edit, config, bg_color, border_color, text_edit_style)
    
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
    
    @staticmethod
    def style_line_edits(
        line_edits: List[QLineEdit],
        config: Dict[str, Any],
        text_color: List[int] = None,
        font_family: str = None,
        font_size: float = None,
        bg_color: List[int] = None,
        border_color: List[int] = None,
        focus_border_color: List[int] = None,
        border_width: int = None,
        border_radius: int = None,
        padding: List[int] = None,
        hover_border_offset: int = None,
        disabled_brightness_factor: float = None
    ) -> None:
        """Apply line edit styling to a list of QLineEdit widgets.
        
        Args:
            line_edits: List of QLineEdit widgets to style.
            config: Configuration dictionary.
            text_color: Text color as [R, G, B]. If None, reads from centralized config.
            font_family: Font family name. If None, reads from centralized config (with font resolution).
            font_size: Font size in points. If None, reads from centralized config (with DPI scaling).
            bg_color: Background color as [R, G, B]. If None, reads from centralized config.
            border_color: Border color as [R, G, B]. If None, reads from centralized config.
            focus_border_color: Focus border color as [R, G, B]. If None, reads from centralized config.
            border_width: Border width in pixels. If None, reads from centralized config.
            border_radius: Border radius in pixels. If None, reads from centralized config.
            padding: Padding as [horizontal, vertical] or [left, top, right, bottom]. If None, reads from centralized config.
            hover_border_offset: Brightness offset for hover border. If None, reads from centralized config.
            disabled_brightness_factor: Brightness factor for disabled state. If None, reads from centralized config.
        """
        from app.utils.font_utils import resolve_font_family, scale_font_size
        
        # Get unified config values if parameters are not provided
        styles_config = config.get('ui', {}).get('styles', {})
        line_edit_config = styles_config.get('line_edit', {})
        
        if text_color is None:
            text_color = line_edit_config.get('text_color', [200, 200, 200])
        if font_family is None:
            font_family_raw = line_edit_config.get('font_family', 'Helvetica Neue')
            font_family = resolve_font_family(font_family_raw)
        if font_size is None:
            font_size_raw = line_edit_config.get('font_size', 11)
            font_size = scale_font_size(font_size_raw)
        if bg_color is None:
            bg_color = line_edit_config.get('background_color', [45, 45, 50])
        if border_color is None:
            border_color = line_edit_config.get('border_color', [60, 60, 65])
        if focus_border_color is None:
            focus_border_color = line_edit_config.get('focus_border_color', [70, 90, 130])
        if border_width is None:
            border_width = line_edit_config.get('border_width', 1)
        if border_radius is None:
            border_radius = line_edit_config.get('border_radius', 3)
        if padding is None:
            padding = line_edit_config.get('padding', [8, 6])
        if hover_border_offset is None:
            hover_border_offset = line_edit_config.get('hover_border_offset', 20)
        if disabled_brightness_factor is None:
            disabled_brightness_factor = line_edit_config.get('disabled_brightness_factor', 0.5)
        
        apply_line_edit_styling(
            line_edits, config, text_color, font_family, font_size,
            bg_color, border_color, focus_border_color, border_width,
            border_radius, padding, hover_border_offset, disabled_brightness_factor
        )
    
    @staticmethod
    def style_spinboxes(
        spinboxes: List,
        config: Dict[str, Any],
        text_color: List[int] = None,
        font_family: str = None,
        font_size: float = None,
        bg_color: List[int] = None,
        border_color: List[int] = None,
        focus_border_color: List[int] = None,
        border_width: int = None,
        border_radius: int = None,
        padding: List[int] = None,
        disabled_brightness_factor: float = None,
        hide_buttons: bool = None
    ) -> None:
        """Apply spinbox styling to a list of QSpinBox and QDoubleSpinBox widgets.
        
        Args:
            spinboxes: List of QSpinBox or QDoubleSpinBox widgets to style.
            config: Configuration dictionary.
            text_color: Text color as [R, G, B]. If None, reads from centralized config.
            font_family: Font family name. If None, reads from centralized config (with font resolution).
            font_size: Font size in points. If None, reads from centralized config (with DPI scaling).
            bg_color: Background color as [R, G, B]. If None, reads from centralized config.
            border_color: Border color as [R, G, B]. If None, reads from centralized config.
            focus_border_color: Focus border color as [R, G, B]. If None, reads from centralized config.
            border_width: Border width in pixels. If None, reads from centralized config.
            border_radius: Border radius in pixels. If None, reads from centralized config.
            padding: Padding as [horizontal, vertical] or [left, top, right, bottom]. If None, reads from centralized config.
            disabled_brightness_factor: Brightness factor for disabled state. If None, reads from centralized config.
            hide_buttons: Whether to hide up/down buttons. If None, reads from centralized config.
        """
        from app.utils.font_utils import resolve_font_family, scale_font_size
        
        # Get unified config values if parameters are not provided
        styles_config = config.get('ui', {}).get('styles', {})
        spinbox_config = styles_config.get('spinbox', {})
        
        if text_color is None:
            text_color = spinbox_config.get('text_color', [200, 200, 200])
        if font_family is None:
            font_family_raw = spinbox_config.get('font_family', 'Helvetica Neue')
            font_family = resolve_font_family(font_family_raw)
        if font_size is None:
            font_size_raw = spinbox_config.get('font_size', 11)
            font_size = scale_font_size(font_size_raw)
        if bg_color is None:
            bg_color = spinbox_config.get('background_color', [45, 45, 50])
        if border_color is None:
            border_color = spinbox_config.get('border_color', [60, 60, 65])
        if focus_border_color is None:
            focus_border_color = spinbox_config.get('focus_border_color', [70, 90, 130])
        if border_width is None:
            border_width = spinbox_config.get('border_width', 1)
        if border_radius is None:
            border_radius = spinbox_config.get('border_radius', 3)
        if padding is None:
            padding = spinbox_config.get('padding', [8, 6])
        if disabled_brightness_factor is None:
            disabled_brightness_factor = spinbox_config.get('disabled_brightness_factor', 0.5)
        if hide_buttons is None:
            hide_buttons = spinbox_config.get('hide_buttons', True)
        
        apply_spinbox_styling(
            spinboxes, config, text_color, font_family, font_size,
            bg_color, border_color, focus_border_color, border_width,
            border_radius, padding, disabled_brightness_factor, hide_buttons
        )
    
    @staticmethod
    def style_date_edits(
        date_edits: List,
        config: Dict[str, Any],
        text_color: List[int] = None,
        font_family: str = None,
        font_size: float = None,
        bg_color: List[int] = None,
        border_color: List[int] = None,
        focus_border_color: List[int] = None,
        border_width: int = None,
        border_radius: int = None,
        padding: List[int] = None,
        disabled_brightness_factor: float = None
    ) -> None:
        """Apply date edit styling to a list of QDateEdit, QTimeEdit, and QDateTimeEdit widgets.
        
        Args:
            date_edits: List of QDateEdit, QTimeEdit, or QDateTimeEdit widgets to style.
            config: Configuration dictionary.
            text_color: Text color as [R, G, B]. If None, reads from centralized config.
            font_family: Font family name. If None, reads from centralized config (with font resolution).
            font_size: Font size in points. If None, reads from centralized config (with DPI scaling).
            bg_color: Background color as [R, G, B]. If None, reads from centralized config.
            border_color: Border color as [R, G, B]. If None, reads from centralized config.
            focus_border_color: Focus border color as [R, G, B]. If None, reads from centralized config.
            border_width: Border width in pixels. If None, reads from centralized config.
            border_radius: Border radius in pixels. If None, reads from centralized config.
            padding: Padding as [horizontal, vertical] or [left, top, right, bottom]. If None, reads from centralized config.
            disabled_brightness_factor: Brightness factor for disabled state. If None, reads from centralized config.
        """
        from app.utils.font_utils import resolve_font_family, scale_font_size
        
        # Get unified config values if parameters are not provided
        styles_config = config.get('ui', {}).get('styles', {})
        date_edit_config = styles_config.get('date_edit', {})
        
        if text_color is None:
            text_color = date_edit_config.get('text_color', [200, 200, 200])
        if font_family is None:
            font_family_raw = date_edit_config.get('font_family', 'Helvetica Neue')
            font_family = resolve_font_family(font_family_raw)
        if font_size is None:
            font_size_raw = date_edit_config.get('font_size', 11)
            font_size = scale_font_size(font_size_raw)
        if bg_color is None:
            bg_color = date_edit_config.get('background_color', [45, 45, 50])
        if border_color is None:
            border_color = date_edit_config.get('border_color', [60, 60, 65])
        if focus_border_color is None:
            focus_border_color = date_edit_config.get('focus_border_color', [70, 90, 130])
        if border_width is None:
            border_width = date_edit_config.get('border_width', 1)
        if border_radius is None:
            border_radius = date_edit_config.get('border_radius', 3)
        if padding is None:
            padding = date_edit_config.get('padding', [8, 6])
        if disabled_brightness_factor is None:
            disabled_brightness_factor = date_edit_config.get('disabled_brightness_factor', 0.5)
        
        apply_date_edit_styling(
            date_edits, config, text_color, font_family, font_size,
            bg_color, border_color, focus_border_color, border_width,
            border_radius, padding, disabled_brightness_factor
        )
    
    @staticmethod
    def style_group_boxes(
        group_boxes: List[QGroupBox],
        config: Dict[str, Any],
        border_color: List[int] = None,
        border_width: int = None,
        border_radius: int = None,
        bg_color: List[int] = None,
        margin_top: int = None,
        padding_top: int = None,
        title_font_family: str = None,
        title_font_size: float = None,
        title_font_weight: str = None,
        title_color: List[int] = None,
        title_left: int = None,
        title_padding: List[int] = None,
        content_margins: List[int] = None,
        use_transparent_palette: bool = False
    ) -> None:
        """Apply group box styling to a list of QGroupBox widgets.
        
        Args:
            group_boxes: List of QGroupBox widgets to style.
            config: Configuration dictionary.
            border_color: Border color as [R, G, B]. If None, reads from centralized config.
            border_width: Border width in pixels. If None, reads from centralized config.
            border_radius: Border radius in pixels. If None, reads from centralized config.
            bg_color: Background color as [R, G, B]. If None, reads from centralized config (may be transparent).
            margin_top: Top margin in pixels. If None, reads from centralized config.
            padding_top: Top padding in pixels. If None, reads from centralized config.
            title_font_family: Title font family name. If None, reads from centralized config (with font resolution).
            title_font_size: Title font size in points. If None, reads from centralized config (with DPI scaling).
            title_font_weight: Title font weight (e.g., 'bold', 'normal'). If None, reads from centralized config.
            title_color: Title text color as [R, G, B]. If None, reads from centralized config.
            title_left: Left offset for title in pixels. If None, reads from centralized config.
            title_padding: Title padding as [left, right] in pixels. If None, reads from centralized config.
            content_margins: Content margins as [left, top, right, bottom] for layout. If None, not set.
            use_transparent_palette: If True and bg_color is None/transparent, sets palette for transparent background (macOS).
        """
        from app.utils.font_utils import resolve_font_family, scale_font_size
        
        # Get unified config values if parameters are not provided
        styles_config = config.get('ui', {}).get('styles', {})
        group_box_config = styles_config.get('group_box', {})
        
        if border_color is None:
            border_color = group_box_config.get('border_color', [60, 60, 65])
        if border_width is None:
            border_width = group_box_config.get('border_width', 1)
        if border_radius is None:
            border_radius = group_box_config.get('border_radius', 5)
        if bg_color is None:
            bg_color_raw = group_box_config.get('background_color')
            # If None in config, use None (transparent), otherwise use the color
            bg_color = bg_color_raw if bg_color_raw is not None else None
        if margin_top is None:
            margin_top = group_box_config.get('margin_top', 10)
        if padding_top is None:
            padding_top = group_box_config.get('padding_top', 5)
        if title_font_family is None:
            title_font_family_raw = group_box_config.get('title_font_family', 'Helvetica Neue')
            title_font_family = resolve_font_family(title_font_family_raw)
        if title_font_size is None:
            title_font_size_raw = group_box_config.get('title_font_size', 11)
            title_font_size = scale_font_size(title_font_size_raw)
        if title_font_weight is None:
            title_font_weight = group_box_config.get('title_font_weight')
        if title_color is None:
            title_color = group_box_config.get('title_color', [240, 240, 240])
        if title_left is None:
            title_left = group_box_config.get('title_left', 10)
        if title_padding is None:
            title_padding = group_box_config.get('title_padding', [0, 5])
        
        apply_group_box_styling(
            group_boxes, config, border_color, border_width, border_radius,
            bg_color, margin_top, padding_top, title_font_family, title_font_size,
            title_font_weight, title_color, title_left, title_padding,
            content_margins, use_transparent_palette
        )

