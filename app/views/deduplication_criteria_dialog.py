"""Deduplication criteria dialog for selecting how duplicate games are identified."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QCheckBox,
    QComboBox,
    QSizePolicy,
    QSpacerItem,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette, QWheelEvent
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events to prevent accidental value changes."""
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Override wheel event to ignore it completely."""
        event.ignore()
    
    def showPopup(self) -> None:
        """Override showPopup to apply styling to popup window on macOS."""
        super().showPopup()
        # Access view after popup is shown to ensure it's fully initialized
        view = self.view()
        if view:
            # Get background and text colors from combo box palette (set via stylesheet)
            combo_palette = self.palette()
            bg_color = combo_palette.color(self.backgroundRole())
            text_color = combo_palette.color(self.foregroundRole())
            
            # Set viewport background to remove white borders
            viewport = view.viewport()
            if viewport:
                viewport.setAutoFillBackground(True)
                viewport_palette = viewport.palette()
                viewport_palette.setColor(viewport.backgroundRole(), bg_color)
                viewport.setPalette(viewport_palette)
            
            # Also set view palette to ensure consistency
            view_palette = view.palette()
            view_palette.setColor(view.backgroundRole(), bg_color)
            view_palette.setColor(view.foregroundRole(), text_color)
            view.setPalette(view_palette)
            view.setAutoFillBackground(True)
            
            # CRITICAL: Fix the popup window itself (QFrame) - this is where the white borders come from
            popup_window = view.window()
            if popup_window and popup_window != self.window():
                popup_window.setAutoFillBackground(True)
                popup_palette = popup_window.palette()
                # Set all background-related roles to the dark color
                popup_palette.setColor(popup_window.backgroundRole(), bg_color)
                popup_palette.setColor(popup_palette.ColorRole.Base, bg_color)
                popup_palette.setColor(popup_palette.ColorRole.Window, bg_color)
                popup_palette.setColor(popup_palette.ColorRole.Button, bg_color)
                popup_window.setPalette(popup_palette)


class DeduplicationMode(Enum):
    """Deduplication matching modes."""
    EXACT_PGN = "exact_pgn"
    MOVES_ONLY = "moves_only"
    NORMALIZED_PGN = "normalized_pgn"
    HEADER_BASED = "header_based"


class DeduplicationCriteriaDialog(QDialog):
    """Dialog for selecting deduplication criteria."""
    
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        """Initialize the deduplication criteria dialog.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.selected_mode: Optional[DeduplicationMode] = None
        self.selected_headers: List[str] = []
        
        # Load config
        self._load_config()
        
        # Setup UI
        self._setup_ui()
        
        # Apply styling
        self._apply_styling()
        
        # Set defaults
        self._set_defaults()
        
        # Update description and customization area based on initial selection
        self._on_mode_changed()
        
        self.setWindowTitle("Deduplication Criteria")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('deduplication_criteria', {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get('width', 600)
        self.dialog_height = dialog_config.get('height', 450)
        
        # Background and colors
        self.bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.border_color = dialog_config.get('border_color', [60, 60, 65])
        self.text_color = dialog_config.get('text_color', [200, 200, 200])
        from app.utils.font_utils import scale_font_size
        self.font_size = scale_font_size(dialog_config.get('font_size', 11))
        
        # Layout
        layout_config = dialog_config.get('layout', {})
        self.layout_spacing = layout_config.get('spacing', 10)
        self.layout_margins = layout_config.get('margins', [15, 15, 15, 15])
        self.section_spacing = layout_config.get('section_spacing', 15)
        
        # Buttons
        buttons_config = dialog_config.get('buttons', {})
        self.button_width = buttons_config.get('width', 120)
        self.button_height = buttons_config.get('height', 30)
        self.button_border_radius = buttons_config.get('border_radius', 3)
        self.button_padding = buttons_config.get('padding', 5)
        self.button_bg_offset = buttons_config.get('background_offset', 20)
        self.button_hover_offset = buttons_config.get('hover_background_offset', 30)
        self.button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        self.button_spacing = buttons_config.get('spacing', 10)
        
        # Labels
        labels_config = dialog_config.get('labels', {})
        self.label_font_family = labels_config.get('font_family', 'Helvetica Neue')
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.label_font_size = scale_font_size(labels_config.get('font_size', 11))
        self.label_text_color = labels_config.get('text_color', [200, 200, 200])
        
        # Description text
        description_config = dialog_config.get('description', {})
        self.description_font_family = description_config.get('font_family', 'Helvetica Neue')
        from app.utils.font_utils import scale_font_size
        self.description_font_size = scale_font_size(description_config.get('font_size', 10))
        self.description_text_color = description_config.get('text_color', [180, 180, 180])
        self.description_margin_top = description_config.get('margin_top', 8)
        
        # Inputs (for combo box)
        inputs_config = dialog_config.get('inputs', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        input_font_family_raw = inputs_config.get('font_family', 'Cascadia Mono')
        self.input_font_family = resolve_font_family(input_font_family_raw)
        self.input_font_size = scale_font_size(inputs_config.get('font_size', 11))
        self.input_text_color = inputs_config.get('text_color', [240, 240, 240])
        self.input_bg_color = inputs_config.get('background_color', [30, 30, 35])
        self.input_border_color = inputs_config.get('border_color', [60, 60, 65])
        self.input_border_radius = inputs_config.get('border_radius', 3)
        self.input_padding = inputs_config.get('padding', [8, 6])
        
        # Groups
        groups_config = dialog_config.get('groups', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.group_title_font_family = resolve_font_family(groups_config.get('title_font_family', 'Helvetica Neue'))
        self.group_title_font_size = scale_font_size(groups_config.get('title_font_size', 11))
        self.group_title_color = groups_config.get('title_color', [240, 240, 240])
        self.group_content_margins = groups_config.get('content_margins', [10, 15, 10, 10])
        self.group_margin_top = groups_config.get('margin_top', 10)
        self.group_padding_top = groups_config.get('padding_top', 5)
        
        # Checkboxes
        checkbox_config = dialog_config.get('checkboxes', {})
        self.checkbox_spacing = checkbox_config.get('spacing', 5)
        self.checkbox_text_color = checkbox_config.get('text_color', [200, 200, 200])
        from app.utils.font_utils import scale_font_size
        self.checkbox_font_size = scale_font_size(checkbox_config.get('font_size', 11))
        
        # Mode options and descriptions
        modes_config = dialog_config.get('modes', {})
        self.mode_options = modes_config.get('options', [
            {'value': 'exact_pgn', 'label': 'Exact PGN Match'},
            {'value': 'moves_only', 'label': 'Moves Only'},
            {'value': 'normalized_pgn', 'label': 'Normalized PGN Match'},
            {'value': 'header_based', 'label': 'Header Based Match'}
        ])
        self.mode_descriptions = modes_config.get('descriptions', {
            'exact_pgn': 'Match games with identical PGN strings (headers + moves). This is the most strict matching mode.',
            'moves_only': 'Match games with identical moves, ignoring header information. Useful when the same game appears with different metadata.',
            'normalized_pgn': 'Match games after removing comments, variations, annotations, and extra whitespace. Useful when PGN formatting differs.',
            'header_based': 'Match games based on selected header fields. Useful when you want to identify games by specific metadata rather than moves.'
        })
        
        # Default mode
        self.default_mode = dialog_config.get('default_mode', 'exact_pgn')
        
        # Available header fields for header-based matching
        self.header_fields = dialog_config.get('header_fields', ['White', 'Black', 'Date', 'Result', 'Event', 'Site', 'Round'])
        self.default_headers = dialog_config.get('default_headers', ['White', 'Black', 'Date', 'Result'])
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Set dialog size (fixed, non-resizable)
        self.setFixedSize(self.dialog_width, self.dialog_height)
        
        # Set background color
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(self.bg_color[0], self.bg_color[1], self.bg_color[2]))
        self.setPalette(palette)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(self.layout_spacing)
        layout.setContentsMargins(self.layout_margins[0], self.layout_margins[1], self.layout_margins[2], self.layout_margins[3])
        
        # Matching Mode group
        mode_group = QGroupBox("Matching Mode")
        mode_group_layout = QVBoxLayout(mode_group)
        mode_group_layout.setSpacing(self.layout_spacing)
        mode_group_layout.setContentsMargins(
            self.group_content_margins[0], self.group_content_margins[1],
            self.group_content_margins[2], self.group_content_margins[3]
        )
        
        # Combo box for matching modes
        self.mode_combo = NoWheelComboBox()
        for option in self.mode_options:
            self.mode_combo.addItem(option['label'], option['value'])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_group_layout.addWidget(self.mode_combo)
        
        # Description label (below combo box)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        mode_group_layout.addWidget(self.description_label)
        
        layout.addWidget(mode_group)
        
        # Customization area (for header-based mode)
        self.customization_group = QGroupBox("Options")
        customization_layout = QVBoxLayout(self.customization_group)
        customization_layout.setSpacing(self.checkbox_spacing)
        customization_layout.setContentsMargins(
            self.group_content_margins[0], self.group_content_margins[1],
            self.group_content_margins[2], self.group_content_margins[3]
        )
        
        # Header fields checkboxes
        header_label = QLabel("Select header fields to match:")
        customization_layout.addWidget(header_label)
        
        self.header_checkboxes: Dict[str, QCheckBox] = {}
        for header_field in self.header_fields:
            checkbox = QCheckBox(header_field)
            self.header_checkboxes[header_field] = checkbox
            customization_layout.addWidget(checkbox)
        
        self.customization_group.setVisible(False)
        layout.addWidget(self.customization_group)
        
        # Dynamic spacer to fill space when customization is hidden
        # This spacer will be adjusted when mode changes
        self.spacer_item = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        layout.addItem(self.spacer_item)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(self.button_spacing)
        
        button_layout.addStretch()
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        # OK button
        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._on_ok_clicked)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json to all UI elements."""
        # Get inputs config for combo box styling
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('deduplication_criteria', {})
        inputs_config = dialog_config.get('inputs', {})
        
        # Button styling
        button_style = (
            f"QPushButton {{"
            f"min-width: {self.button_width}px;"
            f"min-height: {self.button_height}px;"
            f"background-color: rgb({self.bg_color[0] + self.button_bg_offset}, {self.bg_color[1] + self.button_bg_offset}, {self.bg_color[2] + self.button_bg_offset});"
            f"border: 1px solid rgb({self.border_color[0]}, {self.border_color[1]}, {self.border_color[2]});"
            f"border-radius: {self.button_border_radius}px;"
            f"color: rgb({self.text_color[0]}, {self.text_color[1]}, {self.text_color[2]});"
            f"font-size: {self.font_size}pt;"
            f"padding: {self.button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({self.bg_color[0] + self.button_hover_offset}, {self.bg_color[1] + self.button_hover_offset}, {self.bg_color[2] + self.button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({self.bg_color[0] + self.button_pressed_offset}, {self.bg_color[1] + self.button_pressed_offset}, {self.bg_color[2] + self.button_pressed_offset});"
            f"}}"
        )
        
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)
        
        # Label styling - apply to ALL labels to prevent macOS theme override
        label_style = (
            f"QLabel {{"
            f"font-family: \"{self.label_font_family}\";"
            f"font-size: {self.label_font_size}pt;"
            f"color: rgb({self.label_text_color[0]}, {self.label_text_color[1]}, {self.label_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        
        # Apply stylesheet and palette to all labels to ensure macOS doesn't override
        # Group box titles are styled via QGroupBox::title, not QLabel, so we can style all QLabels
        for label in self.findChildren(QLabel):
            # Apply stylesheet
            label.setStyleSheet(label_style)
            # Also set palette to ensure color is applied (macOS sometimes ignores stylesheet)
            label_palette = label.palette()
            label_palette.setColor(label.foregroundRole(), QColor(self.label_text_color[0], self.label_text_color[1], self.label_text_color[2]))
            label.setPalette(label_palette)
            # Force update to ensure styling is applied
            label.update()
        
        # Description label styling (override for description)
        description_style = (
            f"QLabel {{"
            f"font-family: \"{self.description_font_family}\";"
            f"font-size: {self.description_font_size}pt;"
            f"color: rgb({self.description_text_color[0]}, {self.description_text_color[1]}, {self.description_text_color[2]});"
            f"margin-top: {self.description_margin_top}px;"
            f"background-color: transparent;"
            f"}}"
        )
        self.description_label.setStyleSheet(description_style)
        # Set palette to prevent macOS override
        description_palette = self.description_label.palette()
        description_palette.setColor(self.description_label.foregroundRole(), QColor(self.description_text_color[0], self.description_text_color[1], self.description_text_color[2]))
        self.description_label.setPalette(description_palette)
        self.description_label.update()
        
        # Combo box styling (using input styling)
        # Get selection colors from config (use defaults if not available)
        selection_bg = inputs_config.get('selection_background_color', [70, 90, 130])
        selection_text = inputs_config.get('selection_text_color', [240, 240, 240])
        
        combo_style = (
            f"QComboBox {{"
            f"font-family: \"{self.input_font_family}\";"
            f"font-size: {self.input_font_size}pt;"
            f"color: rgb({self.input_text_color[0]}, {self.input_text_color[1]}, {self.input_text_color[2]});"
            f"background-color: rgb({self.input_bg_color[0]}, {self.input_bg_color[1]}, {self.input_bg_color[2]});"
            f"border: 1px solid rgb({self.input_border_color[0]}, {self.input_border_color[1]}, {self.input_border_color[2]});"
            f"border-radius: {self.input_border_radius}px;"
            f"padding: {self.input_padding[1]}px {self.input_padding[0]}px;"
            f"}}"
            f"QComboBox:hover {{"
            f"border: 1px solid rgb({self.input_border_color[0] + 20}, {self.input_border_color[1] + 20}, {self.input_border_color[2] + 20});"
            f"}}"
            f"QComboBox QAbstractItemView {{"
            f"background-color: rgb({self.input_bg_color[0]}, {self.input_bg_color[1]}, {self.input_bg_color[2]});"
            f"color: rgb({self.input_text_color[0]}, {self.input_text_color[1]}, {self.input_text_color[2]});"
            f"selection-background-color: rgb({selection_bg[0]}, {selection_bg[1]}, {selection_bg[2]});"
            f"selection-color: rgb({selection_text[0]}, {selection_text[1]}, {selection_text[2]});"
            f"border: 1px solid rgb({self.input_border_color[0]}, {self.input_border_color[1]}, {self.input_border_color[2]});"
            f"}}"
        )
        self.mode_combo.setStyleSheet(combo_style)
        
        # Fix combo box palette roles that are white (Base and Button)
        combo_palette = self.mode_combo.palette()
        combo_palette.setColor(combo_palette.ColorRole.Base, QColor(self.input_bg_color[0], self.input_bg_color[1], self.input_bg_color[2]))
        combo_palette.setColor(combo_palette.ColorRole.Button, QColor(self.input_bg_color[0], self.input_bg_color[1], self.input_bg_color[2]))
        self.mode_combo.setPalette(combo_palette)
        
        # Set palette on combo box view to prevent macOS override
        view = self.mode_combo.view()
        if view:
            view_palette = view.palette()
            view_palette.setColor(view.backgroundRole(), QColor(self.input_bg_color[0], self.input_bg_color[1], self.input_bg_color[2]))
            view_palette.setColor(view.foregroundRole(), QColor(self.input_text_color[0], self.input_text_color[1], self.input_text_color[2]))
            view_palette.setColor(QPalette.ColorRole.Highlight, QColor(selection_bg[0], selection_bg[1], selection_bg[2]))
            view_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(selection_text[0], selection_text[1], selection_text[2]))
            view.setPalette(view_palette)
            view.setAutoFillBackground(True)
        
        # Checkbox styling
        checkbox_style = (
            f"QCheckBox {{"
            f"font-size: {self.checkbox_font_size}pt;"
            f"color: rgb({self.checkbox_text_color[0]}, {self.checkbox_text_color[1]}, {self.checkbox_text_color[2]});"
            f"spacing: {self.checkbox_spacing}px;"
            f"}}"
        )
        
        for checkbox in self.findChildren(QCheckBox):
            checkbox.setStyleSheet(checkbox_style)
        
        # Group box styling
        group_style = (
            f"QGroupBox {{"
            f"border: 1px solid rgb({self.border_color[0]}, {self.border_color[1]}, {self.border_color[2]});"
            f"border-radius: 3px;"
            f"margin-top: {self.group_margin_top}px;"
            f"padding-top: {self.group_padding_top}px;"
            f"}}"
            f"QGroupBox::title {{"
            f"subcontrol-origin: margin;"
            f"subcontrol-position: top left;"
            f"padding-left: 5px;"
            f"padding-right: 5px;"
            f"padding-top: {self.group_padding_top}px;"
            f"font-family: \"{self.group_title_font_family}\";"
            f"font-size: {self.group_title_font_size}pt;"
            f"color: rgb({self.group_title_color[0]}, {self.group_title_color[1]}, {self.group_title_color[2]});"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
    
    def _set_defaults(self) -> None:
        """Set default values."""
        # Set default combo box selection based on config
        default_index = 0
        for idx, option in enumerate(self.mode_options):
            if option['value'] == self.default_mode:
                default_index = idx
                break
        self.mode_combo.setCurrentIndex(default_index)
        
        # Set default header checkboxes
        for header_field in self.default_headers:
            if header_field in self.header_checkboxes:
                self.header_checkboxes[header_field].setChecked(True)
    
    def _on_mode_changed(self) -> None:
        """Handle mode combo box change.
        
        Updates description text and shows/hides customization area.
        Adjusts spacer to fill empty space appropriately.
        """
        current_value = self.mode_combo.currentData()
        if not current_value:
            return
        
        # Update description
        description = self.mode_descriptions.get(current_value, '')
        self.description_label.setText(description)
        
        # Show/hide customization area based on mode
        if current_value == 'header_based':
            self.customization_group.setVisible(True)
            # When customization is visible, use minimal spacer
            self.spacer_item.changeSize(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        else:
            self.customization_group.setVisible(False)
            # When customization is hidden, expand spacer to fill space
            self.spacer_item.changeSize(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
    
    def _on_ok_clicked(self) -> None:
        """Handle OK button click."""
        current_value = self.mode_combo.currentData()
        if not current_value:
            return
        
        # Map value to enum
        mode_map = {
            'exact_pgn': DeduplicationMode.EXACT_PGN,
            'moves_only': DeduplicationMode.MOVES_ONLY,
            'normalized_pgn': DeduplicationMode.NORMALIZED_PGN,
            'header_based': DeduplicationMode.HEADER_BASED
        }
        
        self.selected_mode = mode_map.get(current_value)
        if not self.selected_mode:
            return
        
        # Collect selected headers if header-based mode
        if self.selected_mode == DeduplicationMode.HEADER_BASED:
            self.selected_headers = [field for field, checkbox in self.header_checkboxes.items() if checkbox.isChecked()]
            # Validate: at least one header must be selected
            if not self.selected_headers:
                from app.views.message_dialog import MessageDialog
                MessageDialog.show_warning(
                    self.config,
                    "Invalid Selection",
                    "Please select at least one header field for header-based matching.",
                    self
                )
                return
        
        self.accept()
    
    def get_criteria(self) -> Tuple[DeduplicationMode, List[str]]:
        """Get the selected deduplication criteria.
        
        Returns:
            Tuple of (mode, headers) where headers is only used for HEADER_BASED mode.
        """
        return (self.selected_mode, self.selected_headers)
