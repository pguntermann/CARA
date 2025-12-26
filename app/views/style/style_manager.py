"""Style manager for applying consistent UI element styling."""

from typing import Dict, Any, List
from PyQt6.QtWidgets import QScrollArea

from app.views.style.scrollbar import (
    apply_scrollbar_styling,
    apply_table_scrollbar_styling,
    apply_table_view_scrollbar_styling
)


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

