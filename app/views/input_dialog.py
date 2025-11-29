"""Input dialog for text input."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)
from PyQt6.QtGui import QPalette, QColor
from typing import Dict, Any, Optional, Tuple


class InputDialog(QDialog):
    """Styled input dialog for text input."""
    
    def __init__(self, config: Dict[str, Any], title: str, label: str, 
                 initial_text: str = "", parent=None) -> None:
        """Initialize the input dialog.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            label: Label text for the input field.
            initial_text: Initial text value (default: empty string).
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.result_text = ""
        self.result_ok = False
        
        # Get input dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('input_dialog', {})
        layout_config = dialog_config.get('layout', {})
        title_config = dialog_config.get('title', {})
        label_config = dialog_config.get('label', {})
        input_config = dialog_config.get('input', {})
        buttons_config = dialog_config.get('buttons', {})
        
        # Set dialog properties
        self.setWindowTitle(title)
        dialog_width = dialog_config.get('width', 400)
        dialog_height = dialog_config.get('height', 220)
        self.setFixedSize(dialog_width, dialog_height)
        
        # Set dialog background color
        bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.setAutoFillBackground(True)
        dialog_palette = self.palette()
        dialog_palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(dialog_palette)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout_spacing = layout_config.get('spacing', 15)
        layout_margins = layout_config.get('margins', [15, 15, 15, 15])
        layout.setSpacing(layout_spacing)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Title
        title_font_size = title_config.get('font_size', 14)
        title_padding = title_config.get('padding', 5)
        title_spacing_after = title_config.get('spacing_after', 5)
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet(f"font-size: {title_font_size}pt; padding: {title_padding}px;")
        layout.addWidget(title_label)
        
        # Add spacing after title (from config)
        layout.addSpacing(title_spacing_after)
        
        # Label
        label_font_size = label_config.get('font_size', 11)
        label_padding = label_config.get('padding', 5)
        label_text_color = label_config.get('text_color', [200, 200, 200])
        label_spacing_after = label_config.get('spacing_after', 3)
        prompt_label = QLabel(label)
        prompt_label.setStyleSheet(
            f"font-size: {label_font_size}pt; "
            f"padding: {label_padding}px; "
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
        )
        layout.addWidget(prompt_label)
        
        # Add spacing between label and input field (from config)
        layout.addSpacing(label_spacing_after)
        
        # Input field
        input_font_family = input_config.get('font_family', 'Helvetica Neue')
        input_font_size = input_config.get('font_size', 11)
        input_text_color = input_config.get('text_color', [240, 240, 240])
        input_bg_color = input_config.get('background_color', [30, 30, 35])
        input_border_color = input_config.get('border_color', [60, 60, 65])
        input_border_radius = input_config.get('border_radius', 3)
        input_padding = input_config.get('padding', [2, 6, 2, 6])
        input_min_width = input_config.get('minimum_width', 200)
        input_min_height = input_config.get('minimum_height', 25)
        
        self.input_field = QLineEdit()
        self.input_field.setText(initial_text)
        self.input_field.setMinimumWidth(input_min_width)
        self.input_field.setMinimumHeight(input_min_height)
        # Make input field expand to fill available width
        from PyQt6.QtWidgets import QSizePolicy
        self.input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Add left margin to align input field with label text (label has padding, so we need margin to match)
        self.input_field.setStyleSheet(
            f"QLineEdit {{"
            f"font-family: {input_font_family};"
            f"font-size: {input_font_size}pt;"
            f"color: rgb({input_text_color[0]}, {input_text_color[1]}, {input_text_color[2]});"
            f"background-color: rgb({input_bg_color[0]}, {input_bg_color[1]}, {input_bg_color[2]});"
            f"border: 1px solid rgb({input_border_color[0]}, {input_border_color[1]}, {input_border_color[2]});"
            f"border-radius: {input_border_radius}px;"
            f"padding: {input_padding[0]}px {input_padding[1]}px {input_padding[2]}px {input_padding[3]}px;"
            f"margin-left: {label_padding}px;"
            f"}}"
        )
        layout.addWidget(self.input_field)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        # Get button styling from config
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        button_font_size = buttons_config.get('font_size', 10)
        text_color = buttons_config.get('text_color', [200, 200, 200])
        border_color = buttons_config.get('border_color', [60, 60, 65])
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {button_font_size}pt;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
        )
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet(button_style)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        ok_button = QPushButton("OK")
        ok_button.setStyleSheet(button_style)
        ok_button.clicked.connect(self._on_ok_clicked)
        ok_button.setDefault(True)  # Make OK the default button (Enter key triggers it)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        # Connect Enter key in input field to OK action
        self.input_field.returnPressed.connect(self._on_ok_clicked)
        
        # Set focus on input field and select all text
        self.input_field.setFocus()
        self.input_field.selectAll()
    
    def _on_ok_clicked(self) -> None:
        """Handle OK button click."""
        self.result_text = self.input_field.text()
        self.result_ok = True
        self.accept()
    
    @staticmethod
    def get_text(config: Dict[str, Any], title: str, label: str, 
                 initial_text: str = "", parent=None) -> Tuple[str, bool]:
        """Show an input dialog and return the result.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            label: Label text for the input field.
            initial_text: Initial text value (default: empty string).
            parent: Parent widget.
            
        Returns:
            Tuple of (text: str, ok: bool). 
            text is the entered text (empty if cancelled).
            ok is True if user clicked OK, False if cancelled.
        """
        dialog = InputDialog(config, title, label, initial_text, parent)
        dialog.exec()
        return (dialog.result_text, dialog.result_ok)

