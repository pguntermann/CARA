"""Engine dialog for adding UCI chess engines."""

import sys
import re
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QSizePolicy,
    QApplication,
    QWidget,
    QGroupBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QResizeEvent, QShowEvent, QPalette, QColor
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


class EngineValidationThread(QThread):
    """Thread for validating engine in background."""
    
    validation_complete = pyqtSignal(bool, str, str, str)  # success, error, name, author
    
    def __init__(self, engine_path: Path, validation_service) -> None:
        """Initialize validation thread.
        
        Args:
            engine_path: Path to engine executable.
            validation_service: EngineValidationService instance.
        """
        super().__init__()
        self.engine_path = engine_path
        self.validation_service = validation_service
    
    def run(self) -> None:
        """Run engine validation."""
        # Don't save to file during validation - only when user clicks "Add Engine"
        result = self.validation_service.validate_engine(self.engine_path, save_to_file=False)
        
        if result.is_valid:
            self.validation_complete.emit(True, "", result.name, result.author)
        else:
            self.validation_complete.emit(False, result.error_message, "", "")


class EngineDialog(QDialog):
    """Dialog for adding UCI chess engines."""
    
    def __init__(self, config: Dict[str, Any], engine_controller, parent=None) -> None:
        """Initialize the engine dialog.
        
        Args:
            config: Configuration dictionary.
            engine_controller: EngineController instance.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.engine_controller = engine_controller
        self.engine_path: Optional[Path] = None
        self.engine_name: str = ""
        self.engine_author: str = ""
        self.engine_version: str = ""
        self.validation_thread: Optional[EngineValidationThread] = None
        
        # Store fixed size - set it BEFORE layout is set up
        # Read size from config, accounting for Windows frame margins
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_dialog', {})
        width = dialog_config.get('width', 600)
        height = dialog_config.get('height', 400)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size BEFORE UI setup to prevent layout from requesting more space
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Add UCI Engine")
    
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event to enforce fixed size."""
        super().showEvent(event)
        # Re-enforce fixed size after dialog is shown
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
    
    def sizeHint(self) -> QSize:
        """Return the fixed size as the size hint."""
        return self._fixed_size
    
    def minimumSizeHint(self) -> QSize:
        """Return the fixed size as the minimum size hint."""
        return self._fixed_size
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize event to prevent resizing."""
        super().resizeEvent(event)
        # If size changed, immediately restore fixed size
        if event.size() != self._fixed_size:
            # Block signals temporarily to prevent recursion
            self.blockSignals(True)
            current_pos = self.pos()
            self.setGeometry(current_pos.x(), current_pos.y(), self._fixed_size.width(), self._fixed_size.height())
            self.setFixedSize(self._fixed_size)
            self.setMinimumSize(self._fixed_size)
            self.setMaximumSize(self._fixed_size)
            self.blockSignals(False)
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Get layout spacing and margins from config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_dialog', {})
        layout_config = dialog_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 10)
        layout_margins = layout_config.get('margins', [10, 10, 10, 10])
        engine_info_section_spacing = layout_config.get('engine_info_section_spacing', 2)
        buttons_config = dialog_config.get('buttons', {})
        
        layout = QVBoxLayout(self)
        layout.setSpacing(layout_spacing)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        layout.addSpacing(layout_spacing)
        
        # Engine path selection group
        path_group = QGroupBox("Select UCI Engine")
        path_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        path_group_layout = QVBoxLayout(path_group)
        # Get group box content margins from config
        group_box_config = dialog_config.get('group_box', {})
        group_margins = group_box_config.get('content_margins', [10, 15, 10, 10])
        path_group_layout.setContentsMargins(
            group_margins[0], group_margins[1], group_margins[2], group_margins[3]
        )
        # Get spacing from config
        group_content_spacing = group_box_config.get('content_spacing', 8)
        path_group_layout.setSpacing(group_content_spacing)
        
        # Path input and browse button in horizontal layout
        self.path_layout = QHBoxLayout()
        self.path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout_spacing = group_box_config.get('path_layout_spacing', 8)
        self.path_layout.setSpacing(path_layout_spacing)
        self.path_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.path_input = QLineEdit()
        self.path_input.setReadOnly(True)
        self.path_input.setPlaceholderText("Select engine executable...")
        self.path_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Ensure no margins for proper alignment
        self.path_input.setContentsMargins(0, 0, 0, 0)
        
        self.browse_button = QPushButton("...")
        self.browse_button.clicked.connect(self._browse_engine_path)
        self.browse_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Add widgets with explicit vertical alignment
        self.path_layout.addWidget(self.path_input, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.path_layout.addWidget(self.browse_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        path_group_layout.addLayout(self.path_layout)
        
        layout.addWidget(path_group)
        
        layout.addSpacing(layout_spacing)
        
        # Engine information group box (read-only after validation)
        engine_info_group = QGroupBox("Engine Information")
        engine_info_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        engine_info_layout = QVBoxLayout(engine_info_group)
        engine_info_layout.setSpacing(engine_info_section_spacing)
        # Get group box content margins from config
        group_box_config = dialog_config.get('group_box', {})
        group_margins = group_box_config.get('content_margins', [10, 15, 10, 10])
        engine_info_layout.setContentsMargins(
            group_margins[0], group_margins[1], group_margins[2], group_margins[3]
        )
        
        # Name
        name_layout = QHBoxLayout()
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(0)
        self.name_label = QLabel("Name:")
        # Minimum width will be set from config in _apply_styling
        self.name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.name_input = QLineEdit()
        self.name_input.setReadOnly(True)
        self.name_input.setPlaceholderText("Will be populated after validation...")
        self.name_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        name_layout.addWidget(self.name_label)
        name_layout.addWidget(self.name_input)
        engine_info_layout.addLayout(name_layout)
        
        # Author
        author_layout = QHBoxLayout()
        author_layout.setContentsMargins(0, 0, 0, 0)
        author_layout.setSpacing(0)
        self.author_label = QLabel("Author:")
        # Minimum width will be set from config in _apply_styling
        self.author_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.author_input = QLineEdit()
        self.author_input.setReadOnly(True)
        self.author_input.setPlaceholderText("Will be populated after validation...")
        self.author_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        author_layout.addWidget(self.author_label)
        author_layout.addWidget(self.author_input)
        engine_info_layout.addLayout(author_layout)
        
        # Version (derived from author/name)
        version_layout = QHBoxLayout()
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(0)
        self.version_label = QLabel("Version:")
        # Minimum width will be set from config in _apply_styling
        self.version_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.version_input = QLineEdit()
        self.version_input.setReadOnly(True)
        self.version_input.setPlaceholderText("Will be populated after validation...")
        self.version_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        version_layout.addWidget(self.version_label)
        version_layout.addWidget(self.version_input)
        engine_info_layout.addLayout(version_layout)
        
        layout.addWidget(engine_info_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        self.validate_button = QPushButton("Validate Engine")
        self.validate_button.setEnabled(False)
        self.validate_button.clicked.connect(self._validate_engine)
        button_layout.addWidget(self.validate_button)
        
        self.add_button = QPushButton("Add Engine")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._add_engine)
        button_layout.addWidget(self.add_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Connect path input changes
        self.path_input.textChanged.connect(self._on_path_changed)
    
    def _apply_styling(self) -> None:
        """Apply styling to UI elements based on configuration."""
        ui_config = self.config.get('ui', {})
        dialog_config = ui_config.get('dialogs', {}).get('engine_dialog', {})
        
        # Dialog background color
        bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        palette.setColor(QPalette.ColorRole.Window, QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(palette)
        
        # Labels styling - apply to specific labels
        labels_config = dialog_config.get('labels', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        label_font_family = resolve_font_family(labels_config.get('font_family', 'Helvetica Neue'))
        label_font_size = int(scale_font_size(labels_config.get('font_size', 11)))
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        label_min_width = labels_config.get('minimum_width', 100)
        
        # Apply label styling to specific labels
        label_style = (
            f"font-family: {label_font_family}; "
            f"font-size: {label_font_size}pt; "
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
        )
        
        # Style all labels directly
        labels = [self.name_label, self.author_label, self.version_label]
        for label in labels:
            label.setStyleSheet(label_style)
            label.setMinimumWidth(label_min_width)
        
        # Input widgets styling (QLineEdit) - use StyleManager approach with direct stylesheet
        input_config = dialog_config.get('input_widgets', {})
        # Get padding from config (preserve existing format for alignment)
        input_padding_raw = input_config.get('padding', [2, 6, 2, 6])
        if len(input_padding_raw) == 4:
            # Convert [left, top, right, bottom] to [horizontal, vertical] for StyleManager
            input_padding = [input_padding_raw[0], input_padding_raw[1]]
        else:
            input_padding = input_padding_raw
        
        # Use dialog-specific background color and font to match combobox styling
        input_bg = input_config.get('background_color', [45, 45, 50])
        bg_color = input_bg if isinstance(input_bg, list) else [input_bg[0], input_bg[1], input_bg[2]]
        
        # Get dialog-specific font family and size
        from app.utils.font_utils import resolve_font_family, scale_font_size
        input_font_family_raw = input_config.get('font_family', 'Helvetica Neue')
        input_font_family = resolve_font_family(input_font_family_raw)
        input_font_size = scale_font_size(input_config.get('font_size', 11))
        
        # Apply unified line edit styling using StyleManager
        from app.views.style import StyleManager
        StyleManager.style_line_edits(
            [self.path_input, self.name_input, self.author_input, self.version_input],
            self.config,
            font_family=input_font_family,  # Match original dialog font
            font_size=input_font_size,  # Match original dialog font size
            bg_color=bg_color,  # Match combobox background color
            padding=input_padding  # Preserve existing padding for alignment
        )
        
        # Get the natural height of the input field after styling is applied
        # This accounts for font size, padding, and DPI scaling automatically
        self.path_input.updateGeometry()
        natural_height = self.path_input.sizeHint().height()
        if natural_height <= 0:
            # Fallback: calculate from font metrics and padding
            from PyQt6.QtGui import QFontMetrics, QFont
            from app.utils.font_utils import resolve_font_family, scale_font_size
            styles_config = self.config.get('ui', {}).get('styles', {})
            line_edit_config = styles_config.get('line_edit', {})
            font_family = resolve_font_family(line_edit_config.get('font_family', 'Helvetica Neue'))
            font_size = scale_font_size(line_edit_config.get('font_size', 11))
            font = QFont(font_family, font_size)
            fm = QFontMetrics(font)
            text_height = fm.height()
            # input_padding is now [horizontal, vertical]
            padding_vertical = input_padding[1] * 2  # vertical padding on both sides
            border_width = line_edit_config.get('border_width', 1)
            natural_height = text_height + padding_vertical + (border_width * 2)
        
        final_height = natural_height
        
        # Group box styling - use StyleManager
        group_box_config = dialog_config.get('group_box', {})
        group_border_color = group_box_config.get('border_color', [60, 60, 65])
        group_border_width = group_box_config.get('border_width', 1)
        group_border_radius = group_box_config.get('border_radius', 5)
        group_bg_color = group_box_config.get('background_color')  # None = use unified default
        group_title_color = group_box_config.get('title_color', [240, 240, 240])
        group_title_font_family = resolve_font_family(group_box_config.get('title_font_family', 'Helvetica Neue'))
        group_title_font_size = scale_font_size(group_box_config.get('title_font_size', 11))
        group_margin_top = group_box_config.get('margin_top', 10)
        group_padding_top = group_box_config.get('padding_top', 10)
        group_title_left = group_box_config.get('title_left', 10)
        group_title_padding = group_box_config.get('title_padding', [0, 5])
        
        # Get all group boxes from layout
        group_boxes = []
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QGroupBox):
                group_boxes.append(item.widget())
        
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=group_border_color,
                border_width=group_border_width,
                border_radius=group_border_radius,
                bg_color=group_bg_color,
                margin_top=group_margin_top,
                padding_top=group_padding_top,
                title_font_family=group_title_font_family,
                title_font_size=group_title_font_size,
                title_color=group_title_color,
                title_left=group_title_left,
                title_padding=group_title_padding
            )
        
        # Apply button styling using StyleManager (uses unified config)
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        
        # Get colors from dialog background for consistency
        dialog_bg = dialog_config.get('background_color', [40, 40, 45])
        # Use border color from unified line edit config for consistency
        bg_color_list = [dialog_bg[0], dialog_bg[1], dialog_bg[2]]
        styles_config = self.config.get('ui', {}).get('styles', {})
        line_edit_config = styles_config.get('line_edit', {})
        unified_border_color = line_edit_config.get('border_color', [60, 60, 65])
        border_color_list = [unified_border_color[0], unified_border_color[1], unified_border_color[2]]
        
        from app.views.style import StyleManager
        from app.utils.font_utils import resolve_font_family, scale_font_size
        
        # Get line edit config values for matching font, border radius, and border width
        line_edit_font_family = resolve_font_family(line_edit_config.get('font_family', 'Helvetica Neue'))
        line_edit_font_size = scale_font_size(line_edit_config.get('font_size', 11))
        line_edit_border_radius = line_edit_config.get('border_radius', 3)
        line_edit_border_width = line_edit_config.get('border_width', 1)
        
        # Apply button styling to main buttons
        main_buttons = [self.validate_button, self.add_button, self.cancel_button]
        StyleManager.style_buttons(
            main_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )
        
        # Style Browse button FIRST to get its natural size hint
        # Use the same font, border width, radius, and padding as input field for perfect alignment
        button_padding = input_padding[1]  # Use vertical padding from input config (same as input field)
        
        StyleManager.style_buttons(
            [self.browse_button],
            self.config,
            bg_color_list,
            border_color_list,
            font_family=line_edit_font_family,  # Match input field font family
            font_size=line_edit_font_size,  # Match input field font size
            border_radius=line_edit_border_radius,  # Match input field border radius
            padding=button_padding  # Same vertical padding as input field
        )
        
        # Get size hints from both widgets after styling
        self.path_input.updateGeometry()
        self.browse_button.updateGeometry()
        input_size_hint = self.path_input.sizeHint().height()
        button_size_hint = self.browse_button.sizeHint().height()
        
        # Use the maximum of both size hints to ensure both widgets align properly
        # This accounts for any differences in how Qt calculates size hints
        if input_size_hint > 0 and button_size_hint > 0:
            final_height = max(input_size_hint, button_size_hint)
        else:
            final_height = input_size_hint if input_size_hint > 0 else button_size_hint
        
        if final_height <= 0:
            # Fallback: use the calculated final_height from earlier
            pass  # final_height already calculated above
        
        # Set fixed height on both widgets using the same calculated height
        self.path_input.setFixedHeight(final_height)
        self.path_input.setMinimumHeight(final_height)
        self.path_input.setMaximumHeight(final_height)
        
        # Override the button's stylesheet to match input field border width exactly
        # and remove any height constraints, ensure margins are zero
        button_stylesheet = self.browse_button.styleSheet()
        # Remove any existing height/min-height/max-height constraints from stylesheet
        button_stylesheet = re.sub(r'(height|min-height|max-height):\s*\d+px;', '', button_stylesheet)
        # Ensure border width matches input field exactly
        button_stylesheet = re.sub(
            r'border:\s*\d+px',
            f'border: {line_edit_border_width}px',
            button_stylesheet
        )
        # Ensure margins are zero and add vertical alignment
        if 'margin:' not in button_stylesheet:
            button_stylesheet = button_stylesheet.replace(
                "QPushButton {",
                "QPushButton {\nmargin: 0px;"
            )
        else:
            button_stylesheet = re.sub(r'margin:\s*[^;]+;', 'margin: 0px;', button_stylesheet)
        # Add vertical alignment
        if 'vertical-align:' not in button_stylesheet:
            button_stylesheet = button_stylesheet.replace(
                "QPushButton {",
                "QPushButton {\nvertical-align: middle;"
            )
        self.browse_button.setStyleSheet(button_stylesheet)
        
        # Also ensure button has no margins programmatically
        self.browse_button.setContentsMargins(0, 0, 0, 0)
        
        # Set fixed height programmatically to match input field exactly
        # Qt's setFixedHeight sets the total widget height, padding is inside
        self.browse_button.setFixedHeight(final_height)
        self.browse_button.setMinimumHeight(final_height)
        self.browse_button.setMaximumHeight(final_height)
        
        # Ensure both widgets have the same size policy for alignment
        self.path_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.browse_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Ensure button padding matches input field padding exactly in the stylesheet
        # Input field uses: padding: {input_padding[1]}px {input_padding[0]}px; (vertical horizontal)
        # Button's StyleManager applies padding as a single value, so we need to override it
        button_stylesheet_final = self.browse_button.styleSheet()
        # Replace padding to use same format as input field: vertical horizontal
        button_stylesheet_final = re.sub(
            r'padding:\s*\d+px;',
            f'padding: {input_padding[1]}px {input_padding[0]}px;',
            button_stylesheet_final
        )
        # Ensure text is centered for proper alignment
        if 'text-align:' not in button_stylesheet_final:
            button_stylesheet_final = button_stylesheet_final.replace(
                "QPushButton {",
                "QPushButton {\ntext-align: center;"
            )
        self.browse_button.setStyleSheet(button_stylesheet_final)
        
    def _browse_engine_path(self) -> None:
        """Browse for engine executable file."""
        # Determine file filter based on platform
        if sys.platform == "win32":
            file_filter = "Executable Files (*.exe);;All Files (*)"
        elif sys.platform == "darwin":  # macOS
            file_filter = "All Files (*)"
        else:  # Linux and other Unix-like systems
            file_filter = "All Files (*)"
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select UCI Engine Executable",
            "",
            file_filter
        )
        
        if file_path:
            self.engine_path = Path(file_path)
            self.path_input.setText(str(self.engine_path))
            self._reset_engine_info()
            self.validate_button.setEnabled(True)
            self.add_button.setEnabled(False)
            # Report status to main window status bar
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            progress_service.set_status("Click 'Validate Engine' to verify this is a UCI engine.")
    
    def _on_path_changed(self, text: str) -> None:
        """Handle path input changes."""
        if text:
            self.validate_button.setEnabled(True)
        else:
            self.validate_button.setEnabled(False)
            self.add_button.setEnabled(False)
            self._reset_engine_info()
    
    def _reset_engine_info(self) -> None:
        """Reset engine information fields."""
        self.name_input.clear()
        self.author_input.clear()
        self.version_input.clear()
        self.engine_name = ""
        self.engine_author = ""
        self.engine_version = ""
    
    def _validate_engine(self) -> None:
        """Validate the selected engine."""
        if not self.engine_path:
            return
        
        # Disable controls during validation
        self.validate_button.setEnabled(False)
        self.add_button.setEnabled(False)
        
        # Report status to main window status bar
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
        progress_service.set_indeterminate(True)
        progress_service.set_status("Validating engine... Please wait.")
        
        # Start validation in background thread
        self.validation_thread = EngineValidationThread(
            self.engine_path,
            self.engine_controller.validation_service
        )
        self.validation_thread.validation_complete.connect(self._on_validation_complete)
        self.validation_thread.start()
    
    def _on_validation_complete(self, success: bool, error: str, name: str, author: str) -> None:
        """Handle validation completion.
        
        Args:
            success: True if validation succeeded.
            error: Error message if validation failed.
            name: Engine name if validation succeeded.
            author: Engine author if validation succeeded.
        """
        # Hide progress bar in main window status bar
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.hide_progress()
        progress_service.set_indeterminate(False)
        
        self.validate_button.setEnabled(True)
        
        if success:
            # Populate engine info
            self.engine_name = name
            self.engine_author = author
            # Extract version using the validation service's static method
            from app.services.engine_validation_service import EngineValidationService
            self.engine_version = EngineValidationService._extract_version(author, name)
            
            self.name_input.setText(name)
            self.author_input.setText(author)
            self.version_input.setText(self.engine_version)
            
            # Enable add button
            self.add_button.setEnabled(True)
            # Report success status to main window status bar
            progress_service.set_status("Engine validated successfully! Click 'Add Engine' to add it.")
        else:
            # Show error
            self._reset_engine_info()
            # Report error status to main window status bar
            progress_service.set_status(f"Validation failed: {error}")
            
            # Show error dialog
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Validation Failed",
                f"Failed to validate engine:\n\n{error}",
                self
            )
    
    def _add_engine(self) -> None:
        """Add the validated engine."""
        if not self.engine_path or not self.engine_name:
            return
        
        # Check if engine with same path already exists
        existing_engine = self.engine_controller.get_engine_model().get_engine_by_path(str(self.engine_path))
        if existing_engine:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Engine Already Exists",
                f"An engine with path '{self.engine_path}' is already configured.",
                self
            )
            return
        
        # Save engine options to file now that user is adding the engine
        validation_service = self.engine_controller.validation_service
        options_saved, options = validation_service.refresh_engine_options(
            self.engine_path,
            enable_debug=False,
            save_to_file=True  # Save to file when user adds the engine
        )
        
        # Save recommended defaults for all tasks
        from app.services.engine_parameters_service import EngineParametersService
        from app.services.engine_configuration_service import EngineConfigurationService, TaskType
        
        parameters_service = EngineParametersService.get_instance()
        parameters_service.load()
        config_service = EngineConfigurationService(self.config)
        
        # Get recommended defaults for each task
        tasks_parameters = {
            "evaluation": config_service.get_recommended_defaults(TaskType.EVALUATION),
            "game_analysis": config_service.get_recommended_defaults(TaskType.GAME_ANALYSIS),
            "manual_analysis": config_service.get_recommended_defaults(TaskType.MANUAL_ANALYSIS)
        }
        
        # Save task parameters
        parameters_service.set_all_task_parameters(str(self.engine_path), tasks_parameters)
        
        # Add engine through controller
        success, message, engine = self.engine_controller.add_engine(
            self.engine_path,
            self.engine_name,
            self.engine_author,
            self.engine_version
        )
        
        if success:
            self.accept()
        else:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Add Engine Failed",
                f"Failed to add engine:\n\n{message}",
                self
            )
    
    def closeEvent(self, event) -> None:
        """Handle dialog close event."""
        # Cancel validation thread if running
        if self.validation_thread and self.validation_thread.isRunning():
            self.validation_thread.terminate()
            self.validation_thread.wait()
        event.accept()

