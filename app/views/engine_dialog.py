"""Engine dialog for adding UCI chess engines."""

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
from PyQt6.QtGui import QResizeEvent, QShowEvent, QMoveEvent, QPalette, QColor
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
        
        # Engine path selection
        path_layout = QHBoxLayout()
        path_label = QLabel("Engine Path:")
        path_label.setMinimumWidth(100)
        self.path_input = QLineEdit()
        self.path_input.setReadOnly(True)
        self.path_input.setPlaceholderText("Select engine executable...")
        browse_button = QPushButton("...")
        browse_button.clicked.connect(self._browse_engine_path)
        
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(browse_button)
        layout.addLayout(path_layout)
        
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
        name_label = QLabel("Name:")
        name_label.setMinimumWidth(100)
        name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.name_input = QLineEdit()
        self.name_input.setReadOnly(True)
        self.name_input.setPlaceholderText("Will be populated after validation...")
        self.name_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        engine_info_layout.addLayout(name_layout)
        
        # Author
        author_layout = QHBoxLayout()
        author_layout.setContentsMargins(0, 0, 0, 0)
        author_layout.setSpacing(0)
        author_label = QLabel("Author:")
        author_label.setMinimumWidth(100)
        author_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.author_input = QLineEdit()
        self.author_input.setReadOnly(True)
        self.author_input.setPlaceholderText("Will be populated after validation...")
        self.author_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        author_layout.addWidget(author_label)
        author_layout.addWidget(self.author_input)
        engine_info_layout.addLayout(author_layout)
        
        # Version (derived from author/name)
        version_layout = QHBoxLayout()
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(0)
        version_label = QLabel("Version:")
        version_label.setMinimumWidth(100)
        version_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.version_input = QLineEdit()
        self.version_input.setReadOnly(True)
        self.version_input.setPlaceholderText("Will be populated after validation...")
        self.version_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        version_layout.addWidget(version_label)
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
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
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
        
        # Labels styling
        labels_config = dialog_config.get('labels', {})
        label_font_family = labels_config.get('font_family', 'Helvetica Neue')
        label_font_size = labels_config.get('font_size', 11)
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        label_min_width = labels_config.get('minimum_width', 100)
        
        # Apply label styling to all labels
        for label in self.findChildren(QLabel):
            label.setStyleSheet(
                f"font-family: {label_font_family}; "
                f"font-size: {label_font_size}pt; "
                f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
                f"margin: 0px;"
                f"padding: 0px;"
            )
            label.setMinimumWidth(label_min_width)
        
        # Input widgets styling (QLineEdit)
        input_config = dialog_config.get('input_widgets', {})
        input_bg = input_config.get('background_color', [45, 45, 50])
        input_text = input_config.get('text_color', [200, 200, 200])
        input_border = input_config.get('border_color', [60, 60, 65])
        input_border_width = input_config.get('border_width', 1)
        input_border_radius = input_config.get('border_radius', 3)
        input_padding = input_config.get('padding', [2, 6, 2, 6])
        input_font_family = input_config.get('font_family', 'Helvetica Neue')
        input_font_size = input_config.get('font_size', 11)
        
        input_stylesheet = f"""
            QLineEdit {{
                background-color: rgb({input_bg[0]}, {input_bg[1]}, {input_bg[2]});
                color: rgb({input_text[0]}, {input_text[1]}, {input_text[2]});
                border: {input_border_width}px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});
                border-radius: {input_border_radius}px;
                padding: {input_padding[0]}px {input_padding[1]}px {input_padding[2]}px {input_padding[3]}px;
                font-family: {input_font_family};
                font-size: {input_font_size}pt;
                margin: 0px;
            }}
            QLineEdit:hover {{
                border: {input_border_width}px solid rgb({min(255, input_border[0] + 20)}, {min(255, input_border[1] + 20)}, {min(255, input_border[2] + 20)});
            }}
            QLineEdit:focus {{
                border: {input_border_width}px solid rgb(70, 90, 130);
            }}
        """
        
        # Apply input widget styling
        for line_edit in self.findChildren(QLineEdit):
            line_edit.setStyleSheet(input_stylesheet)
        
        # Group box styling
        group_box_config = dialog_config.get('group_box', {})
        group_border_color = group_box_config.get('border_color', [60, 60, 65])
        group_border_radius = group_box_config.get('border_radius', 5)
        group_bg_color = group_box_config.get('background_color', [40, 40, 45])
        group_title_color = group_box_config.get('title_color', [240, 240, 240])
        group_title_font_family = group_box_config.get('title_font_family', 'Helvetica Neue')
        group_title_font_size = group_box_config.get('title_font_size', 11)
        group_margin_top = group_box_config.get('margin_top', 10)
        group_padding_top = group_box_config.get('padding_top', 10)
        group_title_left = group_box_config.get('title_left', 10)
        group_title_padding = group_box_config.get('title_padding', [0, 5])
        
        group_style = (
            f"QGroupBox {{"
            f"border: 1px solid rgb({group_border_color[0]}, {group_border_color[1]}, {group_border_color[2]});"
            f"border-radius: {group_border_radius}px;"
            f"margin-top: {group_margin_top}px;"
            f"padding-top: {group_padding_top}px;"
            f"background-color: rgb({group_bg_color[0]}, {group_bg_color[1]}, {group_bg_color[2]});"
            f"}}"
            f"QGroupBox::title {{"
            f"font-family: \"{group_title_font_family}\";"
            f"font-size: {group_title_font_size}pt;"
            f"color: rgb({group_title_color[0]}, {group_title_color[1]}, {group_title_color[2]});"
            f"subcontrol-origin: margin;"
            f"left: {group_title_left}px;"
            f"padding: {group_title_padding[0]} {group_title_padding[1]}px;"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
        
        # Buttons styling (match Classification Settings Dialog template)
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        # Get colors from dialog background and labels for consistency
        dialog_bg = dialog_config.get('background_color', [40, 40, 45])
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        label_font_size = labels_config.get('font_size', 11)
        # Use border color from input widgets for consistency
        input_border = input_config.get('border_color', [60, 60, 65])
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({dialog_bg[0] + button_bg_offset}, {dialog_bg[1] + button_bg_offset}, {dialog_bg[2] + button_bg_offset});"
            f"border: 1px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"font-size: {label_font_size}pt;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({dialog_bg[0] + button_hover_offset}, {dialog_bg[1] + button_hover_offset}, {dialog_bg[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({dialog_bg[0] + button_pressed_offset}, {dialog_bg[1] + button_pressed_offset}, {dialog_bg[2] + button_pressed_offset});"
            f"}}"
            f"QPushButton:disabled {{"
            f"background-color: rgb({(dialog_bg[0] + button_bg_offset) // 2}, {(dialog_bg[1] + button_bg_offset) // 2}, {(dialog_bg[2] + button_bg_offset) // 2});"
            f"color: rgb({label_text_color[0] // 2}, {label_text_color[1] // 2}, {label_text_color[2] // 2});"
            f"}}"
        )
        
        # Apply button styling to all buttons except Browse button (which is part of file selection control)
        for button in self.findChildren(QPushButton):
            # Skip Browse button - it's part of the file selection control, not a main dialog button
            if button.text() == "...":
                continue
            button.setStyleSheet(button_style)
        
        # Style Browse button separately as a smaller control button that matches input field height
        # Get input field padding to calculate height
        input_padding = input_config.get('padding', [2, 6, 2, 6])
        input_font_size = input_config.get('font_size', 11)
        # Calculate approximate input field height: font size + top padding + bottom padding + border
        # We'll use a fixed height that matches typical input field height
        input_field_height = input_font_size + input_padding[0] + input_padding[2] + (input_border_width * 2) + 4  # +4 for line height
        
        browse_button_style = (
            f"QPushButton {{"
            f"background-color: rgb({dialog_bg[0] + button_bg_offset}, {dialog_bg[1] + button_bg_offset}, {dialog_bg[2] + button_bg_offset});"
            f"border: 1px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"font-size: {input_font_size}pt;"
            f"padding: {input_padding[0]}px {input_padding[1]}px {input_padding[2]}px {input_padding[3]}px;"
            f"min-height: {input_field_height}px;"
            f"max-height: {input_field_height}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({dialog_bg[0] + button_hover_offset}, {dialog_bg[1] + button_hover_offset}, {dialog_bg[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({dialog_bg[0] + button_pressed_offset}, {dialog_bg[1] + button_pressed_offset}, {dialog_bg[2] + button_pressed_offset});"
            f"}}"
        )
        
        # Apply Browse button styling
        for button in self.findChildren(QPushButton):
            if button.text() == "...":
                button.setStyleSheet(browse_button_style)
                break
        
    
    def _browse_engine_path(self) -> None:
        """Browse for engine executable file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select UCI Engine Executable",
            "",
            "Executable Files (*.exe);;All Files (*)"
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

