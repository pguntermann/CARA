"""Style manager for applying consistent UI element styling."""

from pathlib import Path
from typing import Dict, Any, List
from PyQt6.QtWidgets import QScrollArea, QCheckBox, QComboBox

from app.views.style.scrollbar import (
    apply_scrollbar_styling,
    apply_table_scrollbar_styling,
    apply_table_view_scrollbar_styling
)
from app.views.style.checkbox import apply_checkbox_styling
from app.views.style.combobox import apply_combobox_styling


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

