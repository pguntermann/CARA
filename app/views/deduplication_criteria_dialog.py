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
from PyQt6.QtGui import QColor, QPalette
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum


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
        # Set spacing to 0 to disable automatic spacing - we'll use explicit spacing instead
        layout.setSpacing(0)
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
        self.mode_combo = QComboBox()
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
        
        layout.addSpacing(self.section_spacing)
        
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
        
        # Add spacing before buttons
        layout.addSpacing(self.section_spacing)
        layout.addLayout(button_layout)
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json to all UI elements."""
        # Get inputs config for combo box styling
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('deduplication_criteria', {})
        inputs_config = dialog_config.get('inputs', {})
        
        # Apply button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        buttons = list(self.findChildren(QPushButton))
        if buttons:
            StyleManager.style_buttons(
                buttons,
                self.config,
                list(self.bg_color),
                list(self.border_color),
                min_width=self.button_width,
                min_height=self.button_height
            )
        
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
        
        # Apply combobox styling using StyleManager
        # Get selection colors from config (use defaults if not available)
        selection_bg = inputs_config.get('selection_background_color', [70, 90, 130])
        selection_text = inputs_config.get('selection_text_color', [240, 240, 240])
        
        from app.views.style import StyleManager
        
        # Get focus border color for combobox
        focus_border_color = inputs_config.get('focus_border_color', [0, 120, 212])
        
        # Apply styling to combobox
        StyleManager.style_comboboxes(
            [self.mode_combo],
            self.config,
            self.input_text_color,
            self.input_font_family,
            self.input_font_size,
            self.input_bg_color,
            self.input_border_color,
            focus_border_color,
            selection_bg,
            selection_text,
            border_width=1,
            border_radius=self.input_border_radius,
            padding=self.input_padding
        )
        
        # Apply checkbox styling using StyleManager
        from pathlib import Path
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        
        # Use input border and background colors for checkbox indicator
        input_bg_color = self.input_bg_color
        input_border_color = self.input_border_color
        
        # Get all checkboxes and apply styling
        checkboxes = self.findChildren(QCheckBox)
        StyleManager.style_checkboxes(
            checkboxes,
            self.config,
            self.checkbox_text_color,
            self.label_font_family,  # Use label font family for checkboxes
            self.checkbox_font_size,
            input_bg_color,
            input_border_color,
            checkmark_path
        )
        
        # Group box styling - use StyleManager
        # Read values from dialog's groups config, or use unified defaults (pass None)
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('deduplication_criteria', {})
        groups_config = dialog_config.get('groups', {})
        
        group_boxes = list(self.findChildren(QGroupBox))
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=self.border_color,
                border_width=groups_config.get('border_width'),  # None = use unified default
                border_radius=groups_config.get('border_radius'),  # None = use unified default
                bg_color=groups_config.get('background_color'),  # None = use unified default
                margin_top=self.group_margin_top,
                padding_top=self.group_padding_top,
                title_font_family=self.group_title_font_family,
                title_font_size=self.group_title_font_size,
                title_color=self.group_title_color,
                title_left=groups_config.get('title_left'),  # None = use unified default
                title_padding=groups_config.get('title_padding')  # None = use unified default
            )
    
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
