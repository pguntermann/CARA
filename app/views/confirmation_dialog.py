"""Confirmation dialog for user confirmations."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QPalette, QColor
from typing import Dict, Any


class ConfirmationDialog(QDialog):
    """Styled confirmation dialog for user confirmations."""
    
    def __init__(self, config: Dict[str, Any], title: str, message: str, parent=None) -> None:
        """Initialize the confirmation dialog.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            message: Confirmation message.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        # Get confirmation dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('confirmation_dialog', {})
        layout_config = dialog_config.get('layout', {})
        title_config = dialog_config.get('title', {})
        message_config = dialog_config.get('message', {})
        buttons_config = dialog_config.get('buttons', {})
        
        # Set dialog properties
        self.setWindowTitle(title)
        dialog_width = dialog_config.get('width', 400)
        
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
        from app.utils.font_utils import scale_font_size
        title_font_size = scale_font_size(title_config.get('font_size', 14))
        title_padding = title_config.get('padding', 5)
        # Get title text color from config, fallback to dialog text_color or default
        title_text_color = title_config.get('text_color', dialog_config.get('text_color', [240, 240, 240]))
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet(
            f"font-size: {title_font_size}pt; "
            f"padding: {title_padding}px; "
            f"color: rgb({title_text_color[0]}, {title_text_color[1]}, {title_text_color[2]});"
            f"background-color: transparent;"
        )
        # Set palette to prevent macOS override
        title_label_palette = title_label.palette()
        title_label_palette.setColor(title_label.foregroundRole(), QColor(title_text_color[0], title_text_color[1], title_text_color[2]))
        title_label.setPalette(title_label_palette)
        title_label.update()
        layout.addWidget(title_label)
        
        # Message
        message_font_size = scale_font_size(message_config.get('font_size', 11))
        message_padding = message_config.get('padding', 5)
        message_text_color = message_config.get('text_color', [200, 200, 200])
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        # Set minimum width to ensure proper word wrapping calculation
        message_label.setMinimumWidth(dialog_width - layout_margins[0] - layout_margins[2] - (message_padding * 2))
        message_label.setStyleSheet(
            f"font-size: {message_font_size}pt; "
            f"padding: {message_padding}px; "
            f"color: rgb({message_text_color[0]}, {message_text_color[1]}, {message_text_color[2]});"
        )
        layout.addWidget(message_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        # Apply button styling using StyleManager (uses unified config)
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        border_color = buttons_config.get('border_color', [60, 60, 65])
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        from app.views.style import StyleManager
        no_button = QPushButton("No")
        no_button.clicked.connect(self.reject)
        button_layout.addWidget(no_button)
        
        yes_button = QPushButton("Yes")
        yes_button.clicked.connect(self.accept)
        button_layout.addWidget(yes_button)
        
        # Style both buttons using StyleManager
        StyleManager.style_buttons(
            [no_button, yes_button],
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )
        
        layout.addLayout(button_layout)
        
        # Let Qt calculate the natural size after layout is set up
        # This accounts for DPI scaling automatically
        self.setMinimumWidth(dialog_width)
        self.adjustSize()
        
        # Ensure minimum height from config
        min_height = dialog_config.get('height', 150)
        if self.height() < min_height:
            self.setMinimumHeight(min_height)
            self.resize(self.width(), min_height)
    
    @staticmethod
    def show_confirmation(config: Dict[str, Any], title: str, message: str, parent=None) -> bool:
        """Show a confirmation dialog and return the result.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            message: Confirmation message.
            parent: Parent widget.
            
        Returns:
            True if user confirmed (Yes), False if cancelled (No).
        """
        dialog = ConfirmationDialog(config, title, message, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted

