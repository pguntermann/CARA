"""Annotation preferences dialog for configuring color palette and text font."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QGroupBox,
    QGridLayout,
    QSizePolicy,
    QColorDialog,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPalette, QPainter, QPen, QPixmap, QIcon, QFontDatabase
from typing import Dict, Any, List, Optional
from copy import deepcopy


class ColorSwatchButton(QPushButton):
    """Button that displays a color swatch and opens color picker on click."""
    
    def __init__(self, color: QColor, size: int, parent=None) -> None:
        """Initialize the color swatch button.
        
        Args:
            color: Initial color to display.
            size: Size of the swatch (width and height).
            parent: Parent widget.
        """
        super().__init__(parent)
        self._color = color
        self._size = size
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._update_icon()
    
    def set_color(self, color: QColor) -> None:
        """Set the color and update the icon.
        
        Args:
            color: New color to display.
        """
        self._color = color
        self._update_icon()
    
    def get_color(self) -> QColor:
        """Get the current color.
        
        Returns:
            Current color.
        """
        return self._color
    
    def _update_icon(self) -> None:
        """Update the button icon with the current color."""
        pixmap = QPixmap(self._size, self._size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.drawEllipse(1, 1, self._size - 2, self._size - 2)
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(self._size, self._size))
        self.setStyleSheet("border: none; background: transparent;")


class AnnotationPreferencesDialog(QDialog):
    """Dialog for configuring annotation preferences."""
    
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        """Initialize the annotation preferences dialog.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self._original_colors: List[QColor] = []
        self._original_font_family: str = ""
        self._original_font_size: int = 0
        
        # Load config
        self._load_config()
        
        # Setup UI
        self._setup_ui()
        
        # Apply styling
        self._apply_styling()
        
        # Load current user settings
        self._load_user_settings()
        
        # Store original values for cancel
        self._store_original_values()
        
        self.setWindowTitle("Annotation Preferences")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('annotation_preferences', {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get('width', 600)
        self.dialog_height = dialog_config.get('height', 500)
        self.dialog_min_width = dialog_config.get('minimum_width', 500)
        self.dialog_min_height = dialog_config.get('minimum_height', 400)
        
        # Background and colors
        self.bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.border_color = dialog_config.get('border_color', [60, 60, 65])
        self.text_color = dialog_config.get('text_color', [200, 200, 200])
        self.font_size = dialog_config.get('font_size', 11)
        
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
        self.label_font_size = labels_config.get('font_size', 11)
        self.label_text_color = labels_config.get('text_color', [200, 200, 200])
        
        # Inputs
        inputs_config = dialog_config.get('inputs', {})
        from app.utils.font_utils import resolve_font_family
        input_font_family_raw = inputs_config.get('font_family', 'Cascadia Mono')
        self.input_font_family = resolve_font_family(input_font_family_raw)
        self.input_font_size = inputs_config.get('font_size', 11)
        self.input_text_color = inputs_config.get('text_color', [240, 240, 240])
        self.input_bg_color = inputs_config.get('background_color', [30, 30, 35])
        self.input_border_color = inputs_config.get('border_color', [60, 60, 65])
        self.input_border_radius = inputs_config.get('border_radius', 3)
        self.input_padding = inputs_config.get('padding', [8, 6])
        
        # Groups
        groups_config = dialog_config.get('groups', {})
        self.group_title_font_family = groups_config.get('title_font_family', 'Helvetica Neue')
        self.group_title_font_size = groups_config.get('title_font_size', 11)
        self.group_title_color = groups_config.get('title_color', [240, 240, 240])
        self.group_content_margins = groups_config.get('content_margins', [10, 15, 10, 10])
        self.group_margin_top = groups_config.get('margin_top', 10)
        self.group_padding_top = groups_config.get('padding_top', 5)
        
        # Color swatches
        color_swatches_config = dialog_config.get('color_swatches', {})
        self.swatch_size = color_swatches_config.get('size', 40)
        self.swatch_spacing = color_swatches_config.get('spacing', 8)
        self.swatches_per_row = color_swatches_config.get('per_row', 5)
        
        # Font size spinbox
        font_size_config = dialog_config.get('font_size_spinbox', {})
        self.font_size_min = font_size_config.get('minimum', 8)
        self.font_size_max = font_size_config.get('maximum', 72)
        self.font_size_default = font_size_config.get('default', 12)
        
        # Get default colors from annotations config
        annotations_config = self.config.get('ui', {}).get('panels', {}).get('detail', {}).get('annotations', {})
        default_preset_colors = annotations_config.get('preset_colors', [[255, 100, 100], [100, 220, 100], [150, 200, 255], [255, 200, 100], [200, 100, 255], [100, 220, 255], [255, 150, 200], [150, 150, 255], [200, 200, 100], [240, 240, 240]])
        self.default_colors = [QColor(color[0], color[1], color[2]) for color in default_preset_colors]
        
        # Get default font from config (if available, otherwise use Arial)
        self.default_font_family = annotations_config.get('text_font_family', 'Arial')
        self.default_font_size = annotations_config.get('text_font_size', 12)
    
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
        
        # Color Palette group
        color_group = QGroupBox("Color Palette")
        color_group_layout = QGridLayout(color_group)
        color_group_layout.setSpacing(self.swatch_spacing)
        color_group_layout.setContentsMargins(
            self.group_content_margins[0], self.group_content_margins[1],
            self.group_content_margins[2], self.group_content_margins[3]
        )
        
        self.color_swatches: List[ColorSwatchButton] = []
        row = 0
        col = 0
        for i, default_color in enumerate(self.default_colors):
            swatch = ColorSwatchButton(default_color, self.swatch_size, self)
            swatch.clicked.connect(lambda checked, idx=i: self._on_color_swatch_clicked(idx))
            self.color_swatches.append(swatch)
            color_group_layout.addWidget(swatch, row, col)
            col += 1
            if col >= self.swatches_per_row:
                col = 0
                row += 1
        
        layout.addWidget(color_group)
        
        # Text Font group
        font_group = QGroupBox("Text Annotation Font")
        font_group_layout = QVBoxLayout(font_group)
        font_group_layout.setContentsMargins(
            self.group_content_margins[0], self.group_content_margins[1],
            self.group_content_margins[2], self.group_content_margins[3]
        )
        font_group_layout.setSpacing(self.layout_spacing)
        
        # Font family
        font_family_layout = QHBoxLayout()
        font_family_label = QLabel("Font Family:")
        font_family_label.setMinimumWidth(100)
        self.font_family_combo = QComboBox()
        self.font_family_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.font_family_combo.setEditable(True)
        
        # Populate with fonts, filtering out problematic ones
        problematic_fonts = {"Small Fonts", "System", "MS Sans Serif", "MS Serif"}
        all_fonts = QFontDatabase.families()
        valid_fonts = sorted([f for f in all_fonts if f not in problematic_fonts])
        self.font_family_combo.addItems(valid_fonts)
        
        font_family_layout.addWidget(font_family_label)
        font_family_layout.addWidget(self.font_family_combo)
        font_group_layout.addLayout(font_family_layout)
        
        # Font size
        font_size_layout = QHBoxLayout()
        font_size_label = QLabel("Font Size:")
        font_size_label.setMinimumWidth(100)
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setMinimum(self.font_size_min)
        self.font_size_spinbox.setMaximum(self.font_size_max)
        self.font_size_spinbox.setValue(self.font_size_default)
        self.font_size_spinbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Hide increment/decrement buttons
        self.font_size_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        font_size_layout.addWidget(font_size_label)
        font_size_layout.addWidget(self.font_size_spinbox)
        font_group_layout.addLayout(font_size_layout)
        
        layout.addWidget(font_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(self.button_spacing)
        
        # Reset to defaults button
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        button_layout.addWidget(self.reset_button)
        
        button_layout.addStretch()
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save_clicked)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json to all UI elements."""
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
        
        # Label styling
        label_style = (
            f"QLabel {{"
            f"font-family: \"{self.label_font_family}\";"
            f"font-size: {self.label_font_size}pt;"
            f"color: rgb({self.label_text_color[0]}, {self.label_text_color[1]}, {self.label_text_color[2]});"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)
        
        # Input styling (font combo and spinbox)
        input_style = (
            f"QComboBox, QSpinBox {{"
            f"font-family: \"{self.input_font_family}\";"
            f"font-size: {self.input_font_size}pt;"
            f"color: rgb({self.input_text_color[0]}, {self.input_text_color[1]}, {self.input_text_color[2]});"
            f"background-color: rgb({self.input_bg_color[0]}, {self.input_bg_color[1]}, {self.input_bg_color[2]});"
            f"border: 1px solid rgb({self.input_border_color[0]}, {self.input_border_color[1]}, {self.input_border_color[2]});"
            f"border-radius: {self.input_border_radius}px;"
            f"padding: {self.input_padding[1]}px {self.input_padding[0]}px;"
            f"}}"
        )
        
        self.font_family_combo.setStyleSheet(input_style)
        self.font_size_spinbox.setStyleSheet(input_style)
        
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
    
    def _load_user_settings(self) -> None:
        """Load current user settings and apply to UI."""
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings = settings_service.get_settings()
        
        annotations_prefs = settings.get('annotations', {})
        
        # Load colors
        preset_colors = annotations_prefs.get('preset_colors', None)
        if preset_colors:
            for i, color_list in enumerate(preset_colors):
                if i < len(self.color_swatches):
                    self.color_swatches[i].set_color(QColor(color_list[0], color_list[1], color_list[2]))
        else:
            # Use defaults
            for i, default_color in enumerate(self.default_colors):
                if i < len(self.color_swatches):
                    self.color_swatches[i].set_color(default_color)
        
        # Load font
        font_family = annotations_prefs.get('text_font_family', self.default_font_family)
        if font_family is None:
            font_family = self.default_font_family
        font_size = annotations_prefs.get('text_font_size', self.default_font_size)
        if font_size is None:
            font_size = self.default_font_size
        
        # Set font family (find index in combo box)
        index = self.font_family_combo.findText(font_family)
        if index >= 0:
            self.font_family_combo.setCurrentIndex(index)
        else:
            # If not found, try to set it by text (may add it if it's a valid font)
            self.font_family_combo.setCurrentText(font_family)
        
        self.font_size_spinbox.setValue(font_size)
    
    def _store_original_values(self) -> None:
        """Store original values for cancel operation."""
        self._original_colors = [swatch.get_color() for swatch in self.color_swatches]
        self._original_font_family = self.font_family_combo.currentText()
        self._original_font_size = self.font_size_spinbox.value()
    
    def _on_color_swatch_clicked(self, index: int) -> None:
        """Handle color swatch button click.
        
        Args:
            index: Index of the clicked swatch.
        """
        swatch = self.color_swatches[index]
        current_color = swatch.get_color()
        
        # Open color dialog
        color = QColorDialog.getColor(current_color, self, "Select Color")
        if color.isValid():
            swatch.set_color(color)
    
    def _on_reset_clicked(self) -> None:
        """Handle reset to defaults button click."""
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        # Reset colors to defaults
        for i, default_color in enumerate(self.default_colors):
            if i < len(self.color_swatches):
                self.color_swatches[i].set_color(default_color)
        
        # Reset font to defaults
        index = self.font_family_combo.findText(self.default_font_family)
        if index >= 0:
            self.font_family_combo.setCurrentIndex(index)
        else:
            # If not found, try to set it by text
            self.font_family_combo.setCurrentText(self.default_font_family)
        self.font_size_spinbox.setValue(self.default_font_size)
        
        progress_service.set_status("Reset annotation preferences to defaults")
    
    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        from app.services.user_settings_service import UserSettingsService
        from app.services.progress_service import ProgressService
        settings_service = UserSettingsService.get_instance()
        progress_service = ProgressService.get_instance()
        
        # Collect current values
        colors = []
        for swatch in self.color_swatches:
            color = swatch.get_color()
            colors.append([color.red(), color.green(), color.blue()])
        
        font_family = self.font_family_combo.currentText()
        font_size = self.font_size_spinbox.value()
        
        # Update user settings
        settings = settings_service.get_settings()
        if 'annotations' not in settings:
            settings['annotations'] = {}
        
        settings['annotations']['preset_colors'] = colors
        settings['annotations']['text_font_family'] = font_family
        settings['annotations']['text_font_size'] = font_size
        
        # Save to file
        if settings_service.save():
            progress_service.set_status("Annotation preferences saved")
            self.accept()
        else:
            progress_service.set_status("Failed to save annotation preferences")

