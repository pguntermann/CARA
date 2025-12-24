"""Engine configuration dialog for setting engine parameters per task."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QPushButton,
    QScrollArea,
    QGroupBox,
    QFormLayout,
    QSizePolicy,
    QApplication,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIntValidator, QResizeEvent, QShowEvent, QMoveEvent, QWheelEvent
from pathlib import Path
from typing import Optional, Dict, Any, List
from app.utils.font_utils import resolve_font_family, scale_font_size


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events to prevent accidental value changes."""
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Override wheel event to ignore it completely."""
        event.ignore()


class EngineConfigurationDialog(QDialog):
    """Dialog for configuring engine parameters per task."""
    
    def __init__(self, config: Dict[str, Any], engine_id: str, engine_controller, parent=None) -> None:
        """Initialize the engine configuration dialog.
        
        Args:
            config: Configuration dictionary.
            engine_id: ID of the engine to configure.
            engine_controller: EngineController instance.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.engine_id = engine_id
        self.engine_controller = engine_controller
        
        
        # Get engine data
        engine_model = engine_controller.get_engine_model()
        engine = engine_model.get_engine(engine_id)
        if not engine:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Engine Not Found",
                f"Engine with ID '{engine_id}' not found.",
                self
            )
            self.reject()
            return
        
        self.engine = engine
        self.engine_path = Path(engine.path)
        
        # Load engine options from engine_parameters.json
        from app.services.engine_parameters_service import EngineParametersService
        self.parameters_service = EngineParametersService.get_instance()
        self.parameters_service.load()
        self.engine_options = self.parameters_service.get_engine_options(str(self.engine_path))
        
        # Initialize engine configuration service for validation and defaults
        from app.services.engine_configuration_service import EngineConfigurationService, TaskType
        self.config_service = EngineConfigurationService(config)
        self.TaskType = TaskType  # Store reference for use in methods
        
        # Task constants
        self.TASK_EVALUATION = "evaluation"
        self.TASK_GAME_ANALYSIS = "game_analysis"
        self.TASK_MANUAL_ANALYSIS = "manual_analysis"
        
        # Store widgets for each task: {task: {param_name: widget}}
        self.task_widgets: Dict[str, Dict[str, Any]] = {
            self.TASK_EVALUATION: {},
            self.TASK_GAME_ANALYSIS: {},
            self.TASK_MANUAL_ANALYSIS: {}
        }
        # Track per-task UI sections for dynamic sizing
        self._task_sections: Dict[str, Dict[str, Any]] = {}
        
        # Store fixed size - set it BEFORE layout is set up
        # Read size from config, accounting for Windows frame margins
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        width = dialog_config.get('width', 600)
        height = dialog_config.get('height', 792)  # Default: 800 - 8 (bottom frame margin)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size BEFORE UI setup to prevent layout from requesting more space
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle(f"Engine Configuration - {engine.name}")
    
    def showEvent(self, event: QShowEvent) -> None:
        """Override show event to set fixed size after layout is calculated."""
        super().showEvent(event)
        # Re-enforce fixed size after dialog is shown
        # The resizeEvent handler will catch and correct any resize attempts
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        QTimer.singleShot(0, self._adjust_layouts)
    
    def sizeHint(self) -> QSize:
        """Return the fixed size as the size hint to prevent layout from expanding."""
        return self._fixed_size
    
    def minimumSizeHint(self) -> QSize:
        """Return the fixed size as the minimum size hint."""
        return self._fixed_size
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Override resize event to prevent resizing."""
        if event.size() != self._fixed_size:
            # Immediately restore fixed size using setGeometry to prevent layout expansion
            event.ignore()
            self.blockSignals(True)
            current_pos = self.pos()
            self.setGeometry(current_pos.x(), current_pos.y(), self._fixed_size.width(), self._fixed_size.height())
            self.setFixedSize(self._fixed_size)
            self.setMinimumSize(self._fixed_size)
            self.setMaximumSize(self._fixed_size)
            self.blockSignals(False)
            return
        event.accept()
    
    def moveEvent(self, event: QMoveEvent) -> None:
        """Override move event."""
        super().moveEvent(event)

    def _adjust_layouts(self) -> None:
        """Adjust tab widget and scroll area heights after layout is ready."""
        self._adjust_tab_widget_height()
        self._adjust_scroll_areas()

    def _adjust_tab_widget_height(self) -> None:
        """Ensure the tab widget height fits within the fixed dialog."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        layout_config = dialog_config.get('layout', {})
        layout_margins = layout_config.get('margins', [10, 10, 10, 10])
        layout_spacing = layout_config.get('spacing', 10)
        top_margin = layout_margins[1]
        bottom_margin = layout_margins[3]

        header_height = self.info_label.height() or self.info_label.sizeHint().height()
        button_height = max(
            self.ok_button.height() or self.ok_button.sizeHint().height(),
            self.cancel_button.height() or self.cancel_button.sizeHint().height()
        )

        # There are two spacings in the vertical layout (between header/tab and tab/buttons)
        total_spacing = layout_spacing * 2

        available_height = (
            self._fixed_size.height()
            - top_margin
            - bottom_margin
            - header_height
            - button_height
            - total_spacing
        )

        # Ensure we don't set negative heights
        available_height = max(available_height, 100)

        self.tab_widget.setMinimumHeight(available_height)
        self.tab_widget.setMaximumHeight(available_height)

    def _adjust_scroll_areas(self) -> None:
        """Ensure each task scroll area fits within its tab."""
        for task, info in self._task_sections.items():
            tab = info['tab']
            scroll = info['scroll']
            copy_group = info['copy_group']
            common_group = info['common_group']
            tab_layout_margins = info['tab_layout_margins']
            tab_layout_spacing = info['tab_layout_spacing']
            top_spacer = info['top_spacer']
            group_margin_top = info['group_margin_top']
            group_padding_top = info['group_padding_top']
            group_border_width = info['group_border_width']
            min_height = info['min_height']

            tab_height = tab.height()
            if tab_height <= 0:
                continue

            used_height = (
                tab_layout_margins[1]  # top margin
                + top_spacer
                + copy_group.sizeHint().height()
                + tab_layout_spacing
                + common_group.sizeHint().height()
                + tab_layout_spacing
                + group_margin_top
                + group_padding_top
                + (group_border_width * 2)
                + tab_layout_spacing  # spacing before bottom margin
                + tab_layout_margins[3]  # bottom margin
            )

            available = tab_height - used_height
            available = max(available, min_height)
            scroll.setFixedHeight(available)
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Get layout spacing and margins from config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        layout_config = dialog_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 10)
        layout_margins = layout_config.get('margins', [10, 10, 10, 10])
        
        layout = QVBoxLayout(self)
        layout.setSpacing(layout_spacing)
        # Prevent layout from resizing the dialog
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Engine info header
        self.info_label = QLabel(f"<b>Engine:</b> {self.engine.name}<br><b>Path:</b> {self.engine_path}")
        self.info_label.setWordWrap(True)
        self.info_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.info_label)
        
        # Tab widget for tasks
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(False)  # Disable document mode for better control
        self.tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Create tabs for each task
        self._create_task_tab(self.TASK_EVALUATION, "Evaluation")
        self._create_task_tab(self.TASK_GAME_ANALYSIS, "Game Analysis")
        self._create_task_tab(self.TASK_MANUAL_ANALYSIS, "Manual Analysis")
        
        # Configure QTabBar after tabs are added
        self._configure_tab_bar()
        
        layout.addWidget(self.tab_widget, stretch=1)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.ok_button = QPushButton("Save Changes")
        self.ok_button.clicked.connect(self._on_ok_clicked)
        button_layout.addWidget(self.ok_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
    
    def _create_task_tab(self, task: str, task_label: str) -> None:
        """Create a tab for a specific task.
        
        Args:
            task: Task identifier.
            task_label: Display label for the task.
        """
        tab = QWidget()
        # Set background color immediately when tab is created
        # This ensures the first tab has the correct background from the start
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        tabs_config = dialog_config.get('tabs', {})
        tabs_layout_config = dialog_config.get('tabs_layout', {})
        groups_config = dialog_config.get('groups', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        from PyQt6.QtGui import QPalette, QColor
        tab.setAutoFillBackground(True)
        tab_palette = tab.palette()
        tab_palette.setColor(tab.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_palette.setColor(QPalette.ColorRole.Window, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_palette.setColor(QPalette.ColorRole.Base, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab.setPalette(tab_palette)
        
        tab_layout = QVBoxLayout(tab)
        tab_layout_spacing = tabs_layout_config.get('spacing', 15)
        tab_layout_margins = tabs_layout_config.get('margins', [15, 10, 15, 10])
        tab_layout.setSpacing(tab_layout_spacing)
        # Add padding around the tab content to prevent group boxes from touching borders
        # Left, Top, Right, Bottom margins
        tab_layout.setContentsMargins(tab_layout_margins[0], tab_layout_margins[1], tab_layout_margins[2], tab_layout_margins[3])
        
        # Add a small spacer at the top to create space between tab bar and first group
        top_spacer = tabs_layout_config.get('top_spacer', 5)
        tab_layout.addSpacing(top_spacer)
        
        # Copy parameters section
        copy_group = QGroupBox("Copy Parameters")
        copy_layout = QHBoxLayout()
        copy_layout_spacing = tabs_layout_config.get('copy_layout_spacing', 10)
        copy_layout.setSpacing(copy_layout_spacing)
        
        # Create buttons to copy from other tasks
        other_tasks = [t for t in [self.TASK_EVALUATION, self.TASK_GAME_ANALYSIS, self.TASK_MANUAL_ANALYSIS] if t != task]
        for other_task in other_tasks:
            # Format task name for button label (e.g., "game_analysis" -> "Game Analysis")
            task_name = other_task.replace("_", " ").title()
            copy_button = QPushButton(f"Copy {task_name}")
            # Use a lambda with default arguments to capture the correct values
            copy_button.clicked.connect(
                lambda checked, src=other_task, dst=task: self._copy_parameters(src, dst)
            )
            copy_layout.addWidget(copy_button)
        
        # Add stretch to push reset button to the right
        copy_layout.addStretch()
        
        # Add "Reset to Engine Defaults" button (right-aligned)
        reset_button = QPushButton("Reset to Engine Defaults")
        reset_button.clicked.connect(lambda checked, t=task: self._reset_to_defaults(t))
        copy_layout.addWidget(reset_button)
        copy_group.setLayout(copy_layout)
        tab_layout.addWidget(copy_group)
        
        # Common parameters section
        common_group = QGroupBox("Common Parameters")
        common_layout = QFormLayout()
        common_layout_spacing = tabs_layout_config.get('common_layout_spacing', 10)
        common_layout.setSpacing(common_layout_spacing)
        # Set field growth policy to make fields expand
        common_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Set alignment for macOS compatibility (left-align labels and form)
        common_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        common_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        # Get saved parameters for this task (with fallback to recommended defaults)
        task_type_map = {
            self.TASK_EVALUATION: self.TaskType.EVALUATION,
            self.TASK_GAME_ANALYSIS: self.TaskType.GAME_ANALYSIS,
            self.TASK_MANUAL_ANALYSIS: self.TaskType.MANUAL_ANALYSIS
        }
        task_type = task_type_map.get(task, self.TaskType.EVALUATION)
        recommended_defaults = self.config_service.get_recommended_defaults(task_type)
        
        # Load saved parameters from engine_parameters.json
        saved_params = self.parameters_service.get_task_parameters(str(self.engine_path), task)
        
        # Use saved values if available, otherwise use recommended defaults
        threads_value = saved_params.get("threads", recommended_defaults.get("threads", 1))
        depth_value = saved_params.get("depth", recommended_defaults.get("depth", 0))
        movetime_value = saved_params.get("movetime", recommended_defaults.get("movetime", 0))
        
        # Threads
        threads_edit = QLineEdit()
        threads_edit.setText(str(threads_value))
        threads_edit.setValidator(QIntValidator(1, 512))
        threads_edit.setToolTip("Number of threads for engine analysis (1-512)")
        threads_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        common_layout.addRow("Threads:", threads_edit)
        self.task_widgets[task]["threads"] = threads_edit
        
        # Depth
        depth_edit = QLineEdit()
        depth_edit.setText(str(depth_value))
        depth_edit.setValidator(QIntValidator(0, 100))
        depth_edit.setToolTip("Maximum search depth (0 = unlimited, max 100)")
        depth_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        common_layout.addRow("Max Depth:", depth_edit)
        self.task_widgets[task]["depth"] = depth_edit
        
        # Movetime (in milliseconds)
        movetime_edit = QLineEdit()
        movetime_edit.setText(str(movetime_value))
        movetime_edit.setValidator(QIntValidator(0, 3600000))  # 1 hour max
        movetime_edit.setToolTip("Maximum time per move in milliseconds (0 = unlimited, max 3600000)")
        movetime_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        common_layout.addRow("Move Time:", movetime_edit)
        self.task_widgets[task]["movetime"] = movetime_edit
        
        common_group.setLayout(common_layout)
        tab_layout.addWidget(common_group)
        
        # Engine-specific parameters section
        if self.engine_options:
            engine_params_group = QGroupBox("Engine-Specific Parameters")
            engine_params_layout = QFormLayout()
            engine_params_layout_spacing = tabs_layout_config.get('engine_params_layout_spacing', 10)
            engine_params_layout.setSpacing(engine_params_layout_spacing)
            # Set alignment for macOS compatibility (left-align labels and form)
            engine_params_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            engine_params_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            
            # Create scroll area for engine parameters (in case there are many)
            scroll_area_config = dialog_config.get('scroll_area', {})
            min_height = scroll_area_config.get('min_height', 200)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setMinimumHeight(min_height)
            scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            scroll_widget = QWidget()
            scroll_layout = QFormLayout(scroll_widget)
            scroll_layout_spacing = tabs_layout_config.get('scroll_layout_spacing', 10)
            scroll_layout.setSpacing(scroll_layout_spacing)
            # Set field growth policy to make fields expand
            scroll_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            # Set alignment for macOS compatibility (left-align labels and form)
            scroll_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            scroll_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            scroll_layout_margins = tabs_layout_config.get('scroll_layout_margins', [0, 0, 0, 0])
            scroll_layout.setContentsMargins(
                scroll_layout_margins[0],
                scroll_layout_margins[1],
                scroll_layout_margins[2],
                scroll_layout_margins[3],
            )
            
            # Add widgets for each engine option
            for option in self.engine_options:
                option_name = option.get("name", "")
                option_type = option.get("type", "")
                option_default = option.get("default")
                option_min = option.get("min")
                option_max = option.get("max")
                option_var = option.get("var", [])
                
                if not option_name or not option_type:
                    continue
                
                # Skip button type options - they don't need configuration
                if option_type == "button":
                    continue
                
                # Skip "Threads" - it's already in the common parameters section
                if option_name == "Threads":
                    continue
                
                # Get saved value for this option (if available)
                saved_value = saved_params.get(option_name, option_default)
                
                # Create appropriate widget based on option type
                widget = self._create_option_widget(option_type, saved_value, option_min, option_max, option_var)
                if widget:
                    scroll_layout.addRow(f"{option_name}:", widget)
                    # Store widget reference for later retrieval
                    self.task_widgets[task][f"engine_option_{option_name}"] = widget
            
            scroll_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            scroll.setWidget(scroll_widget)
            
            engine_params_group_layout = QVBoxLayout()
            engine_params_group_layout.setContentsMargins(0, 0, 0, 0)
            engine_params_group_layout.addWidget(scroll)
            engine_params_group.setLayout(engine_params_group_layout)
            engine_params_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            tab_layout.addWidget(engine_params_group, stretch=1)

            # Track sections for dynamic sizing
            self._task_sections[task] = {
                'tab': tab,
                'scroll': scroll,
                'copy_group': copy_group,
                'common_group': common_group,
                'tab_layout_margins': tab_layout_margins,
                'tab_layout_spacing': tab_layout_spacing,
                'top_spacer': top_spacer,
                'group_margin_top': groups_config.get('margin_top', 8),
                'group_padding_top': groups_config.get('padding_top', 12),
                'group_border_width': groups_config.get('border_width', 1),
                'min_height': min_height,
            }
        else:
            # No engine options available
            no_options_label = QLabel("No engine-specific parameters available.\nEngine options will be loaded after validation.")
            no_options_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tab_layout.addWidget(no_options_label)
            # Store reference for styling
            if not hasattr(self, '_no_options_labels'):
                self._no_options_labels = []
            self._no_options_labels.append(no_options_label)
        
        # Add tab to tab widget
        self.tab_widget.addTab(tab, task_label)
    
    def _create_option_widget(self, option_type: str, default: Any, min_val: Optional[int], 
                              max_val: Optional[int], var_values: List[str]) -> Optional[Any]:
        """Create a widget for an engine option based on its type.
        
        Args:
            option_type: Type of option (spin, check, combo, string, button).
            default: Default value.
            min_val: Minimum value (for spin).
            max_val: Maximum value (for spin).
            var_values: List of possible values (for combo).
            
        Returns:
            Widget for the option, or None if type is not supported.
        """
        if option_type == "spin":
            line_edit = QLineEdit()
            line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # Set up validator with min/max values
            if min_val is not None and max_val is not None:
                line_edit.setValidator(QIntValidator(min_val, max_val))
            elif min_val is not None:
                line_edit.setValidator(QIntValidator(min_val, 2147483647))  # Max int
            elif max_val is not None:
                line_edit.setValidator(QIntValidator(-2147483648, max_val))  # Min int
            if default is not None:
                line_edit.setText(str(int(default)))
            return line_edit
        
        elif option_type == "check":
            check = QCheckBox()
            if default is not None:
                check.setChecked(bool(default))
            return check
        
        elif option_type == "combo":
            combo = NoWheelComboBox()
            if var_values:
                combo.addItems(var_values)
                if default is not None and str(default) in var_values:
                    combo.setCurrentText(str(default))
            return combo
        
        elif option_type == "string":
            line_edit = QLineEdit()
            line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if default is not None:
                line_edit.setText(str(default))
            return line_edit
        
        elif option_type == "button":
            # Button options don't have values, they trigger actions
            # For now, we'll skip them or show a label
            label = QLabel("(Button option - no configuration needed)")
            return label
        
        return None
    
    def _copy_parameters(self, source_task: str, target_task: str) -> None:
        """Copy parameters from one task to another.
        
        Args:
            source_task: Task identifier to copy from.
            target_task: Task identifier to copy to.
        """
        # Get progress service for status updates
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        # Format task names for display
        source_task_name = source_task.replace("_", " ").title()
        target_task_name = target_task.replace("_", " ").title()
        
        # Show progress bar and set initial status
        progress_service.show_progress()
        progress_service.set_status(f"Copying parameters from {source_task_name} to {target_task_name}...")
        QApplication.processEvents()  # Process events to show the status
        
        # Copy common parameters
        if "threads" in self.task_widgets[source_task] and "threads" in self.task_widgets[target_task]:
            source_text = self.task_widgets[source_task]["threads"].text().strip()
            self.task_widgets[target_task]["threads"].setText(source_text)
        
        if "depth" in self.task_widgets[source_task] and "depth" in self.task_widgets[target_task]:
            source_text = self.task_widgets[source_task]["depth"].text().strip()
            self.task_widgets[target_task]["depth"].setText(source_text)
        
        if "movetime" in self.task_widgets[source_task] and "movetime" in self.task_widgets[target_task]:
            source_text = self.task_widgets[source_task]["movetime"].text().strip()
            self.task_widgets[target_task]["movetime"].setText(source_text)
        
        # Copy engine-specific parameters
        for key, source_widget in self.task_widgets[source_task].items():
            if key.startswith("engine_option_") and key in self.task_widgets[target_task]:
                target_widget = self.task_widgets[target_task][key]
                
                if isinstance(source_widget, QLineEdit) and isinstance(target_widget, QLineEdit):
                    target_widget.setText(source_widget.text())
                elif isinstance(source_widget, QCheckBox) and isinstance(target_widget, QCheckBox):
                    target_widget.setChecked(source_widget.isChecked())
                elif isinstance(source_widget, QComboBox) and isinstance(target_widget, QComboBox):
                    target_widget.setCurrentText(source_widget.currentText())
        
        # Hide progress bar and set final status
        progress_service.hide_progress()
        progress_service.set_status(f"Parameters copied from {source_task_name} to {target_task_name}")
        QApplication.processEvents()  # Process events to update status
    
    def _reset_to_defaults(self, task: str) -> None:
        """Reset parameters to engine defaults for a specific task.
        
        This method refreshes the engine options from the engine itself,
        then resets all parameters to their defaults.
        
        Args:
            task: Task identifier to reset.
        """
        # Get progress service for status updates
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        # Show progress bar and set initial status
        progress_service.show_progress()
        progress_service.set_status("Refreshing engine options from engine...")
        QApplication.processEvents()  # Process events to show the status
        
        try:
            # Refresh engine options from the engine (without saving to file)
            # This only updates the in-memory options for UI display
            validation_service = self.engine_controller.validation_service
            success, refreshed_options = validation_service.refresh_engine_options(
                self.engine_path,
                enable_debug=False,
                save_to_file=False  # Don't save to file - only update UI
            )
            
            if success and refreshed_options:
                # Update in-memory options with fresh defaults from engine
                self.engine_options = refreshed_options
                progress_service.set_status("Resetting parameters to engine defaults...")
                QApplication.processEvents()  # Process events to update status
            else:
                # If refresh failed, show error and use existing options
                progress_service.hide_progress()
                progress_service.set_status("Failed to refresh engine options. Using cached options.")
                from app.views.message_dialog import MessageDialog
                MessageDialog.show_warning(
                    self.config,
                    "Refresh Failed",
                    "Failed to refresh engine options. Using cached options.",
                    self
                )
                # Continue with existing options
                return
        except Exception as e:
            progress_service.hide_progress()
            progress_service.set_status(f"Error refreshing engine options: {str(e)}")
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Refresh Error",
                f"Error refreshing engine options: {str(e)}",
                self
            )
            # Continue with existing options
            return
        
        # Get recommended defaults for this task
        task_type_map = {
            self.TASK_EVALUATION: self.TaskType.EVALUATION,
            self.TASK_GAME_ANALYSIS: self.TaskType.GAME_ANALYSIS,
            self.TASK_MANUAL_ANALYSIS: self.TaskType.MANUAL_ANALYSIS
        }
        task_type = task_type_map.get(task, self.TaskType.EVALUATION)
        recommended_defaults = self.config_service.get_recommended_defaults(task_type)
        
        # Reset common parameters to recommended defaults
        if "threads" in self.task_widgets[task]:
            self.task_widgets[task]["threads"].setText(str(recommended_defaults.get("threads", 1)))
        
        if "depth" in self.task_widgets[task]:
            self.task_widgets[task]["depth"].setText(str(recommended_defaults.get("depth", 0)))
        
        if "movetime" in self.task_widgets[task]:
            self.task_widgets[task]["movetime"].setText(str(recommended_defaults.get("movetime", 0)))
        
        # Reset engine-specific parameters to defaults
        for option in self.engine_options:
            option_name = option.get("name", "")
            option_type = option.get("type", "")
            option_default = option.get("default")
            
            if not option_name or not option_type:
                continue
            
            # Skip button type options
            if option_type == "button":
                continue
            
            key = f"engine_option_{option_name}"
            if key in self.task_widgets[task]:
                widget = self.task_widgets[task][key]
                
                if isinstance(widget, QLineEdit):
                    if option_default is not None:
                        widget.setText(str(option_default))
                    else:
                        widget.setText("")
                elif isinstance(widget, QCheckBox):
                    if option_default is not None:
                        widget.setChecked(bool(option_default))
                    else:
                        widget.setChecked(False)
                elif isinstance(widget, QComboBox):
                    if option_default is not None and str(option_default) in [widget.itemText(i) for i in range(widget.count())]:
                        widget.setCurrentText(str(option_default))
                    elif widget.count() > 0:
                        widget.setCurrentIndex(0)
        
        # Hide progress bar and set final status
        progress_service.hide_progress()
        progress_service.set_status("Parameters reset to engine defaults")
        QApplication.processEvents()  # Process events to update status
    
    def _on_ok_clicked(self) -> None:
        """Handle OK button click."""
        # Get progress service for status updates
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        # Show progress bar and set initial status
        progress_service.show_progress()
        progress_service.set_status("Validating parameters...")
        QApplication.processEvents()  # Process events to show the status
        
        # Validate all task parameters
        all_validation_results = {}
        task_type_map = {
            self.TASK_EVALUATION: self.TaskType.EVALUATION,
            self.TASK_GAME_ANALYSIS: self.TaskType.GAME_ANALYSIS,
            self.TASK_MANUAL_ANALYSIS: self.TaskType.MANUAL_ANALYSIS
        }
        
        for task in [self.TASK_EVALUATION, self.TASK_GAME_ANALYSIS, self.TASK_MANUAL_ANALYSIS]:
            task_type = task_type_map[task]
            parameters = self._get_task_parameters(task)
            validation_result = self.config_service.validate_parameters(task_type, parameters)
            all_validation_results[task] = validation_result
        
        # Check if there are any validation issues
        has_errors = any(result.has_errors for result in all_validation_results.values())
        has_warnings = any(result.has_warnings for result in all_validation_results.values())
        has_info = any(any(issue.severity.value == "info" for issue in result.issues) for result in all_validation_results.values())
        
        if has_errors or has_warnings or has_info:
            # Hide progress bar temporarily while showing validation dialog
            progress_service.hide_progress()
            # Show validation dialog
            if not self._show_validation_dialog(all_validation_results):
                # User cancelled, don't save
                return
            # Show progress bar again for saving
            progress_service.show_progress()
            progress_service.set_status("Saving parameters...")
            QApplication.processEvents()  # Process events to show the status
        
        # Save parameters to engine_parameters.json
        progress_service.set_status("Saving parameters...")
        QApplication.processEvents()  # Process events to update status
        
        tasks_parameters = {}
        for task in [self.TASK_EVALUATION, self.TASK_GAME_ANALYSIS, self.TASK_MANUAL_ANALYSIS]:
            parameters = self._get_task_parameters(task)
            # Only save common parameters (threads, depth, movetime) and engine-specific options
            # Separate common parameters from engine-specific options
            task_params = {
                "threads": parameters.get("threads", 1),
                "depth": parameters.get("depth", 0),
                "movetime": parameters.get("movetime", 0)
            }
            # Add engine-specific options (all keys that are not common parameters)
            for key, value in parameters.items():
                if key not in ["threads", "depth", "movetime"]:
                    task_params[key] = value
            
            tasks_parameters[task] = task_params
        
        # Save to file
        self.parameters_service.set_all_task_parameters(str(self.engine_path), tasks_parameters)
        
        # Hide progress bar and set final status
        progress_service.hide_progress()
        progress_service.set_status(f"Engine configuration saved for {self.engine.name}")
        QApplication.processEvents()  # Process events to update status
        
        # Accept the dialog
        self.accept()
    
    def _show_validation_dialog(self, validation_results: Dict[str, Any]) -> bool:
        """Show validation dialog with issues and get user confirmation.
        
        Args:
            validation_results: Dictionary mapping task names to ValidationResult objects.
            
        Returns:
            True if user confirmed to save despite issues, False if user cancelled.
        """
        from app.services.engine_configuration_service import ValidationSeverity
        
        # Get validation dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        validation_config = dialog_config.get('validation_dialog', {})
        validation_layout_config = validation_config.get('layout', {})
        validation_title_config = validation_config.get('title', {})
        validation_desc_config = validation_config.get('description', {})
        validation_task_header_config = validation_config.get('task_header', {})
        validation_scroll_config = validation_config.get('scroll_area', {})
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Parameter Validation")
        dialog_width = validation_config.get('width', 600)
        dialog_height = validation_config.get('height', 400)
        # Make dialog non-resizable by setting fixed size
        dialog.setFixedSize(dialog_width, dialog_height)
        
        # Set dialog background color
        tabs_config = dialog_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        from PyQt6.QtGui import QPalette, QColor
        dialog.setAutoFillBackground(True)
        dialog_palette = dialog.palette()
        dialog_palette.setColor(dialog.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        dialog.setPalette(dialog_palette)
        
        layout = QVBoxLayout(dialog)
        layout_spacing = validation_layout_config.get('spacing', 15)
        layout_margins = validation_layout_config.get('margins', [15, 15, 15, 15])
        layout.setSpacing(layout_spacing)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Title
        title_font_size = scale_font_size(validation_title_config.get('font_size', 14))
        title_padding = validation_title_config.get('padding', 5)
        title_label = QLabel("<b>Parameter Validation Issues</b>")
        title_label.setStyleSheet(f"font-size: {title_font_size}pt; padding: {title_padding}px;")
        layout.addWidget(title_label)
        
        # Description
        desc_font_size = scale_font_size(validation_desc_config.get('font_size', 11))
        desc_padding = validation_desc_config.get('padding', 5)
        desc_text_color = validation_desc_config.get('text_color', [200, 200, 200])
        desc_label = QLabel(
            "The following issues were found with your parameter settings. "
            "You can choose to save anyway or cancel to fix the issues."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"font-size: {desc_font_size}pt; "
            f"padding: {desc_padding}px; "
            f"color: rgb({desc_text_color[0]}, {desc_text_color[1]}, {desc_text_color[2]});"
        )
        layout.addWidget(desc_label)
        
        # Scroll area for issues
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_min_height = validation_scroll_config.get('min_height', 250)
        scroll.setMinimumHeight(scroll_min_height)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)
        
        # Task names for display
        task_names = {
            self.TASK_EVALUATION: "Evaluation",
            self.TASK_GAME_ANALYSIS: "Game Analysis",
            self.TASK_MANUAL_ANALYSIS: "Manual Analysis"
        }
        
        # Add issues for each task
        for task, result in validation_results.items():
            if not result.issues:
                continue
            
            # Task header
            task_header_font_size = scale_font_size(validation_task_header_config.get('font_size', 12))
            task_header_padding = validation_task_header_config.get('padding', 5)
            task_header_text_color = validation_task_header_config.get('text_color', [220, 220, 220])
            task_label = QLabel(f"<b>{task_names[task]}</b>")
            task_label.setStyleSheet(
                f"font-size: {task_header_font_size}pt; "
                f"padding: {task_header_padding}px; "
                f"color: rgb({task_header_text_color[0]}, {task_header_text_color[1]}, {task_header_text_color[2]});"
            )
            scroll_layout.addWidget(task_label)
            
            # Group issues by severity
            errors = [issue for issue in result.issues if issue.severity == ValidationSeverity.ERROR]
            warnings = [issue for issue in result.issues if issue.severity == ValidationSeverity.WARNING]
            infos = [issue for issue in result.issues if issue.severity == ValidationSeverity.INFO]
            
            # Show errors
            for issue in errors:
                issue_widget = self._create_issue_widget(issue, "error")
                scroll_layout.addWidget(issue_widget)
            
            # Show warnings
            for issue in warnings:
                issue_widget = self._create_issue_widget(issue, "warning")
                scroll_layout.addWidget(issue_widget)
            
            # Show info
            for issue in infos:
                issue_widget = self._create_issue_widget(issue, "info")
                scroll_layout.addWidget(issue_widget)
            
            # Add spacing after task
            scroll_layout.addSpacing(10)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons (use same styling as main dialog)
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        # Get colors for button styling
        groups_config = dialog_config.get('groups', {})
        bg_color = groups_config.get('background_color', [40, 40, 45])
        border_color = groups_config.get('border_color', [60, 60, 65])
        labels_config = dialog_config.get('labels', {})
        text_color = labels_config.get('text_color', [200, 200, 200])
        font_size = scale_font_size(labels_config.get('font_size', 11))
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
        )
        
        button_layout = QHBoxLayout()
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet(button_style)
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)
        
        save_button = QPushButton("Save Anyway")
        save_button.setStyleSheet(button_style)
        save_button.clicked.connect(dialog.accept)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
        
        # Show dialog and return result
        return dialog.exec() == QDialog.DialogCode.Accepted
    
    def _create_issue_widget(self, issue, severity: str) -> QWidget:
        """Create a widget to display a validation issue.
        
        Args:
            issue: ValidationIssue object.
            severity: Severity level ("error", "warning", "info").
            
        Returns:
            QWidget displaying the issue.
        """
        # Get validation dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        validation_config = dialog_config.get('validation_dialog', {})
        issue_widget_config = validation_config.get('issue_widget', {})
        severity_labels_config = validation_config.get('severity_labels', {})
        issue_message_config = validation_config.get('issue_message', {})
        
        widget = QWidget()
        layout = QHBoxLayout(widget)
        issue_margins = issue_widget_config.get('margins', [10, 5, 10, 5])
        issue_spacing = issue_widget_config.get('spacing', 10)
        layout.setContentsMargins(issue_margins[0], issue_margins[1], issue_margins[2], issue_margins[3])
        layout.setSpacing(issue_spacing)
        
        # Severity icon/color
        severity_colors_config = severity_labels_config.get('colors', {})
        severity_colors = {
            "error": severity_colors_config.get('error', [255, 100, 100]),
            "warning": severity_colors_config.get('warning', [255, 200, 100]),
            "info": severity_colors_config.get('info', [150, 200, 255])
        }
        severity_labels_text = {
            "error": "ERROR",
            "warning": "WARNING",
            "info": "INFO"
        }
        
        severity_width = severity_labels_config.get('width', 80)
        severity_font_size = scale_font_size(severity_labels_config.get('font_size', 10))
        severity_padding = severity_labels_config.get('padding', [2, 8])
        severity_border_radius = severity_labels_config.get('border_radius', 3)
        
        severity_label = QLabel(severity_labels_text[severity])
        severity_color = severity_colors[severity]
        severity_label.setStyleSheet(
            f"background-color: rgb({severity_color[0]}, {severity_color[1]}, {severity_color[2]}); "
            f"color: rgb(0, 0, 0); "
            f"padding: {severity_padding[0]}px {severity_padding[1]}px; "
            f"border-radius: {severity_border_radius}px; "
            f"font-weight: bold; "
            f"font-size: {severity_font_size}pt;"
        )
        severity_label.setFixedWidth(severity_width)
        severity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(severity_label)
        
        # Issue message
        message_font_size = scale_font_size(issue_message_config.get('font_size', 11))
        message_padding = issue_message_config.get('padding', 2)
        message_text_color = issue_message_config.get('text_color', [200, 200, 200])
        message_label = QLabel(issue.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(
            f"font-size: {message_font_size}pt; "
            f"padding: {message_padding}px; "
            f"color: rgb({message_text_color[0]}, {message_text_color[1]}, {message_text_color[2]});"
        )
        layout.addWidget(message_label, stretch=1)
        
        return widget
    
    def _get_task_parameters(self, task: str) -> Dict[str, Any]:
        """Get parameter values for a specific task.
        
        Args:
            task: Task identifier.
            
        Returns:
            Dictionary with parameter values.
        """
        params = {}
        
        # Get common parameters
        if "threads" in self.task_widgets[task]:
            text = self.task_widgets[task]["threads"].text().strip()
            if text:
                try:
                    # Handle decimal values by rounding to nearest integer
                    params["threads"] = int(round(float(text)))
                except (ValueError, OverflowError):
                    params["threads"] = 1  # Default fallback
            else:
                params["threads"] = 1
        if "depth" in self.task_widgets[task]:
            text = self.task_widgets[task]["depth"].text().strip()
            if text:
                try:
                    # Handle decimal values by rounding to nearest integer
                    params["depth"] = int(round(float(text)))
                except (ValueError, OverflowError):
                    params["depth"] = 0  # Default fallback (0 = unlimited)
            else:
                params["depth"] = 0
        if "movetime" in self.task_widgets[task]:
            text = self.task_widgets[task]["movetime"].text().strip()
            if text:
                try:
                    # Handle decimal values by rounding to nearest millisecond
                    params["movetime"] = int(round(float(text)))
                except (ValueError, OverflowError):
                    params["movetime"] = 0  # Default fallback
            else:
                params["movetime"] = 0
        
        # Get engine-specific parameters
        for key, widget in self.task_widgets[task].items():
            if key.startswith("engine_option_"):
                option_name = key.replace("engine_option_", "")
                
                if isinstance(widget, QLineEdit):
                    # Check if this was originally a spin type (integer)
                    # We'll need to check the option type, but for now, try to parse as int
                    text = widget.text().strip()
                    if text:
                        try:
                            params[option_name] = int(text)
                        except ValueError:
                            params[option_name] = text
                    else:
                        params[option_name] = ""
                elif isinstance(widget, QCheckBox):
                    params[option_name] = widget.isChecked()
                elif isinstance(widget, QComboBox):
                    params[option_name] = widget.currentText()
        
        return params
    
    def _apply_styling(self) -> None:
        """Apply styling to UI elements based on configuration."""
        ui_config = self.config.get('ui', {})
        dialog_config = ui_config.get('dialogs', {}).get('engine_configuration', {})
        
        # Header styling
        header_config = dialog_config.get('header', {})
        header_bg = header_config.get('background_color', [245, 245, 245])
        header_text = header_config.get('text_color', [51, 51, 51])
        header_border = header_config.get('border_color', [204, 204, 204])
        header_border_width = header_config.get('border_width', 1)
        header_border_radius = header_config.get('border_radius', 5)
        header_padding = header_config.get('padding', [10, 10, 10, 10])
        header_font_family = header_config.get('font_family', 'Helvetica Neue')
        header_font_size = scale_font_size(header_config.get('font_size', 11))
        header_font_style = header_config.get('font_style', 'normal')
        
        header_style = (
            f"padding: {header_padding[0]}px {header_padding[1]}px {header_padding[2]}px {header_padding[3]}px; "
            f"background-color: rgb({header_bg[0]}, {header_bg[1]}, {header_bg[2]}); "
            f"color: rgb({header_text[0]}, {header_text[1]}, {header_text[2]}); "
            f"border: {header_border_width}px solid rgb({header_border[0]}, {header_border[1]}, {header_border[2]}); "
            f"border-radius: {header_border_radius}px; "
            f"font-family: {header_font_family}; "
            f"font-size: {header_font_size}pt; "
            f"font-style: {header_font_style};"
        )
        self.info_label.setStyleSheet(header_style)
        
        # Tab widget styling
        tabs_config = dialog_config.get('tabs', {})
        tab_font_family = tabs_config.get('font_family', 'Helvetica Neue')
        tab_font_size = scale_font_size(tabs_config.get('font_size', 10))
        tab_height = tabs_config.get('tab_height', 24)
        pane_bg = tabs_config.get('pane_background', [255, 255, 255])
        colors_config = tabs_config.get('colors', {})
        
        normal = colors_config.get('normal', {})
        norm_bg = normal.get('background', [245, 245, 245])
        norm_text = normal.get('text', [51, 51, 51])
        norm_border = normal.get('border', [204, 204, 204])
        
        hover = colors_config.get('hover', {})
        hover_bg = hover.get('background', [235, 235, 235])
        hover_text = hover.get('text', [51, 51, 51])
        hover_border = hover.get('border', [180, 180, 180])
        
        active = colors_config.get('active', {})
        active_bg = active.get('background', [70, 90, 130])
        active_text = active.get('text', [255, 255, 255])
        active_border = active.get('border', [100, 120, 160])
        
        tab_stylesheet = f"""
            QTabWidget {{
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
            }}
            QTabWidget::pane {{
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
            }}
            QTabBar {{
                alignment: left;
            }}
            QTabBar::tab {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                padding: 4px 12px;
                margin-right: 2px;
                font-family: {tab_font_family};
                font-size: {tab_font_size}pt;
                min-height: {tab_height}px;
                min-width: 80px;
            }}
            QTabBar::tab:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
                border: 1px solid rgb({hover_border[0]}, {hover_border[1]}, {hover_border[2]});
            }}
            QTabBar::tab:selected {{
                background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                color: rgb({active_text[0]}, {active_text[1]}, {active_text[2]});
                border: 1px solid rgb({active_border[0]}, {active_border[1]}, {active_border[2]});
            }}
        """
        self.tab_widget.setStyleSheet(tab_stylesheet)
    
    def _configure_tab_bar(self) -> None:
        """Configure QTabBar for macOS compatibility (left-aligned, content-sized tabs)."""
        from PyQt6.QtGui import QPalette, QColor
        
        tab_bar = self.tab_widget.tabBar()
        tab_bar.setExpanding(False)  # Allow tabs to size to content instead of filling space
        tab_bar.setElideMode(Qt.TextElideMode.ElideNone)  # Prevent text truncation
        tab_bar.setUsesScrollButtons(True)  # Enable scroll buttons when tabs don't fit
        tab_bar.setDrawBase(False)  # Don't draw base line
        
        # Get pane background color from config
        ui_config = self.config.get('ui', {})
        dialog_config = ui_config.get('dialogs', {}).get('engine_configuration', {})
        tabs_config = dialog_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [255, 255, 255])
        
        # Set background color directly on tab widgets (QWidget) to ensure dark background
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            # Use setAutoFillBackground and palette to ensure background is applied
            tab.setAutoFillBackground(True)
            palette = tab.palette()
            palette.setColor(tab.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
            palette.setColor(QPalette.ColorRole.Window, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
            palette.setColor(QPalette.ColorRole.Base, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
            tab.setPalette(palette)
            
            # Also set background on the tab's layout if it exists
            # Note: Don't override margins here - they're set in _create_task_tab for proper padding
            if tab.layout():
                pass  # Margins are already set in _create_task_tab
        
        # Also ensure the tab widget's pane has the correct background
        self.tab_widget.setAutoFillBackground(True)
        tab_widget_palette = self.tab_widget.palette()
        tab_widget_palette.setColor(self.tab_widget.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_widget_palette.setColor(QPalette.ColorRole.Window, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_widget_palette.setColor(QPalette.ColorRole.Base, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        self.tab_widget.setPalette(tab_widget_palette)
        
        # Group box styling
        groups_config = dialog_config.get('groups', {})
        group_bg = groups_config.get('background_color', [40, 40, 45])
        group_border = groups_config.get('border_color', [60, 60, 65])
        group_border_width = groups_config.get('border_width', 1)
        group_border_radius = groups_config.get('border_radius', 5)
        group_title_font_family = groups_config.get('title_font_family', 'Helvetica Neue')
        group_title_font_size = scale_font_size(groups_config.get('title_font_size', 11))
        group_title_font_weight = groups_config.get('title_font_weight', 'bold')
        group_title_color = groups_config.get('title_color', [220, 220, 220])
        group_spacing = groups_config.get('spacing', 10)
        group_margin_top = groups_config.get('margin_top', 8)
        group_padding_top = groups_config.get('padding_top', 12)
        
        group_stylesheet = f"""
            QGroupBox {{
                background-color: rgb({group_bg[0]}, {group_bg[1]}, {group_bg[2]});
                border: {group_border_width}px solid rgb({group_border[0]}, {group_border[1]}, {group_border[2]});
                border-radius: {group_border_radius}px;
                margin-top: {group_margin_top}px;
                padding-top: {group_padding_top}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
                font-family: {group_title_font_family};
                font-size: {group_title_font_size}pt;
                font-weight: {group_title_font_weight};
                color: rgb({group_title_color[0]}, {group_title_color[1]}, {group_title_color[2]});
            }}
        """
        
        # Apply group box styling to all group boxes
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            for child in tab.findChildren(QGroupBox):
                child.setStyleSheet(group_stylesheet)
        
        # Labels styling
        labels_config = dialog_config.get('labels', {})
        label_font_family = labels_config.get('font_family', 'Helvetica Neue')
        label_font_size = scale_font_size(labels_config.get('font_size', 10))
        form_label_font_size = scale_font_size(labels_config.get('form_label_font_size', labels_config.get('font_size', 10)))
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        label_disabled_color = labels_config.get('disabled_color', [128, 128, 128])
        label_empty_color = labels_config.get('empty_label_color', [128, 128, 128])
        label_empty_font_style = labels_config.get('empty_label_font_style', 'italic')
        label_empty_padding = labels_config.get('empty_label_padding', [20, 20, 20, 20])
        
        # Apply label styling - need to apply to all labels including form labels
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            for label in tab.findChildren(QLabel):
                # Skip if it's a no_options_label (will be styled separately)
                if hasattr(self, '_no_options_labels') and label in self._no_options_labels:
                    continue
                
                # Check if this is a form label (in a QFormLayout)
                is_form_label = label.parent() and isinstance(label.parent().layout(), QFormLayout)
                # Use form_label_font_size for form labels to match input widget font size
                font_size = form_label_font_size if is_form_label else label_font_size
                
                # Apply light text color for labels on dark backgrounds
                label.setStyleSheet(
                    f"font-family: {label_font_family}; "
                    f"font-size: {font_size}pt; "
                    f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
                )
        
        # Style empty options labels if they exist
        if hasattr(self, '_no_options_labels'):
            empty_label_style = (
                f"color: rgb({label_empty_color[0]}, {label_empty_color[1]}, {label_empty_color[2]}); "
                f"padding: {label_empty_padding[0]}px {label_empty_padding[1]}px {label_empty_padding[2]}px {label_empty_padding[3]}px; "
                f"font-style: {label_empty_font_style};"
            )
            for no_options_label in self._no_options_labels:
                no_options_label.setStyleSheet(empty_label_style)
        
        # Form layout spacing
        form_layout_config = dialog_config.get('form_layout', {})
        form_spacing = form_layout_config.get('spacing', 10)
        label_min_width = form_layout_config.get('label_minimum_width', 100)
        
        # Apply form layout spacing
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            for form_layout in tab.findChildren(QFormLayout):
                form_layout.setSpacing(form_spacing)
            # Set label minimum width
            for label in tab.findChildren(QLabel):
                if label.parent() and isinstance(label.parent().layout(), QFormLayout):
                    label.setMinimumWidth(label_min_width)
        
        # Input widgets styling (QLineEdit, QComboBox, QCheckBox)
        input_config = dialog_config.get('input_widgets', {})
        input_bg = input_config.get('background_color', [45, 45, 50])
        input_text = input_config.get('text_color', [200, 200, 200])
        input_border = input_config.get('border_color', [60, 60, 65])
        input_border_width = input_config.get('border_width', 1)
        input_border_radius = input_config.get('border_radius', 3)
        input_padding = input_config.get('padding', [2, 6, 2, 6])
        input_font_family = input_config.get('font_family', 'Helvetica Neue')
        input_font_size = scale_font_size(input_config.get('font_size', 9))
        
        # Get checkmark icon path
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        checkmark_url = str(checkmark_path).replace("\\", "/") if checkmark_path.exists() else ""
        
        input_stylesheet = f"""
            QLineEdit {{
                background-color: rgb({input_bg[0]}, {input_bg[1]}, {input_bg[2]});
                color: rgb({input_text[0]}, {input_text[1]}, {input_text[2]});
                border: {input_border_width}px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});
                border-radius: {input_border_radius}px;
                padding: {input_padding[0]}px {input_padding[1]}px {input_padding[2]}px {input_padding[3]}px;
                font-family: {input_font_family};
                font-size: {input_font_size}pt;
            }}
            QLineEdit:hover {{
                border: {input_border_width}px solid rgb({min(255, input_border[0] + 20)}, {min(255, input_border[1] + 20)}, {min(255, input_border[2] + 20)});
            }}
            QLineEdit:focus {{
                border: {input_border_width}px solid rgb(70, 90, 130);
            }}
            QComboBox {{
                background-color: rgb({input_bg[0]}, {input_bg[1]}, {input_bg[2]});
                color: rgb({input_text[0]}, {input_text[1]}, {input_text[2]});
                border: {input_border_width}px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});
                border-radius: {input_border_radius}px;
                padding: {input_padding[0]}px {input_padding[1]}px {input_padding[2]}px {input_padding[3]}px;
                font-family: {input_font_family};
                font-size: {input_font_size}pt;
            }}
            QComboBox:hover {{
                border: {input_border_width}px solid rgb({min(255, input_border[0] + 20)}, {min(255, input_border[1] + 20)}, {min(255, input_border[2] + 20)});
            }}
            QComboBox:focus {{
                border: {input_border_width}px solid rgb(70, 90, 130);
            }}
            QComboBox::drop-down {{
                border: none;
                background-color: transparent;
                width: 0px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QComboBox QAbstractItemView {{
                background-color: rgb({input_bg[0]}, {input_bg[1]}, {input_bg[2]});
                color: rgb({input_text[0]}, {input_text[1]}, {input_text[2]});
                selection-background-color: rgb(70, 90, 130);
                selection-color: rgb(240, 240, 240);
                border: {input_border_width}px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});
            }}
            QCheckBox {{
                color: rgb({input_text[0]}, {input_text[1]}, {input_text[2]});
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: {input_border_width}px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});
                border-radius: 3px;
                background-color: rgb({input_bg[0]}, {input_bg[1]}, {input_bg[2]});
            }}
            QCheckBox::indicator:hover {{
                border: {input_border_width}px solid rgb({min(255, input_border[0] + 20)}, {min(255, input_border[1] + 20)}, {min(255, input_border[2] + 20)});
            }}
            QCheckBox::indicator:checked {{
                background-color: rgb(70, 90, 130);
                border: {input_border_width}px solid rgb(100, 120, 160);
                image: url({checkmark_url});
            }}
        """
        
        # Apply input widget styling to individual widgets only (not to tab widget itself)
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            
            # Apply to individual widgets to ensure they get styled
            for lineedit in tab.findChildren(QLineEdit):
                lineedit.setStyleSheet(input_stylesheet)
            for combobox in tab.findChildren(QComboBox):
                combobox.setStyleSheet(input_stylesheet)
            for checkbox in tab.findChildren(QCheckBox):
                checkbox.setStyleSheet(input_stylesheet)
        
        # Buttons styling (match Classification Settings Dialog template)
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        # Get background color for button offset calculation
        groups_config = dialog_config.get('groups', {})
        bg_color = groups_config.get('background_color', [40, 40, 45])
        border_color = groups_config.get('border_color', [60, 60, 65])
        text_color = labels_config.get('text_color', [200, 200, 200])
        font_size = scale_font_size(labels_config.get('font_size', 11))
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
        )
        
        # Apply button styling to all buttons
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)
        
        # Set dialog background color to match dark theme (apply last to ensure it's not overridden)
        tabs_config = dialog_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        from PyQt6.QtGui import QPalette, QColor
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Also set stylesheet to ensure background color covers the entire window including frame
        # Apply this last so it doesn't get overridden by other stylesheets
        dialog_stylesheet = f"""
            QDialog {{
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
            }}
        """
        # Append to existing stylesheet if any, otherwise set it
        current_stylesheet = self.styleSheet()
        if current_stylesheet:
            self.setStyleSheet(current_stylesheet + "\n" + dialog_stylesheet)
        else:
            self.setStyleSheet(dialog_stylesheet)

