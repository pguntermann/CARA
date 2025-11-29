"""About dialog for displaying application information."""

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtCore import Qt
from typing import Dict, Any


class AboutDialog(QDialog):
    """Styled about dialog displaying application information."""
    
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        """Initialize the about dialog.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        # Get about dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('about_dialog', {})
        
        # Set dialog properties
        self.setWindowTitle("About CARA")
        dialog_width = dialog_config.get('width', 550)
        dialog_height = dialog_config.get('height', 300)
        self.setFixedSize(dialog_width, dialog_height)
        
        # Set dialog background color
        bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.setAutoFillBackground(True)
        dialog_palette = self.palette()
        dialog_palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(dialog_palette)
        
        # Create main layout
        main_layout = QVBoxLayout(self)
        layout_config = dialog_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 25)
        layout_margins = layout_config.get('margins', [30, 30, 30, 30])
        main_layout.setSpacing(layout_spacing)
        main_layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Create horizontal layout for icon and text
        content_layout = QHBoxLayout()
        icon_text_gap = layout_config.get('icon_text_gap', 25)
        content_layout.setSpacing(icon_text_gap)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Icon section
        icon_config = dialog_config.get('icon', {})
        icon_size = icon_config.get('size', 120)
        icon_label = QLabel()
        icon_path = Path(__file__).parent.parent.parent / "appicon.svg"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            pixmap = icon.pixmap(icon_size, icon_size)
            icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        content_layout.addWidget(icon_label)
        
        # Text section
        text_layout = QVBoxLayout()
        text_element_spacing = layout_config.get('text_element_spacing', 10)
        text_layout.setSpacing(text_element_spacing)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        # App name
        app_name_config = dialog_config.get('app_name', {})
        app_name_font_family = app_name_config.get('font_family', 'Helvetica Neue')
        app_name_font_size = app_name_config.get('font_size', 26)
        app_name_font_weight = app_name_config.get('font_weight', 'bold')
        app_name_color = app_name_config.get('color', [240, 240, 240])
        app_name_margin_bottom = app_name_config.get('margin_bottom', 6)
        
        app_name_label = QLabel("CARA")
        app_name_label.setIndent(0)
        app_name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        app_name_label.setStyleSheet(
            f"font-family: {app_name_font_family}; "
            f"font-size: {app_name_font_size}pt; "
            f"font-weight: {app_name_font_weight}; "
            f"color: rgb({app_name_color[0]}, {app_name_color[1]}, {app_name_color[2]});"
            f"margin: 0px; "
            f"margin-bottom: {app_name_margin_bottom}px; "
            f"padding: 0px;"
        )
        text_layout.addWidget(app_name_label, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Full name
        full_name_config = dialog_config.get('full_name', {})
        full_name_font_family = full_name_config.get('font_family', 'Helvetica Neue')
        full_name_font_size = full_name_config.get('font_size', 13)
        full_name_color = full_name_config.get('color', [200, 200, 200])
        full_name_margin_bottom = full_name_config.get('margin_bottom', 12)
        
        full_name_label = QLabel("Chess Analysis and Review Application")
        full_name_label.setIndent(0)
        full_name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        full_name_label.setStyleSheet(
            f"font-family: {full_name_font_family}; "
            f"font-size: {full_name_font_size}pt; "
            f"color: rgb({full_name_color[0]}, {full_name_color[1]}, {full_name_color[2]});"
            f"margin: 0px; "
            f"margin-bottom: {full_name_margin_bottom}px; "
            f"padding: 0px;"
        )
        text_layout.addWidget(full_name_label, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Version
        version_config = dialog_config.get('version', {})
        version_font_family = version_config.get('font_family', 'Helvetica Neue')
        version_font_size = version_config.get('font_size', 11)
        version_color = version_config.get('color', [180, 180, 180])
        version_label_text = version_config.get('label', 'Version')
        version_margin_bottom = version_config.get('margin_bottom', 12)
        app_version = self.config.get('version', '2.1')
        
        version_label = QLabel(f"{version_label_text} {app_version}")
        version_label.setIndent(0)
        version_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        version_label.setStyleSheet(
            f"font-family: {version_font_family}; "
            f"font-size: {version_font_size}pt; "
            f"color: rgb({version_color[0]}, {version_color[1]}, {version_color[2]});"
            f"margin: 0px; "
            f"margin-bottom: {version_margin_bottom}px; "
            f"padding: 0px;"
        )
        text_layout.addWidget(version_label, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Description
        description_config = dialog_config.get('description', {})
        description_font_family = description_config.get('font_family', 'Helvetica Neue')
        description_font_size = description_config.get('font_size', 11)
        description_color = description_config.get('color', [200, 200, 200])
        description_text = description_config.get('text', 'A comprehensive chess analysis and review application.')
        description_line_height = description_config.get('line_height', 1.5)
        description_margin_bottom = description_config.get('margin_bottom', 15)
        description_max_width = description_config.get('max_width', 350)
        
        description_label = QLabel(description_text)
        description_label.setIndent(0)
        description_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            f"font-family: {description_font_family}; "
            f"font-size: {description_font_size}pt; "
            f"color: rgb({description_color[0]}, {description_color[1]}, {description_color[2]});"
            f"line-height: {description_line_height};"
            f"margin: 0px; "
            f"margin-bottom: {description_margin_bottom}px; "
            f"padding: 0px;"
        )
        description_label.setMaximumWidth(description_max_width)
        text_layout.addWidget(description_label, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Copyright
        copyright_config = dialog_config.get('copyright', {})
        copyright_font_family = copyright_config.get('font_family', 'Helvetica Neue')
        copyright_font_size = copyright_config.get('font_size', 10)
        copyright_color = copyright_config.get('color', [150, 150, 150])
        copyright_text1 = copyright_config.get('text1', 'Copyright (C) 2025 Philipp Guntermann')
        copyright_text2 = copyright_config.get('text2', '')
        
        copyright_label1 = QLabel(copyright_text1)
        copyright_label1.setIndent(0)
        copyright_label1.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        copyright_label1.setStyleSheet(
            f"font-family: {copyright_font_family}; "
            f"font-size: {copyright_font_size}pt; "
            f"color: rgb({copyright_color[0]}, {copyright_color[1]}, {copyright_color[2]});"
            f"margin: 0px; "
            f"padding: 0px;"
        )
        text_layout.addWidget(copyright_label1, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Copyright line 2 (only if text2 is provided)
        if copyright_text2:
            copyright_label2 = QLabel(copyright_text2)
            copyright_label2.setIndent(0)
            copyright_label2.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            copyright_label2.setStyleSheet(
                f"font-family: {copyright_font_family}; "
                f"font-size: {copyright_font_size}pt; "
                f"color: rgb({copyright_color[0]}, {copyright_color[1]}, {copyright_color[2]});"
                f"margin: 0px; "
                f"padding: 0px;"
            )
            text_layout.addWidget(copyright_label2, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Contact email
        contact_config = dialog_config.get('contact', {})
        contact_font_family = contact_config.get('font_family', 'Helvetica Neue')
        contact_font_size = contact_config.get('font_size', 10)
        contact_color = contact_config.get('color', [150, 150, 150])
        contact_email = contact_config.get('email', 'pguntermann@me.com')
        contact_label_text = contact_config.get('label', 'Contact:')
        contact_margin_top = contact_config.get('margin_top', 8)
        
        # Display as plain text (not clickable)
        contact_text = f"{contact_label_text} {contact_email}"
        
        contact_label = QLabel(contact_text)
        contact_label.setIndent(0)
        contact_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        contact_label.setWordWrap(False)  # Don't wrap email addresses
        contact_label.setStyleSheet(
            f"font-family: {contact_font_family}; "
            f"font-size: {contact_font_size}pt; "
            f"color: rgb({contact_color[0]}, {contact_color[1]}, {contact_color[2]});"
            f"margin: 0px; "
            f"margin-top: {contact_margin_top}px; "
            f"padding: 0px;"
        )
        # Don't set maximum width - let it use full available width
        text_layout.addWidget(contact_label, 0, Qt.AlignmentFlag.AlignLeft)
        
        # License
        license_config = dialog_config.get('license', {})
        license_font_family = license_config.get('font_family', 'Helvetica Neue')
        license_font_size = license_config.get('font_size', 10)
        license_color = license_config.get('color', [150, 150, 150])
        license_text = license_config.get('text', 'Licensed under the GNU General Public License v3.0 (GPL-3.0)')
        license_margin_top = license_config.get('margin_top', 8)
        
        license_label = QLabel(license_text)
        license_label.setIndent(0)
        license_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        license_label.setWordWrap(True)
        license_label.setStyleSheet(
            f"font-family: {license_font_family}; "
            f"font-size: {license_font_size}pt; "
            f"color: rgb({license_color[0]}, {license_color[1]}, {license_color[2]});"
            f"margin: 0px; "
            f"margin-top: {license_margin_top}px; "
            f"padding: 0px;"
        )
        license_label.setMaximumWidth(description_max_width)
        text_layout.addWidget(license_label, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Add stretch to push content to top
        text_layout.addStretch()
        
        content_layout.addLayout(text_layout)
        content_layout.addStretch()
        
        main_layout.addLayout(content_layout)
        
        # Button section
        button_section_top_margin = layout_config.get('button_section_top_margin', 25)
        main_layout.addSpacing(button_section_top_margin)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Get button styling from config
        buttons_config = dialog_config.get('buttons', {})
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
        button_alignment = buttons_config.get('alignment', 'right')
        
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
        
        close_button = QPushButton("Close")
        close_button.setStyleSheet(button_style)
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        main_layout.addLayout(button_layout)

