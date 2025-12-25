"""Message dialog for warnings, information, and errors."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QPalette, QColor
from typing import Dict, Any, Literal


class MessageDialog(QDialog):
    """Styled message dialog for warnings, information, and errors."""
    
    def __init__(self, config: Dict[str, Any], title: str, message: str, 
                 message_type: Literal["warning", "information", "critical", "error"] = "information",
                 parent=None) -> None:
        """Initialize the message dialog.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            message: Message text.
            message_type: Type of message ("warning", "information", "critical", or "error").
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        # Get message dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('message_dialog', {})
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
        
        # Get button styling from config
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        button_font_size = scale_font_size(buttons_config.get('font_size', 10))
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
        
        ok_button = QPushButton("OK")
        ok_button.setStyleSheet(button_style)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
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
    def show_warning(config: Dict[str, Any], title: str, message: str, parent=None) -> None:
        """Show a warning message dialog.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            message: Warning message.
            parent: Parent widget.
        """
        dialog = MessageDialog(config, title, message, "warning", parent)
        dialog.exec()
    
    @staticmethod
    def show_information(config: Dict[str, Any], title: str, message: str, parent=None) -> None:
        """Show an information message dialog.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            message: Information message.
            parent: Parent widget.
        """
        dialog = MessageDialog(config, title, message, "information", parent)
        dialog.exec()
    
    @staticmethod
    def show_critical(config: Dict[str, Any], title: str, message: str, parent=None) -> None:
        """Show a critical error message dialog.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            message: Critical error message.
            parent: Parent widget.
        """
        dialog = MessageDialog(config, title, message, "critical", parent)
        dialog.exec()
    
    @staticmethod
    def show_error(config: Dict[str, Any], title: str, message: str, parent=None) -> None:
        """Show an error message dialog.
        
        Args:
            config: Configuration dictionary.
            title: Dialog title.
            message: Error message.
            parent: Parent widget.
        """
        dialog = MessageDialog(config, title, message, "error", parent)
        dialog.exec()

